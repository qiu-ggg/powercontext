# 运行说明

本文覆盖：玩法与创意、环境与版本、模型与插件、安装→导入→初始化→启动、外部服务与限额、占位配置项、开源组件署名。

## 1. 创意与玩法

**一句话**：你对酒馆老板老周搞恶作剧，他表面不发作，却把每一笔都记进账本；下次见面先翻旧账，怒气越高报复越狠。

- **可玩性来自"因果"而不是"人设"**：同一个玩家名（输入变量 `player_name`）在任意新会话里都会触发同一本账。
- **可视化反馈**：每条回答固定展示 `怒气值 / 本次增量 / 判定 / 老周状态 / 翻出的旧账条数 / 命中的图鉴 / 旧账摘录`。
- **升级曲线**：怒气 < 4 装没事；≥ 4 冷脸；≥ 8 抄擀面杖并主动报复；≥ 15 下通缉令。
- **图鉴检索**：玩家描述招式后，先去 seekdb 向量库检索「恶作剧图鉴」，模型会参考图鉴里的"预期效果/反制手段"来演老周。
- **推荐玩法**：用同一个名字连玩 3 轮（先辣椒水、再假蟑螂、最后换假酒），观察旧账从 0 条涨到 2 条、怒气从 3 涨到 11、老周从"装没事"变成"擀面杖"。

## 2. 环境与版本

### 2.1 本项目已验证环境（作者实际跑通）

| 组件 | 版本 | 端口 |
| --- | --- | --- |
| Dify（API + Web + Worker + 插件守护进程） | 1.18.0（源码部署） | 5001 / 3000 / 5002、5003 |
| PostgreSQL | 17.4 | 5433 |
| Redis | 8.10.3 | 6380 |
| Dify Plugin Daemon | 0.6.14（本地编译） | 5002 / 5003 |
| OceanBase seekdb | 1.4.0（`5.7.25-OceanBase seekdb-v1.4.0.0`，内核 r1.4.0.0） | 2881 |
| PowerContext | 1.2.0 | 8000 |
| Ollama | 0.40.13 | 11434 |
| Dify 代码沙箱 | 自研极简实现（见 `backend/sandbox_server.py`） | 8194 |
| 操作系统 | Windows 11 26200（无 Docker） | — |

> 作者环境是"无 Docker 的 Windows 原生部署"，因此额外提供了两个 Windows 兼容补丁与一个本地代码沙箱；**判题环境使用官方 Docker Compose 时不需要这些补丁**。详见 `docs/03-dependencies.md` §6、§7。

### 2.2 推荐的复现环境（Docker）

- Docker Engine 24+ / Compose v2
- Dify 1.18.0（`git clone --branch 1.18.0`）
- seekdb 容器（`oceanbase/seekdb`，建议固定 1.4.0）
- PowerContext 1.2.0（`uv tool install powercontext==1.2.0` 或官方镜像）
- Ollama 0.40+（或任意 OpenAI 兼容推理服务）

## 3. 模型与插件

### 3.1 模型

| 用途 | 模型 | 维度 / 参数 | 说明 |
| --- | --- | --- | --- |
| 对话（老周） | `qwen2.5:7b` | 7.6B | 中文稳定，能按 system prompt 输出严格 JSON |
| 文本嵌入 | `bge-m3` | 1024 维 | **必须用中文友好的嵌入模型**；实测 `nomic-embed-text` 对中文检索几乎不可用 |

Ollama 提供 OpenAI 兼容端点 `http://<host>:11434/v1`，API Key 可填任意非空字符串（如 `ollama`）。

### 3.2 插件

| 插件 | 版本 | 来源 |
| --- | --- | --- |
| `langgenius/openai_api_compatible` | `0.0.73`（`@4cf123ffaa4556f079bed6c47f3a462cc825504b859b183239e74eb19136a4b5`） | Dify Marketplace |

插件只用于把 Ollama 的 OpenAI 兼容接口接入 Dify 的模型层；Chatflow 自身不包含自研插件。

## 4. 安装 → 导入 → 初始化 → 启动

### 4.1 启动 Dify 与 seekdb 向量后端（Docker）

