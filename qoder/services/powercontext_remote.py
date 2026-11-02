"""
PowerContext 远程客户端
通过 HTTP 连接真实的 PowerContext Server（API v1.4，实测版本 1.4.1）

与 services/powercontext_service.py 的本地兼容实现不同，本模块不发 SQL，
所有读写都由 PowerContext Server 完成：
  - Scope：POST /v1/scopes（以 user_id 派生的幂等键创建/复用）
  - 写入：POST /v1/memory/remember、POST /v1/memory/entries/revise
  - 读取：POST /v1/memory/entries/list
  - 搜索：POST /v1/memory/search（服务端 FTS 检索）
  - 删除：POST /v1/memory/entries/retire

本模块只依赖标准库，便于在离线/内网环境运行。
"""

import json
import time
import urllib.error
import urllib.request


class PowerContextRemoteError(RuntimeError):
    """远程 PowerContext 调用失败"""


class RemotePowerContextClient:
    """真实 PowerContext Server 的 HTTP 客户端"""

    def __init__(self, base_url, timeout=5.0):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._scope_cache = {}

    # ---------- 底层 HTTP ----------

    def _request(self, method, path, payload=None, timeout=None):
        url = f"{self.base_url}{path}"
        data = None
        headers = {'Accept': 'application/json'}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json; charset=utf-8'

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                body = resp.read().decode('utf-8')
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', errors='replace')[:500]
            err = PowerContextRemoteError(f"{method} {path} -> HTTP {e.code}: {detail}")
            err.status = e.code
            err.detail = detail
            raise err from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise PowerContextRemoteError(f"{method} {path} 连接失败: {e}") from None
        except json.JSONDecodeError as e:
            raise PowerContextRemoteError(f"{method} {path} 返回非 JSON: {e}") from None

    def available(self):
        """探测服务是否可用"""
        try:
            data = self._request('GET', '/v1/capabilities', timeout=2.0)
            return isinstance(data, dict) and bool(data)
        except PowerContextRemoteError:
            return False

    # ---------- Scope ----------

    def ensure_scope(self, user_id):
        """按 user_id 幂等创建/复用 Scope，返回真实 scope_id"""
        if user_id in self._scope_cache:
            return self._scope_cache[user_id]

        payload = {
            'title': f'Smart Knowledge Hub · {user_id}',
            'summary': 'Smart Knowledge Hub 学习与科研记忆作用域',
            'idempotency_key': f'smart-knowledge-hub:{user_id}',
        }
        data = self._request('POST', '/v1/scopes', payload)
        scope_id = data.get('scope_id')
        if not scope_id:
            raise PowerContextRemoteError(f'创建 Scope 未返回 scope_id: {data}')
        self._scope_cache[user_id] = scope_id
        return scope_id

    # ---------- Memory 读写 ----------

    def _list_entries(self, user_id, include_inactive=False):
        scope_id = self.ensure_scope(user_id)
        payload = {'scope_id': scope_id}
        if include_inactive:
            payload['include_inactive'] = True
        data = self._request('POST', '/v1/memory/entries/list', payload)
        return data.get('entries') or []

    @staticmethod
    def _pick_entry(entries, kind):
        matched = [e for e in entries if e.get('kind') == kind and e.get('state') == 'active']
        if not matched:
            return None
        # 同一 kind 若有多个活动条目，取版本最高的
        return max(matched, key=lambda e: e.get('version', 0))

    def _citation(self, entry):
        return entry['citation']

    def save(self, user_id, kind, text, reason=None):
        """按 kind 写入记忆；已存在则 revise，不存在则 remember"""
        scope_id = self.ensure_scope(user_id)
        entry = self._pick_entry(self._list_entries(user_id), kind)

        if entry:
            payload = {
                'scope_id': scope_id,
                'citation': self._citation(entry),
                'kind': kind,
                'text': text,
                'reason': reason,
            }
            try:
                return self._request('POST', '/v1/memory/entries/revise', payload)
            except PowerContextRemoteError as e:
                if getattr(e, 'status', None) != 409:
                    raise
                # 版本冲突：重新读取后再改一次
                entry = self._pick_entry(self._list_entries(user_id), kind)
                if not entry:
                    return self._remember(scope_id, kind, text, reason)
                payload['citation'] = self._citation(entry)
                return self._request('POST', '/v1/memory/entries/revise', payload)

        return self._remember(scope_id, kind, text, reason)

    def _remember(self, scope_id, kind, text, reason=None):
        payload = {
            'scope_id': scope_id,
            'kind': kind,
            'text': text,
            'reason': reason,
        }
        return self._request('POST', '/v1/memory/remember', payload)

    def load(self, user_id, kind):
        """按 kind 读取一条记忆，返回 (value, entry)"""
        entry = self._pick_entry(self._list_entries(user_id), kind)
        if not entry:
            return None, None
        return self._decode(entry.get('text', '')), entry

    def load_all(self, user_id):
        """读取全部活动记忆，返回 {kind: value}"""
        entries = self._list_entries(user_id)
        result = {}
        for kind in {e.get('kind') for e in entries if e.get('state') == 'active'}:
            entry = self._pick_entry(entries, kind)
            if entry:
                result[kind] = self._decode(entry.get('text', ''))
        return result

    def retire(self, user_id, kind, reason=None):
        scope_id = self.ensure_scope(user_id)
        entry = self._pick_entry(self._list_entries(user_id), kind)
        if not entry:
            return False
        self._request('POST', '/v1/memory/entries/retire', {
            'scope_id': scope_id,
            'citation': self._citation(entry),
            'reason': reason,
        })
        return True

    def search(self, user_id, query, limit=10):
        """调用真实 PowerContext 的 Memory 搜索（服务端 FTS/向量）"""
        scope_id = self.ensure_scope(user_id)
        data = self._request('POST', '/v1/memory/search', {
            'scope_id': scope_id,
            'query': query,
            'limit': max(1, min(limit, 50)),
        })

        # 搜索结果只带 citation，再用列表补上 kind
        kind_by_entry = {}
        for entry in self._list_entries(user_id):
            entry_id = (entry.get('citation') or {}).get('entry_id')
            if entry_id:
                kind_by_entry[entry_id] = entry.get('kind', '')

        results = []
        for hit in data.get('hits') or []:
            entry_id = (hit.get('citation') or {}).get('entry_id', '')
            text = hit.get('text', '')
            results.append({
                'artifact_id': kind_by_entry.get(entry_id) or entry_id,
                'kind': kind_by_entry.get(entry_id, 'memory'),
                'description': '',
                'content': self._decode(text),
                'score': hit.get('score', 0.0),
                'mode': data.get('mode', ''),
            })
        return results

    def recall(self, user_id, kind=None, limit=50):
        scope_id = self.ensure_scope(user_id)
        entries = self._list_entries(user_id)
        manifest = {'scope_id': scope_id, 'entries': [], 'total': 0, 'mode': 'remote'}

        for entry in entries:
            if entry.get('state') != 'active':
                continue
            if kind and entry.get('kind') != kind:
                continue
            manifest['entries'].append({
                'artifact_id': entry.get('kind', ''),
                'kind': entry.get('kind', ''),
                'description': '',
                'content': self._decode(entry.get('text', '')),
            })
            if len(manifest['entries']) >= limit:
                break

        manifest['total'] = len(manifest['entries'])
        return manifest

    # ---------- 工具 ----------

    @staticmethod
    def _decode(text):
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    @staticmethod
    def encode_value(value):
        """与本地实现一致：字符串原样存，其余存 JSON"""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def wait_ready(base_url, timeout=20.0):
        """等待服务就绪（供启动脚本使用）"""
        client = RemotePowerContextClient(base_url)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if client.available():
                return True
            time.sleep(0.5)
        return False
