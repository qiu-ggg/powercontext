import crypto from "node:crypto";

const SENTENCE_END = /[。！？!?；;\n]/;

export function normalizeText(input) {
  return String(input ?? "")
    .replace(/\r\n?/g, "\n")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function splitUnits(text) {
  const units = [];
  let buf = "";
  for (const ch of text) {
    buf += ch;
    if (SENTENCE_END.test(ch)) {
      if (buf.trim()) units.push(buf.trim());
      buf = "";
    }
  }
  if (buf.trim()) units.push(buf.trim());
  return units;
}

export function chunkText(text, { target = 360, overlap = 60, max = 500 } = {}) {
  const clean = normalizeText(text);
  if (!clean) return [];

  const paragraphs = clean.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  const chunks = [];
  let current = "";

  const flush = () => {
    const body = current.trim();
    if (body.length < 12) {
      current = "";
      return;
    }
    chunks.push(body);
    const tail = body.slice(-overlap);
    const cut = Math.max(tail.lastIndexOf("。"), tail.lastIndexOf("；"), tail.lastIndexOf("\n"));
    current = cut > 10 ? tail.slice(cut + 1) : tail;
  };

  for (const paragraph of paragraphs) {
    for (const unit of splitUnits(paragraph)) {
      if (unit.length > max) {
        if (current.trim()) flush();
        for (let i = 0; i < unit.length; i += max - overlap) {
          chunks.push(unit.slice(i, i + max).trim());
        }
        current = "";
        continue;
      }
      if (current && current.length + unit.length + 1 > target) flush();
      current = current ? `${current} ${unit}` : unit;
      if (current.length >= max) flush();
    }
    if (current && current.length >= target * 0.75) flush();
  }
  if (current.trim().length >= 12) chunks.push(current.trim());

  return chunks.filter((c, index, all) => c.length >= 12 && all.indexOf(c) === index);
}

export function docIdFor(title, source) {
  return crypto.createHash("sha1").update(`${title}\u0000${source}`).digest("hex").slice(0, 16);
}

export function titleOf(name, content) {
  const heading = normalizeText(content).match(/^#{1,3}\s+(.+)$/m);
  if (heading) return heading[1].trim();
  return name.replace(/\.(md|markdown|txt)$/i, "");
}

export function prepareDocuments(documents) {
  return documents.map((doc) => {
    const title = doc.title || titleOf(doc.name || "未命名文档", doc.content);
    const source = doc.name || title;
    const docId = doc.docId || docIdFor(title, source);
    const parts = chunkText(doc.content);
    const chunks = parts.map((text, index) => ({
      id: `${docId}#c${index}`,
      text,
      metadata: {
        doc_id: docId,
        doc_title: title,
        chunk_index: index,
        source,
        char_count: text.length,
      },
    }));
    return {
      docId,
      title,
      source,
      charCount: normalizeText(doc.content).length,
      chunks,
    };
  });
}
