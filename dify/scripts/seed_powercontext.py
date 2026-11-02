#!/usr/bin/env python3
"""为某个玩家预置「旧账」，用于直接演示"老玩家进门就被翻账"。

用法：
  python seed_powercontext.py --player 铁柱 --preset medium
  python seed_powercontext.py --player 铁柱 --text "铁柱把盐当糖倒进了甜酒桶。（怒气 +4）"

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

PRESETS = {
    "light": [
        "{player}趁老周转身，往他的啤酒里加了辣椒水。（怒气 +2）",
    ],
    "medium": [
        "{player}往老周的啤酒里加了辣椒水，老周灌了半天凉水。（怒气 +3）",
        "{player}把假蟑螂塞进老周的杯垫底下，老周骂了一句。（怒气 +3）",
    ],
    "heavy": [
        "{player}往老周的啤酒里加了辣椒水。（怒气 +3）",
        "{player}把假蟑螂塞进老周的杯垫底下。（怒气 +3）",
        "{player}把盐罐和糖罐对调，整晚的甜酒都毁了。（怒气 +4）",
        "{player}偷偷把老周的招牌酒换成兑水的假酒。（怒气 +5）",
    ],
}


def ensure_scope(player: str) -> str:
    resp = requests.post(
        f"{BASE}/v1/scopes",
        json={
            "title": f"记仇酒馆::{player}",
            "summary": f"玩家 {player} 在记仇酒馆的恩怨账本",
            "idempotency_key": f"grudge-scope::{player}",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("scope_id") or data["scope"]["scope_id"]


def remember(scope_id: str, text: str) -> None:
    resp = requests.post(
        f"{BASE}/v1/memory/remember",
        json={
            "scope_id": scope_id,
            "kind": "grudge_event",
            "text": text,
            "reason": "玩家在记仇酒馆对老周实施恶作剧",
        },
        timeout=30,
    )
    resp.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--player", required=True)
    parser.add_argument("--preset", choices=sorted(PRESETS), default="medium")
    parser.add_argument("--text", action="append", default=[], help="自定义旧账，可重复")
    args = parser.parse_args()

    texts = args.text or [t.format(player=args.player) for t in PRESETS[args.preset]]
    scope_id = ensure_scope(args.player)
    print(f"scope_id={scope_id}")
    for text in texts:
        remember(scope_id, text)
        print(f"  + {text}")
    print(f"完成：{args.player} 现有 {len(texts)} 条预置旧账")
    return 0


if __name__ == "__main__":
    sys.exit(main())
