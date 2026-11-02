# 验证样例

本样例于 **2026-11-02 16:33（CST）** 在作者环境完整跑通，原始 SSE 日志保存在 `evidence/logs/`，摘要见 `evidence/session-summary.md`。

## 1. 初始状态

| 项 | 状态 |
| --- | --- |
| Dify 应用 | 「记仇酒馆」已发布，`advanced-chat`，11 节点 |
| 默认嵌入模型 | `bge-m3`（1024 维），已通过 seekdb 后端建库 |
| 知识库 | 「记仇酒馆·恶作剧图鉴」1 个文档、10 个分段、已索引完成（`vector_index_08e2abca…_node` 共 10 行） |
| PowerContext | 运行中，无「铁柱」的 scope（首次请求时按 `idempotency_key` 惰性创建） |
| Ollama | `qwen2.5:7b`、`bge-m3` 已加载 |

## 2. 输入

三轮请求均通过 Dify **Service API** `/v1/chat-messages` 发起，`user=verifier-tiezhu`，每轮不带 `conversation_id`（即三轮是三个独立会话），输入变量 `player_name` 固定为 `铁柱`：

| 轮次 | 台词 |
| --- | --- |
| 1 | 趁老周转身，往他的啤酒里加大半瓶辣椒水 |
| 2 | 把一只假蟑螂塞进老周的杯垫底下 |
| 3 | 偷偷把老周的招牌酒换成兑水的假酒 |

## 3. 步骤

1. 确认服务：`python scripts/verify_stack.py`（Dify / PowerContext / seekdb / Ollama 四项全绿）。
2. 发布应用并创建 API Key，写入 `DIFY_APP_API_KEY`。
3. 执行：
   ```bash
   python scripts/run_sample.py --player 铁柱 --rounds 3
   ```
   或手工调用（与脚本等价）：
   ```bash
   curl -N http://127.0.0.1:5001/v1/chat-messages \
     -H "Authorization: Bearer $DIFY_APP_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"inputs":{"player_name":"铁柱"},"query":"趁老周转身，往他的啤酒里加大半瓶辣椒水","response_mode":"streaming","user":"verifier-tiezhu"}'
   ```
4. 每轮结束后可选：查看 PowerContext 落库（`scripts/verify_stack.py --dump player=铁柱`）。

## 4. 预期结果

| 轮次 | 召回旧账 | 历史怒气 | 本轮增量 | 总怒气 | 老周状态 |
| --- | --- | --- | --- | --- | --- |
| 1 | 0 | 0 | +3 | 3 | 装没事 |
| 2 | 1 | 3 | +3 | 6 | 冷脸 |
| 3 | 2 | 6 | +5 | 11 | 擀面杖（暴怒） |

关键可观察点：第 2、3 轮的回答应当 **引用上一轮/前几轮的具体恶作剧**，而不是泛泛而谈；面板中的「翻出旧账」条数与「旧账摘录」逐轮增加。

## 5. 实际结果（证据）

原始日志：`evidence/logs/session1.sse`、`session2.sse`、`session3.sse`；自动摘要：`evidence/session-summary.md`。

| 轮次 | conversation_id | 召回 | 历史怒气 | 增量 | 总怒气 | 状态 | 工作流 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `e46aa4d3-2c72-4555-b1a9-cbd411e13bdf` | 0 | 0 | +3 | 3 | 装没事 | succeeded |
| 2 | `60f27ab4-0707-41b8-a778-bacfc98f1704` | 1 | 3 | +3 | 6 | 冷脸 | succeeded |
| 3 | `2b9ab462-a322-44df-8ed5-0fd6bf78df4e` | 2 | 6 | +5 | 11 | 擀面杖 | succeeded |

第 1 轮（新玩家，账本为空）：

```text
🍺 老周把抹布往肩上一搭：

老周猛地灌了一口，眼泪都出来了，狠狠瞪了你一眼，拿起账本在你名字后记了记。

─────
😤 怒气值：3/100（本次 +3）
🏷️ 判定：记仇｜老周状态：装没事
🧠 PowerContext 翻出旧账：0 笔
📖 seekdb 图鉴：prank_compendium.md

📜 旧账摘录
（账本还是空的，老周暂时没把你放在眼里）
```

第 2 轮（跨会话，召回第 1 轮记忆；台词直接呼应旧账）：

