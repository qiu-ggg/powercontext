# 技术实现与真实性说明

本文件回答一个问题：seekdb 和 PowerContext 在这个项目里到底是怎么用的。

## 结论

| 技术 | 使用方式 | 是否可以称为「使用了该技术」 |
|------|----------|------------------------------|
| PowerContext | 真实 PowerContext Server 1.4.1，HTTP API v1.4；Scope、Memory 读写/更新/停用、搜索均由服务端完成 | 可以。本机已实测 remember、原子记忆更新、list、search、lifecycle，原始日志见 `docs/logs/` 与 `docs/evidence/` |
| seekdb | 未连接 seekdb 服务。检索层是 **SQLite FTS5 兼容检索层**，接口与结果结构对齐 seekdb 的检索模式 | 属于「seekdb 兼容检索层」，不能称为「已接入 seekdb」 |

赛制要求 seekdb、PowerContext 至少使用一种。本项目选择以 **PowerContext 真实服务**满足技术结合要求；seekdb 方向作为兼容检索层保留，并在页面、README 和本文件中明确标注，不冒充真实服务。

## PowerContext：真实服务的调用链

代码位置：

- `services/powercontext_remote.py`：真实服务的 HTTP 客户端（仅标准库 `urllib`）
- `services/powercontext_service.py`：按 `POWERCONTEXT_MODE` 选择后端；默认 `remote`，`local` 仅用于离线预览
- `services/knowledge_service.py`：业务层不区分后端，读写记忆统一走上述接口

实测环境：

- Windows 11，应用使用 Python 3.10.11
- PowerContext 1.4.1 安装在独立 venv（Python 3.12.14），监听 `127.0.0.1:8000`
- 存储：SQLite；访问模式：`disabled`
- 未配置生成/嵌入模型，因此搜索返回 `mode: "fts"`

接口映射：

| 业务动作 | PowerContext API |
|----------|------------------|
| 用户空间 | `POST /v1/scopes`，幂等键 `smart-knowledge-hub:{user_id}` |
| 新增记忆 | `POST /v1/memory/remember` |
| 更新记忆 | `PUT /v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}`，请求头 `If-Match: "revision:N"`；409/412/428 时重读修订号后重试一次 |
| 读取全部活动记忆 | `POST /v1/memory/entries/list` |
| 记忆搜索 | `POST /v1/memory/search` |
| 删除/停用 | `POST /v1/atomic-memory/lifecycle`，`state=forgotten` |

### 原始调用日志（2026-11-03）

除下面的摘要外，仓库保留了脚本直接发出的完整 HTTP 请求与原始响应：

- 日志：`docs/logs/powercontext-calls-2026-11-03.log`
- 抓取脚本：`tools/capture_powercontext_log.py`
- 覆盖：`GET /health/ready`、`POST /v1/scopes`、`POST /v1/memory/remember`、`POST /v1/memory/search`、`POST /v1/context/prepare`、`POST /v1/memory/entries/retire`、`POST /v1/memory/entries/list`
- 实测作用域：`scp_1grbwtytbjp9ejqwnd4pw6d7gx`
- 搜索返回 `mode: "fts"`；`context/prepare` 返回带 citation 的 prepared context；retire 后条目状态为 `inactive`

> 说明：上面的日志是较早一次采集，服务返回旧 citation 结构。随后用独立 HOME 启动了新的 1.4.1 实例做最终验证（`127.0.0.1:8001`），二次保存同一 kind 时响应以 `artifact` + `state_version` 为主，旧客户端会抛 `KeyError: citation`；生产客户端因此改为原子记忆 `PUT` + `If-Match`，停用改用 lifecycle。最终验证的启动日志与 12 个 HTTP 响应见 `docs/evidence/`，其中 `search_history` 的 `artifact.revision` 从 3 递增到 4。

### 最终验证：1.4.1 原子记忆写入（2026-11-03）

- 启动日志：`docs/evidence/remote-run.log`
- HTTP 样本：`docs/evidence/api-samples.log`
- 实例：PowerContext Server 1.4.1，SQLite 存储，`127.0.0.1:8001`，独立 HOME
- 关键结果：`GET /api/health` 返回 `"powercontext":"remote"` 与 `"retrieval":"SQLite FTS5 兼容检索层（未连接 seekdb 服务）"`；`/api/memory/recall`、`/api/memory/search`、`/api/dashboard` 均返回真实数据
- 写入证明：`search_history` 的 `artifact.revision` 从 3 递增到 4，说明同一记忆被真实服务更新，而不是写本地 SQLite
- 复现命令见 `docs/evidence/README.md`

