# PowerContext 原始调用日志

- `powercontext-calls-2026-11-03.log`：脚本直接发给真实 PowerContext Server 1.4.1 的 HTTP 请求与原始响应。
- 抓取脚本：`tools/capture_powercontext_log.py`
- 环境：Windows 11，PowerContext Server 1.4.1，`127.0.0.1:8000`，SQLite 存储，访问模式 `disabled`
- 覆盖接口：`/health/ready`、`/v1/capabilities`、`/v1/scopes`、`/v1/memory/remember`、`/v1/memory/search`、`/v1/context/prepare`、`/v1/memory/entries/list`、`/v1/memory/entries/retire`

日志中的关键结果：
- Scope 幂等创建，返回 `scp_1grbwtytbjp9ejqwnd4pw6d7gx`
- 写入探针记忆后返回 `entry_id` 与 `state: "active"`
- 搜索返回 `mode: "fts"`，命中同一条记忆
- `context/prepare` 返回带 citation 的 prepared context
- retire 后条目状态变为 `inactive`

复现：

```bash
python tools/capture_powercontext_log.py
```

脚本不依赖应用的本地兼容实现，也不会写入令牌或个人信息。探针记忆在抓取结束时会停用，避免污染业务数据。
