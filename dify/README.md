# 记仇酒馆 · Grudge Tavern

> 一个用 Dify Chatflow 编排、以 **PowerContext** 做跨会话长期记忆、以 **seekdb** 做恶作剧图鉴向量检索的「记仇 NPC」小游戏。

你在酒馆里对老板老周搞恶作剧。老周不生气——他把每一笔都记进账本。
下一次进门，他会先翻旧账，怒气越高，态度越差；怒气到 8 他抄起擀面杖，到 15 直接下通缉令。

- 核心不是聊天，而是**记忆**：同一玩家跨会话的恩怨会被 PowerContext 真召回，并在回答里被引用。
- 图鉴不是提示词硬编码：招式说明存在 seekdb 向量库里，Dify 用中文语义检索命中后再交给模型。

## 技术组合

| 层 | 组件 | 作用 |
| --- | --- | --- |
| 编排 | Dify 1.18.0（Advanced Chat / Chatflow） | 11 个节点的流程：清洗输入 → 建 scope → 召回旧账 → 检索图鉴 → LLM 判罚 → 写入记忆 |
| 长期记忆 | PowerContext 1.2.0 | 每个玩家一个 scope；`/v1/memory/remember` 写入、`/v1/memory/search` 跨会话召回 |
| 向量库 | OceanBase seekdb 1.4.0 | Dify 内置 `VECTOR_STORE=seekdb` 后端，`vector_index_<dataset>_node` 表存 1024 维向量 |
| 模型 | Ollama 0.40.13：qwen2.5:7b（对话）+ bge-m3（中文嵌入） | 全部本地推理，无需外部 API Key |

## 目录

```
dify/
├── README.md
├── dsl/                 # Dify 应用 DSL（.difypkg 与单文件 .yml 两种形态）
├── docs/                # 运行说明、验证样例、依赖材料、设计说明
├── data/                # 知识库原始数据（恶作剧图鉴）
├── scripts/             # 初始化 / 预置 / 重置 / 验证 / 一键跑样例 / 本地试玩入口
├── backend/             # 自研辅助源码（本地代码沙箱、Chatflow 生成器）
└── evidence/            # 验证 SSE 原始日志、通缉令演示、seekdb / PowerContext 落库证明、试玩录屏
```

## 快速开始

1. 按 [docs/01-run-guide.md](docs/01-run-guide.md) 启动 Dify（seekdb 向量后端）、PowerContext、Ollama。
2. 导入 `dsl/grudge-tavern.difypkg`，按说明配置模型凭据与 Dataset ID。
3. 运行 `scripts/init_knowledge.py` 创建知识库并完成索引，把打印出的 Dataset ID 填回 Chatflow。
4. 发布应用，运行 `scripts/run_sample.py` 连打三轮，观察怒气与旧账变化。
5. 想直接玩：设置 `DIFY_APP_API_KEY` 后运行 `scripts/demo_server.py`，打开 `http://127.0.0.1:8195`。
6. 对照 [docs/02-verification.md](docs/02-verification.md) 与 `evidence/` 复核；`evidence/demo.mp4` 是试玩页面的连续录屏。

## 已验证环境

Windows 11（10.0.26200）× Dify 1.18.0 源码 + 原生 PostgreSQL 17.4 / Redis 8.10.3 / 插件守护进程 0.6.14，
seekdb 1.4.0（2881），PowerContext 1.2.0（8000），Ollama 0.40.13（11434）。
完整版本、端口、限额与无 Docker 部署方式见 [docs/01-run-guide.md](docs/01-run-guide.md)。
