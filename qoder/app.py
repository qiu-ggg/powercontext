"""
Flask 主应用
智能知识库 - Smart Knowledge Hub
PowerContext 真实服务 + SQLite FTS5 兼容检索层
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from config import Config
from services.knowledge_service import knowledge_service
from services.powercontext_service import powercontext_service


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    Config.init_app(app)
    CORS(app)
    register_routes(app)
    return app


def register_routes(app):

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/search')
    def search_page():
        categories = knowledge_service.seekdb.get_all_categories()
        return render_template('search.html', categories=categories)

    @app.route('/dashboard')
    def dashboard_page():
        return render_template('dashboard.html')

    @app.route('/document/<int:doc_id>')
    def document_page(doc_id):
        document = knowledge_service.seekdb.get_document_by_id(doc_id)
        if not document:
            return jsonify({'error': '文档不存在'}), 404
        return render_template('document.html', document=document)

    @app.route('/api/health', methods=['GET'])
    def health_check():
        ctx = powercontext_service.describe()
        return jsonify({
            'status': 'ok',
            'service': 'Smart Knowledge Hub',
            'version': '1.1.1',
            'retrieval': 'SQLite FTS5 兼容检索层（未连接 seekdb 服务）',
            'seekdb': '未连接 seekdb 服务；检索由 SQLite FTS5 兼容层完成',
            'powercontext': ctx['mode'],
            'powercontext_detail': ctx
        })

    @app.route('/api/powercontext/status', methods=['GET'])
    def powercontext_status():
        return jsonify(powercontext_service.describe())

    @app.route('/api/search', methods=['GET'])
    def search():
        query = request.args.get('q', '')
        user_id = request.args.get('user_id', 'default_user')
        category = request.args.get('category')
        limit = int(request.args.get('limit', 20))
        record_history = request.args.get('record', '1') not in ('0', 'false', 'False')

        if not query:
            return jsonify({'error': '请提供搜索关键词'}), 400

        try:
            results = knowledge_service.search_knowledge(
                user_id=user_id,
                query=query,
                category=category,
                limit=limit,
                record_history=record_history
            )
            return jsonify({
                'query': query,
                'count': len(results),
                'results': results
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/document/<int:doc_id>', methods=['GET', 'POST'])
    def get_document(doc_id):
        # GET：读取文档并加载进度；POST：页面离开时用 sendBeacon 上报浏览时长
        if request.method == 'POST':
            payload = request.get_json(silent=True) or request.form
            user_id = payload.get('user_id', 'default_user')
            try:
                view_duration = int(payload.get('view_duration', 0) or 0)
            except (TypeError, ValueError):
                view_duration = 0

            if view_duration <= 0:
                return jsonify({'success': True, 'recorded': False})

            try:
                knowledge_service.get_document(
                    user_id=user_id,
                    document_id=doc_id,
                    view_duration=view_duration
                )
                return jsonify({'success': True, 'recorded': True, 'view_duration': view_duration})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        user_id = request.args.get('user_id', 'default_user')
        view_duration = int(request.args.get('view_duration', 0))

        try:
            document = knowledge_service.get_document(
                user_id=user_id,
                document_id=doc_id,
                view_duration=view_duration
            )
            if document:
                return jsonify(document)
            return jsonify({'error': '文档不存在'}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/document', methods=['POST'])
    def add_document():
        data = request.get_json()
        if not data:
            return jsonify({'error': '请提供文档数据'}), 400

        for field in ['title', 'content', 'category']:
            if field not in data:
                return jsonify({'error': f'缺少必需字段: {field}'}), 400

        try:
            doc_id = knowledge_service.add_document(
                title=data['title'],
                content=data['content'],
                category=data['category'],
                tags=data.get('tags', ''),
                vector_embedding=data.get('vector_embedding')
            )
            if doc_id:
                return jsonify({'success': True, 'document_id': doc_id}), 201
            return jsonify({'error': '添加文档失败'}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/progress/<int:doc_id>', methods=['POST'])
    def save_progress(doc_id):
        data = request.get_json()
        if not data:
            return jsonify({'error': '请提供进度数据'}), 400

        user_id = data.get('user_id', 'default_user')
        progress = data.get('progress')
        last_position = data.get('last_position', 0)

        if progress is None:
            return jsonify({'error': '请提供学习进度'}), 400

        try:
            success = knowledge_service.save_document_progress(
                user_id=user_id,
                document_id=doc_id,
                progress=progress,
                last_position=last_position
            )
            if success:
                return jsonify({'success': True})
            return jsonify({'error': '保存进度失败'}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/dashboard/<user_id>', methods=['GET'])
    def get_dashboard(user_id):
        try:
            dashboard = knowledge_service.get_user_dashboard(user_id)
            return jsonify(dashboard)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/preferences/<user_id>', methods=['GET'])
    def get_preferences(user_id):
        try:
            preferences = knowledge_service.get_user_preferences(user_id)
            return jsonify({'preferences': preferences or {}})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/preferences/<user_id>', methods=['POST'])
    def set_preferences(user_id):
        data = request.get_json()
        if not data or 'preferences' not in data:
            return jsonify({'error': '请提供偏好设置'}), 400

        try:
            success = knowledge_service.set_user_preferences(
                user_id=user_id,
                preferences=data['preferences']
            )
            if success:
                return jsonify({'success': True})
            return jsonify({'error': '保存偏好失败'}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/analytics/<user_id>', methods=['GET'])
    def get_analytics(user_id):
        try:
            analytics = knowledge_service.get_learning_analytics(user_id)
            return jsonify(analytics)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/categories', methods=['GET'])
    def get_categories():
        try:
            categories = knowledge_service.seekdb.get_all_categories()
            return jsonify({'categories': categories})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/statistics', methods=['GET'])
    @app.route('/api/stats', methods=['GET'])
    def get_statistics():
        try:
            stats = knowledge_service.seekdb.get_statistics()
            return jsonify(stats)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/memory/search/<user_id>', methods=['GET'])
    def search_memory(user_id):
        """PowerContext 记忆搜索接口"""
        query = request.args.get('q', '')
        limit = int(request.args.get('limit', 10))
        if not query:
            return jsonify({'error': '请提供搜索关键词'}), 400
        try:
            results = knowledge_service.powercontext.search_memory(user_id, query, limit)
            return jsonify({'query': query, 'count': len(results), 'results': results})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/memory/recall/<user_id>', methods=['GET'])
    def recall_memory(user_id):
        """PowerContext 上下文召回接口"""
        kind = request.args.get('kind')
        limit = int(request.args.get('limit', 50))
        try:
            manifest = knowledge_service.powercontext.recall_context(user_id, kind=kind, limit=limit)
            return jsonify(manifest)
        except Exception as e:
            return jsonify({'error': str(e)}), 500


app = create_app()

if __name__ == '__main__':
    print("=" * 60)
    print("智能知识库 - Smart Knowledge Hub")
    print("=" * 60)
    print("检索层: SQLite FTS5 兼容检索层（未连接 seekdb 服务）")
    ctx = powercontext_service.describe()
    print(f"PowerContext: {ctx['mode']} ({ctx['version']})")
    if ctx.get('fallback_reason'):
        print(f"  回退原因: {ctx['fallback_reason']}")
    print(f"访问地址: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=app.config['DEBUG'])
