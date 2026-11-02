# 快速开始指南

> 5 分钟快速体验智能知识库系统

## 🚀 一键启动

### 步骤 1: 安装依赖

```bash
cd D:\SmartKnowledgeHub
pip install -r requirements.txt
```

### 步骤 2: 配置环境

创建 `.env` 文件（或复制 `.env.example`）：

```env
# seekdb 数据库配置
SEEKDB_HOST=localhost
SEEKDB_PORT=3306
SEEKDB_USER=root
SEEKDB_PASSWORD=your_password
SEEKDB_DATABASE=knowledge_hub

# PowerContext 配置
POWERCONTEXT_API_KEY=your_api_key_here
```

### 步骤 3: 初始化数据库

```bash
python init_db.py
```

看到以下输出表示成功：
```
✓ 数据库 knowledge_hub 创建成功
✓ documents 表创建成功
✓ 成功插入 8 条示例文档
```

### 步骤 4: 启动应用

```bash
python app.py
```

应用启动后，访问：http://localhost:5000

---

## 📚 功能体验

### 1️⃣ 智能搜索

**访问**: 首页搜索框 或 点击"检索"

**体验步骤**:
1. 输入关键词："机器学习"
2. 点击搜索按钮
3. 查看搜索结果（应该显示相关文档）
4. 尝试切换分类过滤
5. 观察语义检索效果

**技术展示**:
- ✅ seekdb 全文检索
- ✅ 结果相关性评分
- ✅ PowerContext 记录搜索历史

---

### 2️⃣ 文档阅读

**访问**: 点击搜索结果中的文档标题

**体验步骤**:
1. 阅读文档内容
2. 点击进度按钮标记学习进度（25%/50%/75%/100%）
3. 查看相关文档推荐
4. 返回首页，再次进入该文档
5. 确认进度是否保存成功

**技术展示**:
- ✅ PowerContext 保存学习进度
- ✅ seekdb 查询相关文档
- ✅ 自动记录浏览时长

---

### 3️⃣ 学习仪表盘

**访问**: 点击导航栏"仪表盘"

**体验步骤**:
1. 查看学习统计（文档数、搜索次数、学习时长）
2. 查看"继续学习"列表
3. 查看"最近搜索"历史
4. 设置个人偏好（学习兴趣、目标）
5. 刷新页面，确认偏好是否保存

**技术展示**:
- ✅ PowerContext 存储用户偏好
- ✅ 整合 seekdb + PowerContext 数据
- ✅ 智能推荐算法

---

## 🔍 API 测试

### 使用 curl 测试 API

#### 1. 搜索 API

```bash
curl "http://localhost:5000/api/search?q=机器学习&user_id=test_user&limit=5"
```

**预期响应**:
```json
{
  "query": "机器学习",
  "count": 3,
  "results": [
    {
      "document_id": 1,
      "title": "深度学习入门指南",
      "final_score": 0.85,
      ...
    }
  ]
}
```

#### 2. 获取文档 API

```bash
curl "http://localhost:5000/api/document/1?user_id=test_user"
```

**预期响应**:
```json
{
  "document_id": 1,
  "title": "深度学习入门指南",
  "content": "...",
  "learning_progress": {
    "progress": 0.5,
    "last_position": 50
  }
}
```

#### 3. 保存进度 API

```bash
curl -X POST "http://localhost:5000/api/progress/1" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user", "progress": 0.75, "last_position": 75}'
```

**预期响应**:
```json
{
  "success": true
}
```

#### 4. 仪表盘数据 API

```bash
curl "http://localhost:5000/api/dashboard/test_user"
```

**预期响应**:
```json
{
  "user_stats": {...},
  "db_stats": {...},
  "recommendations": [...],
  "recent_searches": [...]
}
```

---

## 🎯 核心场景演示

### 场景 1: 完整的学习流程

1. **搜索文档**
   - 访问首页
   - 搜索"Python"
   - 浏览搜索结果

2. **阅读文档**
   - 点击"Python 编程最佳实践"
   - 阅读文档内容
   - 标记进度为 50%

3. **查看统计**
   - 访问仪表盘
   - 确认学习进度已记录
   - 查看搜索历史

4. **继续学习**
   - 点击"继续学习"中的文档
   - 确认进度恢复到 50%
   - 继续学习到 100%

5. **个性化推荐**
   - 在仪表盘设置偏好
   - 刷新页面
   - 查看推荐内容是否变化

### 场景 2: 技术验证

#### 验证 seekdb 混合检索

```bash
# 测试全文检索
curl "http://localhost:5000/api/search?q=深度学习&user_id=test"

# 测试分类过滤
curl "http://localhost:5000/api/search?q=机器学习&user_id=test&category=技术"

# 查看返回结果的相关性评分
```

#### 验证 PowerContext 记忆功能

```bash
# 1. 保存进度
curl -X POST "http://localhost:5000/api/progress/1" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "progress": 0.6}'

# 2. 读取进度
curl "http://localhost:5000/api/document/1?user_id=test"
# 检查 learning_progress 字段

# 3. 查看用户记忆
curl "http://localhost:5000/api/analytics/test"
# 检查学习统计信息
```

---

## 📊 数据说明

### 示例数据

项目包含 **8 篇示例文档**，涵盖以下分类：

- **技术** (4篇): 深度学习、数据库、机器学习、云计算
- **编程** (2篇): Python、Web 开发
- **研究** (2篇): NLP、数据科学

### 数据库表

| 表名 | 用途 | 记录数 |
|------|------|--------|
| documents | 存储文档内容 | 8 |
| users | 用户信息 | 0 (运行时创建) |
| learning_progress | 学习进度 | 运行时产生 |
| search_history | 搜索历史 | 运行时产生 |

---

## 🐛 常见问题

### Q1: 数据库连接失败
**解决**: 检查 MySQL 服务是否运行，用户名密码是否正确

### Q2: PowerContext API 错误
**解决**: 检查 API Key 是否正确，网络连接是否正常

### Q3: 页面显示空白
**解决**: 打开浏览器开发者工具，查看是否有 JavaScript 错误

### Q4: 搜索无结果
**解决**: 确认数据库已初始化（运行 `init_db.py`）

---

## 📖 更多资源

- **完整文档**: [README.md](README.md)
- **运行说明**: [RUNNING.md](RUNNING.md)
- **项目结构**: [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)
- **开发记录**: [QODER_DEVELOPMENT_LOG.md](QODER_DEVELOPMENT_LOG.md)

---

## 🎉 开始体验

一切准备就绪！

打开浏览器，访问：**http://localhost:5000**

祝您使用愉快！
