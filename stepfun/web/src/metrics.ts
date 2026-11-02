export interface RankingScore {
  recall: number;
  ndcg: number;
  mrr: number;
  firstHitRank: number | null;
}

export function evaluateRanking(rankedDocIds: string[], goldDocIds: string[], k = 5): RankingScore {
  const gold = new Set(goldDocIds);
  const top = rankedDocIds.slice(0, k);
  const hits = top.filter((id) => gold.has(id));
  const recall = gold.size === 0 ? 0 : hits.length / gold.size;

  let dcg = 0;
  top.forEach((id, index) => {
    if (gold.has(id)) dcg += 1 / Math.log2(index + 2);
  });
  let idcg = 0;
  for (let index = 0; index < Math.min(gold.size, k); index += 1) {
    idcg += 1 / Math.log2(index + 2);
  }
  const ndcg = idcg === 0 ? 0 : dcg / idcg;

  const firstIndex = rankedDocIds.findIndex((id) => gold.has(id));
  const mrr = firstIndex >= 0 ? 1 / (firstIndex + 1) : 0;
  return { recall, ndcg, mrr, firstHitRank: firstIndex >= 0 ? firstIndex + 1 : null };
}

export function uniqueDocIds(docIds: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const id of docIds) {
    if (!id || seen.has(id)) continue;
    seen.add(id);
    result.push(id);
  }
  return result;
}

export function mean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle];
}

export function formatMs(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "—";
  if (ms < 1) return `${(ms * 1000).toFixed(0)} µs`;
  if (ms < 1000) return `${ms.toFixed(1)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export function formatPct(value: number, digits = 1): string {
  if (!Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}
