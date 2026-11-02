#!/usr/bin/env python3
"""检查「记仇酒馆」依赖栈是否就绪；可选打印 seekdb / PowerContext 数据。

用法：
  python verify_stack.py
  python verify_stack.py --dump seekdb
  python verify_stack.py --dump player=铁柱

依赖：标准库；--dump seekdb 需要 pymysql。
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DIFY = os.environ.get("DIFY_BASE_URL", "http://127.0.0.1:5001")
PC = os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8000")
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
SEEKDB_HOST = os.environ.get("SEEKDB_HOST", "127.0.0.1")
SEEKDB_PORT = int(os.environ.get("SEEKDB_PORT", "2881"))
SEEKDB_USER = os.environ.get("SEEKDB_USER", "root")
SEEKDB_PASSWORD = os.environ.get("SEEKDB_PASSWORD", "")
SEEKDB_DATABASE = os.environ.get("SEEKDB_DATABASE", "test")


def get_json(url: str, timeout: float = 5.0):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, payload: dict, timeout: float = 15.0):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check(name: str, fn) -> bool:
    try:
        detail = fn()
    except Exception as exc:  # noqa: BLE001 - 诊断脚本需要展示任意异常
        print(f"[FAIL] {name}: {exc}")
        return False
    print(f"[ OK ] {name}: {detail}")
    return True


def check_dify():
    data = get_json(f"{DIFY}/console/api/setup")
    return f"setup_status={data.get('step') or data.get('status') or data}"


def check_powercontext():
    data = get_json(f"{PC}/health/ready")
    return f"status={data.get('status')}"


def check_ollama():
    data = get_json(f"{OLLAMA}/api/tags")
    names = sorted(m.get("name") for m in data.get("models", []))
    return f"models={names}"


def check_seekdb():
    try:
        import pymysql  # type: ignore
    except ImportError:
        with socket.create_connection((SEEKDB_HOST, SEEKDB_PORT), timeout=5):
            return f"tcp {SEEKDB_HOST}:{SEEKDB_PORT} reachable (install pymysql for detail)"
    conn = pymysql.connect(
        host=SEEKDB_HOST, port=SEEKDB_PORT, user=SEEKDB_USER,
        password=SEEKDB_PASSWORD, database=SEEKDB_DATABASE, charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            version = cur.fetchone()[0]
            cur.execute("SHOW TABLES")
            tables = [r[0] for r in cur.fetchall()]
        vector_tables = [t for t in tables if t.startswith("vector_index_")]
        return f"version={version} vector_tables={vector_tables}"
    finally:
        conn.close()


def dump_seekdb():
    import pymysql  # type: ignore

    conn = pymysql.connect(
        host=SEEKDB_HOST, port=SEEKDB_PORT, user=SEEKDB_USER,
        password=SEEKDB_PASSWORD, database=SEEKDB_DATABASE, charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = [r[0] for r in cur.fetchall()]
            for table in tables:
                if not table.startswith("vector_index_"):
                    continue
                cur.execute(f"SELECT COUNT(*) FROM `{table}`")
                print(f"{table}: {cur.fetchone()[0]} rows")
                cur.execute(f"SELECT id, LEFT(text, 50) FROM `{table}` ORDER BY id LIMIT 3")
                for row in cur.fetchall():
                    print("  ", row[0], "|", row[1].replace("\n", " "))
    finally:
        conn.close()


def dump_player(player: str):
    scope_id = ensure_scope(player)
    data = post_json(f"{PC}/v1/memory/entries/list", {"scope_id": scope_id})
    print(f"scope_id={scope_id}")
    for entry in data.get("entries", []):
        print(f"- [{entry.get('state')}] {entry.get('text')}")


def ensure_scope(player: str) -> str:
    data = post_json(
        f"{PC}/v1/scopes",
        {
            "title": f"记仇酒馆::{player}",
            "summary": f"玩家 {player} 在记仇酒馆的恩怨账本",
            "idempotency_key": f"grudge-scope::{player}",
        },
    )
    scope_id = data.get("scope_id") or (data.get("scope") or {}).get("scope_id")
    if not scope_id:
        raise RuntimeError(f"scope 创建失败: {data}")
    return scope_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", help="seekdb 或 player=<名字>")
    args = parser.parse_args()

    if args.dump == "seekdb":
        dump_seekdb()
        return 0
    if args.dump and args.dump.startswith("player="):
        dump_player(args.dump.split("=", 1)[1])
        return 0

    checks = [
        check("Dify API", check_dify),
        check("PowerContext", check_powercontext),
        check("Ollama", check_ollama),
        check("seekdb", check_seekdb),
    ]
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
