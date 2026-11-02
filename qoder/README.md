# 智能知识库 - Smart Knowledge Hub

面向学习与科研的检索、进度管理与上下文记忆工具，使用 Qoder Desktop 开发。

- 12 篇示例资料可全文检索，支持分类过滤与相关度排序
- 学习进度、搜索历史、浏览时长、偏好设置按用户隔离保存
- 仪表盘展示学习统计、继续学习、最近搜索和上下文召回
- 上下文记忆接入真实的 **PowerContext Server 1.4.1**（HTTP API v1.4），默认强制使用真实服务（`POWERCONTEXT_MODE=remote`），页面会明确显示当前后端

## 技术栈

| 组件 | 技术 | 实际说明 |
|------|------|----------|
| 后端 | Python Flask | REST API + 服务端渲染 |
| 前端 | HTML + CSS + JavaScript | 响应式，无前端构建步骤 |
| 检索层 | SQLite + FTS5 | SQLite FTS5 兼容检索层；不连接 seekdb 服务，向量检索为预留字段 |
| 上下文服务 | PowerContext Server 1.4.1 | 默认 `POWERCONTEXT_MODE=remote`，记忆读写与搜索全部走真实 HTTP 服务 |
| 展示页 | Qoder Sites | https://smartknowledgehub-2yrvvh4q95p.qoder.zone |
| 旧演示站 | WorkBuddy | 静态快照，`/api/*` 不可用；不作为本次验收依据 |

详细边界与验证记录见 [docs/TECHNICAL_BOUNDARIES.md](docs/TECHNICAL_BOUNDARIES.md)。

## PowerContext 接入方式

`services/powercontext_remote.py` 是对真实服务的 HTTP 客户端，`services/powercontext_service.py` 按环境变量选择后端：

| `POWERCONTEXT_MODE` | 行为 |
|------|------|
| `remote`（默认） | 使用真实服务；不可达时直接报错，避免静默降级 |
| `auto` | 启动时探测 `POWERCONTEXT_BASE_URL`，可用则使用真实服务，否则回退本地 SQLite 实现 |
| `local` | 本地兼容实现，仅用于离线预览页面 |

真实服务上调用的接口：

- `POST /v1/scopes`：以 `smart-knowledge-hub:{user_id}` 为幂等键创建/复用 Scope
- `POST /v1/memory/remember`：新增记忆
- `POST /v1/memory/entries/revise`：按 kind 更新已有记忆（冲突时重读后重试一次）
- `POST /v1/memory/entries/list`：读取活动记忆
- `POST /v1/memory/search`：记忆搜索（当前服务未配置嵌入模型，返回 `mode: "fts"`）
- `POST /v1/memory/entries/retire`：停用记忆，保留历史

`GET /api/health` 与仪表盘徽标会显示当前实际后端：

```json
{"powercontext":"remote","powercontext_detail":{"mode":"remote","version":"API v1.4（PowerContext Server 1.4.1）"}}
```

## 快速开始

环境要求：Python 3.8+（运行 Flask 应用）；真实 PowerContext 服务需要 Python 3.11+，启动步骤见 [RUNNING.md](RUNNING.md) 第 3 节（必选）。

```bash
pip install -r requirements.txt
python init_db.py          # 需先启动 PowerContext Server
python app.py              # http://localhost:5000
```

默认 `POWERCONTEXT_MODE=remote`：真实服务不可达时应用会拒绝启动，避免把本地实现误认为真实服务。仅离线预览界面时才设置 `POWERCONTEXT_MODE=local`。

## 项目结构

```
SmartKnowledgeHub/
├── app.py                          # Flask 路由
├── config.py                       # 路径与环境配置
├── init_db.py                      # 初始化检索库与示例记忆
├── requirements.txt
├── services/
│   ├── seekdb_service.py           # SQLite + FTS5 检索层（seekdb 兼容接口）
│   ├── powercontext_remote.py      # 真实 PowerContext HTTP 客户端
│   ├── powercontext_service.py     # 后端选择 + 本地兼容实现
│   └── knowledge_service.py        # 业务整合
├── templates/                      # 首页、检索、文档、仪表盘
├── static/css/style.css
├── web/                            # Qoder Sites 展示页（静态）
├── docs/
│   ├── TECHNICAL_BOUNDARIES.md     # 技术真实性与边界说明
│   ├── screenshots/                # 实机截图
│   ├── qoder-sessions/             # Qoder 对话证据（需求拆解 / 编码 / 调试）
│   └── logs/                       # PowerContext 原始 HTTP 调用日志
├── tools/
│   └── capture_powercontext_log.py # 原始调用日志采集脚本
├── RUNNING.md
├── QUICKSTART.md
├── QODER_DEVELOPMENT_LOG.md
├── SUBMISSION_INFO.md
└── SUBMISSION_CHECKLIST.md
```

