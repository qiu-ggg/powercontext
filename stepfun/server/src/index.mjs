import express from "express";
import fs from "node:fs/promises";
import path from "node:path";
import { config } from "./config.mjs";
import {
  initDb,
  listCollections,
  createCollection,
  getRegistry,
  deleteCollection,
  listDocs,
  statsFor,
  ingestDocuments,
  refreshCollection,
  search,
  buildEvalCollection,
  evalSearch,
  dropCollectionByName,
  dbVersion,
  getClient,
} from "./db.mjs";
import { prepareDocuments } from "./chunk.mjs";
import { loadCorpus, evalFixture } from "./corpus.mjs";

const app = express();
app.use(express.json({ limit: "64mb" }));

app.use((req, res, next) => {
  res.setHeader("Cross-Origin-Opener-Policy", "same-origin");
  res.setHeader("Cross-Origin-Embedder-Policy", "require-corp");
  res.setHeader("Cross-Origin-Resource-Policy", "cross-origin");
  next();
});

const startedAt = Date.now();
let dbInfo = { version: "unknown" };

function fail(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function asyncRoute(handler) {
  return (req, res, next) => Promise.resolve(handler(req, res)).catch(next);
}

function assertVector(vector, dim, label) {
  if (
    !Array.isArray(vector) ||
    vector.length !== dim ||
    !vector.every((value) => typeof value === "number" && Number.isFinite(value))
  ) {
    throw fail(400, `${label} 必须是 ${dim} 个有限数值`);
  }
}

app.get("/api/health", asyncRoute(async (_req, res) => {
  const started = performance.now();
  const version = await dbVersion();
  res.json({
    ok: true,
    db: { version, latencyMs: performance.now() - started, config: { host: config.db.host, port: config.db.port, database: config.db.database } },
    model: config.modelId,
    dim: config.dim,
    uptimeSec: Math.round((Date.now() - startedAt) / 1000),
  });
}));

app.get("/api/collections", asyncRoute(async (_req, res) => {
  res.json({ collections: await listCollections() });
}));

app.post("/api/collections", asyncRoute(async (req, res) => {
  const name = String(req.body?.name ?? "").trim();
  if (!name) throw fail(400, "知识库名称不能为空");
  if (name.length > 80) throw fail(400, "知识库名称过长");
  const registry = await createCollection(name);
  res.status(201).json({ collection: registry });
}));

app.delete("/api/collections/:id", asyncRoute(async (req, res) => {
  const ok = await deleteCollection(req.params.id);
  if (!ok) throw fail(404, "知识库不存在");
  res.json({ ok });
}));

app.get("/api/collections/:id/stats", asyncRoute(async (req, res) => {
  const registry = await getRegistry(req.params.id);
  if (!registry) throw fail(404, "知识库不存在");
  res.json({ collection: await statsFor(registry) });
}));

app.get("/api/collections/:id/docs", asyncRoute(async (req, res) => {
  const registry = await getRegistry(req.params.id);
  if (!registry) throw fail(404, "知识库不存在");
  res.json({ documents: await listDocs(registry.id) });
}));

app.post("/api/collections/:id/prepare", asyncRoute(async (req, res) => {
  const registry = await getRegistry(req.params.id);
  if (!registry) throw fail(404, "知识库不存在");
  const documents = req.body?.documents;
  if (!Array.isArray(documents) || documents.length === 0) {
    throw fail(400, "documents 不能为空");
  }
  const prepared = prepareDocuments(
    documents.map((doc) => ({
      name: String(doc.name ?? "未命名文档"),
      content: String(doc.content ?? ""),
    })),
  ).filter((doc) => doc.chunks.length > 0);
  const chunkCount = prepared.reduce((sum, doc) => sum + doc.chunks.length, 0);
  res.json({
    documents: prepared,
    summary: { documentCount: prepared.length, chunkCount },
    dim: registry.dim,
  });
}));

app.post("/api/collections/:id/ingest", asyncRoute(async (req, res) => {
  const registry = await getRegistry(req.params.id);
  if (!registry) throw fail(404, "知识库不存在");
  const documents = req.body?.documents;
  if (!Array.isArray(documents) || documents.length === 0) throw fail(400, "documents 不能为空");

  for (const doc of documents) {
    if (!Array.isArray(doc.chunks) || doc.chunks.length === 0) throw fail(400, `文档 ${doc.title ?? doc.docId} 没有分块`);
    for (const chunk of doc.chunks) {
      assertVector(chunk.vector, registry.dim, `分块 ${chunk.id} 的向量`);
    }
  }

  const result = await ingestDocuments(registry, documents, {
    batchSize: Number(req.body?.batchSize ?? 64),
    refreshPolicy: req.body?.refreshPolicy,
  });
  res.json(result);
}));

app.post("/api/collections/:id/search", asyncRoute(async (req, res) => {
  const registry = await getRegistry(req.params.id);
  if (!registry) throw fail(404, "知识库不存在");
  const { vector, text = "", topK = 8, mode = "hybrid", rankConstant = 60 } = req.body ?? {};
  assertVector(vector, registry.dim, "query vector");
  if (mode !== "vector" && !String(text).trim()) throw fail(400, "该检索模式需要查询文本");
  const result = await search(registry, {
    vector,
    text: String(text),
    topK: Number(topK),
    mode,
    rankConstant: Number(rankConstant),
  });
  res.json(result);
}));

app.post("/api/collections/:id/refresh", asyncRoute(async (req, res) => {
  const registry = await getRegistry(req.params.id);
  if (!registry) throw fail(404, "知识库不存在");
  res.json(await refreshCollection(registry));
}));

app.get("/api/corpus", asyncRoute(async (_req, res) => {
  res.json({ documents: await loadCorpus() });
}));

app.get("/api/eval/fixture", asyncRoute(async (_req, res) => {
  const fixture = await evalFixture();
  res.json({
    chunks: fixture.chunks,
    queries: fixture.queries,
    stats: {
      documentCount: fixture.documents.length,
      chunkCount: fixture.chunks.length,
      queryCount: fixture.queries.length,
    },
  });
}));

const evalCollections = new Map();

app.post("/api/eval/build", asyncRoute(async (req, res) => {
  const { dtype, chunks } = req.body ?? {};
  if (!Array.isArray(chunks) || chunks.length === 0) throw fail(400, "chunks 不能为空");
  for (const chunk of chunks) {
    assertVector(chunk.vector, config.dim, `chunk ${chunk.id} 的向量`);
  }
  const name = `eval_${String(dtype || "x").replace(/[^a-z0-9]/gi, "")}_${Date.now().toString(36)}`;
  const collection = await buildEvalCollection(name, chunks);
  evalCollections.set(name, collection);
  res.json({ collectionName: name, chunkCount: chunks.length });
}));

app.post("/api/eval/search", asyncRoute(async (req, res) => {
  const { collectionName, vector, text, topK = 10 } = req.body ?? {};
  const collection = evalCollections.get(collectionName);
  if (!collection) throw fail(404, "评测集合不存在或已清理");
  assertVector(vector, config.dim, "向量");
  const started = performance.now();
  const hits = await evalSearch(collection, vector, String(text ?? ""), Number(topK));
  res.json({ hits, dbMs: performance.now() - started });
}));

app.delete("/api/eval/:name", asyncRoute(async (req, res) => {
  const name = req.params.name;
  evalCollections.delete(name);
  if (!name.startsWith("eval_")) throw fail(400, "非法集合名");
  await dropCollectionByName(name);
  res.json({ ok: true });
}));

app.get("/api/models", asyncRoute(async (_req, res) => {
  const onnxDir = path.join(config.modelsDir, config.modelId, "onnx");
  const wanted = {
    fp32: "model.onnx",
    fp16: "model_fp16.onnx",
    int8: "model_int8.onnx",
    q8: "model_quantized.onnx",
  };
  const files = {};
  for (const [dtype, file] of Object.entries(wanted)) {
    try {
      const stat = await fs.stat(path.join(onnxDir, file));
      files[dtype] = { file: `onnx/${file}`, bytes: stat.size };
    } catch {
      files[dtype] = { file: `onnx/${file}`, bytes: null };
    }
  }
  const tokenizerBytes = await Promise.all(
    ["config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "vocab.txt"].map(async (name) => {
      try {
        return (await fs.stat(path.join(config.modelsDir, config.modelId, name))).size;
      } catch {
        return 0;
      }
    }),
  );
  res.json({
    modelId: config.modelId,
    source: "https://huggingface.co/Xenova/bge-small-zh-v1.5",
    baseModel: "BAAI/bge-small-zh-v1.5",
    dim: config.dim,
    files,
    tokenizerBytes: tokenizerBytes.reduce((a, b) => a + b, 0),
  });
}));

