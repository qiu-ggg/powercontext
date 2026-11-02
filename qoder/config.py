"""
应用配置类
seekdb 和 PowerContext 均使用本地 SQLite 存储
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
