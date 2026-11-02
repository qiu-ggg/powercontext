/**
 * Starts a local seekdb 1.4 server on 127.0.0.1:2881.
 *
 * The seekdb server binary ships inside the pylibseekdb wheel. Put it at
 * backend/seekdb/seekdb(.exe) or point SEEKDB_BIN at it, e.g.:
 *   python -c "import pylibseekdb,os;print(os.path.join(os.path.dirname(pylibseekdb.__file__),'..','pylibseekdb.libs','seekdb.exe'))"
 *
 * Env: SEEKDB_BIN, SEEKDB_BASE_DIR (.seekdb_base), SEEKDB_PORT (2881).
 * Usage: node scripts/seekdb-server.mjs
 */
import { spawn } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const port = Number(process.env.SEEKDB_PORT ?? 2881);
const baseDir = path.resolve(root, process.env.SEEKDB_BASE_DIR ?? ".seekdb_base");
const exe = process.platform === "win32" ? "seekdb.exe" : "seekdb";

const candidates = [
  process.env.SEEKDB_BIN,
  path.join(root, "backend", "seekdb", exe),
  path.join(root, "backend", exe),
].filter(Boolean);

const binary = candidates.find((candidate) => fs.existsSync(candidate));

function isListening() {
  return new Promise((resolve) => {
    const socket = net.connect({ host: "127.0.0.1", port }, () => {
      socket.destroy();
      resolve(true);
    });
    socket.on("error", () => resolve(false));
    socket.setTimeout(1000, () => {
      socket.destroy();
      resolve(false);
    });
  });
}

if (await isListening()) {
  console.log(`[seekdb] 127.0.0.1:${port} 已在监听，无需重复启动`);
  process.exit(0);
}

if (!binary) {
  console.error("[seekdb] 未找到 seekdb 可执行文件。");
  console.error(`  已尝试：${candidates.join(", ")}`);
  console.error("  请设置 SEEKDB_BIN，或把二进制放到 backend/seekdb/seekdb(.exe)。");
  console.error("  pylibseekdb wheel 内的路径示例：pylibseekdb.libs/seekdb.exe");
  process.exit(1);
}

fs.mkdirSync(baseDir, { recursive: true });
console.log(`[seekdb] ${binary}`);
console.log(`[seekdb] base-dir=${baseDir} port=${port}`);

const child = spawn(binary, ["--nodaemon", "--base-dir", baseDir, "--port", String(port)], {
  cwd: baseDir,
  stdio: "inherit",
});

const stop = (signal) => {
  if (!child.killed) child.kill(signal);
};
process.on("SIGINT", () => stop("SIGINT"));
process.on("SIGTERM", () => stop("SIGTERM"));
child.on("exit", (code, signal) => {
  process.exit(code ?? (signal ? 1 : 0));
});
