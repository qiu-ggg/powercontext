# 比赛提交材料清单

> Qoder × OceanBase 开发比赛提交材料（2026-11-02 更新）

## 基本信息

- **项目名称**: 智能知识库（Smart Knowledge Hub）
- **赛道**: Qoder × OceanBase
- **开发工具**: Qoder
- **技术结合**: PowerContext 1.4.1（真实 HTTP 服务，默认 remote）+ SQLite FTS5 兼容检索层（seekdb 兼容接口，如实标注）
- **项目位置**: `D:\SmartKnowledgeHub`

---

## 提交材料

### 1. 项目网站网址 ✅

**网址**: https://smartknowledgehub-2yrvvh4q95p.qoder.zone

**状态**: 已通过 Qoder Sites 发布
- 发布记录：`get_publish_status` 返回 `published: true`
- 已用无痕环境验证：首页、搜索页、仪表盘、文档页均可访问
- 截图：`docs/screenshots/qoder-site.png`

**内容说明**：该站点是提交展示页（项目说明、技术实现、验证数据、截图、运行方式、材料入口），不是线上 Flask 运行实例。Flask 应用需要按 `RUNNING.md` 在本地启动；线上不能运行 Flask 的原因已在站点和 `docs/TECHNICAL_BOUNDARIES.md` 中写明。

> 注：早期曾用 WorkBuddy 部署过一个旧版演示站。它是静态快照，`/api/*` 返回 403，反映的也是接入真实 PowerContext 之前的版本，不能作为本次验收依据。以本 Qoder Site 与本地可运行源码为准。

---

### 2. 代码仓库 ✅

**仓库**: https://github.com/qiu-ggg/powercontext
**分支**: `2026-competition-ecosystem`
**目录**: 项目资产放在仓库的 `qoder/` 目录下

仓库内容包括：
- [x] 完整项目源码（Flask 应用 + 服务层 + 模板 + 静态资源）
- [x] `README.md` / `RUNNING.md` / `QUICKSTART.md` / `PROJECT_STRUCTURE.md`
- [x] `QODER_DEVELOPMENT_LOG.md`（Qoder 开发记录）
- [x] `docs/TECHNICAL_BOUNDARIES.md`（技术真实性说明与实测记录）
- [x] `docs/screenshots/`（本地运行、Qoder Site 与 Qoder 对话截图）
- [x] `docs/logs/`（PowerContext 原始请求/响应日志）
- [x] `docs/qoder-sessions/`（需求拆解、编码、调试对话截图）
- [x] `requirements.txt` / `.env.example` / `.gitignore`
- [x] `web/`（提交展示页源码）

**公开状态**: 仓库已按要求提供访问权限；提交时使用测评平台登记时的只读令牌，令牌不写入任何文件。

---

### 3. 运行说明 ✅

**文件**: `RUNNING.md`

包含：
- Python 3.8+ 运行 Flask 应用
- 必选接入真实 PowerContext Server 1.4.1（Python 3.11+，安装/初始化/启动/健康检查）
- 默认 `POWERCONTEXT_MODE=remote`；`local` 仅用于离线预览
- 初始化与启动命令、功能验证步骤与回归检查（学习时长、搜索去重）
- 数据重置方式

---

### 4. 验证样例 ✅

**文件**: `QUICKSTART.md`、`README.md`、`docs/TECHNICAL_BOUNDARIES.md`

三个可复现样例：

1. **文献检索**：输入「深度学习」→ SQLite FTS5 兼容检索层返回匹配文档及评分，同时 PowerContext 搜索相关记忆。
2. **学习进度追踪**：文档页标记 25%/50%/75%/100% → PowerContext 保存 `learning_progress` 记忆，刷新后恢复，仪表盘汇总。
3. **个性化仪表盘**：展示浏览数、完成数、累计学习时长、搜索次数、继续学习列表、上下文召回和偏好设置。