### 实测记录（2026-11-02）

创建 Scope：

```http
POST /v1/scopes
{"title":"Smart Knowledge Hub · demo_user","summary":"学习与科研记忆作用域","idempotency_key":"smart-knowledge-hub:demo_user"}
```

返回：

```json
{"scope_id":"scp_7nqcgr26xa07n99yc9jqq762n1","version":1}
```

写入记忆（业务代码使用 kind = 记忆键，例如 `learning_progress_1`）：

```http
POST /v1/memory/remember
{"scope_id":"scp_7nqcgr26xa07n99yc9jqq762n1","kind":"learning_progress","text":"用户正在学习文档《深度学习入门指南》，当前进度 50%。"}
```

返回包含 `entry.citation.entry_id`、`version`、`state:"active"`，说明记忆由服务端持久化。

搜索记忆：

```http
POST /v1/memory/search
{"scope_id":"scp_7nqcgr26xa07n99yc9jqq762n1","query":"学习进度 深度学习","limit":5}
```

返回：

```json
{"memory":{"family":"memory","artifact_id":"memory","revision":1},
 "mode":"fts",
 "hits":[{"citation":{"entry_id":"mem_ent_..."},"text":"用户正在学习文档《深度学习入门指南》，当前进度 50%。","score":0.0164,"matched_by":["fts"]}]}
```

应用侧验证：

```bash
curl http://127.0.0.1:5000/api/health
# {"powercontext":"remote","powercontext_detail":{"mode":"remote","version":"API v1.4（PowerContext Server 1.4.1）"}}

curl http://127.0.0.1:5000/api/analytics/demo_user
# {"backend":"remote","total_study_time":6380,"total_searches":5,...}
```

`init_db.py` 在 `POWERCONTEXT_MODE=remote` 下的输出：

```
步骤 2/3: 初始化 PowerContext...
  后端: remote (API v1.4（PowerContext Server 1.4.1）)
  ✓ 已清理 demo_user 的旧记忆 (6 条)
  ✓ 用户偏好已保存
  ✓ 学习进度已保存 (3 篇文档)
  ✓ 搜索历史已保存 (3 条)
  ✓ 浏览记录已保存 (4 篇文档)
  PowerContext 初始化完成: 4 篇已浏览, 3 次搜索, 学习时长 6200 秒
```

### 模式选择与回退

- `remote`（默认）：使用真实服务；不可达直接抛错，避免把本地写入误当成真实服务
- `auto`：启动时探测服务；可用则使用真实服务，不可用则回退本地实现
- `local`：使用本地实现，仅用于没有 Python 运行时的离线预览

无论哪种模式，`GET /api/health`、首页徽标、检索页与仪表盘都会显示实际后端，不会把本地实现标成远程服务。

## seekdb：本地兼容检索层

实现位置：`services/seekdb_service.py`

已实现：

- `documents` 表保存文档（标题、正文、分类、标签、时间）
- FTS5 虚拟表 `documents_fts`（unicode61 分词）+ INSERT/UPDATE/DELETE 触发器
- `hybrid_search()`：FTS5 关键词检索、分类过滤、相关度归一化排序
- 统计与分类列表接口

未实现 / 明确不属于本项目：

- 没有连接 seekdb 或 OceanBase 的 MySQL 协议端口
- 没有真实向量索引或嵌入模型；`vector_score` 为预留字段，恒为 0，不参与最终排序
- 因此不能声称「所有文档存储和搜索均通过 seekdb 完成」

这条路线保留的原因是：检索接口与结果结构稳定，后续若部署 seekdb，可在不改业务层的情况下替换存储实现。

## 运行时与部署边界

- 本地运行：Flask + SQLite；真实 PowerContext 默认必选（`POWERCONTEXT_MODE=remote`，不可达即报错）
- Qoder Sites：只发布静态展示页（`web/`），不执行 Flask，`/api/*` 不可用；页面已明确标注为静态快照
- WorkBuddy：旧版部署，同为静态快照，不能作为运行验收依据

## 已知限制

1. PowerContext 服务当前只在本机验证，未提供公网常驻实例；Qoder Sites 展示页是静态快照，应用需按 `RUNNING.md` 本地运行。
2. PowerContext 未配置嵌入模型，记忆搜索为 FTS，不是向量检索。
3. seekdb 未接入真实服务；向量检索只是预留字段。
4. 示例数据为 12 篇自建资料，使用数据规模有限，不把它包装成真实用户量。
