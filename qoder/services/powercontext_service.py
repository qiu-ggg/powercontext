"""
PowerContext 服务模块

支持两种后端，由环境变量切换：

- remote：连接真实的 PowerContext Server（API v1.4，实测 1.4.1），
  记忆读写、FTS 搜索与 Scope 隔离全部由服务端完成，见 powercontext_remote.py
- local：本地 SQLite 兼容实现（Scope 隔离、Memory、Search、Recall 的语义对齐），
  用于没有 PowerContext 服务的离线演示

POWERCONTEXT_MODE=remote（默认）时强制使用真实服务，不可达会直接报错；
POWERCONTEXT_MODE=auto 时优先使用真实服务，探测失败才退回本地；
POWERCONTEXT_MODE=local 仅用于离线预览页面，验收时必须使用 remote。
"""

import sqlite3
import os
import json
import time
from datetime import datetime

from services.powercontext_remote import RemotePowerContextClient, PowerContextRemoteError

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'powercontext.db')

# PowerContext 单条记忆上限 8192 UTF-8 字节，远程模式下需控制聚合记忆的体积
REMOTE_TEXT_LIMIT = 8000


class PowerContextService:
    """PowerContext 上下文服务（真实服务优先，本地兼容实现兜底）"""

    def __init__(self, db_path=None, mode=None, base_url=None):
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

        requested = (mode or os.getenv('POWERCONTEXT_MODE', 'remote')).strip().lower()
        self.base_url = base_url or os.getenv('POWERCONTEXT_BASE_URL', 'http://127.0.0.1:8000')
        self._remote_client = None
        self.mode = 'local'
        self.remote_error = None

        if requested in ('remote', 'auto'):
            client = RemotePowerContextClient(self.base_url)
            if client.available():
                self._remote_client = client
                self.mode = 'remote'
            elif requested == 'remote':
                raise RuntimeError(
                    f'POWERCONTEXT_MODE=remote，但 {self.base_url} 上没有可用的 PowerContext 服务。'
                    '请先启动 PowerContext Server（见 RUNNING.md），或改用 POWERCONTEXT_MODE=local。'
                )
            else:
                self.remote_error = f'{self.base_url} 不可达，已回退本地实现'

    @property
    def is_remote(self):
        return self._remote_client is not None

    def describe(self):
        """返回当前后端信息，供健康检查/页面展示"""
        return {
            'mode': self.mode,
            'base_url': self.base_url if self.is_remote else None,
            'version': 'API v1.4（PowerContext Server 1.4.1）' if self.is_remote else '本地兼容实现（SQLite）',
            'fallback_reason': self.remote_error,
        }

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS scopes (
                    id TEXT PRIMARY KEY,
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
                );

                CREATE TABLE IF NOT EXISTS atomic_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT '',
                    description TEXT DEFAULT '',
                    text TEXT NOT NULL,
                    value_json TEXT DEFAULT '{}',
                    lifecycle TEXT DEFAULT 'active',
                    revision INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                    UNIQUE(scope_id, artifact_id),
                    FOREIGN KEY (scope_id) REFERENCES scopes(id)
                );

                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY (scope_id) REFERENCES scopes(id)
                );

                CREATE INDEX IF NOT EXISTS idx_memory_scope ON atomic_memory(scope_id);
                CREATE INDEX IF NOT EXISTS idx_memory_lifecycle ON atomic_memory(lifecycle);
                CREATE INDEX IF NOT EXISTS idx_memory_kind ON atomic_memory(kind);
                CREATE INDEX IF NOT EXISTS idx_sources_scope ON sources(scope_id);
            """)
            conn.commit()
        finally:
            conn.close()

    def _ensure_scope(self, scope_id):
        conn = self._get_conn()
        try:
            existing = conn.execute("SELECT id FROM scopes WHERE id = ?", (scope_id,)).fetchone()
            if not existing:
                conn.execute("INSERT INTO scopes (id) VALUES (?)", (scope_id,))
                conn.commit()
        finally:
            conn.close()

    def save_memory(self, user_id, key, value, metadata=None):
        """
        保存用户记忆 - 对应 PowerContext 的 Create/Replace Artifact (atomic-memory)
        
        Args:
            user_id: 用作 scope_id
            key: artifact_id
            value: 记忆内容
            metadata: 元数据
        """
        if self.is_remote:
            try:
                self._remote_client.save(
                    user_id, key,
                    RemotePowerContextClient.encode_value(value),
                    reason=f'save {key}'
                )
                return True
            except PowerContextRemoteError as e:
                print(f"PowerContext 远程写入失败: {e}")
                return False

        self._ensure_scope(user_id)
        conn = self._get_conn()
        try:
            existing = conn.execute(
                "SELECT revision FROM atomic_memory WHERE scope_id = ? AND artifact_id = ?",
                (user_id, key)
            ).fetchone()

            text_content = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
            description = key.replace('_', ' ').title()
            kind = key.split('_')[0] if '_' in key else key

            if existing:
                new_rev = existing['revision'] + 1
                conn.execute(
                    """UPDATE atomic_memory
                       SET text = ?, description = ?, kind = ?, value_json = ?,
                           revision = ?, lifecycle = 'active',
                           updated_at = datetime('now', 'localtime')
                       WHERE scope_id = ? AND artifact_id = ?""",
                    (text_content, description, kind, json.dumps(metadata or {}, ensure_ascii=False),
                     new_rev, user_id, key)
                )
            else:
                conn.execute(
                    """INSERT INTO atomic_memory (scope_id, artifact_id, kind, description, text, value_json)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (user_id, key, kind, description, text_content,
                     json.dumps(metadata or {}, ensure_ascii=False))
                )

            conn.execute(
                """INSERT INTO sources (scope_id, source_type, content_json)
                   VALUES (?, 'memory_write', ?)""",
                (user_id, json.dumps({
                    'artifact_id': key,
                    'action': 'upsert',
                    'timestamp': datetime.now().isoformat()
                }, ensure_ascii=False))
            )
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            print(f"保存记忆失败: {e}")
            return False
        finally:
            conn.close()

    def get_memory(self, user_id, key):
        """
        获取用户记忆 - 对应 PowerContext 的 Get Artifact State
        
        Args:
            user_id: scope_id
            key: artifact_id
        
        Returns:
            记忆值，如果不存在则返回 None
        """
        if self.is_remote:
            try:
                value, _ = self._remote_client.load(user_id, key)
                return value
            except PowerContextRemoteError as e:
                print(f"PowerContext 远程读取失败: {e}")
                return None

        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT text, lifecycle FROM atomic_memory
                   WHERE scope_id = ? AND artifact_id = ? AND lifecycle = 'active'""",
                (user_id, key)
            ).fetchone()
            if not row:
                return None
            try:
                return json.loads(row['text'])
            except (json.JSONDecodeError, TypeError):
                return row['text']
        finally:
            conn.close()

    def delete_memory(self, user_id, key):
        """
        删除用户记忆 - 对应 PowerContext 的 lifecycle: forget
        """
        if self.is_remote:
            try:
                return self._remote_client.retire(user_id, key, reason=f'forget {key}')
            except PowerContextRemoteError as e:
                print(f"PowerContext 远程删除失败: {e}")
                return False

        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE atomic_memory SET lifecycle = 'forgotten',
                   updated_at = datetime('now', 'localtime')
                   WHERE scope_id = ? AND artifact_id = ?""",
                (user_id, key)
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"删除记忆出错: {e}")
            return False
        finally:
            conn.close()

    def get_all_memories(self, user_id):
        """
        获取用户的所有活跃记忆 - 对应 PowerContext 的 List Atomic Memory
        """
        if self.is_remote:
            try:
                return self._remote_client.load_all(user_id)
            except PowerContextRemoteError as e:
                print(f"PowerContext 远程列表失败: {e}")
                return {}

        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT artifact_id, text, kind, lifecycle
                   FROM atomic_memory
                   WHERE scope_id = ? AND lifecycle = 'active'
                   ORDER BY updated_at DESC""",
                (user_id,)
            ).fetchall()

            memories = {}
            for row in rows:
                try:
                    memories[row['artifact_id']] = json.loads(row['text'])
                except (json.JSONDecodeError, TypeError):
                    memories[row['artifact_id']] = row['text']
            return memories
        finally:
            conn.close()

    def search_memory(self, user_id, query, limit=10):
        """
        搜索记忆 - 远程模式调用 PowerContext 的 POST /v1/memory/search
        （服务端 FTS 检索；本地模式用 LIKE 兼容实现）
        """
        if self.is_remote:
            try:
                return self._remote_client.search(user_id, query, limit)
            except PowerContextRemoteError as e:
                print(f"PowerContext 远程搜索失败: {e}")
                return []

        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT artifact_id, kind, description, text,
                          CASE WHEN text LIKE ? THEN 1.0 ELSE 0.0 END as relevance
                   FROM atomic_memory
                   WHERE scope_id = ? AND lifecycle = 'active'
                     AND (text LIKE ? OR kind LIKE ? OR description LIKE ? OR artifact_id LIKE ?)
                   ORDER BY relevance DESC, updated_at DESC
                   LIMIT ?""",
                (f'%{query}%', user_id, f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%', limit)
            ).fetchall()

            results = []
            for row in rows:
                try:
                    value = json.loads(row['text'])
                except (json.JSONDecodeError, TypeError):
                    value = row['text']
                results.append({
                    'artifact_id': row['artifact_id'],
                    'kind': row['kind'],
                    'description': row['description'],
                    'content': value,
                    'score': row['relevance']
                })
            return results
        finally:
            conn.close()

    def recall_context(self, user_id, kind=None, tags=None, limit=50):
        """
        召回上下文 - 远程模式读取 PowerContext 的活动 Memory 条目；
        本地模式返回同结构清单
        """
        if self.is_remote:
            try:
                return self._remote_client.recall(user_id, kind=kind, limit=limit)
            except PowerContextRemoteError as e:
                print(f"PowerContext 远程召回失败: {e}")
                return {'scope_id': user_id, 'entries': [], 'total': 0, 'mode': 'remote-error'}

        conn = self._get_conn()
        try:
            sql = """SELECT artifact_id, kind, description, text
                     FROM atomic_memory
                     WHERE scope_id = ? AND lifecycle = 'active'"""
            params = [user_id]

            if kind:
                sql += " AND kind = ?"
                params.append(kind)

            sql += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()

            manifest = {
                'scope_id': user_id,
                'entries': [],
                'total': len(rows)
            }

            for row in rows:
                try:
                    value = json.loads(row['text'])
                except (json.JSONDecodeError, TypeError):
                    value = row['text']
                manifest['entries'].append({
                    'artifact_id': row['artifact_id'],
                    'kind': row['kind'],
                    'description': row['description'],
                    'content': value
                })

            return manifest
        finally:
            conn.close()

    def save_learning_progress(self, user_id, document_id, progress, last_position=0):
        """保存学习进度"""
        progress_data = {
            'document_id': document_id,
            'progress': progress,
            'last_position': last_position,
            'updated_at': datetime.now().isoformat()
        }
        key = f'learning_progress_{document_id}'
        return self.save_memory(user_id, key, progress_data)

    def get_learning_progress(self, user_id, document_id):
        """获取学习进度"""
        key = f'learning_progress_{document_id}'
        return self.get_memory(user_id, key)

    def save_user_preferences(self, user_id, preferences):
        """保存用户偏好设置"""
        return self.save_memory(user_id, 'preferences', preferences)

    def get_user_preferences(self, user_id):
        """获取用户偏好设置"""
        return self.get_memory(user_id, 'preferences')

    def add_search_history(self, user_id, query, results_count=0):
        """添加搜索历史（相同查询在 30 秒内只保留一条，避免刷新/回显造成重复）"""
        history = self.get_memory(user_id, 'search_history') or []
        if not isinstance(history, list):
            history = []

        now = datetime.now()
        last = history[-1] if history else None
        if isinstance(last, dict) and last.get('query') == query:
            try:
                last_time = datetime.fromisoformat(last.get('timestamp', ''))
            except (ValueError, TypeError):
                last_time = None
            if last_time and (now - last_time).total_seconds() <= 30:
                last['results_count'] = results_count
                last['timestamp'] = now.isoformat()
                return self.save_memory(user_id, 'search_history', history)

        history.append({
            'query': query,
            'results_count': results_count,
            'timestamp': now.isoformat()
        })

        if self.is_remote:
            history = self._fit_remote_text(history, keep=20)
        else:
            history = history[-50:]
        return self.save_memory(user_id, 'search_history', history)

    @staticmethod
    def _fit_remote_text(items, keep):
        """裁剪聚合记忆，确保不超过 PowerContext 单条 8192 字节限制"""
        items = items[-keep:]
        while items:
            text = json.dumps(items, ensure_ascii=False)
            if len(text.encode('utf-8')) <= REMOTE_TEXT_LIMIT:
                break
            items = items[1:]
        return items

    def get_search_history(self, user_id, limit=20):
        """获取搜索历史"""
        history = self.get_memory(user_id, 'search_history') or []
        return history[-limit:]

    def add_viewed_documents(self, user_id, document_id, view_duration=0):
        """添加浏览文档记录"""
        viewed = self.get_memory(user_id, 'viewed_documents') or []

        for doc in viewed:
            if doc.get('document_id') == document_id:
                doc['view_duration'] = doc.get('view_duration', 0) + view_duration
                doc['last_viewed'] = datetime.now().isoformat()
                return self.save_memory(user_id, 'viewed_documents', viewed)

        viewed.append({
            'document_id': document_id,
            'view_duration': view_duration,
            'last_viewed': datetime.now().isoformat()
        })
        if self.is_remote:
            viewed = self._fit_remote_text(viewed, keep=50)
        else:
            viewed = viewed[-100:]
        return self.save_memory(user_id, 'viewed_documents', viewed)

    def get_recommendations(self, user_id, category=None, limit=5):
        """获取个性化推荐（基于学习历史）"""
        viewed = self.get_memory(user_id, 'viewed_documents') or []

        doc_scores = {}
        for doc in viewed:
            doc_id = doc.get('document_id')
            score = doc.get('view_duration', 0)
            if doc_id is not None:
                doc_scores[doc_id] = score

        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        recommendations = [doc_id for doc_id, score in sorted_docs if score > 0][:limit]
        return recommendations

    def get_user_statistics(self, user_id):
        """获取用户学习统计信息"""
        all_memories = self.get_all_memories(user_id)

        viewed_docs = all_memories.get('viewed_documents', [])
        if not isinstance(viewed_docs, list):
            viewed_docs = []

        search_hist = all_memories.get('search_history', [])
        if not isinstance(search_hist, list):
            search_hist = []

        total_study_time = sum(
            doc.get('view_duration', 0)
            for doc in viewed_docs if isinstance(doc, dict)
        )

        stats = {
            'total_documents_viewed': len(viewed_docs),
            'total_searches': len(search_hist),
            'total_study_time': total_study_time,
            'viewed_documents': viewed_docs,
            'search_history': search_hist,
            'categories_learned': [],
            'recent_activity': [],
            'backend': self.mode
        }

        for doc in viewed_docs:
            if isinstance(doc, dict) and 'category' in doc:
                if doc['category'] not in stats['categories_learned']:
                    stats['categories_learned'].append(doc['category'])

        for key, value in all_memories.items():
            if key.startswith('learning_progress_') and isinstance(value, dict):
                doc_id = key.replace('learning_progress_', '')
                stats['recent_activity'].append({
                    'type': 'learning',
                    'document_id': doc_id,
                    'progress': value.get('progress', 0),
                    'updated_at': value.get('updated_at', '')
                })

        stats['recent_activity'].sort(
            key=lambda x: x.get('updated_at', ''), reverse=True
        )
        stats['recent_activity'] = stats['recent_activity'][:10]

        return stats


powercontext_service = PowerContextService()
