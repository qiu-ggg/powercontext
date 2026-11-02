# 项目结构说明

## 目录结构

```
SmartKnowledgeHub/
├── app.py                      # Flask 主应用入口
├── config.py                   # 配置文件
├── init_db.py                  # 数据库初始化脚本
├── requirements.txt            # Python 依赖列表
├── README.md                   # 项目说明文档
├── RUNNING.md                  # 运行说明文档
├── .env.example                # 环境变量示例
├── .gitignore                  # Git 忽略文件配置
│
├── services/                   # 服务模块包
│   ├── __init__.py            # 服务模块初始化
│   ├── seekdb_service.py      # seekdb 数据库服务
│   ├── powercontext_service.py # PowerContext 上下文服务
│   └── knowledge_service.py   # 知识库业务逻辑服务
│
├── static/                     # 静态资源目录
│   ├── css/
│   │   └── style.css          # 全局样式文件
│   ├── js/                     # JavaScript 文件（可扩展）
│   └── images/                 # 图片资源（可扩展）
│
├── templates/                  # HTML 模板目录
│   ├── index.html             # 首页模板
│   ├── search.html            # 搜索页模板
│   ├── dashboard.html         # 仪表盘页模板
│   └── document.html          # 文档详情页模板
│
└── uploads/                    # 文件上传目录（运行时创建）
```

## 核心模块说明

### 1. app.py - Flask 主应用

**职责**: 
- 创建和配置 Flask 应用
- 注册路由（页面路由和 API 路由）
- 启动 Web 服务器

**关键功能**:
- `/` - 首页
- `/search` - 搜索页面
- `/dashboard` - 仪表盘页面
- `/document/<id>` - 文档详情页面
- `/api/search` - 搜索 API
- `/api/document` - 文档 CRUD API
- `/api/progress` - 学习进度 API
- `/api/dashboard` - 仪表盘数据 API
- `/api/preferences` - 用户偏好 API
- `/api/analytics` - 学习分析 API

### 2. config.py - 配置管理

**职责**:
- 集中管理应用配置
- 从环境变量读取敏感信息
- 提供配置默认值

**配置项**:
- Flask 配置（SECRET_KEY, DEBUG）
- seekdb 数据库配置（主机、端口、用户名、密码、数据库名）
- PowerContext 配置（API URL、API Key）
- 文件上传配置（上传目录、文件大小限制、允许的文件类型）
- 检索配置（向量权重、文本权重、结果数量限制）

### 3. services/seekdb_service.py - seekdb 服务

**职责**:
- 封装 seekdb 数据库操作
- 实现混合检索（向量检索 + 全文检索）
- 管理文档的增删改查

**核心方法**:
- `hybrid_search()` - 混合检索
- `add_document()` - 添加文档
- `get_document_by_id()` - 获取文档详情
- `get_all_categories()` - 获取所有分类
- `get_statistics()` - 获取统计信息

**技术实现**:
- 使用 SQLAlchemy 进行数据库操作
- 使用 MySQL 全文索引实现文本检索
- 预留向量检索接口（需根据 seekdb 实际 API 调整）

### 4. services/powercontext_service.py - PowerContext 服务

**职责**:
- 封装 PowerContext API 调用
- 管理用户记忆和上下文
- 提供学习进度追踪功能

**核心方法**:
- `save_memory()` - 保存用户记忆
- `get_memory()` - 获取用户记忆
- `delete_memory()` - 删除用户记忆
- `save_learning_progress()` - 保存学习进度
- `get_learning_progress()` - 获取学习进度
- `save_user_preferences()` - 保存用户偏好
- `add_search_history()` - 添加搜索历史
- `get_recommendations()` - 获取个性化推荐

**技术实现**:
- 使用 HTTP REST API 与 PowerContext 服务通信
- 支持记忆持久化和上下文管理
- 实现简单的推荐算法（基于浏览时长和频率）

### 5. services/knowledge_service.py - 知识库服务

**职责**:
- 整合 seekdb 和 PowerContext
- 实现完整的业务逻辑
- 提供面向前端的服务接口

**核心方法**:
- `search_knowledge()` - 搜索知识库
- `get_document()` - 获取文档详情
- `save_document_progress()` - 保存学习进度
- `get_user_dashboard()` - 获取用户仪表盘数据
- `get_learning_analytics()` - 获取学习分析数据

**业务逻辑**:
- 搜索时同时调用 seekdb 检索和 PowerContext 记录历史
- 获取文档时同时返回学习进度信息
- 仪表盘数据整合来自两个服务的信息

## 前端架构

### 模板系统

使用 Jinja2 模板引擎：

1. **index.html** - 首页
   - 展示项目介绍
   - 快速搜索入口
   - 统计信息展示

2. **search.html** - 搜索页面
   - 高级搜索表单
   - 分类过滤选项
   - 语义检索开关
   - 搜索结果列表

