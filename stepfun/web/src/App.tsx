import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type CollectionInfo,
  type DocumentInfo,
  type HealthInfo,
  type ModelInfo,
} from "./api";
import { useEmbedder, type BackendPref } from "./useEmbedder";
import { detectWebgpu, type WebgpuInfo } from "./webgpu";
import { Chip, Progress, type Notify, type NotifyKind } from "./components";
import { formatBytes, formatMs } from "./metrics";
import ImportPanel from "./panels/ImportPanel";
import SearchPanel from "./panels/SearchPanel";
import EvalPanel from "./panels/EvalPanel";
import AboutPanel from "./panels/AboutPanel";

type Tab = "import" | "search" | "eval" | "about";

const BACKEND_OPTIONS: { key: BackendPref; label: string; hint: string }[] = [
  { key: "auto", label: "自动", hint: "优先 WebGPU FP16，否则 WASM INT8" },
  { key: "webgpu", label: "WebGPU", hint: "强制 WebGPU + FP16" },
  { key: "wasm-int8", label: "WASM INT8", hint: "强制 WASM + 量化 INT8" },
  { key: "wasm-fp32", label: "WASM FP32", hint: "质量基线（未量化）" },
];

function dtypeLabel(dtype: string | null): string {
  if (dtype === "fp16") return "FP16";
  if (dtype === "q8") return "INT8";
  if (dtype === "fp32") return "FP32";
  if (dtype === "int8") return "INT8";
  return dtype ?? "—";
}

