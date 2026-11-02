#!/usr/bin/env python3
"""在 Dify 中创建「恶作剧图鉴」知识库并完成索引。

用法：
  export DIFY_BASE_URL=http://127.0.0.1:5001
  export DIFY_CONSOLE_EMAIL=you@example.com
  export DIFY_CONSOLE_PASSWORD=change-me
  python init_knowledge.py --file ../data/prank_compendium.md --name 记仇酒馆·恶作剧图鉴

可选：
  --embedding-model     默认 bge-m3:latest
  --embedding-provider  默认 langgenius/openai_api_compatible/openai_api_compatible
  --dataset-id          已有数据集则跳过创建，直接上传文档
  --separator           默认 ===ENTRY===
  --max-tokens          默认 500

依赖：pip install requests
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.environ.get("DIFY_BASE_URL", "http://127.0.0.1:5001")
EMAIL = os.environ.get("DIFY_CONSOLE_EMAIL", "")
PASSWORD = os.environ.get("DIFY_CONSOLE_PASSWORD", "")


def login(session: requests.Session) -> None:
    if not EMAIL or not PASSWORD:
        raise SystemExit("请先设置 DIFY_CONSOLE_EMAIL / DIFY_CONSOLE_PASSWORD")
    resp = session.post(
        f"{BASE}/console/api/login",
        json={
            "email": EMAIL,
            "password": base64.b64encode(PASSWORD.encode()).decode(),
            "remember_me": True,
            "language": "zh-Hans",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise SystemExit(f"登录失败 {resp.status_code}: {resp.text[:300]}")


def csrf_header(session: requests.Session) -> dict[str, str]:
    token = session.cookies.get("csrf_token")
    return {"X-CSRF-Token": token} if token else {}


def upload_file(session: requests.Session, path: Path) -> str:
    with path.open("rb") as fh:
        resp = session.post(
            f"{BASE}/console/api/files/upload",
            params={"source": "datasets"},
            files={"file": (path.name, fh, "text/markdown")},
            headers=csrf_header(session),
            timeout=60,
        )
    if resp.status_code not in (200, 201):
        raise SystemExit(f"上传失败 {resp.status_code}: {resp.text[:300]}")
    return resp.json()["id"]


def create_dataset(session: requests.Session, name: str, description: str) -> str:
    resp = session.post(
        f"{BASE}/console/api/datasets",
        json={
            "name": name,
            "description": description,
            "indexing_technique": "high_quality",
            "permission": "only_me",
            "provider": "vendor",
        },
        headers=csrf_header(session),
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise SystemExit(f"创建知识库失败 {resp.status_code}: {resp.text[:300]}")
    return resp.json()["id"]


def create_document(
    session: requests.Session,
    dataset_id: str,
    file_id: str,
    *,
    embedding_model: str,
    embedding_provider: str,
    separator: str,
    max_tokens: int,
) -> None:
    payload = {
        "indexing_technique": "high_quality",
        "data_source": {
            "info_list": {
                "data_source_type": "upload_file",
                "file_info_list": {"file_ids": [file_id]},
            }
        },
        "process_rule": {
            "mode": "custom",
            "rules": {
                "pre_processing_rules": [
                    {"id": "remove_extra_spaces", "enabled": True},
                    {"id": "remove_urls_emails", "enabled": False},
                ],
                "segmentation": {
                    "separator": separator,
                    "max_tokens": max_tokens,
                    "chunk_overlap": 0,
                },
            },
        },
        "doc_form": "text_model",
        "doc_language": "Chinese",
        "embedding_model": embedding_model,
        "embedding_model_provider": embedding_provider,
    }
    resp = session.post(
        f"{BASE}/console/api/datasets/{dataset_id}/documents",
        json=payload,
        headers=csrf_header(session),
        timeout=120,
    )
    if resp.status_code not in (200, 201):
        raise SystemExit(f"创建文档失败 {resp.status_code}: {resp.text[:500]}")


def wait_index(session: requests.Session, dataset_id: str, timeout: int = 600) -> list[dict]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = session.get(
            f"{BASE}/console/api/datasets/{dataset_id}/documents",
            params={"page": 1, "limit": 20},
            timeout=30,
        )
        docs = resp.json().get("data", [])
        if docs and all(d.get("indexing_status") == "completed" for d in docs):
            return docs
        statuses = [d.get("indexing_status") for d in docs]
        print(f"  索引中… {statuses}")
        time.sleep(5)
    raise SystemExit("索引超时，请到 Dify 后台查看分段状态")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="图鉴 markdown 路径")
    parser.add_argument("--name", default="记仇酒馆·恶作剧图鉴")
    parser.add_argument("--description", default="酒馆里流传的恶作剧招式、效果与老周的应对方式。")
    parser.add_argument("--dataset-id", default="")
    parser.add_argument("--embedding-model", default="bge-m3:latest")
    parser.add_argument(
        "--embedding-provider",
        default="langgenius/openai_api_compatible/openai_api_compatible",
    )
    parser.add_argument("--separator", default="===ENTRY===")
    parser.add_argument("--max-tokens", type=int, default=500)
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"文件不存在: {path}")

    session = requests.Session()
    print(f"登录 {BASE} …")
    login(session)

    print(f"上传 {path.name} …")
    file_id = upload_file(session, path)

    dataset_id = args.dataset_id
    if not dataset_id:
        print("创建知识库 …")
        dataset_id = create_dataset(session, args.name, args.description)
    else:
        print(f"复用知识库 {dataset_id}")

    print("创建文档并触发索引 …")
    create_document(
        session,
        dataset_id,
        file_id,
        embedding_model=args.embedding_model,
        embedding_provider=args.embedding_provider,
        separator=args.separator,
        max_tokens=args.max_tokens,
    )

    docs = wait_index(session, dataset_id)
    print("\n索引完成：")
    for doc in docs:
        print(f"  - {doc.get('name')}  segments={doc.get('segment_count')}  status={doc.get('indexing_status')}")
    print(f"\nDATASET_ID={dataset_id}")
    print("请把该 ID 填到 Chatflow「检索恶作剧图鉴」节点的知识库里，然后重新发布应用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
