import { useEffect, useMemo, useState } from "react";
import { api, type EvalFixture, type ModelInfo } from "../api";
import type { useEmbedder } from "../useEmbedder";
import { Card, Chip, Empty, Progress, Stat, type Notify } from "../components";
import { evaluateRanking, formatBytes, formatMs, formatPct, mean, median, uniqueDocIds } from "../metrics";

type Embedder = ReturnType<typeof useEmbedder>;

interface QueryResult {
  id: string;
  query: string;
  recall: number;
  ndcg: number;
  mrr: number;
  firstHitRank: number | null;
  topDocIds: string[];
  embedMs: number;
  dbMs: number;
  e2eMs: number;
}

interface EvalRun {
  id: string;
  ts: string;
  device: string;
  dtype: string;
  dim: number;
  modelId: string;
  loadMs: number;
  coldMs: number;
  chunkCount: number;
  queryCount: number;
  embedChunksMs: number;
  chunkThroughput: number;
  queryEmbedMs: number;
  dbMs: number;
  e2eMs: number;
  quality: { recall5: number; ndcg5: number; mrr: number };
  perQuery: QueryResult[];
}

const STORAGE_KEY = "eseek.evalRuns.v1";

function loadRuns(): EvalRun[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default function EvalPanel({
  embedder,
  models,
  notify,
}: {
  embedder: Embedder;
  models: ModelInfo | null;
  notify: Notify;
}) {
  const [fixture, setFixture] = useState<EvalFixture | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<{ label: string; done: number; total: number } | null>(null);
  const [runs, setRuns] = useState<EvalRun[]>(loadRuns);
  const [currentId, setCurrentId] = useState<string | null>(() => loadRuns()[0]?.id ?? null);
  const [benchResults, setBenchResults] = useState<{ batchSize: number; ms: number; throughput: number }[] | null>(null);
  const [benching, setBenching] = useState(false);
  const [showPerQuery, setShowPerQuery] = useState(false);

  useEffect(() => {
    api
      .evalFixture()
      .then(setFixture)
      .catch((error) => notify((error as Error).message, "error"));
  }, [notify]);

  const current = useMemo(() => runs.find((run) => run.id === currentId) ?? runs[0] ?? null, [runs, currentId]);
  const baseline = useMemo(() => runs.find((run) => run.dtype === "fp32"), [runs]);
  const ready = embedder.state.status === "ready";

  const sizeFor = (dtype: string) => {
    const bytes = models?.files?.[dtype]?.bytes ?? null;
    return bytes;
  };

  const persist = (next: EvalRun[]) => {
    setRuns(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  };

  const runEvaluation = async () => {
    if (!ready) {
      notify("请先在左侧初始化推理后端", "error");
      return;
    }
    if (!fixture) {
      notify("评测集尚未加载完成", "error");
      return;
    }
    const cfg = { device: embedder.state.device ?? "wasm", dtype: embedder.state.dtype ?? "int8" };
    setRunning(true);
    let collectionName: string | null = null;
    try {
      const texts = fixture.chunks.map((chunk) => chunk.text);
      setProgress({ label: "端侧向量化评测语料", done: 0, total: texts.length });
      const embedStarted = performance.now();
      const embedded = await embedder.embed(texts, 32, (event) =>
        setProgress({ label: "端侧向量化评测语料", done: event.done, total: event.total }),
      );
      const embedChunksMs = performance.now() - embedStarted;

      setProgress({ label: "写入 seekdb 评价集合并刷新索引", done: 0, total: 1 });
      const built = await api.evalBuild(
        cfg.dtype,
        fixture.chunks.map((chunk, index) => ({ ...chunk, vector: embedded.vectors[index] })),
      );
      collectionName = built.collectionName;
      setProgress({ label: "写入 seekdb 评价集合并刷新索引", done: 1, total: 1 });

      const perQuery: QueryResult[] = [];
      for (let index = 0; index < fixture.queries.length; index += 1) {
        const query = fixture.queries[index];
        const started = performance.now();
        const queryEmbedding = await embedder.embedOne(query.query);
        const response = await api.evalSearch(built.collectionName, queryEmbedding.vector, query.query, 10);
        const e2eMs = performance.now() - started;
        const ranked = uniqueDocIds(response.hits.map((hit) => hit.docId));
        const score = evaluateRanking(ranked, query.goldDocIds, 5);
        perQuery.push({
          id: query.id,
          query: query.query,
          recall: score.recall,
          ndcg: score.ndcg,
          mrr: score.mrr,
          firstHitRank: score.firstHitRank,
          topDocIds: ranked.slice(0, 5),
          embedMs: queryEmbedding.ms,
          dbMs: response.dbMs,
          e2eMs,
        });
        setProgress({ label: "逐条查询评测（seekdb 混合检索）", done: index + 1, total: fixture.queries.length });
      }

      const run: EvalRun = {
        id: `${Date.now().toString(36)}`,
        ts: new Date().toISOString(),
        device: cfg.device,
        dtype: cfg.dtype,
        dim: embedder.state.dim ?? 0,
        modelId: embedder.state ? "Xenova/bge-small-zh-v1.5" : "",
        loadMs: embedder.state.loadMs ?? 0,
        coldMs: embedder.state.coldMs ?? 0,
        chunkCount: fixture.chunks.length,
        queryCount: fixture.queries.length,
        embedChunksMs,
        chunkThroughput: fixture.chunks.length / (embedChunksMs / 1000),
        queryEmbedMs: median(perQuery.map((item) => item.embedMs)),
        dbMs: median(perQuery.map((item) => item.dbMs)),
        e2eMs: median(perQuery.map((item) => item.e2eMs)),
        quality: {
          recall5: mean(perQuery.map((item) => item.recall)),
          ndcg5: mean(perQuery.map((item) => item.ndcg)),
          mrr: mean(perQuery.map((item) => item.mrr)),
        },
        perQuery,
      };
      persist([run, ...runs].slice(0, 12));
      setCurrentId(run.id);
      setShowPerQuery(false);
      await api.saveResults(`eval_${cfg.device}_${cfg.dtype}_${run.id}`, run);
      notify(
        `评测完成：Recall@5 ${formatPct(run.quality.recall5)} · nDCG@5 ${formatPct(run.quality.ndcg5)} · MRR ${run.quality.mrr.toFixed(3)}`,
        "success",
      );
    } catch (error) {
      notify((error as Error).message, "error");
    } finally {
      if (collectionName) {
        void api.evalDrop(collectionName).catch(() => undefined);
      }
      setRunning(false);
      setProgress(null);
    }
  };

  const runBatchBench = async () => {
    if (!fixture || !ready) {
      notify("请先加载模型并准备评测集", "error");
      return;
    }
    setBenching(true);
    setBenchResults(null);
    try {
      const texts = fixture.chunks.slice(0, 48).map((chunk) => chunk.text);
      const results: { batchSize: number; ms: number; throughput: number }[] = [];
      for (const size of [1, 8, 16, 32]) {
        const started = performance.now();
        await embedder.embed(texts, size);
        const ms = performance.now() - started;
        results.push({ batchSize: size, ms, throughput: texts.length / (ms / 1000) });
      }
      setBenchResults(results);
      void api
        .saveResults(`batch_${embedder.state.device}_${embedder.state.dtype}_${Date.now()}`, {
          ts: new Date().toISOString(),
          device: embedder.state.device,
          dtype: embedder.state.dtype,
          textCount: texts.length,
          results,
        })
        .catch(() => undefined);
      notify("批大小基准完成", "success");
    } catch (error) {
      notify((error as Error).message, "error");
    } finally {
      setBenching(false);
    }
  };

  const removeRun = (id: string) => {
    persist(runs.filter((run) => run.id !== id));
    if (currentId === id) setCurrentId(null);
  };

  const downloadRun = () => {
    if (!current) return;
    const blob = new Blob([JSON.stringify(current, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `eval_${current.device}_${current.dtype}_${current.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="stack">
      <Card
        title="检索质量与性能评测"
        subtitle={
          fixture
            ? `固定评测集：${fixture.stats.documentCount} 篇文档 / ${fixture.stats.chunkCount} 个分块 / ${fixture.stats.queryCount} 条查询；使用 seekdb 混合检索，文档级 Recall@5、nDCG@5、MRR。`
            : "正在加载固定评测集…"
        }
        actions={
          <div className="row-actions">
            <button className="btn ghost" onClick={downloadRun} disabled={!current}>
              导出当前结果
            </button>
            <button className="btn primary" onClick={() => void runEvaluation()} disabled={running || !ready || !fixture}>
              {running ? "评测中…" : "运行当前后端评测"}
            </button>
          </div>
        }
      >
        <div className="eval-banner">
          <div>
            <strong>当前后端</strong>
            <span>
              {embedder.state.status === "ready"
                ? `${embedder.state.device === "webgpu" ? "WebGPU" : "WASM"} · ${embedder.state.dtype} · ${embedder.state.dim} 维`
                : "未初始化（请在左侧加载模型）"}
            </span>
          </div>
          <div>
            <strong>评测流程</strong>
            <span>浏览器向量化 → 写入临时 seekdb 集合 → refresh_index → 逐条混合检索 → 自动删除临时集合</span>
          </div>
          <div>
            <strong>对比方式</strong>
            <span>切换左侧后端并各运行一次；语料、查询、topK=5、RRF 参数完全一致</span>
          </div>
        </div>

        {progress && (
          <Progress value={progress.total ? progress.done / progress.total : 0} label={progress.label} />
        )}

        {runs.length === 0 && !running && (
          <Empty title="还没有评测结果" hint="分别在 WebGPU FP16、WASM INT8、WASM FP32 下运行一次即可得到量化前后对比。" />
        )}

        {current && (
          <>
            <div className="measure-grid eval-metrics">
              <Stat label="Recall@5" value={formatPct(current.quality.recall5)} hint={`${current.queryCount} 条查询`} />
              <Stat label="nDCG@5" value={formatPct(current.quality.ndcg5)} hint="文档级二值相关性" />
              <Stat label="MRR" value={current.quality.mrr.toFixed(3)} hint="首个相关文档排名" />
              <Stat
                label="向量化吞吐"
                value={`${current.chunkThroughput.toFixed(1)} 块/秒`}
                hint={`${current.chunkCount} 块 / ${formatMs(current.embedChunksMs)}`}
              />
              <Stat label="查询向量化" value={formatMs(current.queryEmbedMs)} hint="中位数" />
              <Stat label="seekdb 检索" value={formatMs(current.dbMs)} hint="中位数（混合检索）" />
              <Stat label="端到端" value={formatMs(current.e2eMs)} hint="查询向量化 + 检索" />
              <Stat label="模型加载" value={formatMs(current.loadMs)} hint={`冷启动推理 ${formatMs(current.coldMs)}`} />
            </div>

            {current.dtype !== "fp32" && baseline && baseline.id !== current.id && (
              <div className="delta-row">
                <Chip tone={current.quality.recall5 >= baseline.quality.recall5 - 0.02 ? "good" : "warn"}>
                  Recall@5 相对 FP32 基线 {((current.quality.recall5 - baseline.quality.recall5) * 100).toFixed(1)} pp
                </Chip>
                <Chip tone="neutral">
                  nDCG@5 {((current.quality.ndcg5 - baseline.quality.ndcg5) * 100).toFixed(1)} pp
                </Chip>
                <Chip tone="neutral">
                  体积 {formatBytes(sizeFor(current.dtype))} vs {formatBytes(sizeFor("fp32"))}
                  {sizeFor(current.dtype) && sizeFor("fp32")
                    ? `（${(Number(sizeFor("fp32")) / Number(sizeFor(current.dtype))).toFixed(2)}× 压缩）`
                    : ""}
                </Chip>
              </div>
            )}

            <div className="row-actions">
              <button className="btn ghost small" onClick={() => setShowPerQuery((value) => !value)}>
                {showPerQuery ? "收起逐条结果" : "展开逐条结果"}
              </button>
            </div>

            {showPerQuery && (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>查询</th>
                      <th className="num">Recall@5</th>
                      <th className="num">nDCG@5</th>
                      <th className="num">首个命中</th>
                      <th className="num">端到端</th>
                      <th>Top-5 文档 ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {current.perQuery.map((item) => (
                      <tr key={item.id}>
                        <td className="mono">{item.id}</td>
                        <td>{item.query}</td>
                        <td className="num">{item.recall.toFixed(2)}</td>
                        <td className="num">{item.ndcg.toFixed(3)}</td>
                        <td className="num">{item.firstHitRank ?? "—"}</td>
                        <td className="num mono">{formatMs(item.e2eMs)}</td>
                        <td className="mono tiny">{item.topDocIds.join(" · ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Card>

      <Card
        title="历次评测"
        subtitle="结果保存在浏览器 localStorage，同时由服务端写入 results/*.json 以便复现。"
      >
        {runs.length === 0 ? (
          <Empty title="暂无记录" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>后端</th>
                  <th className="num">模型体积</th>
                  <th className="num">Recall@5</th>
                  <th className="num">nDCG@5</th>
                  <th className="num">MRR</th>
                  <th className="num">向量化</th>
                  <th className="num">查询延迟</th>
                  <th className="num">seekdb</th>
                  <th className="num">端到端</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} className={run.id === current?.id ? "selected" : ""}>
                    <td className="mono tiny">{new Date(run.ts).toLocaleString()}</td>
                    <td>
                      <Chip tone={run.device === "webgpu" ? "accent" : "neutral"}>
                        {run.device === "webgpu" ? "WebGPU" : "WASM"} · {run.dtype}
                      </Chip>
                      {run.dtype === "fp32" && <span className="tiny muted"> 基线</span>}
                    </td>
                    <td className="num mono">{formatBytes(sizeFor(run.dtype))}</td>
                    <td className="num">{formatPct(run.quality.recall5)}</td>
                    <td className="num">{formatPct(run.quality.ndcg5)}</td>
                    <td className="num">{run.quality.mrr.toFixed(3)}</td>
                    <td className="num">{run.chunkThroughput.toFixed(1)}/s</td>
                    <td className="num mono">{formatMs(run.queryEmbedMs)}</td>
                    <td className="num mono">{formatMs(run.dbMs)}</td>
                    <td className="num mono">{formatMs(run.e2eMs)}</td>
                    <td className="row-actions">
                      <button className="link" onClick={() => setCurrentId(run.id)}>
                        查看
                      </button>
                      <button className="link danger" onClick={() => removeRun(run.id)}>
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card
        title="批大小基准"
        subtitle="相同 48 个分块，在当前后端依次以 1 / 8 / 16 / 32 的批大小向量化；用于支撑批处理优化结论。"
        actions={
          <button className="btn ghost" onClick={() => void runBatchBench()} disabled={benching || !ready || !fixture}>
            {benching ? "运行中…" : "运行批大小基准"}
          </button>
        }
      >
        {!benchResults ? (
          <Empty title="尚未运行" hint="首次运行包含 JIT/缓存预热，建议结合热态多次结果解读。" />
        ) : (
          <div className="bench">
            {benchResults.map((item) => (
              <div className="bench-row" key={item.batchSize}>
                <span className="bench-label">batch {item.batchSize}</span>
                <div className="bench-bar">
                  <span
                    style={{
                      width: `${Math.max(
                        3,
                        (item.throughput / Math.max(...benchResults.map((entry) => entry.throughput))) * 100,
                      )}%`,
                    }}
                  />
                </div>
                <span className="bench-value">{item.throughput.toFixed(1)} 块/秒</span>
                <span className="muted mono">{formatMs(item.ms)}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
