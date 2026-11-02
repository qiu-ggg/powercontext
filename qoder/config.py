"""
应用配置类

- 检索层：本地 SQLite + FTS5，作为 seekdb 兼容检索层，不连接 seekdb 服务
- 上下文层：默认强制连接真实 PowerContext Server（POWERCONTEXT_MODE=remote），
  服务不可达直接报错；仅在显式设置 POWERCONTEXT_MODE=local/auto 时才使用本地兼容实现
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')


class Config:
    """应用配置"""

    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'

    SEEKDB_PATH = os.path.join(DATA_DIR, 'seekdb.db')
    POWERCONTEXT_PATH = os.path.join(DATA_DIR, 'powercontext.db')

    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'pdf', 'txt', 'md', 'doc', 'docx'}

    DEFAULT_VECTOR_WEIGHT = 0.7
    DEFAULT_TEXT_WEIGHT = 0.3
    MAX_SEARCH_RESULTS = 50

    @staticmethod
    def init_app(app):
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
