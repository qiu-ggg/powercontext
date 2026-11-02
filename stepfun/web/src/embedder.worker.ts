import { env, pipeline } from "@huggingface/transformers";

/**
 * Runs entirely inside the browser. Model files are served from /models,
 * ONNX Runtime WASM binaries from /wasm; no remote inference endpoint exists.
 */
const ctx = self as unknown as {
  postMessage(message: unknown, transfer?: Transferable[]): void;
  onmessage: ((event: MessageEvent) => void) | null;
  crossOriginIsolated: boolean;
  hardwareConcurrency: number;
};

const LOCAL_MODEL_PATH = "/models/";
const WASM_PATH = "/wasm/";

env.allowLocalModels = true;
env.allowRemoteModels = false;
env.useBrowserCache = false;
env.localModelPath = LOCAL_MODEL_PATH;
(env.backends.onnx as any).wasm.wasmPaths = WASM_PATH;
(env.backends.onnx as any).wasm.numThreads = ctx.crossOriginIsolated
  ? Math.min(4, Math.max(1, ctx.hardwareConcurrency || 2))
  : 1;

type InitMessage = {
  type: "init";
  device: "webgpu" | "wasm";
  dtype: "fp32" | "fp16" | "q8" | "int8";
  modelId: string;
};

type EmbedMessage = {
  type: "embed";
  id: number;
  texts: string[];
  batchSize: number;
};

let extractor: any = null;
let activeDevice: "webgpu" | "wasm" = "wasm";
let activeDtype = "int8";
let modelDim = 0;

function post(message: unknown, transfer?: Transferable[]) {
  ctx.postMessage(message, transfer);
}

async function loadModel(device: "webgpu" | "wasm", dtype: string, modelId: string) {
  const files = new Map<string, { loaded: number; total: number }>();
  const started = performance.now();
  const instance = await pipeline("feature-extraction", modelId, {
    device,
    dtype: dtype as any,
    progress_callback: (event: any) => {
      if (event?.status === "progress" && event.file) {
        files.set(event.file, { loaded: Number(event.loaded ?? 0), total: Number(event.total ?? 0) });
        let loaded = 0;
        let total = 0;
        for (const entry of files.values()) {
          loaded += entry.loaded;
          total += entry.total;
        }
        post({
          type: "load-progress",
          file: event.file,
          fileProgress: Number(event.progress ?? 0),
          loaded,
          total,
          ratio: total > 0 ? loaded / total : 0,
        });
      } else if (event?.status === "ready" || event?.status === "done") {
        post({ type: "load-progress", file: event.file ?? "", ratio: 1, loaded: 1, total: 1 });
      }
    },
  });
  const loadMs = performance.now() - started;
  return { instance, loadMs };
}

async function handleInit(message: InitMessage) {
  try {
    post({ type: "status", stage: "loading", device: message.device, dtype: message.dtype });
    let device = message.device;
    let dtype = message.dtype;
    let fallbackReason: string | null = null;
    let loaded;
    try {
      loaded = await loadModel(device, dtype, message.modelId);
    } catch (error) {
      if (device !== "webgpu") throw error;
      fallbackReason = `WebGPU 初始化失败（${(error as Error).message}），已自动降级到 WASM INT8`;
      post({ type: "status", stage: "fallback", message: fallbackReason });
      device = "wasm";
      dtype = "int8";
      loaded = await loadModel(device, dtype, message.modelId);
    }

    extractor = loaded.instance;
    activeDevice = device;
    activeDtype = dtype;

    const coldStarted = performance.now();
    const warm = await extractor(["预热查询"], { pooling: "cls", normalize: true });
    const coldMs = performance.now() - coldStarted;
    modelDim = Number(warm.dims[warm.dims.length - 1]);
    warm.dispose?.();

    post({
      type: "ready",
      device,
      dtype,
      dim: modelDim,
      loadMs: loaded.loadMs,
      coldMs,
      fallbackReason,
      threads: (env.backends.onnx as any).wasm.numThreads,
      crossOriginIsolated: ctx.crossOriginIsolated,
    });
  } catch (error) {
    post({ type: "error", message: (error as Error).message || String(error) });
  }
}

async function handleEmbed(message: EmbedMessage) {
  const { id, texts, batchSize } = message;
  const size = Math.max(1, Math.min(256, Math.floor(batchSize) || 32));
  const startedAll = performance.now();
  const rows: Float32Array[] = [];
  const batchMs: number[] = [];
  let dim = modelDim;
  try {
    for (let offset = 0; offset < texts.length; offset += size) {
      const batch = texts.slice(offset, offset + size);
      const started = performance.now();
      const output = await extractor(batch, { pooling: "cls", normalize: true });
      const ms = performance.now() - started;
      dim = Number(output.dims[output.dims.length - 1]);
      const data = output.data as Float32Array;
      for (let row = 0; row < batch.length; row += 1) {
        rows.push(data.slice(row * dim, (row + 1) * dim));
      }
      output.dispose?.();
      batchMs.push(ms);
      post({
        type: "embed-progress",
        id,
        done: Math.min(texts.length, offset + batch.length),
        total: texts.length,
        batchMs: ms,
        batchSize: batch.length,
      });
    }
    const flat = new Float32Array(rows.length * dim);
    rows.forEach((row, index) => flat.set(row, index * dim));
    post(
      {
        type: "embed-result",
        id,
        count: rows.length,
        dim,
        vectors: flat.buffer,
        totalMs: performance.now() - startedAll,
        batchMs,
      },
      [flat.buffer],
    );
  } catch (error) {
    post({ type: "embed-error", id, message: (error as Error).message || String(error) });
  }
}

ctx.onmessage = (event: MessageEvent) => {
  const message = event.data;
  if (message?.type === "init") void handleInit(message as InitMessage);
  else if (message?.type === "embed") void handleEmbed(message as EmbedMessage);
};
