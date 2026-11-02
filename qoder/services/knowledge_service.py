"""
知识库服务模块
整合 seekdb 和 PowerContext，提供完整的业务逻辑
"""

from services.seekdb_service import seekdb_service
from services.powercontext_service import powercontext_service


class KnowledgeService:
    """知识库服务"""

    def __init__(self):
        self.seekdb = seekdb_service
        self.powercontext = powercontext_service

    def search_knowledge(self, user_id, query, category=None, limit=20, record_history=True):
        """搜索知识库；record_history=False 用于相关推荐等非用户主动搜索"""
        filters = {}
        if category:
            filters['category'] = category

        results = self.seekdb.hybrid_search(
            query=query,
            filters=filters if filters else None,
            limit=limit
        )

        if record_history:
            self.powercontext.add_search_history(
                user_id=user_id,
                query=query,
                results_count=len(results)
            )

        return results

    def get_document(self, user_id, document_id, view_duration=0):
        """获取文档详情并记录浏览"""
        document = self.seekdb.get_document_by_id(document_id)

        if document:
            self.powercontext.add_viewed_documents(
                user_id=user_id,
                document_id=document_id,
                view_duration=view_duration
            )

            progress = self.powercontext.get_learning_progress(
                user_id=user_id,
                document_id=document_id
            )
            document['learning_progress'] = progress

        return document

    def save_document_progress(self, user_id, document_id, progress, last_position=0):
        """保存文档学习进度"""
        return self.powercontext.save_learning_progress(
            user_id=user_id,
            document_id=document_id,
            progress=progress,
            last_position=last_position
        )

    def add_document(self, title, content, category, tags, vector_embedding=None):
        """添加新文档"""
        return self.seekdb.add_document(
            title=title,
            content=content,
            category=category,
            tags=tags,
            vector_embedding=vector_embedding
        )

    def get_user_dashboard(self, user_id):
        """获取用户仪表盘数据"""
        user_stats = self.powercontext.get_user_statistics(user_id)
        db_stats = self.seekdb.get_statistics()
        recommendations = self.powercontext.get_recommendations(user_id, limit=5)
        recent_searches = self.powercontext.get_search_history(user_id, limit=10)

        dashboard = {
            'user_stats': user_stats,
            'db_stats': db_stats,
            'recommendations': recommendations,
            'recent_searches': [
                {
                    'query': s['query'],
                    'results_count': s['results_count'],
                    'timestamp': s['timestamp']
                }
                for s in recent_searches
            ],
            'continue_learning': []
        }

        for activity in user_stats.get('recent_activity', []):
            if activity['type'] == 'learning' and activity.get('progress', 0) < 1.0:
                try:
                    doc_id = int(activity['document_id'])
                except (ValueError, TypeError):
                    continue
                doc = self.seekdb.get_document_by_id(doc_id)
                if doc:
                    dashboard['continue_learning'].append({
                        'document_id': doc['document_id'],
                        'title': doc['title'],
                        'progress': activity['progress'],
                        'category': doc.get('category', '')
                    })

        return dashboard

    def set_user_preferences(self, user_id, preferences):
        """设置用户偏好"""
        return self.powercontext.save_user_preferences(user_id, preferences)

    def get_user_preferences(self, user_id):
        """获取用户偏好"""
        return self.powercontext.get_user_preferences(user_id)

    def get_learning_analytics(self, user_id):
        """获取学习分析数据"""
        stats = self.powercontext.get_user_statistics(user_id)
        preferences = self.powercontext.get_user_preferences(user_id) or {}

        analytics = {
            'total_study_time': stats.get('total_study_time', 0),
            'documents_completed': 0,
            'documents_in_progress': 0,
            'favorite_categories': stats.get('categories_learned', []),
            'total_searches': stats.get('total_searches', 0),
            'total_documents_viewed': stats.get('total_documents_viewed', 0),
            'preferences': preferences,
            'backend': stats.get('backend', 'local')
        }

        all_memories = self.powercontext.get_all_memories(user_id)
        completed = 0
        in_progress = 0

        for key, value in all_memories.items():
            if key.startswith('learning_progress_') and isinstance(value, dict):
                progress = value.get('progress', 0)
                if progress >= 1.0:
                    completed += 1
                elif progress > 0:
                    in_progress += 1

        analytics['documents_completed'] = completed
        analytics['documents_in_progress'] = in_progress

        return analytics


knowledge_service = KnowledgeService()
