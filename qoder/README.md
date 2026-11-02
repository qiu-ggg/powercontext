# 智能知识库 - Smart Knowledge Hub

基于 Qoder 开发的智能文献检索与知识管理系统，集成 seekdb 全文检索和 PowerContext 上下文记忆服务。

## 项目简介

智能知识库是一个面向学习和科研场景的效率工具：
- 管理论文、笔记、学习资料
- 通过 seekdb FTS5 全文检索快速找到相关内容
- 通过 PowerContext 追踪学习进度，提供个性化推荐
- 可视化学习统计，了解学习习惯和偏好

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 后端 | Python Flask | Web 框架 |
| 前端 | HTML + CSS + JavaScript | 响应式界面 |
| 数据检索 | seekdb (SQLite + FTS5) | 全文检索 + 结构化查询 |
| 上下文服务 | PowerContext (本地) | Scope 隔离的原子记忆管理 |
| 部署 | Qoder Sites | 一键发布 |

## 核心技术集成

### seekdb 的作用

seekdb 提供混合检索能力：
- **FTS5 全文索引**：关键词匹配，支持中文分词
- **结构化查询**：按分类、时间等字段过滤
- **加权排序**：检索结果按相关性评分排序

```python
# 混合检索示例
results = seekdb.hybrid_search(
    query="深度学习",
    filters={"category": "人工智能"},
    limit=20
)
# 返回: [{document_id, title, content, text_score, final_score, ...}]
```

### PowerContext 的作用

PowerContext 管理用户上下文记忆（兼容 PowerContext API v1.4 规范）：
- **Scope 隔离**：每个用户独立的记忆空间
- **Atomic Memory**：原子记忆（学习进度、搜索历史、偏好设置）
- **Search**：记忆内容搜索
- **Recall**：上下文召回

```python
# 保存学习进度（Atomic Memory）
pc.save_learning_progress(user_id, doc_id, progress=0.75)

# 上下文召回（Recall Manifest）
manifest = pc.recall_context(user_id, kind='learning', limit=10)

# 记忆搜索（Search Artifacts）
results = pc.search_memory(user_id, query='深度学习')
```

## 快速开始

### 环境要求
- Python 3.8+

### 安装步骤

1. 克隆项目
```bash
git clone <your-repo-url>
cd SmartKnowledgeHub
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

3. 初始化数据库（自动创建 SQLite 数据库并导入示例数据）
```bash
python init_db.py
```

4. 启动服务
```bash
python app.py
```

访问 `http://localhost:5000` 查看应用。

## 项目结构

```
SmartKnowledgeHub/
├── app.py                      # Flask 主应用
├── config.py                   # 配置文件
├── init_db.py                  # 数据库初始化脚本
├── requirements.txt            # Python 依赖
├── data/                       # SQLite 数据库文件（运行时生成）
│   ├── seekdb.db              # seekdb 数据库
│   └── powercontext.db        # PowerContext 数据库
├── services/
│   ├── seekdb_service.py      # seekdb 检索服务
│   ├── powercontext_service.py # PowerContext 记忆服务
│   └── knowledge_service.py   # 业务逻辑整合
├── templates/                  # HTML 模板
│   ├── index.html             # 首页
│   ├── search.html            # 搜索页
│   ├── dashboard.html         # 仪表盘
│   └── document.html          # 文档详情
└── static/css/style.css       # 样式文件
```

## 验证样例

### 样例1：文献检索

**操作步骤**:
1. 访问首页，在搜索框输入"深度学习"
2. 点击搜索或按回车
3. 查看搜索结果

**预期结果**:
- seekdb FTS5 返回 1 个匹配结果："深度学习入门指南"
- 结果展示标题、摘要、分类、标签和相关度评分
- PowerContext 同时搜索用户记忆，显示相关历史记录

**技术作用**:
- seekdb: 执行 FTS5 全文检索，返回相关性评分
- PowerContext: 搜索记忆中的相关搜索历史

### 样例2：学习进度追踪

**操作步骤**:
1. 打开任意文档（如 `/document/1`）
2. 点击进度按钮标记学习进度（如 50%）
3. 关闭页面后重新打开
4. 查看进度是否恢复

**预期结果**:
- 进度被正确保存到 PowerContext
- 下次访问自动恢复进度
- 仪表盘显示继续学习列表

**技术作用**:
- PowerContext: 保存和读取 Atomic Memory（learning_progress）

### 样例3：个性化仪表盘

**操作步骤**:
1. 访问 `/dashboard`
2. 查看学习统计、继续学习、搜索历史
3. 查看 PowerContext 上下文召回结果
4. 修改偏好设置并保存

**预期结果**:
- 统计数据来自 PowerContext 记忆
- 上下文召回显示所有活跃记忆
- 偏好设置保存到 PowerContext

**技术作用**:
- PowerContext: Recall Manifest API 召回用户上下文
- seekdb: 提供文档元数据

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/search?q=&user_id=` | GET | seekdb 全文检索 |
| `/api/document/<id>` | GET | 文档详情 |
| `/api/document` | POST | 添加文档 |
| `/api/progress/<id>` | POST | 保存学习进度 |
| `/api/dashboard/<user_id>` | GET | 仪表盘数据 |
| `/api/analytics/<user_id>` | GET | 学习分析 |
| `/api/preferences/<user_id>` | GET/POST | 用户偏好 |
| `/api/memory/search/<user_id>` | GET | PowerContext 记忆搜索 |
| `/api/memory/recall/<user_id>` | GET | PowerContext 上下文召回 |

## 部署

### Qoder Sites 部署

项目通过 Qoder Sites 发布，访问项目网站体验完整功能。

## 许可证

MIT License
