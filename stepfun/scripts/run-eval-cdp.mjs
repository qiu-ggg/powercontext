/**
 * Drives the built app through CDP and runs one evaluation for the selected backend.
 * Prerequisite: browser with --remote-debugging-port=9333, app served at http://127.0.0.1:8787/.
 *
 * Usage: node scripts/run-eval-cdp.mjs <pref>   e.g. wasm-int8 | wasm-fp32 | webgpu
 */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const pref = process.argv[2] ?? "wasm-int8";
const prefLabel = { "wasm-int8": "WASM INT8", "wasm-fp32": "WASM FP32", webgpu: "WebGPU", auto: "自动" }[pref];
const catalog = "http://127.0.0.1:9333";
const appUrl = "http://127.0.0.1:8787/";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const STORAGE_KEY = "eseek.evalRuns.v1";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function getTarget() {
  const list = await (await fetch(`${catalog}/json/list`)).json();
  const pages = list.filter((item) => item.type === "page" && item.webSocketDebuggerUrl);
  return pages.find((item) => (item.url ?? "").startsWith(appUrl)) ?? pages[0];
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
  return { socket, send };
}

async function evaluate(send, expression) {
  const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
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
  const text = await evaluate(send, "document.body.innerText.slice(0, 800)");
  throw new Error(`等待超时：${label}\n--- page ---\n${text}`);
}

const clickButton = (label) => `
  (() => {
    const button = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === ${JSON.stringify(label)});
    if (!button) return false;
    button.click();
    return true;
  })()
`;

async function main() {
  const target = await getTarget();
  if (!target) throw new Error("没有可用的页面 target");
  const { socket, send } = connect(target.webSocketDebuggerUrl);
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Page.navigate", { url: appUrl });
  await sleep(2500);

  const gpuProbe = await evaluate(
    send,
    "navigator.gpu ? navigator.gpu.requestAdapter().then((a) => (a ? 'adapter' : 'null')) : 'undefined'",
  );
  console.log(`[eval] navigator.gpu adapter: ${gpuProbe}`);

  await waitFor(send, `document.querySelector('.pref-grid') !== null`, 20000, "应用加载");
  const prefClicked = await evaluate(
    send,
    `(() => {
      const button = [...document.querySelectorAll('.pref-grid button')].find((b) => b.textContent.trim() === ${JSON.stringify(prefLabel)});
      if (!button) return false;
      button.click();
      return true;
    })()`,
  );
  if (!prefClicked) throw new Error(`找不到后端选项 ${prefLabel}`);
  await sleep(300);
  await evaluate(send, clickButton("加载嵌入模型"));

  await waitFor(
    send,
    `document.body.innerText.includes('冷启动推理') && document.querySelector('.backend-grid') !== null`,
    180000,
    "模型加载",
  );
  const backend = await evaluate(
    send,
    `(() => ({
      grid: document.querySelector('.backend-grid')?.innerText ?? '',
      note: document.querySelector('.inline-note.warn')?.innerText ?? '',
      isolated: document.body.innerText.includes('已启用跨源隔离'),
    }))()`,
  );
  console.log(`[eval] backend ready: ${JSON.stringify(backend)}`);
  if (pref === "wasm-int8" && !backend.grid.includes("INT8")) throw new Error("预期 WASM INT8，但后端精度不是 INT8");
  if (pref === "wasm-fp32" && !backend.grid.includes("FP32")) throw new Error("预期 WASM FP32，但后端精度不是 FP32");
  if (pref === "webgpu" && !backend.grid.includes("WebGPU")) throw new Error("预期 WebGPU，但执行设备不是 WebGPU");

  await evaluate(
    send,
    `[...document.querySelectorAll('.tabs button')].find((b) => b.textContent.includes('评测与基准')).click()`,
  );
  await waitFor(
    send,
    `(() => {
      const button = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === '运行当前后端评测');
      return Boolean(button) && !button.disabled;
    })()`,
    30000,
    "评测面板就绪",
  );

  const before = await evaluate(send, `JSON.parse(localStorage.getItem(${JSON.stringify(STORAGE_KEY)}) || '[]').length`);

  await evaluate(send, clickButton("运行当前后端评测"));
  console.log("[eval] evaluation started…");

  await waitFor(
    send,
    `JSON.parse(localStorage.getItem(${JSON.stringify(STORAGE_KEY)}) || '[]').length > ${before}`,
    240000,
    "评测完成",
  );

  const run = await evaluate(send, `JSON.parse(localStorage.getItem(${JSON.stringify(STORAGE_KEY)}) || '[]')[0]`);
  const summary = {
    ts: new Date().toISOString(),
    navigatorGpu: gpuProbe,
    backend,
    device: run.device,
    dtype: run.dtype,
    dim: run.dim,
    modelId: run.modelId,
    loadMs: run.loadMs,
    coldMs: run.coldMs,
    chunkCount: run.chunkCount,
    queryCount: run.queryCount,
    embedChunksMs: run.embedChunksMs,
    chunkThroughput: run.chunkThroughput,
    queryEmbedMs: run.queryEmbedMs,
    dbMs: run.dbMs,
    e2eMs: run.e2eMs,
    quality: run.quality,
  };
  await fs.mkdir(path.join(root, "results"), { recursive: true });
  const suffix = `${run.device}_${run.dtype}`;
  const screenshot = await send("Page.captureScreenshot", { format: "png" });
  await fs.writeFile(path.join(root, "results", `eval-${suffix}-browser.png`), Buffer.from(screenshot.data, "base64"));
  await fs.writeFile(
    path.join(root, "results", `eval-${suffix}-browser.json`),
    JSON.stringify({ summary, run }, null, 2),
  );
  console.log(JSON.stringify(summary, null, 2));

  if (process.argv[3] === "bench") {
    await evaluate(send, clickButton("运行批大小基准"));
    await waitFor(
      send,
      `document.querySelectorAll('.bench-row').length === 4 && [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === '运行批大小基准')`,
      240000,
      "批大小基准完成",
    );
    const bench = await evaluate(
      send,
      `[...document.querySelectorAll('.bench-row')].map((row) => ({
        batchSize: Number(row.querySelector('.bench-label').innerText.replace(/[^0-9]/g, '')),
        throughput: Number(row.querySelector('.bench-value').innerText.replace(/[^0-9.]/g, '')),
        ms: row.querySelector('.muted.mono').innerText,
      }))`,
    );
    const benchReport = { ts: new Date().toISOString(), device: run.device, dtype: run.dtype, textCount: 48, results: bench };
    await fs.writeFile(path.join(root, "results", `batch-${suffix}-browser.json`), JSON.stringify(benchReport, null, 2));
    console.log(JSON.stringify(benchReport, null, 2));
  }

  socket.close();
}

main().catch((error) => {
  console.error("[run-eval]", error.message);
  process.exit(1);
});
