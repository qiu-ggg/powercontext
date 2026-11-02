const fs = require("fs");

const DATASET_ID = process.argv[2] || "08e2abca-e168-42ee-9cf1-85036e3066e9";
const OUT = process.argv[3] || "tmp/workflow.json";

const codePrep = `import re

def main(player_name: str, query: str) -> dict:
    def clean(s, limit):
        s = (s or "").replace('"', "'").replace("\\\\", "／").replace("\\n", " ").replace("\\r", " ")
        s = re.sub(r"\\s+", " ", s).strip()
        return s[:limit]
    player = clean(player_name, 24) or "无名客"
    action = clean(query, 200)
    return {
        "player": player,
        "action": action,
        "scope_title": clean("记仇酒馆::" + player, 200),
        "scope_summary": clean("玩家 " + player + " 在记仇酒馆的恩怨账本", 300),
        "idem_key": clean("grudge-scope::" + player, 200),
        "memory_query": clean(player + " 怒气", 40),
    }
`;

const codeParseScope = `import json

def main(body: str, status_code: int) -> dict:
    scope_id = ""
    try:
        data = json.loads(body)
        scope_id = data.get("scope_id") or ""
    except Exception:
        scope_id = ""
    return {
        "scope_id": str(scope_id),
        "scope_ok": "yes" if scope_id else "no",
        "scope_raw": str(body)[:300],
    }
`;

const codeParseRecall = `import json
import re

def main(body: str, status_code: int) -> dict:
    hits = []
    try:
        data = json.loads(body)
        hits = data.get("hits") or []
    except Exception:
        hits = []
    seen = set()
    lines = []
    total = 0
    for hit in hits:
        text = str(hit.get("text") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        match = re.search(r"怒气\\s*[+＋]\\s*(\\d+)", text)
        if match:
            total += int(match.group(1))
        lines.append("· " + text)
    if not lines:
        lines = ["（账本还是空的，老周暂时没把你放在眼里）"]
    return {
        "memory_count": len(seen),
        "grudge_total": total,
        "ledger": "\\n".join(lines[:6]),
        "recall_ok": "yes" if hits else "no",
    }
`;

const codeParseLlm = `import json
import re

def main(raw: str, player: str, action: str, grudge_total: int, knowledge: object) -> dict:
    text = raw or ""
    data = None
    for candidate in re.findall(r"\\{.*\\}", text, re.S):
        try:
            data = json.loads(candidate)
            break
        except Exception:
            continue
    reply = ""
    verdict = "记仇"
    delta = 2
    memory = ""
    if isinstance(data, dict):
        reply = str(data.get("reply") or "").strip()
        verdict = str(data.get("verdict") or "记仇").strip()
        try:
            delta = int(data.get("grudge_delta", 2))
        except Exception:
            delta = 2
        memory = str(data.get("memory") or "").strip()
    if not reply:
        reply = re.sub(r"\\{.*\\}", "", text, flags=re.S).strip() or "老周没说话，只是把抹布拧得更紧了。"
    delta = max(0, min(5, delta))

    def clean(s, limit):
        s = (s or "").replace('"', "'").replace("\\\\", "／").replace("\\n", " ").replace("\\r", " ").strip()
        return s[:limit]

    reply = clean(reply, 160)
    verdict = clean(verdict, 12)
    if not memory:
        memory = "玩家【" + player + "】对老周做了：" + action + "。老周的反应：" + reply + "。怒气+" + str(delta) + "。"
    if "怒气" not in memory:
        memory = memory + "（怒气 +" + str(delta) + "）"
    memory = clean(memory, 700)
    titles = []
    seen_titles = set()
    if isinstance(knowledge, list):
        for item in knowledge[:3]:
            if isinstance(item, dict):
                meta = item.get("metadata") or {}
                title = meta.get("title") or item.get("title")
                if title and str(title) not in seen_titles:
                    seen_titles.add(str(title))
                    titles.append(str(title))
    kb = "、".join(titles) if titles else "未命中图鉴"
    total = max(0, int(grudge_total or 0)) + delta
    if total >= 15:
        threat = "通缉令"
    elif total >= 8:
        threat = "擀面杖"
    elif total >= 4:
        threat = "冷脸"
    else:
        threat = "装没事"
    return {
        "reply": reply,
        "verdict": verdict,
        "delta": delta,
        "new_total": total,
        "threat": threat,
        "memory_text": memory,
        "kb_titles": clean(kb, 120),
    }
`;

const strOutput = (names) =>
  Object.fromEntries(names.map((n) => [n, { children: null, type: "string" }]));
const numOutput = (names) =>
  Object.fromEntries(names.map((n) => [n, { children: null, type: "number" }]));

const httpBody = (value) => ({
  type: "json",
  data: [{ key: "", type: "text", value }],
});

const httpData = (title, url, body) => ({
  desc: "",
  title,
  type: "http-request",
  method: "post",
  url,
  authorization: { type: "no-auth" },
  headers: "",
  params: "",
  body: httpBody(body),
  timeout: { connect: 15, read: 60, write: 30 },
  retry_config: {
    enabled: false,
    max_retries: 1,
    retry_interval: 1000,
    exponential_backoff: { enabled: false, multiplier: 2, max_interval: 10000 },
  },
});

