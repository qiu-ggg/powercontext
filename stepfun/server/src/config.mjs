import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

export const ROOT = path.resolve(here, "../..");

export const config = {
  port: Number(process.env.APP_PORT ?? 8787),
  db: {
    host: process.env.SEEKDB_HOST ?? "127.0.0.1",
    port: Number(process.env.SEEKDB_PORT ?? 2881),
    user: process.env.SEEKDB_USER ?? "root",
    password: process.env.SEEKDB_PASSWORD ?? "",
    database: process.env.SEEKDB_DATABASE ?? "test",
    queryTimeout: 120000,
  },
  modelId: process.env.EMBED_MODEL ?? "Xenova/bge-small-zh-v1.5",
  dim: 512,
  webDist: path.join(ROOT, "web", "dist"),
  modelsDir: path.join(ROOT, "web", "public", "models"),
  corpusDir: path.join(ROOT, "corpus"),
  resultsDir: path.join(ROOT, "results"),
};
