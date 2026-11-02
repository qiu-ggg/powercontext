import { useState } from "react";
import { api, type CollectionInfo, type SearchResponse } from "../api";
import type { useEmbedder } from "../useEmbedder";
import { Card, Chip, Empty, Stat, type Notify } from "../components";
import { formatMs } from "../metrics";

type Embedder = ReturnType<typeof useEmbedder>;
type Mode = "hybrid" | "vector" | "fulltext";

const MODE_HINT: Record<Mode, string> = {
  hybrid: "seekdb 单条 SQL 内完成向量召回 + 全文召回 + RRF 融合（DBMS_HYBRID_SEARCH.GET_SQL）",
  vector: "seekdb HNSW 向量索引，余弦距离；得分为 1 − distance",
  fulltext: "seekdb 全文索引（ik 分词），MATCH ... AGAINST 自然语言模式",
};

function Highlight({ text, query }: { text: string; query: string }) {
  const needle = query.trim();
  if (!needle) return <>{text}</>;
  const index = text.toLowerCase().indexOf(needle.toLowerCase());
  if (index < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <mark>{text.slice(index, index + needle.length)}</mark>
      {text.slice(index + needle.length)}
    </>
  );
}

export default function SearchPanel({
  kb,
  embedder,
  notify,
}: {
  kb: CollectionInfo | null;
  embedder: Embedder;
  notify: Notify;
}) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<Mode>("hybrid");
  const [topK, setTopK] = useState(8);
  const [rankConstant, setRankConstant] = useState(60);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [timings, setTimings] = useState<{ embedMs: number; dbMs: number; e2eMs: number } | null>(null);
  const [history, setHistory] = useState<{ query: string; mode: Mode; e2e: number }[]>([]);
  const [showSql, setShowSql] = useState(true);

  const ready = embedder.state.status === "ready";
  const maxScore = result ? Math.max(1e-9, ...result.hits.map((hit) => hit.score)) : 1;

  const run = async (override?: string) => {
    const text = (override ?? query).trim();
    if (!text) {
      notify("请输入查询文本", "error");
      return;
    }
    if (!kb) {
      notify("请先选择知识库", "error");
      return;
    }
    if (!ready) {
      notify("请先在左侧初始化推理后端", "error");
      return;
    }
    if ((kb.chunkCount ?? 0) === 0) {
      notify("当前知识库为空，请先导入文档", "error");
      return;
    }
    setLoading(true);
    try {
      const started = performance.now();
      const embedded = await embedder.embedOne(text);
      const response = await api.search(kb.id, {
        vector: embedded.vector,
        text,
        topK,
        mode,
        rankConstant,
      });
      const e2eMs = performance.now() - started;
      setResult(response);
      setTimings({ embedMs: embedded.ms, dbMs: response.dbMs, e2eMs });
      setHistory((prev) => [{ query: text, mode, e2e: e2eMs }, ...prev].slice(0, 6));
      if (response.hits.length === 0) notify("seekdb 未返回结果，可尝试提高 topK 或换关键词", "info");
    } catch (error) {
      notify((error as Error).message, "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack">
      <Card
        title="检索"
        subtitle="查询向量在你的设备上生成；候选召回与融合排序全部由 seekdb 完成。"
        actions={
          <div className="segmented">
            {(["hybrid", "vector", "fulltext"] as Mode[]).map((item) => (
              <button key={item} className={mode === item ? "active" : ""} onClick={() => setMode(item)}>
                {item === "hybrid" ? "混合" : item === "vector" ? "向量" : "全文"}
              </button>
            ))}
          </div>
        }
      >
        <div className="search-box">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void run();
            }}
            placeholder="例如：seekdb 如何完成向量与全文混合检索？"
            autoFocus
          />
          <button className="btn primary" onClick={() => void run()} disabled={loading}>
            {loading ? "检索中…" : "检索"}
          </button>
        </div>
        <div className="search-options">
          <span className="muted">{MODE_HINT[mode]}</span>
          <label>
            topK
            <select value={topK} onChange={(event) => setTopK(Number(event.target.value))}>
              {[3, 5, 8, 10, 20].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          {mode === "hybrid" && (
            <label>
              RRF k
              <input
                type="number"
                min={1}
                max={200}
                value={rankConstant}
                onChange={(event) => setRankConstant(Number(event.target.value))}
              />
            </label>
          )}
        </div>

        {history.length > 0 && (
          <div className="history">
            <span className="muted">最近：</span>
            {history.map((item, index) => (
              <button
                key={`${item.query}-${index}`}
                className="history-item"
                onClick={() => {
                  setQuery(item.query);
                  setMode(item.mode);
                  void run(item.query);
                }}
                title={`端到端 ${formatMs(item.e2e)}`}
              >
                {item.query}
              </button>
            ))}
          </div>
        )}
      </Card>

      {timings && (
        <div className="latency-strip">
          <div>
            <span>查询向量化</span>
            <strong>{formatMs(timings.embedMs)}</strong>
            <em>{embedder.state.device === "webgpu" ? "WebGPU" : "WASM"} · {embedder.state.dtype}</em>
          </div>
          <div>
            <span>seekdb 检索</span>
            <strong>{formatMs(timings.dbMs)}</strong>
            <em>{result?.mode} 模式</em>
          </div>
          <div className="accent">
            <span>端到端（提交 → 结果）</span>
            <strong>{formatMs(timings.e2eMs)}</strong>
            <em>含本地推理与网络往返</em>
          </div>
        </div>
      )}

      <Card
        title="结果"
        subtitle={
          result
            ? `${result.hits.length} 条 · ${result.mode} · ${result.hits[0]?.scoreKind ?? ""} 分数${
                result.hits.length ? "" : ""
              }`
            : "在 seekdb 中完成召回后返回"
        }
        actions={
          <button className="btn ghost small" onClick={() => setShowSql((value) => !value)}>
            {showSql ? "隐藏 SQL" : "查看 SQL"}
          </button>
        }
      >
        {!result ? (
          <Empty
            title="等待查询"
            hint={kb ? `当前知识库 ${kb.name} 共 ${kb.chunkCount} 个分块` : "请选择或创建知识库"}
          />
        ) : result.hits.length === 0 ? (
          <Empty title="没有命中" hint="混合检索由全文条件与向量近邻共同决定，可尝试更宽泛的关键词。" />
        ) : (
          <ol className="hits">
            {result.hits.map((hit, index) => (
              <li key={hit.id}>
                <div className="hit-rank">{String(index + 1).padStart(2, "0")}</div>
                <div className="hit-body">
                  <div className="hit-head">
                    <span className="hit-title">{hit.docTitle || hit.docId}</span>
                    <Chip tone="neutral">分块 #{hit.chunkIndex + 1}</Chip>
                    {hit.source && <span className="muted mono">{hit.source}</span>}
                    <span className="hit-score">
                      {hit.scoreKind === "rrf" ? "RRF" : hit.scoreKind === "bm25" ? "BM25" : "cosine"}{" "}
                      {hit.score.toFixed(4)}
                    </span>
                  </div>
                  <p className="hit-text">
                    <Highlight text={hit.text} query={query} />
                  </p>
                  <div className="score-bar">
                    <span style={{ width: `${Math.max(2, (hit.score / maxScore) * 100)}%` }} />
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </Card>

      {showSql && result && (
        <Card title="seekdb 执行轨迹" subtitle="来自 seekdb-js 的实际 SQL 调用（含混合检索存储过程生成的语句）。">
          <div className="sql-list">
            {result.sql.map((trace) => (
              <details key={trace.seq} open={result.sql.length <= 3}>
                <summary>
                  <span className="mono">#{trace.seq}</span>
                  <span className="sql-ms">{formatMs(trace.ms)}</span>
                  <span className="sql-preview mono">{trace.sql.slice(0, 110)}…</span>
                </summary>
                <pre>{trace.sql}</pre>
                {trace.params.length > 0 && (
                  <pre className="params">params: {JSON.stringify(trace.params)}</pre>
                )}
              </details>
            ))}
          </div>
          <p className="fine-print">
            混合模式下 seekdb-js 先写入 <span className="mono">@search_parm</span>，再调用{" "}
            <span className="mono">DBMS_HYBRID_SEARCH.GET_SQL</span> 获取并执行一条同时包含向量与全文条件的 SQL，
            融合在数据库内完成，客户端不拼接两路结果。
          </p>
        </Card>
      )}
    </div>
  );
}
