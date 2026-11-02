#!/usr/bin/env python3
"""通过 Dify Service API 连打若干轮，展示跨会话记忆与怒气升级。

用法：
  export DIFY_BASE_URL=http://127.0.0.1:5001
  export DIFY_APP_API_KEY=app-xxxxx
  python run_sample.py --player 铁柱 --rounds 3
  python run_sample.py --player 铁柱 --save-dir ../evidence/logs-run

依赖：pip install requests
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.environ.get("DIFY_BASE_URL", "http://127.0.0.1:5001")
APP_KEY = os.environ.get("DIFY_APP_API_KEY", "")

DEFAULT_QUERIES = [
    "趁老周转身，往他的啤酒里加大半瓶辣椒水",
    "把一只假蟑螂塞进老周的杯垫底下",
    "偷偷把老周的招牌酒换成兑水的假酒",
]

WANT_NODES = {"parse_scope", "parse_recall", "parse_llm"}


def run_once(query: str, player: str, user: str) -> dict:
    resp = requests.post(
        f"{BASE}/v1/chat-messages",
        headers={
            "Authorization": f"Bearer {APP_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "inputs": {"player_name": player},
            "query": query,
            "response_mode": "streaming",
            "user": user,
        },
        stream=True,
        timeout=180,
    )
    if resp.status_code != 200:
        raise SystemExit(f"请求失败 {resp.status_code}: {resp.text[:500]}")

    raw_lines: list[str] = []
    answer = ""
    nodes: dict[str, dict] = {}
    conversation_id = ""
    workflow_status = ""

    for line in resp.iter_lines(decode_unicode=True):
        if line is None:
            continue
        raw_lines.append(line)
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
            workflow_status = (event.get("data") or {}).get("status", "")

    return {
        "query": query,
        "answer": answer.strip(),
        "nodes": nodes,
        "conversation_id": conversation_id,
        "workflow_status": workflow_status,
        "raw": "\n".join(raw_lines),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--player", default="铁柱")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--user", default="verifier")
    parser.add_argument("--queries", help="用 | 分隔的自定义台词")
    parser.add_argument("--save-dir", help="保存每轮 SSE 原始日志的目录")
    parser.add_argument("--strict", action="store_true", help="校验怒气与旧账递增")
    args = parser.parse_args()

    if not APP_KEY:
        raise SystemExit("请先设置 DIFY_APP_API_KEY（应用「访问 API」里创建）")

    queries = args.queries.split("|") if args.queries else DEFAULT_QUERIES
    queries = (queries * ((args.rounds // len(queries)) + 1))[: args.rounds]

    if args.save_dir:
        Path(args.save_dir).mkdir(parents=True, exist_ok=True)

    history = []
    for index, query in enumerate(queries, start=1):
        print(f"\n===== 第 {index} 轮：{query}")
        result = run_once(query, args.player, args.user)
        recall = result["nodes"].get("parse_recall", {})
        verdict = result["nodes"].get("parse_llm", {})
        scope = result["nodes"].get("parse_scope", {})

        print(f"scope: {scope.get('scope_id')}  conversation: {result['conversation_id']}")
        print(
            f"召回 {recall.get('memory_count')} 笔 / 历史怒气 {recall.get('grudge_total')} / "
            f"本轮 +{verdict.get('delta')} → {verdict.get('new_total')}（{verdict.get('threat')}）"
        )
        print(result["answer"])

        if args.save_dir:
            (Path(args.save_dir) / f"session{index}.sse").write_text(result["raw"], encoding="utf-8")

        history.append(result)

    if args.strict and len(history) >= 2:
        problems = []
        for i in range(1, len(history)):
            prev = history[i - 1]["nodes"].get("parse_recall", {})
            curr = history[i]["nodes"].get("parse_recall", {})
            if int(curr.get("memory_count") or 0) <= int(prev.get("memory_count") or 0):
                problems.append(f"第 {i + 1} 轮旧账条数没有增加")
            if int(curr.get("grudge_total") or 0) <= int(prev.get("grudge_total") or 0):
                problems.append(f"第 {i + 1} 轮历史怒气没有增加")
        if problems:
            print("\n[FAIL] " + "；".join(problems))
            return 1
        print("\n[ OK ] 跨会话记忆与怒气累计均递增")
    return 0


if __name__ == "__main__":
    sys.exit(main())
