#!/usr/bin/env python3
"""退役某个玩家的全部旧账（保留历史版本，检索不再命中）。

用法：
  python reset_demo.py --player 铁柱
  python reset_demo.py --player 铁柱 --yes     # 跳过确认

依赖：pip install requests
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8000")


def find_scope(player: str) -> str:
    resp = requests.get(
        f"{BASE}/v1/scopes",
        params={"query": player, "query_field": "title"},
        timeout=30,
    )
    resp.raise_for_status()
    scopes = resp.json().get("items") or resp.json().get("scopes") or []
    for scope in scopes:
        if scope.get("title") == f"记仇酒馆::{player}":
            return scope["scope_id"]
    raise SystemExit(f"未找到玩家 {player} 的 scope（用户名是否写错？）")


def list_entries(scope_id: str) -> list[dict]:
    resp = requests.post(
        f"{BASE}/v1/memory/entries/list",
        json={"scope_id": scope_id},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("entries", [])


def retire(scope_id: str, entry: dict) -> None:
    resp = requests.post(
        f"{BASE}/v1/memory/entries/retire",
        json={
            "scope_id": scope_id,
            "citation": entry["citation"],
            "reason": "demo reset",
        },
        timeout=30,
    )
    resp.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--player", required=True)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    scope_id = find_scope(args.player)
    entries = list_entries(scope_id)
    if not entries:
        print(f"{args.player} 的账本已经是空的")
        return 0

    print(f"scope_id={scope_id}，共 {len(entries)} 条：")
    for entry in entries:
        print(f"  - {entry.get('text')}")

    if not args.yes:
        answer = input("确认全部退役？[y/N] ").strip().lower()
        if answer != "y":
            print("已取消")
            return 1

    for entry in entries:
        retire(scope_id, entry)
    print(f"已退役 {len(entries)} 条，{args.player} 的账本已清空")
    return 0


if __name__ == "__main__":
    sys.exit(main())
