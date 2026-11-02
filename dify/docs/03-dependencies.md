# 依赖材料

对应赛题 §4.4：seekdb 部署配置与读写证明、知识库数据与初始化、记忆/状态预置脚本、插件名称版本与来源、自研插件/后端源码与配置。

## 1. seekdb 部署配置

### 1.1 版本与实例

| 项 | 值 |
| --- | --- |
| 版本 | OceanBase seekdb 1.4.0（`5.7.25-OceanBase seekdb-v1.4.0.0`，内核 `r1.4.0.0`，2026-10-27 构建） |
| 监听 | `0.0.0.0:2881`（MySQL 协议） |
| 用户 / 密码 | `root` / 空（仅本地实验；生产请改密码） |
| 业务库 | `test` |
| 数据目录 | 实例 `--base-dir`（作者：`D:\obca\seekdb-deploy\instance`） |
| 内存上限 | `SEEKDB_MEMORY_LIMIT=2G` |

作者实例的启动方式（二进制 + 数据目录，非 Docker）：

```bat
seekdb.exe --nodaemon --base-dir "D:\obca\seekdb-deploy\instance" --port 2881
```

Docker 等价方式：

```bash
docker run -d --name seekdb \
  -p 2881:2881 \
  -v ./seekdb-data:/var/lib/oceanbase \
  oceanbase/seekdb:1.4.0
```

### 1.2 Dify 侧连接配置

`dify/api/.env`（或 Docker 的 `dify/docker/.env`）：

```dotenv
VECTOR_STORE=seekdb
OCEANBASE_VECTOR_HOST=127.0.0.1     # Docker 内改为 seekdb 服务名
OCEANBASE_VECTOR_PORT=2881
OCEANBASE_VECTOR_USER=root
OCEANBASE_VECTOR_PASSWORD=          # 占位，按实际填写
OCEANBASE_VECTOR_DATABASE=test
SEEKDB_MEMORY_LIMIT=2G
```

Dify 使用该配置后，知识库索引会写入 seekdb；无需手工建表。

### 1.3 读写证明

见 `evidence/seekdb-proof.txt`，要点：

```text
seekdb version: 5.7.25-OceanBase seekdb-v1.4.0.0
tables in test: [... 'vector_index_08e2abca_e168_42ee_9cf1_85036e3066e9_node']

CREATE TABLE `vector_index_08e2abca_e168_42ee_9cf1_85036e3066e9_node` (
  `id` varchar(36) NOT NULL,
  `vector` VECTOR(1024) DEFAULT NULL,
  `text` longtext DEFAULT NULL,
  `metadata` json DEFAULT NULL,
  PRIMARY KEY (`id`),
  VECTOR KEY `vector_index` (`vector`) WITH (LIB=VSAG,DISTANCE=L2,M=16,EF_CONSTRUCTION=256,TYPE=HNSW, EF_SEARCH=64) ...
)

row count: 10
```

- 写：Dify 索引任务把 10 个中文分段写入该表（`text` 为分段原文，`metadata.document_id` 指向文档）。
- 读：Chatflow 的 `knowledge-retrieval` 节点每轮按玩家台词检索 `top_k=3`，三轮日志里均命中 `prank_compendium.md`，其中「辣椒水」轮命中的正文为第 2 个分段。
- 复现读取：
  ```bash
  python scripts/verify_stack.py --dump seekdb
  ```

## 2. 知识库数据与初始化

### 2.1 数据

- 文件：`data/prank_compendium.md`
- 结构：10 个分段，分隔符 `===ENTRY===`（Dify 自定义分段）
- 每段包含：招式名、操作方式、预期效果、老周的反应、反制手段、危险度
- 除 9 个恶作剧外，额外一段「老周的记仇规则」作为行为约束注入检索上下文

### 2.2 初始化

两种方式，任选：

**脚本（推荐，可重复）**

```bash
export DIFY_BASE_URL=http://127.0.0.1:5001
export DIFY_CONSOLE_EMAIL=you@example.com
export DIFY_CONSOLE_PASSWORD=change-me
python scripts/init_knowledge.py --file data/prank_compendium.md --name 记仇酒馆·恶作剧图鉴
```

脚本流程：控制台登录（`POST /console/api/login`，密码 Base64）→ 读取 CSRF Cookie →
上传文件（`POST /console/api/files/upload`）→ 以 `bge-m3` 创建知识库（`POST /console/api/datasets`，自定义分段）→
创建文档并触发索引（`POST /console/api/datasets/{id}/documents`）→ 轮询文档状态至 `completed` → 打印 Dataset ID。