运行时数据在 `data/`：`seekdb.db`（文档与全文索引）与 `powercontext.db`（本地记忆，仅在 local 模式或回退时使用）。

## 验证样例（本机实测）

### 样例 1：检索

1. 首页或 `/search` 输入「深度学习」
2. 预期命中 1 篇《深度学习入门指南》

实测：1 个结果，相关度 100%，分类「人工智能」，标签含 深度学习 / 机器学习 / 神经网络 / CNN / RNN。

### 样例 2：学习进度保存与恢复

1. 打开 `/document/1`
2. 点击 50%
3. 关闭后重新打开

实测：进度稳定在 50%，仪表盘「继续学习」出现该文档，PowerContext 中存在 `learning_progress_1`。

### 样例 3：仪表盘统计与召回

1. 打开 `/dashboard`
2. 查看统计、最近搜索、上下文召回

实测（真实 PowerContext 模式）：已浏览 4、完成学习 1、搜索 5、学习时长 1h46m；召回包含偏好、进度、搜索历史、浏览记录；页头显示 `PowerContext Server 1.4.1`。

### 针对性回归

- 浏览 180 秒后，总学习时长 6200 → 6380 秒
- 相关文档检索带 `record=0`，不写入搜索历史
- 同一关键词连续搜索两次，搜索计数只增加 1
- `/api/analytics/<user>` 返回 `backend: remote`

## API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查，含实际上下文后端 |
| `/api/search?q=&user_id=&category=&record=` | GET | 文档检索；`record=0` 不写搜索历史 |
| `/api/document/<id>` | GET / POST | GET 读取详情与进度；POST 上报浏览时长（支持表单/JSON） |
| `/api/document` | POST | 添加文档 |
| `/api/progress/<id>` | POST | 保存学习进度 |
| `/api/dashboard/<user_id>` | GET | 仪表盘数据 |
| `/api/analytics/<user_id>` | GET | 学习统计 |
| `/api/preferences/<user_id>` | GET / POST | 用户偏好 |
| `/api/memory/search/<user_id>` | GET | 记忆搜索 |
| `/api/memory/recall/<user_id>` | GET | 上下文召回 |
| `/api/powercontext/status` | GET | 当前上下文后端与连接信息 |

## 本轮修复

- 学习时长长期为 0：`sendBeacon` 发往只允许 GET 的接口返回 405；已支持 POST，并让分析接口汇总 `view_duration`
- 相关文档被记为搜索、出现重复历史：相关推荐请求改为 `record=0`；相同查询 30 秒内只保留一条
- 技术真实性：新增真实 PowerContext 远程客户端；检索侧如实标注为 SQLite FTS5 兼容检索层

## Qoder 开发证据

- `docs/qoder-sessions/`：需求拆解、编码实现、调试排错三类对话截图（附 HTML 原文，敏感信息已移除）。
- `docs/logs/powercontext-calls-2026-11-03.log`：真实 PowerContext 的原始 HTTP 请求与响应，覆盖 scope、remember、search、prepare、retire。
- `docs/TECHNICAL_BOUNDARIES.md`：技术边界、实测记录与已知限制。

## 提交信息

- 仓库：https://github.com/qiu-ggg/powercontext
- 分支：`2026-competition-ecosystem`
- 作品目录：`qoder/`
- Qoder UID：`01a19235-1324-7a33-89c7-ecb6d3abe5bf`
- Qoder Sites：https://smartknowledgehub-2yrvvh4q95p.qoder.zone
- 线上演示：https://grudge-tavern.apps.workbuddy.host/?sharecode=UNV2MJ3RH3（静态快照，`/api/*` 不可用，不作为本次验收依据）

## 许可证

MIT License
