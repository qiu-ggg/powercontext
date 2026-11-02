/**
 * Downloads the ONNX embedding model used by the Web Worker into
 * web/public/models/<modelId>/.
 *
 * Defaults to Xenova/bge-small-zh-v1.5. Set HF_ENDPOINT (e.g. https://hf-mirror.com)
 * when huggingface.co is not reachable, and NODE_USE_ENV_PROXY=1 with HTTPS_PROXY
 * if you need a proxy (Node >= 24).
 *
 * Usage: node scripts/fetch-model.mjs [--force] [--variant=fp32|fp16|int8|q8|all]
 */
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repo = process.env.EMBED_MODEL ?? "Xenova/bge-small-zh-v1.5";
const endpoint = (process.env.HF_ENDPOINT ?? "https://huggingface.co").replace(/\/+$/, "");
const targetDir = path.join(root, "web", "public", "models", repo);

const flag = (name) => process.argv.includes(name);
const variantArg = (process.argv.find((arg) => arg.startsWith("--variant=")) ?? "--variant=all").split("=")[1];
const force = flag("--force");

const variants = {
  fp32: ["onnx/model.onnx"],
  fp16: ["onnx/model_fp16.onnx"],
  int8: ["onnx/model_int8.onnx"],
  q8: ["onnx/model_quantized.onnx"],
};
const wanted = variantArg === "all" ? Object.keys(variants) : variantArg.split(",");
for (const key of wanted) {
  if (!variants[key]) {
    console.error(`[fetch-model] unknown variant "${key}" (use fp32|fp16|int8|q8|all)`);
    process.exit(1);
  }
}

const files = [
  { file: "config.json", bytes: 716 },
  { file: "tokenizer.json", bytes: 439125 },
  { file: "tokenizer_config.json", bytes: 367 },
  { file: "special_tokens_map.json", bytes: 125 },
  { file: "vocab.txt", bytes: 109540 },
  ...wanted.flatMap((key) => variants[key].map((file) => ({ file }))),
];

async function sizeOf(file) {
  try {
    return (await fsp.stat(path.join(targetDir, file))).size;
  } catch {
    return null;
  }
}

function human(bytes) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

async function download(file) {
  const url = `${endpoint}/${repo}/resolve/main/${file}`;
  const target = path.join(targetDir, file);
  const expected = files.find((entry) => entry.file === file)?.bytes ?? null;

  if (!force) {
    const existing = await sizeOf(file);
    if (existing != null && (expected == null || existing === expected)) {
      console.log(`[fetch-model] skip ${file} (${human(existing)})`);
      return;
    }
  }

  await fsp.mkdir(path.dirname(target), { recursive: true });
  const tmp = `${target}.part`;
  console.log(`[fetch-model] GET ${url}`);
  const response = await fetch(url, { redirect: "follow", signal: AbortSignal.timeout(30 * 60 * 1000) });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText} for ${url}`);

  const total = Number(response.headers.get("content-length") ?? 0);
  const stream = fs.createWriteStream(tmp);
  let received = 0;
  let lastPrint = 0;
  for await (const chunk of response.body) {
    received += chunk.length;
    if (!stream.write(chunk)) await new Promise((resolve) => stream.once("drain", resolve));
    if (total && Date.now() - lastPrint > 1000) {
      lastPrint = Date.now();
      const pct = ((received / total) * 100).toFixed(1);
      process.stdout.write(`\r[fetch-model] ${file} ${pct}% (${human(received)} / ${human(total)})   `);
    }
  }
  await new Promise((resolve, reject) => stream.end((error) => (error ? reject(error) : resolve())));
  if (total) process.stdout.write("\n");

  if (total && received !== total) throw new Error(`incomplete download for ${file}: ${received}/${total}`);
  if (expected != null && received !== expected) {
    console.warn(`[fetch-model] warning: ${file} is ${received} bytes, expected ${expected} from the upstream repo`);
  }
  await fsp.rename(tmp, target);
  console.log(`[fetch-model] saved ${path.relative(root, target)} (${human(received)})`);
}

for (const entry of files) await download(entry.file);
console.log(`[fetch-model] ready: ${path.relative(root, targetDir)} (variants: ${wanted.join(", ")})`);