**界面**

1. 「知识库 → 创建知识库 → 导入已有文本」，上传 `data/prank_compendium.md`。
2. 分段设置选「自定义」，分隔符填 `===ENTRY===`，最大分段长度 1024。
3. 索引方式选「高质量」，Embedding 模型选 `bge-m3`。
4. 等待索引完成后，复制数据集 ID 回填 Chatflow。

## 3. 记忆 / 状态预置脚本

| 脚本 | 作用 |
| --- | --- |
| `scripts/seed_powercontext.py --player 铁柱 --preset heavy` | 幂等创建玩家 scope，并预置若干条旧账（用于演示"老玩家一进门就被翻旧账"） |
| `scripts/reset_demo.py --player 铁柱` | 列出该玩家所有记忆条目并逐条 `/v1/memory/entries/retire` 退役（保留历史版本） |
| `scripts/verify_stack.py --dump player=铁柱` | 打印 scope 与全部记忆条目，核对召回数据 |

预置数据结构（`/v1/memory/remember`）：

```json
{
  "scope_id": "scp_xxx",
  "kind": "grudge_event",
  "text": "铁柱往老周的啤酒里加了辣椒水，老周狠狠瞪了他一眼并在账本上做了标记。（怒气 +3）",
  "reason": "玩家在记仇酒馆对老周实施恶作剧"
}
```

> 触发语必须保留 `（怒气 +N）` 或 `怒气+N` 形式，召回节点用它累加历史怒气。

## 4. 插件名称、版本与来源

| 插件 | 唯一标识 | 来源 | 用途 |
| --- | --- | --- | --- |
| OpenAI-API-compatible | `langgenius/openai_api_compatible:0.0.73@4cf123ffaa4556f079bed6c47f3a462cc825504b859b183239e74eb19136a4b5` | Dify Marketplace | 将 Ollama 的 OpenAI 兼容接口注册为 Dify 模型供应商 |

- DSL 的 `dependencies` 段已固定该唯一标识，导入时 Dify 会自动提示安装。
- 本项目**没有自研 Dify 插件**；所有业务逻辑放在 Chatflow 节点内。

## 5. 自研后端源码与配置

| 文件 | 作用 | 运行方式 |
| --- | --- | --- |
| `backend/sandbox_server.py` | Windows / 无 Docker 环境下的 Dify 代码沙箱替代品。实现 `POST /v1/sandbox/run`，校验 `X-Api-Key`，UTF-8 执行 `preload+code`，返回 `{code,message,data:{stdout,error}}` | `python backend/sandbox_server.py`（默认 127.0.0.1:8194） |
| `backend/build_workflow.js` | Chatflow 图生成器（11 节点 + 连线），用于迭代 DSL；输出 `workflow.json` 后通过控制台 API 同步 | `node backend/build_workflow.js <DATASET_ID>` |

沙箱配置（`dify/api/.env`）：

```dotenv
CODE_EXECUTION_ENDPOINT=http://127.0.0.1:8194
CODE_EXECUTION_API_KEY=dify-sandbox
```

`build_workflow.js` 中的 Dataset ID、PowerContext 地址、模型名均为可替换占位（脚本参数或文件顶部常量）。

## 6. Windows 兼容补丁（仅无 Docker 部署需要）

作者本地编译了 Dify Plugin Daemon 0.6.14，并打了两个最小补丁，否则 Windows 上插件无法启动或中文响应会变成替换字符：

1. **虚拟环境路径**：`internal/core/local_runtime/setup_python_environment.go`
   Windows 的 venv 解释器是 `.venv/Scripts/python.exe` 而不是 `.venv/bin/python`，新增 `venvPythonPath()` 按 `runtime.GOOS` 选择。
2. **安装目录文件名**：`internal/core/plugin_manager/media_transport/installed_bucket.go`
   插件唯一标识含 `:`（`name:version@hash`），Windows 文件名不允许，落盘后被截断为 `openai_api_compatible`，重启后守护进程无法恢复插件。改为 `%3A` 编码落盘、`List()` 时解码。
3. **子进程 UTF-8**：`internal/core/local_runtime/subprocess.go`
   插件子进程环境白名单加入 `PYTHONUTF8`、`PYTHONIOENCODING`，避免 Windows 管道按 GBK 编码导致中文 JSON 变成 `U+FFFD`。

判题环境使用官方 Docker 镜像时**不需要**以上补丁。