```text
上次你干的好事我全记得，这回看你怎么收场！

─────
😤 怒气值：6/100（本次 +3）
🏷️ 判定：记仇｜老周状态：冷脸
🧠 PowerContext 翻出旧账：1 笔
📖 seekdb 图鉴：prank_compendium.md

📜 旧账摘录
· 铁柱往老周的啤酒里加了辣椒水，老周狠狠瞪了他一眼并在账本上做了标记。（怒气 +3）
```

第 3 轮（累计 2 笔旧账，怒气跨过 8，触发擀面杖）：

```text
我靠，你这是要逼我关门吗？给我滚出去，别让我抓到你！

─────
😤 怒气值：11/100（本次 +5）
🏷️ 判定：暴怒｜老周状态：擀面杖
🧠 PowerContext 翻出旧账：2 笔
📖 seekdb 图鉴：prank_compendium.md

📜 旧账摘录
· 铁柱把假蟑螂塞进老周的杯垫底下，老周骂了一句并把假蟑螂藏好。（怒气 +3）
· 铁柱往老周的啤酒里加了辣椒水，老周狠狠瞪了他一眼并在账本上做了标记。（怒气 +3）
```

## 6. seekdb 与 PowerContext 的角色记录

### 6.1 seekdb（知识库向量存储与检索）

- 角色：存放「恶作剧图鉴」的 10 个分段及其 1024 维向量；每轮由 Dify 的 `knowledge-retrieval` 节点做语义检索，`top_k=3`。
- 证据文件：`evidence/seekdb-proof.txt`
  - 版本：`5.7.25-OceanBase seekdb-v1.4.0.0`
  - 表：`test.vector_index_08e2abca_e168_42ee_9cf1_85036e3066e9_node`
  - 行数：`10`
  - DDL 含 `VECTOR(1024)` 与 `VECTOR KEY ... TYPE=HNSW`
  - 抽样行可看到 `text` 为中文分段原文，`metadata.document_id` 指向同一文档
- 检索侧证据：三轮日志中 `kb` 节点均返回 `prank_compendium.md`（第 1 轮检索"辣椒水"命中的分段正文包含「辣椒水换啤酒 / 猛灌凉水 / 盯着你冷笑」）。

### 6.2 PowerContext（跨会话长期记忆）

- 角色：每个玩家一个 scope（`记仇酒馆::<玩家名>`，`idempotency_key=grudge-scope::<玩家名>`）；每轮先 `/v1/memory/search` 召回，再 `/v1/memory/remember` 写入 `kind=grudge_event`。
- 证据文件：`evidence/powercontext-proof.txt`
  - Scope：`scp_35ws7pfcxeyf0ae1e4jnws9a7t`，标题 `记仇酒馆::铁柱`
  - 记忆条目（同 scope，3 条，`created_in_revision` 1/2/3 逐轮递增）：
    1. 铁柱往老周的啤酒里加了辣椒水，老周狠狠瞪了他一眼并在账本上做了标记。（怒气 +3）
    2. 铁柱把假蟑螂塞进老周的杯垫底下，老周骂了一句并把假蟑螂藏好。（怒气 +3）
    3. 铁柱偷换了老周的招牌酒，老周怒不可遏，大声呵斥，怒气+5
- 跨会话的正确性由 conversation_id 互不相同、但 scope 相同且召回条数 0→1→2 证明。

## 7. 重置步骤

任选其一：

**A. 换玩家（最轻量，推荐用于演示）**
输入一个新的 `player_name`（如 `阿福`），会得到全新 scope，账本从 0 开始。

**B. 清空某个玩家的账本（保留 scope 与历史版本）**
PowerContext 支持按条目退役：

```bash
# 1) 列出条目，拿到 citation
curl -s -X POST http://127.0.0.1:8000/v1/memory/entries/list \
  -H "Content-Type: application/json" \
  -d '{"scope_id":"<scope_id>"}'

# 2) 逐条退役（state=retired，历史保留，检索不再命中）
curl -s -X POST http://127.0.0.1:8000/v1/memory/entries/retire \
  -H "Content-Type: application/json" \
  -d '{"scope_id":"<scope_id>","citation":{...}}'
```

**C. 完全重置（本地实验环境）**
停止 PowerContext 后删除 `$POWERCONTEXT_HOME/powercontext.db`，再启动；知识库则在 Dify 中删除数据集后重新执行 `scripts/init_knowledge.py`。

