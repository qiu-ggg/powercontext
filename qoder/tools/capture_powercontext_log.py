"""
抓取真实 PowerContext Server 的原始请求/响应日志

用途：为提交材料提供可复核的 HTTP 调用记录，而不是只有页面截图。
运行前先启动 PowerContext Server（见 RUNNING.md 第 3 节），然后：

    python tools/capture_powercontext_log.py

日志默认写入 docs/logs/powercontext-calls-<日期>.log。
脚本只使用标准库，不依赖应用的本地实现。
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE_URL = os.getenv('POWERCONTEXT_BASE_URL', 'http://127.0.0.1:8000')
USER_KEY = 'smart-knowledge-hub:evidence-20261103'
PROBE_KIND = 'verification_probe'

LOG_LINES = []


def record(title, method, path, payload, status, body):
    LOG_LINES.append(f'\n===== {title} =====')
    LOG_LINES.append(f'[{datetime.now(timezone.utc).isoformat()}] {method} {BASE_URL}{path}')
    if payload is not None:
        LOG_LINES.append('--- request ---')
        LOG_LINES.append(json.dumps(payload, ensure_ascii=False, indent=2))
    LOG_LINES.append(f'--- response (HTTP {status}) ---')
    LOG_LINES.append(body)


def call(title, method, path, payload=None, timeout=10):
    url = f'{BASE_URL}{path}'
    data = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json; charset=utf-8'

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        status = exc.code

    try:
        parsed = json.loads(raw)
        pretty = json.dumps(parsed, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        parsed = None
        pretty = raw

    record(title, method, path, payload, status, pretty)
    if status >= 400:
        raise SystemExit(f'{method} {path} -> HTTP {status}')
    return parsed if parsed is not None else raw


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'docs', 'logs', f'powercontext-calls-{datetime.now().strftime("%Y-%m-%d")}.log',
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # 0. 健康检查（返回纯文本）
    req = urllib.request.Request(f'{BASE_URL}/health/ready')
    with urllib.request.urlopen(req, timeout=5) as resp:
        ready = resp.read().decode('utf-8', errors='replace')
    record('health/ready', 'GET', '/health/ready', None, resp.status, ready)

    # 1. 能力信息（只保留版本相关字段，避免日志过长）
    caps = call('capabilities', 'GET', '/v1/capabilities')
    summary = {
        'service': caps.get('service') if isinstance(caps, dict) else None,
        'version': caps.get('version') if isinstance(caps, dict) else None,
        'api_version': caps.get('api_version') if isinstance(caps, dict) else None,
        'memory_search': (caps.get('memory') or {}).get('search') if isinstance(caps, dict) else None,
    }
    LOG_LINES.append('--- capabilities 摘要 ---')
    LOG_LINES.append(json.dumps(summary, ensure_ascii=False, indent=2))

    # 2. 幂等 Scope
    scope = call('create scope (idempotency_key)', 'POST', '/v1/scopes', {
        'title': 'Smart Knowledge Hub · 证据抓取',
        'summary': '用于提交材料的真实 PowerContext 调用记录',
        'idempotency_key': USER_KEY,
    })
    scope_id = scope['scope_id']

    # 3. 初始条目
    call('list entries (before)', 'POST', '/v1/memory/entries/list', {'scope_id': scope_id})

    # 4. 写入探针记忆
    text = json.dumps({
        'note': 'PowerContext 原始调用验证',
        'at': datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False)
    created = call('remember probe', 'POST', '/v1/memory/remember', {
        'scope_id': scope_id,
        'kind': PROBE_KIND,
        'text': text,
        'reason': 'capture raw call log for submission',
    })

    # 5. FTS 搜索
    call('memory search', 'POST', '/v1/memory/search', {
        'scope_id': scope_id,
        'query': '原始调用验证',
        'limit': 5,
    })

    # 6. 上下文准备
    call('context prepare', 'POST', '/v1/context/prepare', {
        'scope_id': scope_id,
        'query': 'PowerContext 原始调用验证',
        'max_bytes': 2000,
    })

    # 7. 停用探针，保持作用域干净
    entry = None
    for candidate in created.get('entry', {}), created:
        if isinstance(candidate, dict) and candidate.get('citation'):
            entry = candidate
            break
    if entry:
        call('retire probe', 'POST', '/v1/memory/entries/retire', {
            'scope_id': scope_id,
            'citation': entry['citation'],
            'reason': 'cleanup after evidence capture',
        })

    call('list entries (after)', 'POST', '/v1/memory/entries/list', {'scope_id': scope_id})

    LOG_LINES.insert(0, '\n'.join([
        'PowerContext 原始调用日志',
        f'生成时间（UTC）：{datetime.now(timezone.utc).isoformat()}',
        f'服务地址：{BASE_URL}',
        '说明：以下为脚本直接发出的 HTTP 请求与服务端原始响应，未经应用层改写。',
    ]))

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(LOG_LINES) + '\n')
    print(f'written: {out_path}')
    print(f'scope_id: {scope_id}')


if __name__ == '__main__':
    main()