```bash
git clone https://github.com/langgenius/dify.git --branch 1.18.0
cd dify/docker
cp .env.example .env
```

在 `dify/docker/.env` 中设置：

```dotenv
VECTOR_STORE=seekdb
OCEANBASE_VECTOR_HOST=seekdb
OCEANBASE_VECTOR_PORT=2881
OCEANBASE_VECTOR_USER=root
OCEANBASE_VECTOR_PASSWORD=
OCEANBASE_VECTOR_DATABASE=test
```

在 `docker-compose.yaml` 中加入 seekdb 服务（与 `api`、`worker` 同网络）：

```yaml
  seekdb:
    image: oceanbase/seekdb:1.4.0
    restart: always
    ports:
      - "2881:2881"
    volumes:
      - ./volumes/seekdb:/var/lib/oceanbase
```

随后：

```bash
docker compose up -d
```

首次打开 `http://localhost/install` 设置管理员账号。

> 说明：Dify 会在首次索引知识库时，在 seekdb 的 `test` 库中自动创建
> `vector_index_<dataset_uuid>_node` 表，列为 `id / vector / text / metadata`，
> 向量列类型 `VECTOR(1024)`，HNSW 索引。作者环境的实测 DDL 见 `evidence/seekdb-proof.txt`。

### 4.2 启动 PowerContext

```bash
uv tool install powercontext==1.2.0
# 数据目录（SQLite + FTS5）由 POWERCONTEXT_HOME 指定，默认在用户目录下
export POWERCONTEXT_HOME=$HOME/pc-home
powercontext server run          # 监听 0.0.0.0:8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health/ready
```

### 4.3 启动 Ollama 并拉取模型

```bash
ollama pull qwen2.5:7b
ollama pull bge-m3
```

### 4.4 在 Dify 中接入模型

1. 进入「设置 → 模型供应商」，安装 `OpenAI-API-compatible` 插件。
2. 添加模型凭据：
   - Base URL：`http://<ollama-host>:11434/v1`（Docker 内访问宿主机用 `http://host.docker.internal:11434/v1`）
   - API Key：任意非空（如 `ollama`）
   - 模型名：`qwen2.5:7b`（对话）、`bge-m3`（Text Embedding）
3. 在「系统模型设置」中把 **默认 Text Embedding** 设为 `bge-m3`（否则创建知识库会报 `Default model not found for text-embedding`）。

### 4.5 导入应用

- 方式 A（推荐）：Dify「工作室 → 导入 DSL」选择 `dsl/grudge-tavern.difypkg`。
- 方式 B：选择 `dsl/grudge-tavern.dsl.yml`（单文件 DSL）。
- 导入后如提示缺少插件，先安装 `langgenius/openai_api_compatible:0.0.73`。

### 4.6 初始化知识库并回填 Dataset ID

```bash
pip install requests
export DIFY_BASE_URL=http://127.0.0.1:5001
export DIFY_CONSOLE_EMAIL=you@example.com
export DIFY_CONSOLE_PASSWORD=change-me
python scripts/init_knowledge.py --file data/prank_compendium.md --name 记仇酒馆·恶作剧图鉴
```

脚本会：登录 → 上传文件 → 以 `bge-m3` 为嵌入模型创建知识库（自定义分段，`===ENTRY===` 分隔）→ 触发索引 → 轮询到完成 → **打印 Dataset ID**。

拿到 Dataset ID 后，在 Dify 画布中打开「检索恶作剧图鉴」节点，把它填进 **知识库** 选择框（DSL 里是占位值，导入时可能为空）。

### 4.7 发布与启动

1. 右上角「发布 → 发布更新」。
2. 打开「访问 API」创建 API Key（`app-` 开头），写入环境变量 `DIFY_APP_API_KEY`。
3. 运行样例：

```bash
python scripts/run_sample.py --player 铁柱 --rounds 3
```

脚本用到的全部环境变量见 `scripts/env.example`（不含任何真实密钥）。

### 4.8 无 Docker（Windows 原生）已验证路径

作者实际使用的路径，供同样无法用 Docker 的复现者参考：