const nodes = [
  {
    id: "start",
    type: "custom",
    position: { x: 40, y: 320 },
    sourcePosition: "right",
    targetPosition: "left",
    data: {
      title: "开始",
      type: "start",
      desc: "",
      variables: [
        {
          variable: "player_name",
          label: "你的名字",
          type: "text-input",
          required: true,
          max_length: 24,
          options: [],
        },
      ],
    },
  },
  {
    id: "prep",
    type: "custom",
    position: { x: 300, y: 320 },
    sourcePosition: "right",
    targetPosition: "left",
    data: {
      title: "预处理输入",
      type: "code",
      desc: "清洗玩家输入，生成 JSON 安全的请求字段",
      code_language: "python3",
      code: codePrep,
      variables: [
        { variable: "player_name", value_selector: ["start", "player_name"], value_type: "string" },
        { variable: "query", value_selector: ["sys", "query"], value_type: "string" },
      ],
      outputs: strOutput(["player", "action", "scope_title", "scope_summary", "idem_key", "memory_query"]),
    },
  },
  {
    id: "scope",
    type: "custom",
    position: { x: 560, y: 320 },
    sourcePosition: "right",
    targetPosition: "left",
    data: httpData(
      "创建/复用玩家账本",
      "http://127.0.0.1:8000/v1/scopes",
      '{"title":"{{#prep.scope_title#}}","summary":"{{#prep.scope_summary#}}","idempotency_key":"{{#prep.idem_key#}}"}'
    ),
  },
  {
    id: "parse_scope",
    type: "custom",
    position: { x: 820, y: 320 },
    sourcePosition: "right",
    targetPosition: "left",
    data: {
      title: "解析账本 ID",
      type: "code",
      desc: "从 PowerContext 响应中取出 scope_id",
      code_language: "python3",
      code: codeParseScope,
      variables: [
        { variable: "body", value_selector: ["scope", "body"], value_type: "string" },
        { variable: "status_code", value_selector: ["scope", "status_code"], value_type: "number" },
      ],
      outputs: strOutput(["scope_id", "scope_ok", "scope_raw"]),
    },
  },
  {
    id: "recall",
    type: "custom",
    position: { x: 1080, y: 320 },
    sourcePosition: "right",
    targetPosition: "left",
    data: httpData(
      "召回旧账",
      "http://127.0.0.1:8000/v1/memory/search",
      '{"scope_id":"{{#parse_scope.scope_id#}}","query":"{{#prep.memory_query#}}","limit":50,"mode":"auto"}'
    ),
  },
  {
    id: "parse_recall",
    type: "custom",
    position: { x: 1340, y: 320 },
    sourcePosition: "right",
    targetPosition: "left",
    data: {
      title: "整理旧账",
      type: "code",
      desc: "汇总历史恶作剧与累计怒气",
      code_language: "python3",
      code: codeParseRecall,
      variables: [
        { variable: "body", value_selector: ["recall", "body"], value_type: "string" },
        { variable: "status_code", value_selector: ["recall", "status_code"], value_type: "number" },
      ],
      outputs: {
        ...numOutput(["memory_count", "grudge_total"]),
        ...strOutput(["ledger", "recall_ok"]),
      },
    },
  },
  {
    id: "kb",
    type: "custom",
    position: { x: 1600, y: 320 },
    sourcePosition: "right",
    targetPosition: "left",
    data: {
      title: "检索恶作剧图鉴",
      type: "knowledge-retrieval",
      desc: "从 seekdb 向量库检索对应招式",
      query_variable_selector: ["prep", "action"],
      dataset_ids: [DATASET_ID],
      retrieval_mode: "multiple",
      multiple_retrieval_config: {
        top_k: 3,
        score_threshold: null,
        score_threshold_enabled: false,
        reranking_enable: false,
        reranking_model: { reranking_provider_name: "", reranking_model_name: "" },
      },
    },
  },
  {
    id: "llm",
    type: "custom",
    position: { x: 1860, y: 320 },
    sourcePosition: "right",
    targetPosition: "left",
    data: {
      title: "老周开口",
      type: "llm",
      desc: "结合旧账与图鉴扮演老周，输出结构化判定",
      model: {
        provider: "langgenius/openai_api_compatible/openai_api_compatible",
        name: "qwen2.5:7b",
        mode: "chat",
        completion_params: { temperature: 0.6, max_tokens: 700 },
      },
      prompt_template: [
        {
          role: "system",
          text: `你是"老周"，城南"记仇酒馆"的老板，五十多岁，嘴硬心软，记性极好。玩家会在酒馆里对你搞恶作剧。你要根据【旧账】和【恶作剧图鉴】做出反应。

规则：
1. 如果【旧账】里有玩家以前干过的事，必须明确提起（"上次你……"），语气要像真的记仇。
2. 累计怒气越高，态度越差；达到 8 时你会主动报复（比如往酒里加料、拿出擀面杖）；达到 15 时你会下"通缉令"。
3. 回复用中文口语，80 字以内，有画面感，不要解释规则。
4. 玩家如果道歉并请客，可以和解（grudge_delta 记 0）。
5. 只输出一个 JSON 对象，不要 Markdown 代码块，不要多余文字：
{"reply":"老周的台词","verdict":"记仇|暴怒|和解|无感","grudge_delta":0,"memory":"第三人称总结：玩家做了什么、老周怎么反应、怒气+几"}
grudge_delta 取 0-5 的整数，恶作剧越过分越高。

【玩家】{{#prep.player#}}
【旧账】{{#parse_recall.ledger#}}
【累计怒气】{{#parse_recall.grudge_total#}}
【恶作剧图鉴】
{{#context#}}`,
        },
        { role: "user", text: "{{#sys.query#}}" },
      ],
      context: { enabled: true, variable_selector: ["kb", "result"] },
      memory: {
        window: { enabled: false, size: 10 },
        query_prompt_template: "{{#sys.query#}}",
      },
      vision: { enabled: false },
      variables: [],
    },
  },
  {
    id: "parse_llm",
    type: "custom",
    position: { x: 2120, y: 320 },
    sourcePosition: "right",
    targetPosition: "left",
    data: {
      title: "解析老周的反应",
      type: "code",
      desc: "解析 JSON，计算怒气与升级状态",
      code_language: "python3",
      code: codeParseLlm,
      variables: [
        { variable: "raw", value_selector: ["llm", "text"], value_type: "string" },
        { variable: "player", value_selector: ["prep", "player"], value_type: "string" },
        { variable: "action", value_selector: ["prep", "action"], value_type: "string" },
        { variable: "grudge_total", value_selector: ["parse_recall", "grudge_total"], value_type: "number" },
        { variable: "knowledge", value_selector: ["kb", "result"], value_type: "array[object]" },
      ],
      outputs: {
        ...numOutput(["delta", "new_total"]),
        ...strOutput(["reply", "verdict", "threat", "memory_text", "kb_titles"]),
      },
    },
  },
  {
    id: "remember",
    type: "custom",
    position: { x: 2380, y: 320 },
    sourcePosition: "right",
    targetPosition: "left",
    data: httpData(
      "写入长期记忆",
      "http://127.0.0.1:8000/v1/memory/remember",
      '{"scope_id":"{{#parse_scope.scope_id#}}","kind":"grudge_event","text":"{{#parse_llm.memory_text#}}","reason":"玩家在记仇酒馆对老周实施恶作剧"}'
    ),
  },
  {
    id: "answer",
    type: "custom",
    position: { x: 2640, y: 320 },
    sourcePosition: "right",
    targetPosition: "left",
    data: {
      title: "酒馆现场",
      type: "answer",
      desc: "",
      answer: `🍺 老周把抹布往肩上一搭：

{{#parse_llm.reply#}}

─────
😤 怒气值：{{#parse_llm.new_total#}}/100（本次 +{{#parse_llm.delta#}}）
🏷️ 判定：{{#parse_llm.verdict#}}｜老周状态：{{#parse_llm.threat#}}
🧠 PowerContext 翻出旧账：{{#parse_recall.memory_count#}} 笔
📖 seekdb 图鉴：{{#parse_llm.kb_titles#}}

📜 旧账摘录
{{#parse_recall.ledger#}}`,
      variables: [],
    },
  },
];

