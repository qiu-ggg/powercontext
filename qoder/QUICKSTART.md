# 快速开始指南

> 5 分钟在本机跑起智能知识库。完整步骤见 [RUNNING.md](RUNNING.md)。

## 前置条件

- Python 3.8+：运行 Flask 应用
- Python 3.11+：运行真实 PowerContext Server 1.4.1（默认 `remote` 模式的必需依赖）

## 1. 启动 PowerContext Server

```bash
python -m venv .pc-venv
.pc-venv\Scripts\python -m pip install "powercontext[server,cli]"
.pc-venv\Scripts\powercontext config init --template --language zh --output .env --force
.pc-venv\Scripts\powercontext server run --env-file .env --role all
```

确认服务就绪：

```bash
curl http://127.0.0.1:8000/health/ready
```

## 2. 安装应用依赖

```bash
cd qoder
python -m pip install -r requirements.txt
```

依赖：Flask 3.0.0、flask-cors 4.0.0、python-dotenv 1.0.0。

## 3. 初始化数据

```bash
python init_db.py
```

会创建 `data/seekdb.db`（SQLite + FTS5 检索层）并导入 12 篇示例文档，同时把偏好、学习进度、搜索历史与浏览记录写入真实 PowerContext 服务。脚本会先停用 `demo_user` 的旧记忆，因此可以重复执行而不会让统计数字累加。

## 4. 启动应用

```bash
python app.py
```

访问 http://localhost:5000 。默认 `POWERCONTEXT_MODE=remote`，服务不可达会直接报错；离线预览才设置 `POWERCONTEXT_MODE=local`。

## 5. 验证

```bash
curl http://127.0.0.1:5000/api/health
curl "http://127.0.0.1:5000/api/search?q=深度学习&user_id=demo_user"
curl http://127.0.0.1:5000/api/stats
```

`/api/health` 应返回：

```json
{
  "powercontext": "remote",
  "powercontext_detail": {"mode": "remote", "version": "API v1.4（PowerContext Server 1.4.1）"},
  "retrieval": "SQLite FTS5 兼容检索层（未连接 seekdb 服务）"
}
```

## 6. 技术边界

- 检索层：本地 SQLite + FTS5，作为 **seekdb 兼容检索层**，未连接 seekdb 服务。
- 上下文层：真实 PowerContext Server 1.4.1，记忆写入/更新/搜索均走 HTTP。
- Qoder Sites 展示页：静态快照，`/api/*` 不可用；功能需按上面步骤本地运行。

详细说明与真实响应样本见 [docs/TECHNICAL_BOUNDARIES.md](docs/TECHNICAL_BOUNDARIES.md) 与 [docs/evidence/README.md](docs/evidence/README.md)。