app.post("/api/results", asyncRoute(async (req, res) => {
  const { name, data } = req.body ?? {};
  if (!name || !data) throw fail(400, "name 与 data 必填");
  const safe = String(name).replace(/[^a-z0-9._-]/gi, "_").slice(0, 80);
  await fs.mkdir(config.resultsDir, { recursive: true });
  const target = path.join(config.resultsDir, `${safe}.json`);
  await fs.writeFile(target, JSON.stringify(data, null, 2), "utf8");
  res.json({ ok: true, path: `results/${safe}.json` });
}));

const distIndex = path.join(config.webDist, "index.html");
app.use(express.static(config.webDist, { index: "index.html" }));
app.use(async (req, res, next) => {
  if (req.path.startsWith("/api/")) return next();
  try {
    await fs.access(distIndex);
    res.sendFile(distIndex);
  } catch {
    res.status(404).send("前端尚未构建：请运行 npm run dev（开发）或 npm run build && npm start（生产）。");
  }
});

app.use((err, _req, res, _next) => {
  const status = err.status ?? 500;
  if (status >= 500) console.error("[api]", err);
  res.status(status).json({ error: err.message ?? "内部错误" });
});

async function main() {
  try {
    dbInfo = await initDb();
    console.log(`[stepfun-kb] seekdb ${dbInfo.version} @ ${config.db.host}:${config.db.port}/${config.db.database}`);
  } catch (error) {
    console.error("[stepfun-kb] seekdb 连接失败:", error.message);
    console.error("请先启动本地 seekdb：npm run setup:seekdb（Windows/Linux 可执行文件）或 docker compose up -d seekdb");
    process.exitCode = 1;
    return;
  }
  app.listen(config.port, () => {
    console.log(`[stepfun-kb] API listening on http://127.0.0.1:${config.port}`);
  });
}

main();