1. PostgreSQL 17.4（5433）、Redis 8.10.3（6380）本地启动，建库 `dify` 与 `dify_plugin`。
2. `dify/api/.env`：`DB_PORT=5433`、`REDIS_PORT=6380`、`VECTOR_STORE=seekdb`、seekdb 四项连接参数、`CODE_EXECUTION_ENDPOINT=http://127.0.0.1:8194`、`CODE_EXECUTION_API_KEY=dify-sandbox`。
3. 启动 API（5001）、Celery worker、插件守护进程（5002/5003）。
4. 因为 Windows 上 Dify 官方代码沙箱依赖 Linux/Docker，改为运行 `backend/sandbox_server.py`（仅执行代码节点的 Python，接口与 Dify 沙箱协议一致）。
5. 插件守护进程需要两处 Windows 兼容补丁（`.venv/Scripts/python.exe` 路径、安装目录 `:` 非法文件名与 UTF-8 子进程环境），见 `docs/03-dependencies.md` §6。

## 5. 外部服务、依赖与限额

| 依赖 | 是否必需 | 默认地址 | 限额 / 注意事项 |
| --- | --- | --- | --- |
| Dify API | 必需 | `http://127.0.0.1:5001` | `UPLOAD_FILE_SIZE_LIMIT` 等按 `.env`；本作品只上传 1 个 < 20 KB 的 md 文件 |
| PowerContext | 必需 | `http://127.0.0.1:8000` | 单 scope 记忆按条累积；检索默认 `limit=50`；**FTS 查询串过长会召回为空**，本项目把查询固定为「玩家名 + 怒气」 |
| seekdb | 必需（向量库） | `127.0.0.1:2881` | 作者实例 `SEEKDB_MEMORY_LIMIT=2G`；图鉴 10 个分段，检索 `top_k=3` |
| Ollama | 必需（模型） | `http://127.0.0.1:11434` | 首次调用需加载 7B 模型，冷启动约 5–10 s；单轮 workflow 实测 1.5–6 s |
| 代码沙箱 | 仅无 Docker 时需要 | `http://127.0.0.1:8194` | 只执行 4 个 Python 代码节点；60 s 超时，禁止网络 |

## 6. 占位配置项

提交物中不含任何真实密钥。复现时需要替换的占位项：

| 占位 | 出现位置 | 说明 |
| --- | --- | --- |
| `DIFY_BASE_URL` | 脚本环境变量 | Dify API 地址，如 `http://127.0.0.1:5001` |
| `DIFY_APP_API_KEY` | 脚本环境变量 | 应用「访问 API」里创建的 `app-...` |
| `DIFY_CONSOLE_EMAIL` / `DIFY_CONSOLE_PASSWORD` | `init_knowledge.py` | Dify 控制台账号；密码在请求中按 Dify 约定做 Base64 |
| `POWERCONTEXT_URL` | 脚本 / Chatflow HTTP 节点 | 默认 `http://127.0.0.1:8000` |
| `<DATASET_ID>` | DSL「检索恶作剧图鉴」节点 | `init_knowledge.py` 打印，导入后手动回填 |
| `qwen2.5:7b` / `bge-m3` | LLM 节点 / 默认嵌入模型 | 可替换为其他 OpenAI 兼容模型 |
| `OCEANBASE_VECTOR_*` | Dify `.env` | seekdb 连接参数，默认 root/空密码仅限本地 |

## 7. 开源组件与署名

| 组件 | 许可证 | 说明 |
| --- | --- | --- |
| Dify 1.18.0 | Dify Open Source License（基于 Apache 2.0 附加条件） | 未修改 Dify 品牌/版权信息，仅在本地为保证 Windows 可运行做了构建级调整 |
| PowerContext 1.2.0 | Apache-2.0 | 未修改其源码，仅通过 HTTP API 使用 |
| OceanBase seekdb 1.4.0 | Apache-2.0 | 作为 Dify 向量后端 |
| Ollama | MIT | 本地模型运行时 |
| Qwen2.5-7B | Apache-2.0 | 对话模型 |
| BGE-M3 | MIT | 中文嵌入模型 |
| openai_api_compatible plugin 0.0.73 | Apache-2.0 | Dify Marketplace 插件 |
| 恶作剧图鉴文本 | 本项目原创 | `data/prank_compendium.md` |
