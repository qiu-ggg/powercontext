"""
seekdb 服务模块 - SQLite + FTS5 实现
提供混合检索能力：全文检索 + 结构化查询
兼容 seekdb 的 MySQL 协议接口模式
"""

import sqlite3
import os
import json
import time
from config import Config

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'seekdb.db')


class SeekDBService:
    """seekdb 数据库服务（SQLite + FTS5 实现）"""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT '',
                    tags TEXT DEFAULT '',
                    vector_embedding TEXT DEFAULT '',
                    file_path TEXT DEFAULT '',
                    file_type TEXT DEFAULT '',
                    file_size INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                    title, content, tags,
                    content='documents',
                    content_rowid='id',
                    tokenize='unicode61'
                );

                CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                    INSERT INTO documents_fts(rowid, title, content, tags)
                    VALUES (new.id, new.title, new.content, new.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                    INSERT INTO documents_fts(documents_fts, rowid, title, content, tags)
                    VALUES ('delete', old.id, old.title, old.content, old.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                    INSERT INTO documents_fts(documents_fts, rowid, title, content, tags)
                    VALUES ('delete', old.id, old.title, old.content, old.tags);
                    INSERT INTO documents_fts(rowid, title, content, tags)
                    VALUES (new.id, new.title, new.content, new.tags);
                END;
            """)
            conn.commit()
        finally:
            conn.close()

    def hybrid_search(self, query, vector_weight=0.7, text_weight=0.3, filters=None, limit=20):
        """
        混合检索：FTS5 全文检索 + 结构化过滤
        
        Args:
            query: 查询文本
            vector_weight: 向量检索权重（预留）
            text_weight: 全文检索权重
            filters: 过滤条件字典，支持 category, date_from, date_to
            limit: 返回结果数量限制
        
        Returns:
            检索结果列表
        """
        conn = self._get_conn()
        try:
            conditions = []
            params = []

            if filters:
                if filters.get('category'):
                    conditions.append("d.category = ?")
                    params.append(filters['category'])
                if filters.get('date_from'):
                    conditions.append("d.created_at >= ?")
                    params.append(filters['date_from'])
                if filters.get('date_to'):
                    conditions.append("d.created_at <= ?")
                    params.append(filters['date_to'])

            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)

            safe_query = query.replace('"', '""').strip()

            if safe_query:
                sql = f"""
                    SELECT
                        d.id as document_id,
                        d.title,
                        d.content,
                        d.category,
                        d.tags,
                        d.created_at,
                        d.updated_at,
                        COALESCE(rank, 0) as text_score
                    FROM documents d
                    LEFT JOIN (
                        SELECT rowid, rank
                        FROM documents_fts
                        WHERE documents_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                    ) fts ON d.id = fts.rowid
                    {where_clause}
                    {"AND" if where_clause else "WHERE"} fts.rowid IS NOT NULL
                    ORDER BY text_score ASC
                    LIMIT ?
                """
                params = [safe_query, limit * 2] + params + [limit]

                try:
                    rows = conn.execute(sql, params).fetchall()
                except sqlite3.OperationalError:
                    sql_fallback = f"""
                        SELECT
                            d.id as document_id,
                            d.title,
                            d.content,
                            d.category,
                            d.tags,
                            d.created_at,
                            d.updated_at,
                            0.0 as text_score
                        FROM documents d
                        {where_clause}
                        ORDER BY d.updated_at DESC
                        LIMIT ?
                    """
                    rows = conn.execute(sql_fallback, params[1:-1] + [limit]).fetchall()
            else:
                sql = f"""
                    SELECT
                        d.id as document_id,
                        d.title,
                        d.content,
                        d.category,
                        d.tags,
                        d.created_at,
                        d.updated_at,
                        0.0 as text_score
                    FROM documents d
                    {where_clause}
                    ORDER BY d.updated_at DESC
                    LIMIT ?
                """
                params = params + [limit]
                rows = conn.execute(sql, params).fetchall()

            documents = []
            for row in rows:
                text_score = abs(float(row['text_score'])) if row['text_score'] else 0.0
                final_score = text_score * text_weight
                documents.append({
                    'document_id': row['document_id'],
                    'title': row['title'],
                    'content': row['content'][:500] if row['content'] else '',
                    'category': row['category'] or '未分类',
                    'tags': row['tags'] or '',
                    'text_score': text_score,
                    'vector_score': 0.0,
                    'final_score': min(final_score, 1.0),
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                })

            return documents

        except Exception as e:
            print(f"检索出错: {e}")
            return []
        finally:
            conn.close()

    def add_document(self, title, content, category, tags, vector_embedding=None):
        """添加文档到数据库"""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """INSERT INTO documents (title, content, category, tags, vector_embedding)
                   VALUES (?, ?, ?, ?, ?)""",
                (title, content, category, tags, str(vector_embedding) if vector_embedding else '')
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            conn.rollback()
            print(f"添加文档出错: {e}")
            return None
        finally:
            conn.close()

    def get_document_by_id(self, document_id):
        """根据 ID 获取文档详情"""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            if row:
                return {
                    'document_id': row['id'],
                    'title': row['title'],
                    'content': row['content'],
                    'category': row['category'] or '未分类',
                    'tags': row['tags'] or '',
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                }
            return None
        finally:
            conn.close()

    def get_all_categories(self):
        """获取所有分类"""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT DISTINCT category FROM documents WHERE category != '' ORDER BY category"
            ).fetchall()
            return [row['category'] for row in rows]
        finally:
            conn.close()

    def get_statistics(self):
        """获取数据库统计信息"""
        conn = self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()['cnt']

            cat_rows = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM documents WHERE category != '' GROUP BY category"
            ).fetchall()
            categories = {row['category']: row['cnt'] for row in cat_rows}

            recent_rows = conn.execute(
                "SELECT id, title, created_at FROM documents ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
            recent = [{'id': r['id'], 'title': r['title'], 'created_at': r['created_at']} for r in recent_rows]

            return {
                'total_documents': total,
                'categories': categories,
                'recent_documents': recent
            }
        finally:
            conn.close()


seekdb_service = SeekDBService()
