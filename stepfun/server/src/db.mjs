import crypto from "node:crypto";
import {
  SeekdbClient,
  Schema,
  FulltextIndexConfig,
  VectorIndexConfig,
} from "seekdb";
import { config } from "./config.mjs";

let client;
let traced = false;
const traceLog = [];
let traceSeq = 0;

function wrapExecute() {
  const original = client.execute.bind(client);
  client.execute = async (sql, params) => {
    const started = performance.now();
    const rows = await original(sql, params);
    traceLog.push({
      seq: ++traceSeq,
      ms: performance.now() - started,
      sql: String(sql).replace(/\s+/g, " ").trim(),
      params: params ? params.map((p) => (typeof p === "string" && p.length > 240 ? `${p.slice(0, 240)}…` : p)) : [],
    });
    if (traceLog.length > 200) traceLog.splice(0, traceLog.length - 200);
    return rows;
  };
  traced = true;
}

export function traceMark() {
  return traceSeq;
}

export function traceSince(mark) {
  return traceLog.filter((entry) => entry.seq > mark);
}

export function getClient() {
  return client;
}

export async function initDb() {
  client = new SeekdbClient(config.db);
  if (!traced) wrapExecute();

  const versionRows = await client.execute("SELECT VERSION() AS version");
  const version = versionRows?.[0]?.version ?? "unknown";

  await client.execute(`
    CREATE TABLE IF NOT EXISTS kb_registry (
      id VARCHAR(40) PRIMARY KEY,
      name VARCHAR(200) NOT NULL,
      collection_name VARCHAR(64) NOT NULL,
      model VARCHAR(128) NOT NULL,
      dim INT NOT NULL,
      doc_count INT NOT NULL DEFAULT 0,
      chunk_count INT NOT NULL DEFAULT 0,
      status VARCHAR(24) NOT NULL DEFAULT 'ready',
      last_ingest_ms DOUBLE,
      last_refresh_ms DOUBLE,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `);

  await client.execute(`
    CREATE TABLE IF NOT EXISTS kb_docs (
      kb_id VARCHAR(40) NOT NULL,
      doc_id VARCHAR(80) NOT NULL,
      title VARCHAR(300),
      source VARCHAR(300),
      char_count INT,
      chunk_count INT,
      imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (kb_id, doc_id)
    )
  `);

  return { version };
}

function schemaForDim(dim) {
  return new Schema({
    fulltextIndex: new FulltextIndexConfig("ik", { ik_mode: "smart" }),
    vectorIndex: new VectorIndexConfig({
      hnsw: { dimension: dim, distance: "cosine" },
      embeddingFunction: null,
    }),
  });
}

export async function listCollections() {
  const rows = (await client.execute(
    `SELECT id, name, collection_name, model, dim, doc_count, chunk_count, status,
            last_ingest_ms, last_refresh_ms, created_at, updated_at
       FROM kb_registry ORDER BY created_at DESC`,
  )) ?? [];
  return rows.map(mapRegistry);
}

