import { useCallback, useEffect, useRef, useState } from "react";
import { detectWebgpu } from "./webgpu";

export type BackendPref = "auto" | "webgpu" | "wasm-int8" | "wasm-fp32";
export type InferDevice = "webgpu" | "wasm";
export type InferDtype = "fp32" | "fp16" | "q8" | "int8";

export interface EmbedProgress {
  done: number;
  total: number;
  batchMs: number;
  batchSize: number;
}

export interface EmbedResult {
  vectors: number[][];
  dim: number;
  totalMs: number;
  batchMs: number[];
}

export interface EmbedderState {
  status: "idle" | "loading" | "ready" | "error";
  device: InferDevice | null;
  dtype: InferDtype | null;
  dim: number | null;
  loadMs: number | null;
  coldMs: number | null;
  fallbackReason: string | null;
  progress: { file: string; ratio: number } | null;
  threads: number | null;
  crossOriginIsolated: boolean;
  error: string | null;
}

const INITIAL: EmbedderState = {
  status: "idle",
  device: null,
  dtype: null,
  dim: null,
  loadMs: null,
  coldMs: null,
  fallbackReason: null,
  progress: null,
  threads: null,
  crossOriginIsolated: false,
  error: null,
};

const LABELS: Record<BackendPref, { device: InferDevice; dtype: InferDtype }> = {
  auto: { device: "wasm", dtype: "int8" },
  webgpu: { device: "webgpu", dtype: "fp16" },
  "wasm-int8": { device: "wasm", dtype: "int8" },
  "wasm-fp32": { device: "wasm", dtype: "fp32" },
};

let embedSeq = 0;

export function useEmbedder(modelId: string) {
  const [state, setState] = useState<EmbedderState>(INITIAL);
  const workerRef = useRef<Worker | null>(null);
  const pendingRef = useRef(
    new Map<
      number,
      {
        resolve: (result: EmbedResult) => void;
        reject: (error: Error) => void;
        onProgress?: (progress: EmbedProgress) => void;
      }
    >(),
  );
  const prefRef = useRef<BackendPref>("auto");
  const noteRef = useRef<string | null>(null);

  const terminate = useCallback(() => {
    workerRef.current?.terminate();
    workerRef.current = null;
    pendingRef.current.forEach(({ reject }) => reject(new Error("推理 worker 已重启")));
    pendingRef.current.clear();
  }, []);

  useEffect(() => terminate, [terminate]);

  const init = useCallback(
    async (pref: BackendPref) => {
      terminate();
      prefRef.current = pref;
      noteRef.current = null;
      const target = LABELS[pref];
      let device = target.device;
      let dtype = target.dtype;
      if (pref === "auto") {
        const gpu = await detectWebgpu();
        if (gpu.available && gpu.fp16) {
          device = "webgpu";
          dtype = "fp16";
          noteRef.current = gpu.reason;
        } else {
          device = "wasm";
          dtype = "int8";
          noteRef.current = gpu.available
            ? `${gpu.reason}，自动使用 WASM INT8`
            : `${gpu.reason}，自动降级到 WASM INT8`;
        }
      }

      setState({ ...INITIAL, status: "loading", device, dtype });
      const worker = new Worker(new URL("./embedder.worker.ts", import.meta.url), { type: "module" });
      workerRef.current = worker;

      worker.onmessage = (event: MessageEvent) => {
        const message = event.data;
        if (message.type === "status") {
          if (message.stage === "fallback") {
            setState((prev) => ({ ...prev, fallbackReason: message.message }));
          }
          return;
        }
        if (message.type === "load-progress") {
          setState((prev) => ({
            ...prev,
            progress: { file: message.file || "初始化", ratio: Number(message.ratio ?? 0) },
          }));
          return;
        }
        if (message.type === "ready") {
          setState({
            status: "ready",
            device: message.device,
            dtype: message.dtype,
            dim: Number(message.dim),
            loadMs: Number(message.loadMs),
            coldMs: Number(message.coldMs),
            fallbackReason: message.fallbackReason ?? noteRef.current,
            progress: null,
            threads: Number(message.threads ?? 1),
            crossOriginIsolated: Boolean(message.crossOriginIsolated),
            error: null,
          });
          return;
        }
        if (message.type === "error") {
          setState((prev) => ({ ...prev, status: "error", error: message.message, progress: null }));
          return;
        }
        if (message.type === "embed-progress") {
          pendingRef.current.get(message.id)?.onProgress?.({
            done: message.done,
            total: message.total,
            batchMs: message.batchMs,
            batchSize: message.batchSize,
          });
          return;
        }
        if (message.type === "embed-result") {
          const pending = pendingRef.current.get(message.id);
          if (!pending) return;
          pendingRef.current.delete(message.id);
          const flat = new Float32Array(message.vectors);
          const dim = Number(message.dim);
          const count = Number(message.count);
          const vectors: number[][] = new Array(count);
          for (let index = 0; index < count; index += 1) {
            vectors[index] = Array.from(flat.subarray(index * dim, (index + 1) * dim));
          }
          pending.resolve({
            vectors,
            dim,
            totalMs: Number(message.totalMs),
            batchMs: message.batchMs ?? [],
          });
          return;
        }
        if (message.type === "embed-error") {
          const pending = pendingRef.current.get(message.id);
          if (!pending) return;
          pendingRef.current.delete(message.id);
          pending.reject(new Error(message.message));
        }
      };

      worker.onerror = (event) => {
        setState((prev) => ({ ...prev, status: "error", error: event.message || "worker 运行错误" }));
      };

      worker.postMessage({ type: "init", device, dtype, modelId });
    },
    [modelId, terminate],
  );

  const embed = useCallback(
    (texts: string[], batchSize = 32, onProgress?: (progress: EmbedProgress) => void) =>
      new Promise<EmbedResult>((resolve, reject) => {
        const worker = workerRef.current;
        if (!worker) {
          reject(new Error("推理后端尚未初始化"));
          return;
        }
        const id = ++embedSeq;
        pendingRef.current.set(id, { resolve, reject, onProgress });
        worker.postMessage({ type: "embed", id, texts, batchSize });
      }),
    [],
  );

  const embedOne = useCallback(
    async (text: string) => {
      const result = await embed([text], 1);
      return { vector: result.vectors[0], ms: result.totalMs };
    },
    [embed],
  );

  return { state, init, embed, embedOne };
}
