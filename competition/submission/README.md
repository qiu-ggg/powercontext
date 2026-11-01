# PowerContext 提测说明

本目录是 PowerContext 赛道的提测材料，只新增文件，不改动仓库内任何既有实现。

## 1. 提测坐标

| 项 | 值 |
| --- | --- |
| 仓库 | `qiu-ggg/powercontext`（公开，评委可直接拉取） |
| 分支 | `2026-competition` |
| 分支 HEAD | `bc3eb468b6a16e6435e8c9eced86215affa55639` |
| 冻结基线 | `9db1753434162c0aa7c9f1189a1722e617880a52`（`PowerContext v1.2.0`） |
| 祖先关系 | 成立：`compare` 结果为 `ahead 11 / behind 0`，`merge_base` 等于基线本身 |

提测表单里的 commit 字段请填完整的 40 位十六进制值，不要填分支名或短 SHA。

## 2. 提交前自查清单

以下五项按赛事群里公开的失败分布排序，权重从高到低。前两项占了全部错误提交的六成，且都是**格式问题**，本地跑通也救不回来。

- [ ] **基线祖先关系**：`git merge-base --is-ancestor 9db1753434162c0aa7c9f1189a1722e617880a52 HEAD` 退出码必须是 0。直接把改动合到上游 master 上会判定失败。
- [ ] **仓库地址格式**：`https://<用户名>:<只读令牌>@github.com/<所有者>/<仓库>`。不要填 SSH 地址，不要带 `/tree/<分支>` 子路径，不要用带空格的仓库名。
- [ ] **分支存在于远端**：`git ls-remote --heads origin` 能看到 `2026-competition`。只存在于本地不算。
- [ ] **commit 是合法 SHA**：`git rev-parse HEAD` 的输出，7–64 位十六进制。
- [ ] **提测后不要 force-push**：会删掉对应的历史，已提交的 SHA 变成不可达，该次提交判为 commit 不存在。

补充一条赛事文档反复强调的：**不要把带令牌的仓库地址、密码、SSH 私钥贴进任何文件、截图或聊天**。令牌只给 `Contents: Read-only` 权限。

## 3. 各题落点与验证状态

“本机验证”一列指在本机（macOS，Intel）跑对应 `challenges/<题目>/acceptance` 的结果，不代表评测环境的最终判定。

| 题目 | 实现落点 | 本机验证 | 说明 |
| --- | --- | --- | --- |
| `setup-00-repository-fork` | 分支与基线 | 已核对 | 祖先关系成立，见上表 |
| `source-01-table-evidence` | `src/powercontext/builtin/sources/` | 通过 | CSV 行级采集与原始记录回查 |
| `source-02-pi-history` | `src/powercontext/builtin/sources/` | 通过 | Pi 会话增量 checkpoint |
| `source-03-pdf-retrieval` | `src/powercontext/builtin/sources/` | 通过 | 标题/短语感知的页级召回 |
| `memory-01-source-lifecycle` | `src/powercontext/builtin/runtime/` | 通过 | 证据 DAG 传播 Source 可用性 |
| `memory-02-embedding-batches` | `src/powercontext/builtin/inference/` | 通过 | LRU 向量缓存合并并发嵌入调用 |
| `context-01-evidence-selection` | `src/powercontext/builtin/runtime/` | 通过 | UTF-8 字节预算下的字面证据片段选择 |
| `context-02-incremental-pack` | `src/powercontext/builtin/runtime/context_pack.py` | 14/14 通过 | 传输成本门槛本地无法复现，见第 4 节 |
| `processing-01-count-trigger` | **未合入**，见 `patches/` | 17/17 通过（补丁副本上） | 本仓库尚未应用补丁，该题当前不计分 |
| `retrieval-01-reranking` | `src/powercontext/builtin/` | 通过 | HTTP cross-encoder 重排适配器 |
| `retrieval-02-hybrid-search` | — | 无法本机验证 | 依赖 seekdb 嵌入二进制，见第 4 节 |

## 4. 已知风险

**`processing-01-count-trigger` 是当前唯一明确的功能缺口。** 仓库里的 `config.py` 与 `artifact_processing.py` 仍是冻结基线原文，没有计数准入通道，因此该题的验收用例无法通过。补丁与说明见：

- `patches/processing-01-count-trigger.patch`
- `processing-01-count-trigger.md`

补丁基于冻结基线生成，已用 `patch -p1 --dry-run` 验证可干净应用，应用后与开发分支逐字节一致。**应用补丁会改动三个既有文件，因此本轮未自动执行**，需要人工确认后合入。

**`context-02` 的传输成本门槛没有被证明。** 验收用例 14 项全通过，但官方门槛是“增量传输字节相对全量字节至少省 45%”。本地用 40 轮对话复现时，三种切换节奏下的节省率都是负的（−0.70 ～ −0.78）。原因已定位：`prepare` 输出里第一个发生变化的字节落在第 406 字符附近，基于前缀复用的协议在第一个 chunk 就断掉，而 Base64 的 4/3 膨胀又让增量比原始正文更长。当前实现没有针对这个门槛做优化，实际是否达标取决于评测序列里上下文的稳定程度，本地无法给出结论。

**`retrieval-02-hybrid-search` 在本机无法验证。** 它依赖 `@seekdb/js-bindings`，该包只发布 `linux-x64`、`linux-arm64`、`darwin-arm64` 三种二进制，README 明确写了不支持 macOS x64。本机是 Intel Mac，且没有 Docker / Podman / Colima / Homebrew，无法搭出可运行的 seekdb 环境。

## 5. 如何复跑验收

```bash
cd competition
python -m pytest challenges/<题目目录> -q \
  -o addopts="-p no:cacheprovider --import-mode=importlib" \
  --basetemp=/tmp/pcrun
```

`-o addopts=...` 是必须的：仓库 `pytest.ini` 里的 `-p pytest_asyncio.plugin` 与新版插件的入口点重名，会报 `Plugin already registered under a different name`。`--basetemp` 指向仓库外，避免临时目录落在受限路径下。

`processing-01` 需要额外装 `anthropic`，否则 topic-memory 的子进程会因为 `from anthropic import AsyncAnthropic` 失败，日志里只有 `worker_failed`，看不到真实原因。