function mapRegistry(row) {
  return {
    id: row.id,
    name: row.name,
    collectionName: row.collection_name,
    model: row.model,
    dim: Number(row.dim),
    docCount: Number(row.doc_count),
    chunkCount: Number(row.chunk_count),
    status: row.status,
    lastIngestMs: row.last_ingest_ms == null ? null : Number(row.last_ingest_ms),
    lastRefreshMs: row.last_refresh_ms == null ? null : Number(row.last_refresh_ms),
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export async function createCollection(name, model = config.modelId, dim = config.dim) {
  const id = crypto.randomBytes(6).toString("hex");
  const collectionName = `kb_${id}`;
  await client.createCollection({ name: collectionName, schema: schemaForDim(dim) });
  await client.execute(
    `INSERT INTO kb_registry (id, name, collection_name, model, dim) VALUES (?, ?, ?, ?, ?)`,
    [id, name, collectionName, model, dim],
  );
  return getRegistry(id);
}

export async function getRegistry(id) {
  const rows = await client.execute(`SELECT * FROM kb_registry WHERE id = ?`, [id]);
  if (!rows || rows.length === 0) return null;
  return mapRegistry(rows[0]);
}

export async function getCollectionObject(registry) {
  return client.getCollection({ name: registry.collectionName, embeddingFunction: null });
}

export async function deleteCollection(id) {
  const registry = await getRegistry(id);
  if (!registry) return false;
  await client.deleteCollection(registry.collectionName);
  await client.execute(`DELETE FROM kb_docs WHERE kb_id = ?`, [id]);
  await client.execute(`DELETE FROM kb_registry WHERE id = ?`, [id]);
  return true;
}

export async function listDocs(kbId) {
  const rows = (await client.execute(
    `SELECT doc_id, title, source, char_count, chunk_count, imported_at
       FROM kb_docs WHERE kb_id = ? ORDER BY imported_at DESC`,
    [kbId],
  )) ?? [];
  return rows.map((row) => ({
    docId: row.doc_id,
    title: row.title,
    source: row.source,
    charCount: Number(row.char_count),
    chunkCount: Number(row.chunk_count),
    importedAt: row.imported_at,
  }));
}

export async function statsFor(registry) {
  const collection = await getCollectionObject(registry);
  const count = await collection.count();
  const docs = (await client.execute(`SELECT COUNT(*) AS n FROM kb_docs WHERE kb_id = ?`, [registry.id]))?.[0];
  return {
    ...registry,
    chunkCount: count,
    docCount: Number(docs?.n ?? 0),
  };
}

function toMetadataObject(meta) {
  if (!meta) return {};
  if (typeof meta === "string") {
    try {
      return JSON.parse(meta);
    } catch {
      return {};
    }
  }
  return meta;
}

function idOf(value) {
  if (Buffer.isBuffer(value)) return value.toString("utf8");
  return String(value);
}

function toHit(id, document, metadata, score, scoreKind) {
  const meta = toMetadataObject(metadata);
  return {
    id: idOf(id),
    docId: meta.doc_id ?? "",
    docTitle: meta.doc_title ?? "",
    chunkIndex: Number(meta.chunk_index ?? 0),
    source: meta.source ?? "",
    text: document ?? "",
    score,
    scoreKind,
  };
}

export async function ingestDocuments(registry, documents, options = {}) {
  const batchSize = Number(options.batchSize ?? 64);
  const refreshPolicy = options.refreshPolicy === "batch" ? "batch" : "end";
  const collection = await getCollectionObject(registry);

  let addMs = 0;
  let refreshMs = 0;
  let inserted = 0;
  let refreshedTimes = 0;

  const refresh = async () => {
    const started = performance.now();
    await collection.refresh_index();
    const cost = performance.now() - started;
    refreshMs += cost;
    refreshedTimes += 1;
  };

  const startedAll = performance.now();
  for (const doc of documents) {
    await collection.delete({ where: { doc_id: doc.docId } });
    await client.execute(`DELETE FROM kb_docs WHERE kb_id = ? AND doc_id = ?`, [registry.id, doc.docId]);

    for (let offset = 0; offset < doc.chunks.length; offset += batchSize) {
      const slice = doc.chunks.slice(offset, offset + batchSize);
      const started = performance.now();
      await collection.add({
        ids: slice.map((c) => c.id),
        documents: slice.map((c) => c.text),
        metadatas: slice.map((c) => c.metadata),
        embeddings: slice.map((c) => c.vector),
      });
      addMs += performance.now() - started;
      inserted += slice.length;
      if (refreshPolicy === "batch") await refresh();
    }

    await client.execute(
      `INSERT INTO kb_docs (kb_id, doc_id, title, source, char_count, chunk_count)
       VALUES (?, ?, ?, ?, ?, ?)
       ON DUPLICATE KEY UPDATE title = VALUES(title), source = VALUES(source),
         char_count = VALUES(char_count), chunk_count = VALUES(chunk_count),
         imported_at = CURRENT_TIMESTAMP`,
      [registry.id, doc.docId, doc.title, doc.source, doc.charCount, doc.chunks.length],
    );
  }

  if (refreshPolicy === "end") await refresh();

  const totalMs = performance.now() - startedAll;
  const chunkCount = await collection.count();
  const docRows = (await client.execute(`SELECT COUNT(*) AS n FROM kb_docs WHERE kb_id = ?`, [registry.id]))?.[0];

  await client.execute(
    `UPDATE kb_registry
        SET doc_count = ?, chunk_count = ?, status = 'ready', last_ingest_ms = ?, last_refresh_ms = ?,
            updated_at = CURRENT_TIMESTAMP
      WHERE id = ?`,
    [Number(docRows?.n ?? 0), chunkCount, totalMs, refreshMs, registry.id],
  );

  return {
    inserted,
    refreshedTimes,
    timings: {
      addMs,
      refreshMs,
      totalMs,
    },
    collection: {
      docCount: Number(docRows?.n ?? 0),
      chunkCount,
    },
    refreshPolicy,
    batchSize,
  };
}

export async function refreshCollection(registry) {
  const collection = await getCollectionObject(registry);
  const started = performance.now();
  await collection.refresh_index();
  const ms = performance.now() - started;
  await client.execute(
    `UPDATE kb_registry SET last_refresh_ms = ?, status = 'ready', updated_at = CURRENT_TIMESTAMP WHERE id = ?`,
    [ms, registry.id],
  );
  return { refreshMs: ms, chunkCount: await collection.count() };
}

/**
 * Runs the hybrid query through the public client so every statement
 * (SET @search_parm, DBMS_HYBRID_SEARCH.GET_SQL, generated SQL) lands in the trace.
 * RRF fusion happens inside seekdb, not in this process.
 */
async function hybridSearchInDb(collection, { vector, text, topK, rankConstant }) {
  const table = `c$v2$${collection.collectionId}`;
  const knnK = Math.max(topK * 2, 20);
  const rrfWindow = Math.max(topK * 4, 40);
  const searchParm = {
    query: { query_string: { fields: ["document"], query: text.trim() } },
    knn: { field: "embedding", k: knnK, query_vector: vector },
    rank: { rrf: { rank_window_size: rrfWindow, rank_constant: rankConstant } },
    size: topK,
  };

  await client.execute("SET @search_parm = ?", [JSON.stringify(searchParm)]);
  const rows = await client.execute(
    `SELECT DBMS_HYBRID_SEARCH.GET_SQL('${table}', @search_parm) AS query_sql FROM dual`,
  );
  const generatedSql = String(rows?.[0]?.query_sql ?? "")
    .trim()
    .replace(/^['"]|['"]$/g, "");
  if (!generatedSql) return { rows: [], knnK, rrfWindow, generatedSql: "" };
  const resultRows = (await client.execute(generatedSql)) ?? [];
  return { rows: resultRows, knnK, rrfWindow, generatedSql };
}

function hybridRowScore(row) {
  for (const field of ["_distance", "distance", "_score", "score", "SCORE", "DISTANCE"]) {
    if (row[field] !== undefined && row[field] !== null) return Number(row[field]);
  }
  return 0;
}

/**
 * All retrieval runs inside seekdb. `hybrid` uses DBMS_HYBRID_SEARCH with RRF
 * fusion in a single SQL statement; `vector` uses the SDK vector query;
 * `fulltext` uses MATCH ... AGAINST against the ik full-text index.
 */
export async function search(registry, { vector, text, topK = 8, mode = "hybrid", rankConstant = 60 }) {
  const collection = await getCollectionObject(registry);
  const k = Math.max(1, Math.min(50, Number(topK) || 8));
  const mark = traceMark();
  const started = performance.now();
  let hits = [];
  let meta = {};

  if (mode === "hybrid" && text && text.trim()) {
    const fused = await hybridSearchInDb(collection, { vector, text, topK: k, rankConstant });
    hits = fused.rows.map((row) => toHit(row._id, row.document, row.metadata, hybridRowScore(row), "rrf"));
    meta = { rankConstant, rrfWindow: fused.rrfWindow, knnK: fused.knnK, generatedSql: fused.generatedSql };
  } else if (mode === "fulltext" && text && text.trim()) {
    const table = `c$v2$${collection.collectionId}`;
    const sql = `
      SELECT _id, document, metadata,
             MATCH(document) AGAINST (? IN NATURAL LANGUAGE MODE) AS score
        FROM \`${table}\`
       WHERE MATCH(document) AGAINST (? IN NATURAL LANGUAGE MODE)
       ORDER BY score DESC
       LIMIT ?
    `.trim();
    const rows = (await client.execute(sql, [text.trim(), text.trim(), k])) ?? [];
    hits = rows.map((row) => toHit(row._id, row.document, row.metadata, Number(row.score ?? 0), "bm25"));
  } else {
    const table = `c$v2$${collection.collectionId}`;
    const literal = `[${vector.join(",")}]`;
    const sql = `
      SELECT _id, document, metadata,
             cosine_distance(embedding, '${literal}') AS distance
        FROM \`${table}\`
       ORDER BY cosine_distance(embedding, '${literal}') APPROXIMATE
       LIMIT ?
    `.trim();
    const rows = (await client.execute(sql, [k])) ?? [];
    hits = rows.map((row) => toHit(row._id, row.document, row.metadata, Number(1 - Number(row.distance ?? 1)), "cosine"));
    meta = { metric: "cosine similarity = 1 - distance" };
  }

  const dbMs = performance.now() - started;
  return {
    hits,
    dbMs,
    mode: mode === "hybrid" && (!text || !text.trim()) ? "vector" : mode,
    meta,
    sql: traceSince(mark),
  };
}

export async function buildEvalCollection(name, chunks) {
  const collection = await client.createCollection({
    name,
    schema: schemaForDim(config.dim),
  });
  for (let offset = 0; offset < chunks.length; offset += 64) {
    const slice = chunks.slice(offset, offset + 64);
    await collection.add({
      ids: slice.map((c) => c.id),
      documents: slice.map((c) => c.text),
      metadatas: slice.map((c) => c.metadata),
      embeddings: slice.map((c) => c.vector),
    });
  }
  await collection.refresh_index();
  return collection;
}

export async function evalSearch(collection, vector, text, topK = 10) {
  const res = await collection.hybridSearch({
    query: { whereDocument: { $contains: text } },
    knn: { queryEmbeddings: [vector], nResults: Math.max(topK * 2, 20) },
    rank: { rrf: { rankWindowSize: Math.max(topK * 4, 40), rankConstant: 60 } },
    nResults: topK,
    include: ["documents", "metadatas", "distances"],
  });
  const ids = res.ids?.[0] ?? [];
  const metas = res.metadatas?.[0] ?? [];
  return ids.map((id, i) => ({ id: idOf(id), docId: toMetadataObject(metas[i]).doc_id ?? "" }));
}

export async function dropCollectionByName(name) {
  try {
    await client.deleteCollection(name);
  } catch {
    /* already gone */
  }
}

export async function dbVersion() {
  const rows = await client.execute("SELECT VERSION() AS version");
  return rows?.[0]?.version ?? "unknown";
}

export { schemaForDim };
