/**
 * Verifies the automatic WebGPU -> WASM fallback in a real browser with WebGPU disabled.
 * Prerequisite: a browser started with --remote-debugging-port=9333 and WebGPU disabled,
 * plus the app served at http://127.0.0.1:8787/.
 *
 * Usage: node scripts/verify-fallback.mjs [catalogUrl] [appUrl]
 */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const catalog = process.argv[2] ?? "http://127.0.0.1:9333";
const appUrl = process.argv[3] ?? "http://127.0.0.1:8787/";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function getTarget() {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      const list = await (await fetch(`${catalog}/json/list`)).json();
      const page = list.find((item) => item.type === "page");
      if (page?.webSocketDebuggerUrl) return page;
    } catch {
      /* browser still starting */
    }
    await sleep(500);
  }
  throw new Error("无法连接远程调试端口");
}

function connect(url) {
  const socket = new WebSocket(url);
  let seq = 0;
  const pending = new Map();
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
    }
  });
  const ready = new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve);
    socket.addEventListener("error", reject);
  });
  const send = async (method, params = {}) => {
    await ready;
    const id = ++seq;
    socket.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
  };
  return { socket, send, ready };
}

async function evaluate(send, expression) {
  const result = await send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}

async function waitFor(send, expression, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await evaluate(send, expression);
    if (value) return value;
    await sleep(500);
  }
  throw new Error(`等待超时：${label}`);
}

async function main() {
  const target = await getTarget();
  const { socket, send } = connect(target.webSocketDebuggerUrl);
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Page.navigate", { url: appUrl });
  await sleep(2500);
  await evaluate(send, "localStorage.removeItem('eseek.pref')");
  await send("Page.reload");
  await sleep(2500);

  const gpuProbe = await evaluate(
    send,
    "navigator.gpu ? navigator.gpu.requestAdapter().then((a) => (a ? 'adapter' : 'null')) : 'undefined'",
  );
  if (gpuProbe === "adapter") {
    throw new Error("本应禁用 WebGPU，但 requestAdapter() 返回了适配器");
  }

  await waitFor(
    send,
    `[...document.querySelectorAll('button')].some((b) => b.textContent.trim() === '加载嵌入模型')`,
    20000,
    "应用加载",
  );
  await evaluate(
    send,
    `[...document.querySelectorAll('button')].find((b) => b.textContent.trim() === '加载嵌入模型').click()`,
  );

  await waitFor(
    send,
    `document.body.innerText.includes('WASM INT8') && document.body.innerText.includes('精度')`,
    120000,
    "自动降级并加载 WASM 模型",
  );

  const state = await evaluate(
    send,
    `(() => {
      const text = document.body.innerText;
      const note = document.querySelector('.inline-note.warn')?.innerText ?? '';
      const grid = document.querySelector('.backend-grid')?.innerText ?? '';
      const gpu = [...document.querySelectorAll('.sidebar p.fine-print')].map((p) => p.innerText).find((t) => t.includes('WebGPU')) ?? '';
      return { badge: document.querySelector('.topbar-status .chip-accent, .topbar-status .chip-warn')?.innerText ?? '', note, grid, gpu };
    })()`,
  );
  if (!state.grid.includes("INT8")) throw new Error(`预期自动降级到 INT8，实际后端：${state.grid}`);
  if (!state.note) throw new Error("未显示自动降级说明");

  await evaluate(
    send,
    `[...document.querySelectorAll('.tabs button')].find((b) => b.textContent.includes('混合检索')).click()`,
  );
  await sleep(500);
  await evaluate(
    send,
    `(() => {
      const input = document.querySelector('.search-box input');
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(input, 'RRF 如何融合向量和全文结果');
      input.dispatchEvent(new Event('input', { bubbles: true }));
      [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === '检索').click();
    })()`,
  );

  await waitFor(send, `document.body.innerText.includes('条 · hybrid')`, 60000, "WASM 下检索完成");
  const search = await evaluate(
    send,
    `(() => {
      const text = document.body.innerText;
      const latency = [...document.querySelectorAll('.latency-strip strong')].map((n) => n.innerText);
      const hits = document.querySelectorAll('.hits li').length;
      return { hits, latency, hasHybrid: text.includes('hybrid 模式'), badge: document.querySelector('.topbar-status .chip-warn')?.innerText ?? '' };
    })()`,
  );

  await sleep(1000);
  await evaluate(
    send,
    `[...document.querySelectorAll('button')].find((b) => b.textContent.trim() === '检索').click()`,
  );
  await sleep(2000);
  const warm = await evaluate(
    send,
    `({
      hits: document.querySelectorAll('.hits li').length,
      latency: [...document.querySelectorAll('.latency-strip strong')].map((n) => n.innerText),
    })`,
  );
  search.warm = warm;

  const screenshot = await send("Page.captureScreenshot", { format: "png" });
  await fs.mkdir(path.join(root, "results"), { recursive: true });
  await fs.writeFile(path.join(root, "results", "fallback-wasm.png"), Buffer.from(screenshot.data, "base64"));

  const report = {
    ts: new Date().toISOString(),
    navigatorGpu: gpuProbe,
    selectedBackend: state.badge,
    backendGrid: state.grid,
    fallbackNote: state.note,
    environmentNote: state.gpu,
    search,
  };
  await fs.writeFile(path.join(root, "results", "fallback-verification.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  socket.close();
}

main().catch((error) => {
  console.error("[verify-fallback]", error.message);
  process.exit(1);
});