export default function App() {
  const [tab, setTab] = useState<Tab>("import");
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [models, setModels] = useState<ModelInfo | null>(null);
  const [gpu, setGpu] = useState<WebgpuInfo | null>(null);
  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [currentId, setCurrentId] = useState(() => localStorage.getItem("eseek.kb") ?? "");
  const [stats, setStats] = useState<CollectionInfo | null>(null);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [bootError, setBootError] = useState("");
  const [booting, setBooting] = useState(true);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [toast, setToast] = useState<{ text: string; kind: NotifyKind } | null>(null);
  const [pref, setPref] = useState<BackendPref>(() => {
    const saved = localStorage.getItem("eseek.pref") as BackendPref | null;
    return saved && BACKEND_OPTIONS.some((option) => option.key === saved) ? saved : "auto";
  });

  const notify: Notify = useCallback((text, kind = "info") => {
    setToast({ text, kind });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), toast.kind === "error" ? 6000 : 3800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const embedder = useEmbedder(health?.model ?? "Xenova/bge-small-zh-v1.5");
  const kb = useMemo(
    () => stats ?? collections.find((item) => item.id === currentId) ?? null,
    [stats, collections, currentId],
  );

  const reloadCurrent = useCallback(async (id: string) => {
    const [statsResult, docsResult] = await Promise.all([api.stats(id), api.docs(id)]);
    setStats(statsResult.collection);
    setDocuments(docsResult.documents);
  }, []);

  useEffect(() => {
    if (!currentId) {
      setStats(null);
      setDocuments([]);
      return;
    }
    localStorage.setItem("eseek.kb", currentId);
    void reloadCurrent(currentId).catch((error) => notify((error as Error).message, "error"));
  }, [currentId, reloadCurrent, notify]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [healthResult, modelResult, collectionResult, gpuResult] = await Promise.all([
          api.health(),
          api.models(),
          api.collections(),
          detectWebgpu(),
        ]);
        if (!alive) return;
        setHealth(healthResult);
        setModels(modelResult);
        setGpu(gpuResult);
        let list = collectionResult.collections;
        if (list.length === 0) {
          const created = await api.createCollection("我的知识库");
          list = [created.collection];
        }
        if (!alive) return;
        setCollections(list);
        setCurrentId((prev) => (list.some((item) => item.id === prev) ? prev : list[0].id));
      } catch (error) {
        if (alive) setBootError((error as Error).message);
      } finally {
        if (alive) setBooting(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (embedder.state.status === "ready") localStorage.setItem("eseek.pref", pref);
  }, [embedder.state.status, pref]);

  const refreshAll = useCallback(async () => {
    const [collectionResult] = await Promise.all([
      api.collections(),
      currentId ? reloadCurrent(currentId) : Promise.resolve(),
    ]);
    setCollections(collectionResult.collections);
  }, [currentId, reloadCurrent]);

  const createKb = async () => {
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const created = await api.createCollection(name);
      setCollections((prev) => [created.collection, ...prev]);
      setCurrentId(created.collection.id);
      setNewName("");
      notify(`已创建知识库「${name}」`, "success");
    } catch (error) {
      notify((error as Error).message, "error");
    } finally {
      setCreating(false);
    }
  };

  const removeKb = async (collection: CollectionInfo) => {
    if (!window.confirm(`删除知识库「${collection.name}」及其全部向量与文档登记？`)) return;
    try {
      await api.deleteCollection(collection.id);
      const list = collections.filter((item) => item.id !== collection.id);
      setCollections(list);
      if (currentId === collection.id) setCurrentId(list[0]?.id ?? "");
      notify(`已删除「${collection.name}」`, "success");
    } catch (error) {
      notify((error as Error).message, "error");
    }
  };

  const backendReady = embedder.state.status === "ready";
  const currentBackend = backendReady
    ? `${embedder.state.device === "webgpu" ? "WebGPU" : "WASM"} ${dtypeLabel(embedder.state.dtype)}`
    : embedder.state.status === "loading"
      ? "模型加载中"
      : embedder.state.status === "error"
        ? "后端错误"
        : "后端未初始化";

  if (booting) {
    return (
      <div className="boot">
        <div className="boot-logo">EdgeSeek</div>
        <p>正在连接 seekdb 并读取知识库状态…</p>
      </div>
    );
  }

  if (bootError) {
    return (
      <div className="boot error">
        <div className="boot-logo">EdgeSeek</div>
        <h1>无法连接 seekdb</h1>
        <p className="mono">{bootError}</p>
        <pre className="code">
          # 启动本地 seekdb server（端口 2881）
          npm run setup:seekdb
          # 或
          docker compose up -d seekdb
        </pre>
        <p className="muted">启动后刷新页面。连接参数位于 server/src/config.mjs。</p>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">ES</div>
          <div>
            <h1>EdgeSeek</h1>
            <p>浏览器本地向量化 · seekdb 混合检索</p>
          </div>
        </div>
        <div className="topbar-status">
          <Chip tone="good" title={health?.db.version}>
            seekdb 1.4.0
          </Chip>
          <Chip tone="neutral">{health?.dim ?? 512} 维</Chip>
          <Chip
            tone={backendReady ? (embedder.state.device === "webgpu" ? "accent" : "warn") : "neutral"}
            title={embedder.state.fallbackReason ?? gpu?.reason ?? ""}
          >
            {currentBackend}
          </Chip>
          <Chip tone="neutral" title={models?.modelId}>
            bge-small-zh-v1.5
          </Chip>
        </div>
      </header>

      <div className="shell">
        <aside className="sidebar">
          <section className="side-block">
            <div className="side-title">
              <span>知识库</span>
              <span className="muted">{collections.length}</span>
            </div>
            <div className="kb-list">
              {collections.map((collection) => (
                <div
                  key={collection.id}
                  className={`kb-item ${collection.id === currentId ? "active" : ""}`}
                  onClick={() => setCurrentId(collection.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") setCurrentId(collection.id);
                  }}
                >
                  <div>
                    <div className="kb-name">{collection.name}</div>
                    <div className="kb-meta">
                      {collection.docCount} 篇 · {collection.chunkCount} 块
                    </div>
                  </div>
                  <button
                    className="icon-btn"
                    title="删除知识库"
                    onClick={(event) => {
                      event.stopPropagation();
                      void removeKb(collection);
                    }}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <div className="kb-create">
              <input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void createKb();
                }}
                placeholder="新知识库名称"
              />
              <button className="btn small" onClick={() => void createKb()} disabled={creating || !newName.trim()}>
                新建
              </button>
            </div>
          </section>

          <section className="side-block backend-block">
            <div className="side-title">
              <span>推理后端</span>
              {backendReady && (
                <Chip tone={embedder.state.device === "webgpu" ? "accent" : "warn"}>
                  {embedder.state.device === "webgpu" ? "WebGPU" : "WASM"}
                </Chip>
              )}
            </div>
            <div className="pref-grid">
              {BACKEND_OPTIONS.map((option) => (
                <button
                  key={option.key}
                  className={`pref ${pref === option.key ? "active" : ""}`}
                  title={option.hint}
                  onClick={() => setPref(option.key)}
                  disabled={embedder.state.status === "loading"}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <button
              className="btn primary wide small"
              onClick={() => void embedder.init(pref)}
              disabled={embedder.state.status === "loading"}
            >
              {embedder.state.status === "loading"
                ? "加载模型…"
                : backendReady
                  ? "重新加载模型"
                  : "加载嵌入模型"}
            </button>

            {embedder.state.status === "loading" && (
              <Progress
                value={embedder.state.progress?.ratio ?? 0}
                label={embedder.state.progress?.file ?? "准备模型文件"}
              />
            )}

            {embedder.state.status === "error" && (
              <div className="inline-note error">初始化失败：{embedder.state.error}</div>
            )}

            {backendReady && (
              <>
                <div className="backend-grid">
                  <div>
                    <span>精度</span>
                    <strong>{dtypeLabel(embedder.state.dtype)}</strong>
                  </div>
                  <div>
                    <span>加载</span>
                    <strong>{formatMs(embedder.state.loadMs)}</strong>
                  </div>
                  <div>
                    <span>冷启动推理</span>
                    <strong>{formatMs(embedder.state.coldMs)}</strong>
                  </div>
                  <div>
                    <span>{embedder.state.device === "webgpu" ? "执行设备" : "WASM 线程"}</span>
                    <strong>{embedder.state.device === "webgpu" ? "WebGPU" : (embedder.state.threads ?? 1)}</strong>
                  </div>
                </div>
                {embedder.state.fallbackReason && (
                  <div className="inline-note warn">{embedder.state.fallbackReason}</div>
                )}
                <p className="fine-print">
                  {embedder.state.crossOriginIsolated
                    ? "已启用跨源隔离（COOP/COEP），WASM 多线程可用。"
                    : "未启用跨源隔离，WASM 以单线程运行。"}
                </p>
              </>
            )}
            {!backendReady && embedder.state.status !== "loading" && (
              <p className="fine-print">{gpu?.reason ?? "正在探测 WebGPU…"}</p>
            )}
          </section>

          <section className="side-block">
            <div className="side-title">
              <span>模型体积</span>
              <span className="muted">实际文件</span>
            </div>
            <div className="size-list">
              {(["fp32", "fp16", "int8"] as const).map((key) => {
                const bytes = models?.files?.[key]?.bytes ?? null;
                const base = models?.files?.fp32?.bytes ?? null;
                const label = key === "fp32" ? "FP32 基线" : key === "fp16" ? "FP16" : "INT8";
                return (
                  <div key={key} className="size-row">
                    <span>{label}</span>
                    <span className="mono">{formatBytes(bytes)}</span>
                    <span className="muted tiny">
                      {key === "fp32" ? "1.00×" : base && bytes ? `${(base / bytes).toFixed(2)}×` : "—"}
                    </span>
                  </div>
                );
              })}
            </div>
            <p className="fine-print">compression = FP32 ÷ 量化后；tokenizer 约 {formatBytes(models?.tokenizerBytes)}。</p>
          </section>
        </aside>

        <main className="main">
          <div className="stat-strip kb-strip">
            <div>
              <span>当前知识库</span>
              <strong>{kb?.name ?? "—"}</strong>
            </div>
            <div>
              <span>文档 / 分块</span>
              <strong>
                {kb?.docCount ?? 0} / {kb?.chunkCount ?? 0}
              </strong>
            </div>
            <div>
              <span>最近写入</span>
              <strong>{kb?.lastIngestMs != null ? formatMs(kb.lastIngestMs) : "—"}</strong>
            </div>
            <div>
              <span>最近刷新</span>
              <strong>{kb?.lastRefreshMs != null ? formatMs(kb.lastRefreshMs) : "—"}</strong>
            </div>
            <div>
              <span>集合</span>
              <strong className="mono small-text">{kb?.collectionName ?? "—"}</strong>
            </div>
          </div>

          <nav className="tabs">
            {(
              [
                ["import", "导入与写入"],
                ["search", "混合检索"],
                ["eval", "评测与基准"],
                ["about", "技术说明"],
              ] as [Tab, string][]
            ).map(([key, label]) => (
              <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
                {label}
              </button>
            ))}
          </nav>

          {tab === "import" && (
            <ImportPanel kb={kb} documents={documents} embedder={embedder} notify={notify} onChanged={refreshAll} />
          )}
          {tab === "search" && <SearchPanel kb={kb} embedder={embedder} notify={notify} />}
          {tab === "eval" && <EvalPanel embedder={embedder} models={models} notify={notify} />}
          {tab === "about" && <AboutPanel models={models} health={health} />}
        </main>
      </div>

      {toast && <div className={`toast toast-${toast.kind}`}>{toast.text}</div>}
    </div>
  );
}