**实测数据**（远程模式，2026-11-02）：
- 初始化 12 篇文档
- 学习时长：6200 秒 → 上报 180 秒后变为 6380 秒
- 搜索历史：重复同一关键词只 +1（30 秒去重）；`record=0` 的关联搜索不写入历史
- 仪表盘后端标识：`PowerContext Server 1.4.1`

---

### 5. Qoder 开发记录 ✅

**文件**: `QODER_DEVELOPMENT_LOG.md`

- 需求分析 → 技术选型 → 开发 → 调试 → 部署的完整过程
- 真实问题记录：PowerContext 端口占用、Windows Python 启动器异常、统计字段错位、`sendBeacon` 405、标签搜索污染历史等
- 本轮补充：接入真实 PowerContext、修复统计与去重、重新发布 Qoder Site

---

### 6. 使用效果材料 ✅（基础数据）

- 本地实测截图：`docs/screenshots/`（首页、搜索、仪表盘、Qoder Site）
- 真实服务证据：`docs/TECHNICAL_BOUNDARIES.md`
  - scope：`scp_7nqcgr26xa07n99yc9jqq762n1`
  - `/v1/memory/remember`、`/v1/memory/search`（`mode: "fts"`）、`/v1/memory/entries/list`、`/v1/context/prepare` 均返回真实响应
- 使用规模：当前为开发与自测数据，尚未收集外部用户数据（如实说明，不虚构）

---

## 技术真实性说明

| 组件 | 实际使用方式 | 验收可核对点 |
|------|-------------|-------------|
| PowerContext 1.4.1 | 真实 HTTP 服务，`POWERCONTEXT_MODE=remote` | `data/powercontext.db` 不再被写入；`/api/powercontext/status` 返回 `mode: remote`、`version: 1.4.1`；服务端 scope 与记忆可查询 |
| seekdb | 本地 SQLite + FTS5 兼容检索层，接口与混合检索参数保留，`vector_score` 固定 0.0 | 代码 `services/seekdb_service.py`；`/api/health` 明确标注「seekdb 兼容检索层」；未声称运行了 OceanBase seekdb |

**边界**：本机没有 Docker/WSL，无法运行官方 seekdb 服务，因此没有把 SQLite 说成 seekdb。比赛要求 seekdb / PowerContext 至少接入一个，PowerContext 是真实接入并通过实测的。

---

## 评分维度自评

- **实用价值**：文献检索、学习进度、个性化仪表盘，面向学习与科研场景。
- **使用效果**：功能可复现，统计数据已修正；外部用户数据暂缺。
- **完成度与体验**：搜索、阅读、进度、推荐、偏好完整闭环，响应式界面。
- **技术结合**：PowerContext 真实接入并有调用记录；seekdb 以兼容层实现并明确边界。
- **Qoder 开发实践**：开发记录含真实排错过程，非模板化描述。
- **工程质量**：分层结构、依赖与配置齐全、文档完整、可本地复现。

---

## 提交前检查清单

- [x] Qoder Site 已发布并可访问
- [x] 代码仓库地址与分支确定
- [x] 运行说明可复现
- [x] 验证样例与实测数据
- [x] Qoder 开发记录
- [x] 技术真实性说明
- [x] Qoder 账号 UID：`01a19235-1324-7a33-89c7-ecb6d3abe5bf`
- [x] 最终 Commit id：以最新推送提交为准（`git rev-parse HEAD`，并见 `SUBMISSION_INFO.md`）

---

## 表单填写速查

| 字段 | 填写内容 |
|------|---------|
| 代码仓库地址 | 测评平台已固定，无需修改 |
| Commit id | 推送后执行 `git rev-parse HEAD` 获取完整 40 位 |
| Branch | `2026-competition-ecosystem` |
| 作品链接 | https://smartknowledgehub-2yrvvh4q95p.qoder.zone |
| Qoder UID | `01a19235-1324-7a33-89c7-ecb6d3abe5bf` |
