"""
PowerContext 远程客户端
通过 HTTP 连接真实的 PowerContext Server（API v1.4，实测版本 1.4.1）

与 services/powercontext_service.py 的本地兼容实现不同，本模块不发 SQL，
所有读写都由 PowerContext Server 完成：
  - Scope：POST /v1/scopes（以 user_id 派生的幂等键创建/复用）
  - 写入：POST /v1/memory/remember；更新用 PUT .../artifacts/atomic-memory/{artifact_id} + If-Match
  - 读取：POST /v1/memory/entries/list
  - 搜索：POST /v1/memory/search（服务端 FTS 检索）
  - 停用：POST /v1/atomic-memory/lifecycle（state=forgotten）

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

    def _request(self, method, path, payload=None, timeout=None, headers=None):
        url = f"{self.base_url}{path}"
        data = None
        req_headers = {'Accept': 'application/json'}
        if headers:
            req_headers.update(headers)
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            req_headers['Content-Type'] = 'application/json; charset=utf-8'

        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
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
        return max(matched, key=RemotePowerContextClient._entry_revision)

    @staticmethod
    def _entry_revision(entry):
        artifact = entry.get('artifact') or {}
        return artifact.get('revision') or entry.get('version') or 1

    @staticmethod
    def _artifact(entry):
        return entry.get('artifact') or entry.get('citation') or {}

    def save(self, user_id, kind, text, reason=None):
        """按 kind 写入记忆；已存在则按 If-Match 提交下一修订"""
        scope_id = self.ensure_scope(user_id)
        entry = self._pick_entry(self._list_entries(user_id), kind)

        if not entry:
            return self._remember(scope_id, kind, text, reason)

        try:
            return self._replace(scope_id, entry, kind, text)
        except PowerContextRemoteError as e:
            if getattr(e, 'status', None) not in (409, 412, 428):
                raise
            # 版本冲突：重新读取后重试一次
            entry = self._pick_entry(self._list_entries(user_id), kind)
            if not entry:
                return self._remember(scope_id, kind, text, reason)
            return self._replace(scope_id, entry, kind, text)

    def _replace(self, scope_id, entry, kind, text):
        artifact = self._artifact(entry)
        artifact_id = artifact.get('artifact_id')
        revision = self._entry_revision(entry)
        if not artifact_id:
            raise PowerContextRemoteError('记忆条目缺少 artifact_id，无法更新')
        return self._request(
            'PUT',
            f'/v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}',
            {'content': {'kind': kind, 'text': text}},
            headers={'If-Match': f'"revision:{revision}"'},
        )

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
        artifact = self._artifact(entry)
        self._request('POST', '/v1/atomic-memory/lifecycle', {
            'scope_id': scope_id,
            'target': {
                'artifact': artifact,
                'state_version': entry.get('state_version', 0),
            },
            'state': 'forgotten',
        })
        return True

    def reset(self, user_id):
        """停用该用户的全部活动记忆，返回停用条数（用于初始化前清空演示数据）"""
        scope_id = self.ensure_scope(user_id)
        forgotten = 0
        for entry in self._list_entries(user_id):
            artifact = self._artifact(entry)
            if not artifact.get('artifact_id'):
                continue
            target = {
                'artifact': artifact,
                'state_version': entry.get('state_version', 0),
            }
            payload = {
                'scope_id': scope_id,
                'target': target,
                'state': 'forgotten',
            }
            try:
                self._request('POST', '/v1/atomic-memory/lifecycle', payload)
                forgotten += 1
            except PowerContextRemoteError as e:
                if getattr(e, 'status', None) != 409:
                    continue
                # 状态版本冲突：重新读取后再试一次
                fresh = self._pick_entry(self._list_entries(user_id), entry.get('kind'))
                if not fresh:
                    continue
                payload['target'] = {
                    'artifact': self._artifact(fresh),
                    'state_version': fresh.get('state_version', 0),
                }
                try:
                    self._request('POST', '/v1/atomic-memory/lifecycle', payload)
                    forgotten += 1
                except PowerContextRemoteError:
                    continue
        return forgotten

    def search(self, user_id, query, limit=10):
        """调用真实 PowerContext 的 Memory 搜索（服务端 FTS/向量）"""
        scope_id = self.ensure_scope(user_id)
        data = self._request('POST', '/v1/memory/search', {
            'scope_id': scope_id,
            'query': query,
            'limit': max(1, min(limit, 50)),
        })

        results = []
        for hit in data.get('hits') or []:
            memory = hit.get('memory') or {}
            if memory:
                artifact = memory.get('artifact') or {}
                results.append({
                    'artifact_id': artifact.get('artifact_id', ''),
                    'kind': memory.get('kind', ''),
                    'description': '',
                    'content': self._decode(memory.get('text', '')),
                    'score': hit.get('score', 0.0),
                    'mode': data.get('mode', ''),
                })
                continue
            # 兼容旧版 citation 形状
            citation = hit.get('citation') or {}
            results.append({
                'artifact_id': citation.get('entry_id', ''),
                'kind': hit.get('kind', 'memory'),
                'description': '',
                'content': self._decode(hit.get('text', '')),
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
