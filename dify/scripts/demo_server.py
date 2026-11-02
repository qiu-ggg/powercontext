#!/usr/bin/env python3
"""记仇酒馆本地试玩入口。

一个零依赖的 Web 界面：把浏览器里的输入转发到 Dify Service API，
并把 parse_scope / parse_recall / parse_llm 的输出显示成「老周账本」。

用法：
  export DIFY_APP_API_KEY=app-xxxxx
  python scripts/demo_server.py
  # 打开 http://127.0.0.1:8195
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DIFY = os.environ.get("DIFY_BASE_URL", "http://127.0.0.1:5001")
APP_KEY = os.environ.get("DIFY_APP_API_KEY", "")
PORT = int(os.environ.get("DEMO_PORT", "8195"))
WANT_NODES = {"parse_scope", "parse_recall", "parse_llm"}


def ask_dify(player: str, query: str, user: str) -> dict:
    payload = json.dumps(
        {
            "inputs": {"player_name": player},
            "query": query,
            "response_mode": "streaming",
            "user": user,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        DIFY + "/v1/chat-messages",
        data=payload,
        headers={
            "Authorization": "Bearer " + APP_KEY,
            "Content-Type": "application/json",
        },
    )
    answer = ""
    nodes: dict[str, dict] = {}
    conversation_id = ""
    status = ""
    with urllib.request.urlopen(request, timeout=180) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            kind = event.get("event")
            if kind == "message":
                answer += event.get("answer") or ""
            elif kind == "node_finished":
                data = event.get("data") or {}
                if data.get("node_id") in WANT_NODES:
                    nodes[data["node_id"]] = data.get("outputs") or {}
            elif kind == "message_end":
                conversation_id = event.get("conversation_id") or ""
            elif kind == "workflow_finished":
                status = (event.get("data") or {}).get("status", "")

    scope = nodes.get("parse_scope", {})
    recall = nodes.get("parse_recall", {})
    verdict = nodes.get("parse_llm", {})
    return {
        "answer": answer.strip(),
        "conversation_id": conversation_id,
        "workflow_status": status,
        "scope_id": scope.get("scope_id", ""),
        "memory_count": recall.get("memory_count", 0),
        "grudge_total": recall.get("grudge_total", 0),
        "ledger": recall.get("ledger", ""),
        "delta": verdict.get("delta", 0),
        "new_total": verdict.get("new_total", 0),
        "threat": verdict.get("threat", ""),
        "kb_titles": verdict.get("kb_titles", ""),
    }


PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>记仇酒馆 · Grudge Tavern</title>
<style>
  :root{--bg:#120f0c;--panel:#1d1813;--line:#3a2f24;--amber:#e8a33d;--amber2:#ffd28a;--text:#f2e8d8;--muted:#a89680;--red:#d9534f}
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;background:radial-gradient(1200px 600px at 70% -10%,#3a2612 0%,transparent 60%),var(--bg);color:var(--text);font-family:"Noto Serif SC","Songti SC",Georgia,serif}
  .wrap{max-width:1120px;margin:0 auto;padding:28px 20px 48px;display:grid;grid-template-columns:1fr 340px;gap:20px}
  header{grid-column:1/-1;display:flex;align-items:flex-end;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:14px}
  h1{margin:0;font-size:30px;letter-spacing:4px;color:var(--amber2)}
  header p{margin:6px 0 0;color:var(--muted);font-size:13px}
  .badge{font-size:12px;color:var(--amber);border:1px solid var(--line);padding:6px 10px;border-radius:999px;background:#00000030}
  .chat{background:linear-gradient(180deg,#1c1712,#17130f);border:1px solid var(--line);border-radius:14px;display:flex;flex-direction:column;min-height:600px;box-shadow:0 18px 50px #0008}
  .log{flex:1;padding:20px;overflow-y:auto;max-height:560px}
  .msg{max-width:86%;margin:0 0 14px;padding:12px 14px;border-radius:12px;line-height:1.7;font-size:15px;white-space:pre-wrap;word-break:break-word}
  .me{margin-left:auto;background:#2a2118;border:1px solid #4a3a28;color:#f0dfc4}
  .zhou{background:#161b16;border:1px solid #2c3a2c;color:#e8f0e2}
  .hint{color:var(--muted);font-size:12px;margin-top:4px}
  form{display:flex;gap:10px;padding:14px;border-top:1px solid var(--line);background:#15110d;border-radius:0 0 14px 14px}
  input{flex:1;background:#0f0c09;border:1px solid #3d3022;color:var(--text);border-radius:9px;padding:12px 13px;font-size:15px;font-family:inherit}
  input:focus{outline:none;border-color:var(--amber)}
  button{background:linear-gradient(180deg,var(--amber),#b8731f);color:#1a1208;border:0;border-radius:9px;padding:0 20px;font-size:15px;font-weight:700;cursor:pointer;font-family:inherit}
  button:disabled{opacity:.5;cursor:wait}
  .chips{display:flex;flex-wrap:wrap;gap:8px;padding:0 14px 12px}
  .chip{font-size:12px;color:#d9c4a3;background:#211a13;border:1px solid #3d3022;border-radius:999px;padding:6px 10px;cursor:pointer}
  aside{display:flex;flex-direction:column;gap:14px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
  .card h2{margin:0 0 10px;font-size:13px;letter-spacing:2px;color:var(--amber);font-weight:600}
  .anger{height:10px;border-radius:999px;background:#0e0b08;border:1px solid #34291d;overflow:hidden;margin:8px 0 6px}
  .anger i{display:block;height:100%;width:0;background:linear-gradient(90deg,#7a5a2a,#e8a33d,#d9534f);transition:width .5s}
  .row{display:flex;justify-content:space-between;font-size:13px;color:var(--muted);margin:6px 0}
  .row b{color:var(--text);font-weight:600}
  .ledger{font-size:12px;color:#cdbda6;line-height:1.7;max-height:260px;overflow-y:auto;white-space:pre-wrap}
  .name{display:flex;gap:8px}
  .name input{width:100%}
  .status{font-size:12px;color:var(--muted);padding:0 14px 10px}
  .err{color:#ff9a94}
  @media(max-width:860px){.wrap{grid-template-columns:1fr}.log{max-height:420px}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div><h1>记仇酒馆</h1><p>老周什么都记得。每一笔旧账，都在 PowerContext 里；每一招恶作剧，都在 seekdb 图鉴里。</p></div>
    <div class="badge">Dify Chatflow × PowerContext × seekdb</div>
  </header>

  <section class="chat">
    <div class="log" id="log">
      <div class="msg zhou">🍺 老周把抹布往肩上一搭：<br>又是你？报上名来，今天想干什么。</div>
    </div>
    <div class="chips" id="chips">
      <span class="chip">往他啤酒里加辣椒水</span>
      <span class="chip">往杯垫下塞假蟑螂</span>
      <span class="chip">把他的招牌酒换成假酒</span>
      <span class="chip">上次是我不对，这轮我请</span>
    </div>
    <form id="form">
      <input id="text" maxlength="200" placeholder="对老周说点什么，或者直接搞个恶作剧…" autocomplete="off">
      <button id="send" type="submit">说</button>
    </form>
  </section>

  <aside>
    <div class="card">
      <h2>玩家</h2>
      <div class="name"><input id="player" value="阿福" maxlength="24" placeholder="报上名来"></div>
      <div class="hint">换个名字就是新账本；同名再进门，老周会翻旧账。</div>
    </div>
    <div class="card">
      <h2>老周账本</h2>
      <div class="row"><span>怒气</span><b><span id="angerNum">0</span>/100 · <span id="threat">装没事</span></b></div>
      <div class="anger"><i id="angerBar"></i></div>
      <div class="row"><span>翻出旧账</span><b><span id="memoryCount">0</span> 笔</b></div>
      <div class="row"><span>图鉴命中</span><b id="kb">—</b></div>
      <div class="row"><span>本会话</span><b id="conv">未开始</b></div>
      <div class="status" id="status"></div>
    </div>
    <div class="card">
      <h2>旧账摘录</h2>
      <div class="ledger" id="ledger">（账本还是空的）</div>
    </div>
  </aside>
</div>
<script>
const log = document.getElementById('log');
const form = document.getElementById('form');
const input = document.getElementById('text');
const send = document.getElementById('send');
const statusEl = document.getElementById('status');
let busy = false;

function bubble(text, who) {
  const div = document.createElement('div');
  div.className = 'msg ' + who;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function labelThreat(v) {
  return v || '装没事';
}

async function sendMessage(text) {
  if (busy || !text.trim()) return;
  const player = document.getElementById('player').value.trim() || '无名客';
  busy = true; send.disabled = true;
  bubble(text, 'me');
  const pending = bubble('老周正在翻账本…', 'zhou');
  statusEl.textContent = '';
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({player, query: text})
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || ('HTTP ' + resp.status));
    pending.textContent = data.answer || '老周没说话。';
    document.getElementById('angerNum').textContent = data.new_total;
    document.getElementById('angerBar').style.width = Math.min(100, data.new_total) + '%';
    document.getElementById('threat').textContent = labelThreat(data.threat);
    document.getElementById('memoryCount').textContent = data.memory_count;
    document.getElementById('kb').textContent = data.kb_titles || '未命中';
    document.getElementById('conv').textContent = (data.conversation_id || '').slice(0, 8) || '—';
    document.getElementById('ledger').textContent = data.ledger || '（账本还是空的）';
    statusEl.textContent = '本轮 +' + data.delta + ' · 工作流 ' + (data.workflow_status || '—');
  } catch (err) {
    pending.textContent = '老周把抹布一摔：店里出错了。' + err.message;
    pending.classList.add('err');
  } finally {
    busy = false; send.disabled = false; input.focus();
  }
}

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = input.value;
  input.value = '';
  sendMessage(text);
});
document.querySelectorAll('.chip').forEach((chip) => {
  chip.addEventListener('click', () => sendMessage(chip.textContent));
});
input.focus();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/healthz":
            self._send(200, b'{"ok":true}', "application/json")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, b'{"error":"bad json"}', "application/json")
            return
        player = str(data.get("player") or "无名客")[:24]
        query = str(data.get("query") or "").strip()[:200]
        if not query:
            self._send(400, json.dumps({"error": "说点什么吧"}).encode("utf-8"), "application/json; charset=utf-8")
            return
        try:
            result = ask_dify(player, query, "demo-" + player)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            self._send(502, json.dumps({"error": "Dify %s: %s" % (exc.code, body)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        except Exception as exc:  # noqa: BLE001
            self._send(502, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self._send(200, body, "application/json; charset=utf-8")

    def log_message(self, fmt: str, *args) -> None:
        print("[demo] " + (fmt % args))


def main() -> int:
    if not APP_KEY:
        print("请先设置 DIFY_APP_API_KEY（Dify 应用「访问 API」里创建）")
        return 1
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("记仇酒馆试玩入口：http://127.0.0.1:%d" % PORT)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