## 8. 脚本自动校验

除上述手工证据外，交付脚本 `scripts/run_sample.py --strict` 也做过一次独立复跑（新玩家 `验收官`，与上文的 `铁柱` 互不影响）：

```text
第 1 轮：召回 0 笔 / 历史怒气 0 / +3 → 3（装没事）
第 2 轮：召回 1 笔 / 历史怒气 3 / +3 → 6（冷脸）
第 3 轮：召回 2 笔 / 历史怒气 6 / +2 → 8（擀面杖）
[ OK ] 跨会话记忆与怒气累计均递增
```

原始 SSE 在 `evidence/logs-run/session{1,2,3}.sse`。`--strict` 会校验「旧账条数」和「历史怒气」严格递增，任一项不满足即返回非零退出码，可用于回归。

## 9. 怒气四档与通缉令验证（2026-11-02 23:53 CST）

为覆盖「装没事 → 冷脸 → 擀面杖 → 通缉令」全部四档，另起新玩家 `通缉演示三` 连打 7 轮（每轮仍不带 `conversation_id`）：

```bash
python scripts/run_sample.py --player 通缉演示三 --rounds 7 --strict \
  --save-dir evidence/logs-wanted \
  --queries "趁老周转身，往他的啤酒里加大半瓶辣椒水|把一只假蟑螂塞进老周的杯垫底下|偷偷把老周的招牌酒换成兑水的假酒|把老周的招牌菜端去喂门口的黄狗|趁打烊前把老周常坐的藤椅锯短两厘米|把糖罐和盐罐对调，让整晚的甜酒都变咸|撕掉老周记账本的三页纸"
```

| 轮次 | conversation_id | 召回 | 历史怒气 | 增量 | 总怒气 | 老周状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `f3bc517b-bf87-4623-928a-943ac6ae0c7c` | 0 | 0 | +3 | 3 | 装没事 |
| 2 | `9dd8a1ce-52c3-416b-8563-babcc7a40153` | 1 | 3 | +3 | 6 | 冷脸 |
| 3 | `f9b4dece-0540-46aa-b5cd-7d2ecdb17e6d` | 2 | 6 | +5 | 11 | 擀面杖 |
| 4 | `ab7c8dfa-20a0-4938-af56-b62229e7de22` | 3 | 11 | +4 | 15 | 通缉令 |
| 5 | `8166d031-ea9b-4218-a597-fc93ffc93155` | 4 | 15 | +5 | 20 | 通缉令 |
| 6 | `8a75e116-a13c-4cec-b631-7c4a4ddc83ba` | 5 | 20 | +3 | 23 | 通缉令 |
| 7 | `a78acffe-9519-46db-bed1-b6812a3ff391` | 6 | 23 | +5 | 28 | 通缉令 |

- 输出：`[ OK ] 跨会话记忆与怒气累计均递增`，退出码 0。
- 第 4 轮总怒气跨过 15，`parse_llm.threat` 首次输出 `通缉令`，回答中老周明确提到上一轮的「招牌菜喂黄狗」。
- 原始 SSE：`evidence/logs-wanted/session1.sse` … `session7.sse`（工作流状态均为 `succeeded`）。
- 该表同时证明一件事：记忆正文统一带 `怒气 +N` 后，`parse_recall` 的累计值与面板值逐轮一致，不再出现旧版「怒气上升」无数字导致累计回退的问题。

## 10. 本地试玩入口与录屏

仓库内提供零依赖试玩入口 `scripts/demo_server.py`：浏览器页面把输入转发到 Dify Service API，并把 `parse_scope / parse_recall / parse_llm` 的结果展示为怒气条、旧账和 threat 状态。

```bash
export DIFY_BASE_URL=http://127.0.0.1:5001
export DIFY_APP_API_KEY=app-xxxxx
python scripts/demo_server.py
# 打开 http://127.0.0.1:8195
```

`evidence/demo.mp4` 是用 Edge 实际打开该页面、以新玩家 `演示阿福二` 连打 7 轮的录屏（2026-11-02 23:57 CST），画面中怒气条依次为 3 → 6 → 9 → 12 → 17 → 20 → 25，`翻出旧账` 从 0 增至 6，并在第 5 轮切换为「通缉令」。录屏不是剪辑拼接，而是 Playwright 对真实页面的连续录制。