3. **dashboard.html** - 仪表盘页面
   - 学习统计卡片
   - 继续学习列表
   - 最近搜索历史
   - 个人偏好设置

4. **document.html** - 文档详情页面
   - 文档内容展示
   - 学习进度追踪
   - 相关文档推荐
   - 浏览时长记录

### CSS 样式

**style.css** 采用：
- 响应式设计（支持移动端）
- Flexbox 和 Grid 布局
- 渐变背景和卡片设计
- 平滑过渡动画

**主要样式模块**:
- 导航栏样式
- 英雄区域样式
- 功能卡片样式
- 搜索结果样式
- 仪表盘样式
- 文档详情样式

### JavaScript 交互

各页面的 JavaScript 实现：
- 异步数据加载（Fetch API）
- 搜索功能实现
- 进度条控制
- 表单提交处理
- 错误处理和用户提示

## 数据流程

### 1. 搜索流程

```
用户输入关键词
    ↓
前端发送请求到 /api/search
    ↓
knowledge_service.search_knowledge()
    ↓
seekdb_service.hybrid_search() - 执行混合检索
    ↓
powercontext_service.add_search_history() - 记录搜索历史
    ↓
返回结果给前端
    ↓
渲染搜索结果列表
```

### 2. 学习进度流程

```
用户点击进度按钮（25%/50%/75%/100%）
    ↓
前端发送 POST 到 /api/progress/<doc_id>
    ↓
knowledge_service.save_document_progress()
    ↓
powercontext_service.save_learning_progress()
    ↓
PowerContext API 保存记忆
    ↓
返回成功状态
    ↓
更新前端进度条
```

### 3. 仪表盘数据流程

```
用户访问仪表盘页面
    ↓
前端并行请求多个 API:
  - /api/analytics/<user_id>
  - /api/dashboard/<user_id>
  - /api/preferences/<user_id>
    ↓
knowledge_service 整合数据:
  - 从 PowerContext 获取学习统计
  - 从 seekdb 获取文档统计
  - 获取推荐和搜索历史
    ↓
返回完整数据
    ↓
渲染仪表盘各个模块
```

## 技术特点

### 1. 混合检索

- **向量检索**: 基于语义相似度（预留接口）
- **全文检索**: MySQL FULLTEXT 索引
- **混合排序**: 加权融合两种检索结果

### 2. 上下文记忆

- **学习进度**: 自动保存和恢复
- **搜索历史**: 记录最近 50 条搜索
- **用户偏好**: 个性化设置
- **浏览记录**: 追踪学习时长

### 3. 智能推荐

- 基于浏览时长推荐热门文档
- 基于分类推荐相关内容
- 基于学习进度推荐未完成文档

### 4. 数据分析

- 学习统计（时长、完成度、搜索次数）
- 分类偏好分析
- 学习速度追踪
- 最近活动记录

## 扩展点

### 1. 功能扩展

- [ ] 用户认证系统（注册/登录）
- [ ] 文档上传功能（PDF、Word 解析）
- [ ] 笔记功能（在文档上做笔记）
- [ ] 知识图谱可视化
- [ ] 学习小组/社区功能
- [ ] 移动端 App

### 2. 技术扩展

- [ ] 集成真正的向量检索（如 seekdb 向量插件）
- [ ] 使用 Redis 缓存热点数据
- [ ] 添加 Elasticsearch 全文搜索
- [ ] 使用消息队列处理异步任务
- [ ] 容器化部署（Docker + Kubernetes）

### 3. 性能优化

- [ ] 数据库查询优化（索引、分区）
- [ ] 前端资源压缩（CSS、JS 最小化）
- [ ] 图片懒加载
- [ ] CDN 加速
- [ ] 负载均衡

## 开发规范

### 1. 代码风格

- Python: 遵循 PEP 8
- 使用 4 空格缩进
- 函数和类有文档字符串
- 变量和函数名语义清晰

### 2. 注释规范

- 模块顶部有模块说明
- 复杂逻辑有注释
- 函数有参数和返回值说明
- 使用 TODO 标记待办事项

### 3. 错误处理

- 使用 try-except 捕获异常
- 记录错误日志
- 返回友好的错误信息
- 前端显示错误提示

### 4. 测试

- 编写单元测试
- 测试 API 接口
- 测试前端交互
- 集成测试

## 总结

本项目是一个完整的智能知识库系统，通过整合 seekdb 和 PowerContext，实现了：

1. ✅ 智能检索（混合检索 + 语义搜索）
2. ✅ 学习追踪（进度保存 + 历史记忆）
3. ✅ 个性化推荐（基于用户偏好）
4. ✅ 数据分析（学习统计 + 可视化）
5. ✅ 响应式设计（支持各种设备）

项目结构清晰，代码规范，易于扩展和维护，适合作为比赛作品展示。
