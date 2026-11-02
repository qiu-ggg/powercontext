# 提交信息（SUBMISSION_INFO）

- 作品名称：智能知识库（Smart Knowledge Hub）
- 仓库：https://github.com/qiu-ggg/powercontext
- 分支：`2026-competition-ecosystem`
- Commit id：以本分支最新提交为准（`git rev-parse HEAD`）；压缩包外层 `SUBMISSION_INFO.md` 记录最终 SHA
- 作品目录：仓库中的 `qoder/`
- 作品链接（Qoder Site）：https://smartknowledgehub-2yrvvh4q95p.qoder.zone （静态快照，`/api/*` 不可用）
- Qoder 账号 UID：`01a19235-1324-7a33-89c7-ecb6d3abe5bf`

## Qoder 开发证据

| 环节 | 文件 |
|------|------|
| 需求拆解 | `docs/qoder-sessions/01-requirements.png` |
| 编码实现 | `docs/qoder-sessions/02-coding.png` |
| 调试修复 | `docs/qoder-sessions/03-debugging.png` |
| Qoder Site 发布 | `docs/screenshots/qoder-site.png` |

截图来自本机 Qoder 会话记录，已脱敏与节选，HTML 原文在同目录。

## PowerContext 原始调用日志

- `docs/logs/powercontext-calls-2026-11-03.log`：完整请求与响应（较早一次采集）
- `docs/evidence/remote-run.log`：最终 1.4.1 实例启动日志与 `/health/ready`
- `docs/evidence/api-samples.log`：12 个真实 HTTP 响应，含 `artifact.revision` 递增
- `tools/capture_powercontext_log.py`：采集脚本
- 覆盖 `/v1/scopes`、`/v1/memory/remember`、`/v1/memory/search`（`mode: "fts"`）、
  `/v1/context/prepare`、原子记忆更新与 lifecycle

## 运行方式

PowerContext Server 1.4.1 为必选依赖，默认 `POWERCONTEXT_MODE=remote`：

```bash
cd qoder
python -m pip install -r requirements.txt
python init_db.py
python app.py
```

详细步骤见 `RUNNING.md`，边界说明见 `docs/TECHNICAL_BOUNDARIES.md`。

## 技术真实性

- PowerContext 1.4.1：真实 HTTP 服务接入，默认 remote，已实测；记忆更新使用原子记忆 PUT + `If-Match`，停用使用 lifecycle。
- 检索层：本地 SQLite FTS5 兼容检索层，未声称运行官方 seekdb。
- Qoder Sites 展示页：静态快照，`/api/*` 不可用；功能需按 `RUNNING.md` 本地运行。
- WorkBuddy 旧演示站：同为静态快照，不作为验收证据。
