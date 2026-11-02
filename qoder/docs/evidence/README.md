# 本机运行证据

本目录是 Qoder 侧「真实 PowerContext 服务 + SQLite FTS5 兼容检索层」的可核对记录，均为 2026-11-03 本机实际输出，不是手写样例。

| 文件 | 内容 |
| --- | --- |
| `remote-run.log` | PowerContext Server 1.4.1 启动日志、Flask 应用启动输出、`/health/ready` 返回 |
| `api-samples.log` | 应用与 PowerContext 的 12 个真实 HTTP 响应（健康检查、统计、检索、文档、仪表盘、记忆搜索/召回、Scope 幂等创建、记忆列表、服务端搜索） |
| `../screenshots/home-remote.png` | 首页：显示「后端：PowerContext Server 1.4.1」与文档/搜索统计 |
| `../screenshots/search-remote.png` | 检索页：SQLite FTS5 结果 + PowerContext 记忆搜索 |
| `../screenshots/dashboard-remote.png` | 仪表盘：学习进度、最近搜索、上下文召回 |

## 复现命令

```bash
# 1. 启动 PowerContext 1.4.1（本机 8001，避免与 8000 上的旧库冲突）
POWERCONTEXT_HOME=./pc-home POWERCONTEXT_SERVER_HTTP_PORT=8001 \
  powercontext server run

# 2. 初始化数据并启动应用（默认 remote）
export POWERCONTEXT_BASE_URL=http://127.0.0.1:8001
python init_db.py
python app.py

# 3. 核对
curl http://127.0.0.1:5000/api/health
curl http://127.0.0.1:5000/api/stats
curl "http://127.0.0.1:5000/api/search?q=深度学习&user_id=demo_user&record=0"
```

## 关键核对点

- `/api/health` 返回 `"powercontext": "remote"` 与 `"retrieval": "SQLite FTS5 兼容检索层（未连接 seekdb 服务）"`。
- `/api/health` 的 `version` 为 `1.1.1`，`powercontext_detail.version` 为 `API v1.4（PowerContext Server 1.4.1）`。
- `api-samples.log` 中 `search_history` 的 `artifact.revision` 为 4：每次保存都通过
  `PUT /v1/scopes/{scope_id}/artifacts/atomic-memory/{artifact_id}` + `If-Match: "revision:N"` 提交新修订，
  证明写入发生在真实服务，而不是本地 SQLite 兼容实现。
- `/api/stats`（以及 `/api/statistics`）在本机返回 200；线上 Qoder Sites 是静态快照，不运行 Flask，
  因此该接口在展示页域名下不可用，展示页已明确标注。
