import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = path.join(root, "node_modules", "onnxruntime-web", "dist");
const dst = path.join(root, "web", "public", "wasm");

const files = [
  "ort-wasm-simd-threaded.jsep.mjs",
  "ort-wasm-simd-threaded.jsep.wasm",
  "ort-wasm-simd-threaded.mjs",
  "ort-wasm-simd-threaded.wasm",
];

fs.mkdirSync(dst, { recursive: true });
for (const name of files) {
  const from = path.join(src, name);
  if (!fs.existsSync(from)) {
    console.error(`[copy-wasm] missing ${from}`);
    process.exit(1);
  }
  fs.copyFileSync(from, path.join(dst, name));
}
console.log(`[copy-wasm] ${files.length} files -> web/public/wasm`);