const chain = ["start", "prep", "scope", "parse_scope", "recall", "parse_recall", "kb", "llm", "parse_llm", "remember", "answer"];
const edges = [];
for (let i = 0; i < chain.length - 1; i++) {
  edges.push({
    id: `${chain[i]}-source-${chain[i + 1]}-target`,
    source: chain[i],
    sourceHandle: "source",
    target: chain[i + 1],
    targetHandle: "target",
    type: "custom",
    data: { isInIteration: false, isInLoop: false, sourceType: nodes[i].data.type, targetType: nodes[i + 1].data.type },
    zIndex: 0,
  });
}

const payload = {
  graph: { nodes, edges, viewport: { x: 0, y: 0, zoom: 0.7 } },
  features: {
    file_upload: { enabled: false },
    opening_statement: "欢迎来到记仇酒馆。报上名字，然后告诉老周你想干什么——小心，他什么都记得。",
    retriever_resource: { enabled: true },
    sensitive_word_avoidance: { enabled: false },
    speech_to_text: { enabled: false },
    suggested_questions: ["把他的啤酒换成辣椒水", "往他杯垫下放一只假蟑螂", "上次的事是我不对，这轮我请"],
    suggested_questions_after_answer: { enabled: false },
    text_to_speech: { enabled: false, language: "", voice: "" },
  },
  conversation_variables: [],
};

fs.writeFileSync(OUT, JSON.stringify(payload, null, 2), "utf8");
console.log(`written ${OUT}, nodes=${nodes.length}`);
