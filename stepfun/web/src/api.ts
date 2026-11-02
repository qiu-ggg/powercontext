export interface CollectionInfo {
  id: string;
  name: string;
  collectionName: string;
  model: string;
  dim: number;
  docCount: number;
  chunkCount: number;
  status: string;
  lastIngestMs: number | null;
  lastRefreshMs: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface DocumentInfo {
  docId: string;
  title: string;
  source: string;
  charCount: number;
  chunkCount: number;
  importedAt: string;
}

export interface ChunkPayload {
  id: string;
  text: string;
  metadata: Record<string, string | number>;
}

export interface PreparedDocument {
  docId: string;
  title: string;
  source: string;
  charCount: number;
  chunks: ChunkPayload[];
}

export interface SearchHit {
  id: string;
  docId: string;
  docTitle: string;
  chunkIndex: number;
  source: string;
  text: string;
  score: number;
  scoreKind: string;
}

export interface SqlTrace {
  seq: number;
  ms: number;
  sql: string;
  params: unknown[];
}

export interface SearchResponse {
  hits: SearchHit[];
  dbMs: number;
  mode: string;
  meta: Record<string, unknown>;
  sql: SqlTrace[];
}

export interface EvalFixtureChunk {
  id: string;
  text: string;
  metadata: Record<string, string | number>;
}

export interface EvalFixtureQuery {
  id: string;
  query: string;
  gold: string[];
  goldDocIds: string[];
}

export interface EvalFixture {
  chunks: EvalFixtureChunk[];
  queries: EvalFixtureQuery[];
  stats: { documentCount: number; chunkCount: number; queryCount: number };
}

export interface ModelInfo {
  modelId: string;
  source: string;
  baseModel: string;
  dim: number;
  files: Record<string, { file: string; bytes: number | null }>;
  tokenizerBytes: number;
}

export interface HealthInfo {
  ok: boolean;
  db: { version: string; latencyMs: number; config: { host: string; port: number; database: string } };
  model: string;
  dim: number;
  uptimeSec: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...(init?.headers ?? {}) } : init?.headers,
  });
  const text = await response.text();
  let body: any = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!response.ok) {
    throw new Error(body?.error || `${response.status} ${response.statusText}`);
  }
  return body as T;
}

export const api = {
  health: () => request<HealthInfo>("/api/health"),
  models: () => request<ModelInfo>("/api/models"),
  collections: () => request<{ collections: CollectionInfo[] }>("/api/collections"),
  createCollection: (name: string) =>
    request<{ collection: CollectionInfo }>("/api/collections", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  deleteCollection: (id: string) => request<{ ok: boolean }>(`/api/collections/${id}`, { method: "DELETE" }),
  stats: (id: string) => request<{ collection: CollectionInfo }>(`/api/collections/${id}/stats`),
  docs: (id: string) => request<{ documents: DocumentInfo[] }>(`/api/collections/${id}/docs`),
  prepare: (id: string, documents: { name: string; content: string }[]) =>
    request<{ documents: PreparedDocument[]; summary: { documentCount: number; chunkCount: number }; dim: number }>(
      `/api/collections/${id}/prepare`,
      { method: "POST", body: JSON.stringify({ documents }) },
    ),
  ingest: (
    id: string,
    documents: (PreparedDocument & { chunks: (ChunkPayload & { vector: number[] })[] })[],
    batchSize: number,
    refreshPolicy: "end" | "batch",
  ) =>
    request<{
      inserted: number;
      refreshedTimes: number;
      timings: { addMs: number; refreshMs: number; totalMs: number };
      collection: { docCount: number; chunkCount: number };
      refreshPolicy: string;
      batchSize: number;
    }>(`/api/collections/${id}/ingest`, {
      method: "POST",
      body: JSON.stringify({ documents, batchSize, refreshPolicy }),
    }),
  search: (
    id: string,
    payload: { vector: number[]; text: string; topK: number; mode: "hybrid" | "vector" | "fulltext"; rankConstant?: number },
  ) => request<SearchResponse>(`/api/collections/${id}/search`, { method: "POST", body: JSON.stringify(payload) }),
  refresh: (id: string) => request<{ refreshMs: number; chunkCount: number }>(`/api/collections/${id}/refresh`, { method: "POST" }),
  corpus: () => request<{ documents: { name: string; content: string }[] }>("/api/corpus"),
  evalFixture: () => request<EvalFixture>("/api/eval/fixture"),
  evalBuild: (dtype: string, chunks: (EvalFixtureChunk & { vector: number[] })[]) =>
    request<{ collectionName: string; chunkCount: number }>("/api/eval/build", {
      method: "POST",
      body: JSON.stringify({ dtype, chunks }),
    }),
  evalSearch: (collectionName: string, vector: number[], text: string, topK = 10) =>
    request<{ hits: { id: string; docId: string }[]; dbMs: number }>("/api/eval/search", {
      method: "POST",
      body: JSON.stringify({ collectionName, vector, text, topK }),
    }),
  evalDrop: (name: string) => request<{ ok: boolean }>(`/api/eval/${name}`, { method: "DELETE" }),
  saveResults: (name: string, data: unknown) =>
    request<{ ok: boolean; path: string }>("/api/results", { method: "POST", body: JSON.stringify({ name, data }) }),
};
