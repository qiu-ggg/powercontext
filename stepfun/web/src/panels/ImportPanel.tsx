import { useMemo, useRef, useState } from "react";
import { api, type CollectionInfo, type DocumentInfo, type PreparedDocument } from "../api";
import type { EmbedProgress, useEmbedder } from "../useEmbedder";
import { Card, Empty, Progress, Stat, type Notify } from "../components";
import { formatMs } from "../metrics";

type Embedder = ReturnType<typeof useEmbedder>;

interface IngestReport {
  embedMs: number;
  addMs: number;
  refreshMs: number;
  ingestTotalMs: number;
  e2eMs: number;
  chunkCount: number;
  batchSize: number;
  refreshPolicy: string;
}

export default function ImportPanel({
  kb,
  documents,
  embedder,
  notify,
  onChanged,
}: {
  kb: CollectionInfo | null;
  documents: DocumentInfo[];
  embedder: Embedder;
  notify: Notify;
  onChanged: () => Promise<void>;
}) {
  const [pending, setPending] = useState<{ name: string; content: string }[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [prepared, setPrepared] = useState<PreparedDocument[] | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<EmbedProgress | null>(null);
  const [report, setReport] = useState<IngestReport | null>(null);
  const [batchSize, setBatchSize] = useState(() => Number(localStorage.getItem("eseek.batch") || 32));
  const [refreshPolicy, setRefreshPolicy] = useState<"end" | "batch">("end");
  const [refreshInfo, setRefreshInfo] = useState<{ ms: number; at: string } | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const chunkCount = useMemo(
    () => (prepared ? prepared.reduce((sum, doc) => sum + doc.chunks.length, 0) : 0),
    [prepared],
  );

  const addFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const additions: { name: string; content: string }[] = [];
    for (const file of Array.from(files)) {
      const text = await file.text();
      if (text.trim()) additions.push({ name: file.name, content: text });
    }
    setPending((prev) => {
      const names = new Set(prev.map((doc) => doc.name));
      return [...prev, ...additions.filter((doc) => !names.has(doc.name))];
    });
    setPrepared(null);
    setReport(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const addPasted = () => {
    if (!content.trim()) {
      notify("请先粘贴正文", "error");
      return;
    }
    const name = (title.trim() || `粘贴文档 ${pending.length + 1}`) + ".md";
    if (pending.some((doc) => doc.name === name)) {
      notify("同名文档已在待导入列表中，请修改标题", "error");
      return;
    }
    setPending((prev) => [...prev, { name, content }]);
    setTitle("");
    setContent("");
    setPrepared(null);
    setReport(null);
  };

  const removePending = (name: string) => {
    setPending((prev) => prev.filter((doc) => doc.name !== name));
    setPrepared(null);
  };

  const doPrepare = async () => {
    if (!kb || pending.length === 0) return;
    setPreparing(true);
    try {
      const result = await api.prepare(kb.id, pending);
      setPrepared(result.documents);
      notify(`分块完成：${result.summary.documentCount} 篇 / ${result.summary.chunkCount} 块`, "success");
    } catch (error) {
      notify((error as Error).message, "error");
    } finally {
      setPreparing(false);
    }
  };

  const doIngest = async () => {
    if (!kb || !prepared || prepared.length === 0) return;
    if (embedder.state.status !== "ready") {
      notify("请先在左侧初始化推理后端", "error");
      return;
    }
    setRunning(true);
    setProgress(null);
    setReport(null);
    const started = performance.now();
    try {
      const texts = prepared.flatMap((doc) => doc.chunks.map((chunk) => chunk.text));
      const embedded = await embedder.embed(texts, batchSize, setProgress);
      let cursor = 0;
      const payload = prepared.map((doc) => ({
        ...doc,
        chunks: doc.chunks.map((chunk) => {
          const vector = embedded.vectors[cursor];
          cursor += 1;
          return { ...chunk, vector };
        }),
      }));
      const embedMs = performance.now() - started;
      const result = await api.ingest(kb.id, payload, batchSize, refreshPolicy);
      const e2eMs = performance.now() - started;
      const nextReport: IngestReport = {
        embedMs,
        addMs: result.timings.addMs,
        refreshMs: result.timings.refreshMs,
        ingestTotalMs: result.timings.totalMs,
        e2eMs,
        chunkCount: result.inserted,
        batchSize,
        refreshPolicy: result.refreshPolicy,
      };
      setReport(nextReport);
      setPending([]);
      setPrepared(null);
      setProgress(null);
      notify(`已写入 ${result.inserted} 个分块并完成索引刷新（${result.refreshedTimes} 次）`, "success");
      await onChanged();
      const saved = {
        ts: new Date().toISOString(),
        device: embedder.state.device,
        dtype: embedder.state.dtype,
        ...nextReport,
      };
      localStorage.setItem("eseek.lastIngest", JSON.stringify(saved));
      void api.saveResults(`ingest_${embedder.state.device}_${embedder.state.dtype}_${Date.now()}`, saved).catch(() => undefined);
    } catch (error) {
      notify((error as Error).message, "error");
    } finally {
      setRunning(false);
    }
  };

  const doRefresh = async () => {
    if (!kb) return;
    try {
      const started = performance.now();
      const result = await api.refresh(kb.id);
      const ms = performance.now() - started;
      setRefreshInfo({ ms, at: new Date().toLocaleTimeString() });
      notify(`索引刷新完成：${result.chunkCount} 个分块，${formatMs(result.refreshMs)}`, "success");
      await onChanged();
    } catch (error) {
      notify((error as Error).message, "error");
    }
  };

  const ready = embedder.state.status === "ready";

  return (
    <div className="stack">
      <div className="grid grid-2">
        <Card
          title="导入文档"
          subtitle="文本在浏览器内完成 embedding，随后把向量、原文和元数据写入 seekdb。"
          actions={
            <button className="btn ghost" onClick={() => fileRef.current?.click()} disabled={running}>
              选择 .md / .txt
            </button>
          }
        >
          <input
            ref={fileRef}
            type="file"
            accept=".md,.txt,text/plain,text/markdown"
            multiple
            hidden
            onChange={(event) => void addFiles(event.target.files)}
          />
          <div
            className="dropzone"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              void addFiles(event.dataTransfer.files);
            }}
          >
            <span className="drop-mark">＋</span>
            <div>
              <strong>拖入文本文件</strong>
              <p>或使用下方编辑框粘贴内容；同名文档再次导入会覆盖旧分块。</p>
            </div>
          </div>

          <div className="form-row">
            <label>标题</label>
            <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：seekdb 混合检索笔记" />
          </div>
          <div className="form-row">
            <label>正文</label>
            <textarea
              rows={6}
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="粘贴文档正文…"
            />
          </div>
          <div className="row-actions">
            <button className="btn ghost" onClick={addPasted} disabled={running}>
              加入待导入列表
            </button>
          </div>

          {pending.length > 0 && (
            <div className="pending">
              <div className="pending-head">
                <span>待导入 {pending.length} 篇</span>
                <button className="link" onClick={() => { setPending([]); setPrepared(null); }}>
                  清空
                </button>
              </div>
              {pending.map((doc) => (
                <div className="pending-item" key={doc.name}>
                  <span className="pending-name">{doc.name}</span>
                  <span className="pending-meta">{doc.content.length} 字符</span>
                  <button className="link danger" onClick={() => removePending(doc.name)}>
                    移除
                  </button>
                </div>
              ))}
              <div className="row-actions">
                <button className="btn" onClick={() => void doPrepare()} disabled={preparing || running}>
                  {preparing ? "分块中…" : "预览分块"}
                </button>
              </div>
            </div>
          )}
        </Card>

        <Card
          title="向量化与写入"
          subtitle="批大小影响吞吐；索引刷新策略决定新文档何时可检索。"
          actions={
            <button className="btn ghost" onClick={() => void doRefresh()} disabled={!kb}>
              仅刷新索引
            </button>
          }
        >
          {!prepared ? (
            <Empty
              title="先预览分块"
              hint="分块采用 360 字符目标长度、60 字符重叠，句子边界优先。"
            />
          ) : (
            <>
              <div className="stat-strip">
                <Stat label="文档" value={prepared.length} />
                <Stat label="分块" value={chunkCount} />
                <Stat label="目标维度" value={kb?.dim ?? "—"} />
              </div>
              <div className="prepared-list">
                {prepared.map((doc) => (
                  <details key={doc.docId}>
                    <summary>
                      <span>{doc.title}</span>
                      <span className="muted">{doc.chunks.length} 块 · {doc.charCount} 字符</span>
                    </summary>
                    <p className="snippet">{doc.chunks[0]?.text}</p>
                  </details>
                ))}
              </div>

              <div className="controls">
                <label>
                  批大小
                  <select
                    value={batchSize}
                    onChange={(event) => {
                      const value = Number(event.target.value);
                      setBatchSize(value);
                      localStorage.setItem("eseek.batch", String(value));
                    }}
                  >
                    {[8, 16, 32, 64, 128].map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  刷新策略
                  <select value={refreshPolicy} onChange={(event) => setRefreshPolicy(event.target.value as "end" | "batch")}>
                    <option value="end">全部写入后刷新（推荐）</option>
                    <option value="batch">每批写入后刷新</option>
                  </select>
                </label>
              </div>

              <button className="btn primary wide" onClick={() => void doIngest()} disabled={running || !ready}>
                {running ? "本地向量化并写入中…" : ready ? `向量化 ${chunkCount} 块并写入 seekdb` : "请先初始化推理后端"}
              </button>

              {progress && (
                <Progress
                  value={progress.done / Math.max(1, progress.total)}
                  label={`向量化 ${progress.done}/${progress.total} · 当前批 ${formatMs(progress.batchMs)}`}
                />
              )}
            </>
          )}

          {report && (
            <div className="report">
              <div className="report-head">本次导入实测</div>
              <div className="measure-grid">
                <Stat label="端侧向量化" value={formatMs(report.embedMs)} hint={`${(report.chunkCount / (report.embedMs / 1000)).toFixed(1)} 块/秒`} />
                <Stat label="写入 seekdb" value={formatMs(report.addMs)} hint={`批大小 ${report.batchSize}`} />
                <Stat label="索引刷新" value={formatMs(report.refreshMs)} hint={report.refreshPolicy === "end" ? "写入后一次" : "每批一次"} />
                <Stat label="端到端" value={formatMs(report.e2eMs)} hint={`${report.chunkCount} 块`} />
              </div>
            </div>
          )}

          {refreshInfo && (
            <div className="inline-note success">索引刷新于 {refreshInfo.at} 完成，耗时 {formatMs(refreshInfo.ms)}。</div>
          )}
          <p className="fine-print">
            模型推理在 Web Worker 中执行；写入请求只包含浏览器已算好的向量与原文，服务端不做 embedding。
          </p>
        </Card>
      </div>

      <Card
        title="当前知识库文档"
        subtitle={kb ? `${kb.name} · 集合 ${kb.collectionName}` : "未选择知识库"}
        actions={<span className="muted">{documents.length} 篇文档</span>}
      >
        {documents.length === 0 ? (
          <Empty title="还没有文档" hint="导入第一篇文档后，这里会显示 seekdb 中的文档登记信息。" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>标题</th>
                  <th>来源</th>
                  <th className="num">字符</th>
                  <th className="num">分块</th>
                  <th>导入时间</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr key={doc.docId}>
                    <td>{doc.title}</td>
                    <td className="mono muted">{doc.source}</td>
                    <td className="num">{doc.charCount}</td>
                    <td className="num">{doc.chunkCount}</td>
                    <td className="mono muted">{String(doc.importedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
