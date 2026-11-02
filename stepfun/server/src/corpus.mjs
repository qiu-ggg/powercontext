import fs from "node:fs/promises";
import path from "node:path";
import { config } from "./config.mjs";
import { prepareDocuments } from "./chunk.mjs";

export async function loadCorpus() {
  const dir = path.join(config.corpusDir, "docs");
  const names = (await fs.readdir(dir)).filter((n) => /\.(md|txt)$/i.test(n)).sort();
  const docs = [];
  for (const name of names) {
    const content = await fs.readFile(path.join(dir, name), "utf8");
    docs.push({ name, content });
  }
  return docs;
}

export async function loadQueries() {
  const file = path.join(config.corpusDir, "eval", "queries.json");
  const raw = await fs.readFile(file, "utf8");
  return JSON.parse(raw);
}

export async function evalFixture() {
  const docs = prepareDocuments(await loadCorpus());
  const queries = await loadQueries();
  return {
    documents: docs,
    chunks: docs.flatMap((doc) =>
      doc.chunks.map((chunk) => ({
        id: chunk.id,
        text: chunk.text,
        metadata: chunk.metadata,
      })),
    ),
    queries: queries.map((q) => ({
      ...q,
      goldDocIds: q.gold
        .map((source) => docs.find((doc) => doc.source === source)?.docId)
        .filter(Boolean),
    })),
  };
}
