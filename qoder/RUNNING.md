# 运行说明

## 环境要求

- Python 3.8+
- 无需额外数据库（使用 SQLite）
- 无需外部 API 服务

## 安装步骤

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

依赖列表：
- Flask==3.0.0
- flask-cors==4.0.0
- python-dotenv==1.0.0

### 2. 初始化数据库

```bash
python init_db.py
```

此命令会：
- 在 `data/` 目录下创建 `seekdb.db`（SQLite + FTS5 全文检索）
- 在 `data/` 目录下创建 `powercontext.db`（PowerContext 记忆存储）
- 导入 12 篇示例文档
- 创建 demo_user 的示例记忆数据

### 3. 启动服务

```bash
python app.py
```

服务启动后访问 `http://localhost:5000`

## 功能验证

### 搜索功能
1. 访问首页，在搜索框输入"深度学习"
2. 查看 seekdb FTS5 返回的检索结果
3. 查看 PowerContext 返回的记忆搜索结果

### 学习进度
1. 点击搜索结果中的文档链接
2. 点击进度按钮（25%/50%/75%/100%）标记学习进度
3. 刷新页面，确认进度已恢复

### 仪表盘
1. 访问 `/dashboard`
2. 查看学习统计（来自 PowerContext）
3. 查看上下文召回结果（来自 PowerContext Recall API）
4. 修改偏好设置并保存

## 配置说明

项目使用 SQLite 本地存储，无需额外配置。如需修改，可创建 `.env` 文件：

```env
FLASK_DEBUG=True
SECRET_KEY=your-secret-key
```

## 数据存储

所有数据存储在 `data/` 目录下的 SQLite 数据库中：
- `data/seekdb.db` - 文档数据和全文索引
- `data/powercontext.db` - 用户记忆和上下文数据

删除 `data/` 目录后重新运行 `python init_db.py` 可重置所有数据。
