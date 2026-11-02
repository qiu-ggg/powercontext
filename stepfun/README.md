# StepFun Edge KB · 浏览器端向量化 + seekdb 混合检索

迷你知识库：文本在**浏览器 Web Worker** 内用 ONNX 模型完成向量化，向量/原文/元数据写入
**seekdb 1.4.0**；查询向量同样在本地生成，向量召回、全文召回与 RRF 融合全部由 seekdb 的
`DBMS_HYBRID_SEARCH` 在一条 SQL 内完成。服务端不调用任何云端推理 API，也不回放预计算向量。

```
浏览器                                    本机 API (Express)              seekdb 1.4 (127.0.0.1:2881)
┌─────────────────────────┐   JSON      ┌──────────────────────┐   MySQL  ┌──────────────────────────┐
│ 导入文本 → 分块          │ ──────────> │ /api/collections/... │ ───────> │ c$v2$<id>                │
│ Web Worker: bge-small   │             │ 只做参数校验与转发   │          │  _id/document/metadata/  │
│ 查询文本 → 查询向量      │ <────────── │ 返回命中与 SQL 轨迹  │ <─────── │  embedding               │
│ 结果展示 + 分阶段计时    │             └──────────────────────┘          │  HNSW(cosine) + IK 全文  │
└─────────────────────────┘                                               │  DBMS_HYBRID_SEARCH+RRF  │
                                                                          └──────────────────────────┘
```

## 1. 环境要求

- Node.js ≥ 20（实测 24.18.0），npm 10+
- Microsoft Edge / Chrome（WebGPU 可选；不可用时自动降级到 WASM）
- seekdb 1.4.0 服务端，监听 `127.0.0.1:2881`（MySQL 协议）
- 磁盘：依赖约 400 MB，模型约 190 MB（FP32+FP16+INT8+q8），WASM 运行时约 32 MB

## 2. 启动

```bash
# 1) 安装依赖（postinstall 会把 ORT WASM 文件复制到 web/public/wasm）
npm install

# 2) 下载模型（约 190 MB，可用 HF_ENDPOINT 换镜像）
npm run setup
#   HF_ENDPOINT=https://hf-mirror.com npm run setup
#   只下需要的精度：node scripts/fetch-model.mjs --variant=int8,fp16

# 3) 启动 seekdb（默认 .seekdb_base/，端口 2881）
#    seekdb 二进制来自 pylibseekdb wheel：pylibseekdb.libs/seekdb.exe
#    python -m pip install pylibseekdb==1.4.0.post2
#    然后把它放到 backend/seekdb/seekdb.exe，或设置 SEEKDB_BIN
npm run setup:seekdb

# 4) 构建前端并启动（http://127.0.0.1:8787）
npm run build && npm start
```

开发模式：`npm run dev`（Vite 5173 + API 8787，`/api` 已代理）。

可用环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_PORT` | `8787` | API / 静态站点端口 |
| `SEEKDB_HOST` / `SEEKDB_PORT` | `127.0.0.1` / `2881` | seekdb 连接 |
| `SEEKDB_USER` / `SEEKDB_PASSWORD` | `root` / 空 | seekdb 账号 |
| `SEEKDB_DATABASE` | `test` | 数据库名 |
| `EMBED_MODEL` | `Xenova/bge-small-zh-v1.5` | 本地模型目录名 |
| `HF_ENDPOINT` | `https://huggingface.co` | 模型下载源 |
| `SEEKDB_BIN` / `SEEKDB_BASE_DIR` | 自动查找 / `.seekdb_base` | 启动脚本参数 |

## 3. 使用

1. **导入与写入**：拖入 `.md` / `.txt`（仓库自带 `corpus/docs/` 24 篇）或粘贴正文 → 预览分块
   （360 字目标 / 60 字重叠）→ 选择批大小与刷新策略 → “向量化并写入 seekdb”。
   同名 `doc_id` 会先删除旧分块再写入，实现增量更新；写入后调用 `refresh_index()`，
   新文档立即可检索。
2. **混合检索**：输入查询，选择 `hybrid` / `vector` / `fulltext`，可调 topK 与 RRF k。
   页面显示命中原文、分数、端侧查询向量化耗时、seekdb 耗时、端到端耗时，
   以及实际执行的三条 SQL（`SET @search_parm` → `GET_SQL` → 融合 SQL）。
3. **评测与基准**：固定 24 篇 / 48 块 / 26 条查询，运行当前后端评测（文档级
   Recall@5、nDCG@5、MRR），以及批大小 1/8/16/32 的吞吐基准。结果存 localStorage
   并写入 `results/*.json`。
4. **技术说明**：模型体积、量化、运行时策略、seekdb 表结构与混合检索说明。

左侧可切换后端：`自动`（优先 WebGPU FP16，否则 WASM INT8）、`WebGPU`、`WASM INT8`、
`WASM FP32`。顶栏和状态区始终显示实际执行设备与精度；自动降级时会显示原因。

## 4. 模型与量化

模型：[`Xenova/bge-small-zh-v1.5`](https://huggingface.co/Xenova/bge-small-zh-v1.5)
（BAAI/bge-small-zh-v1.5 的 ONNX 转换版），4 层 BERT，hidden 512，最大 512 tokens，
输出 512 维，CLS pooling + L2 normalize。

| 精度 | 文件 | 体积 | 压缩比 | 用途 |
| --- | --- | --- | --- | --- |
| FP32 | `onnx/model.onnx` | 90.46 MiB | 1.00× | 质量基线 |
| FP16 | `onnx/model_fp16.onnx` | 45.30 MiB | 2.00× | WebGPU 默认 |
| INT8 | `onnx/model_int8.onnx` | 22.80 MiB | 3.97× | WASM 默认 / 降级 |
| q8 | `onnx/model_quantized.onnx` | 22.90 MiB | 3.95× | 仅作 A/B 对照 |

INT8/q8 均为仓库自带量化产物，无需本地再转换；下载脚本按文件字节校验。Tokenizer 等
配套文件约 537 KiB。

## 5. seekdb 结构与检索

- 每个知识库一个集合表 `c$v2$<collectionId>`，列：`_id VARCHAR`、`document TEXT`、
  `metadata JSON`、`embedding VECTOR(512)`。
- 索引：HNSW（dimension=512，distance=cosine）+ 全文索引（`ik`，`ik_mode=smart`）。
- 元数据表：`kb_registry`（知识库/集合/模型/维度/计数/耗时）、`kb_docs`（文档登记）。
- 混合检索：`SET @search_parm = ?` → `SELECT DBMS_HYBRID_SEARCH.GET_SQL(...)` →
  执行生成的 SQL。该 SQL 内同时做全文排名和向量排名，并用
  `1/(rank+k)` 的 RRF 公式融合；客户端只接收最终排序，不在本地拼两路结果。
- 刷新：`refresh_index()`；界面可选“全部写入后刷新”或“每批刷新”。

## 6. 实测结果（2026-11-02）

设备：Windows 10.0.26200 x64 / Edge 156.0.4314.50 / NVIDIA Blackwell（WebGPU，
`shader-f16`）/ 28 逻辑核 / seekdb 1.4.0 / Node 24.18.0。完整数据见
[`results/benchmark-summary.json`](results/benchmark-summary.json)。

| 后端 | 加载 | 冷启动 | 48 块向量化 | 查询向量化 | seekdb | 端到端 | Recall@5 | nDCG@5 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| WebGPU FP16 | 827 ms | 63 ms | 204 ms（235 块/s） | 9.8 ms | 6.3 ms | 19.8 ms | 80.77% | 79.41% | 0.942 |
| WASM INT8 | 532 ms | 9 ms | 3.97 s（12.1 块/s） | 5.1 ms | 6.7 ms | 15.4 ms | 86.54% | 80.73% | 0.923 |
| WASM FP32 | 1.17 s | 52 ms | 5.57 s（8.6 块/s） | 7.4 ms | 7.0 ms | 18.2 ms | 80.77% | 79.41% | 0.942 |
| WASM q8（归档） | 592 ms | 30 ms | 6.51 s（7.4 块/s） | 8.9 ms | 8.2 ms | 20.2 ms | 75.00% | 75.48% | 0.923 |

批大小吞吐（块/秒，48 块）：

| 后端 | batch=1 | 8 | 16 | 32 |
| --- | ---: | ---: | ---: | ---: |
| WebGPU FP16 | 103.5 | 323.8 | 326.1 | 363.6 |
| WASM INT8 | 19.9 | 12.6 | 11.5 | 11.2 |
| WASM FP32 | 15.0 | 9.6 | 9.0 | 8.8 |

24 篇 / 48 块全量导入（WebGPU，batch=32，写后刷新）：向量化 149 ms、写入 154 ms、
刷新 815 ms、端到端 1.25 s。

结论与限制：

- WebGPU 批量吞吐约为 WASM INT8 的 **10–32×**；单条查询因 GPU 调度开销，端侧耗时
  反而略高于 WASM（9.8 ms vs 5.1 ms），但总端到端仍在 20 ms 内。
- FP16 与 FP32 的三项质量指标完全一致，说明 FP16 在这套模型/硬件上无损。
- INT8 的 Recall@5 高于 FP32，但 MRR 低于 FP32；量化改变了 RRF 融合后的排序，
  不能概括为“INT8 全面更好”。q8 在本评测集上明显更差，因此默认改用 `model_int8.onnx`。
- WASM 上“批越大越快”不成立：本工作负载下 batch=1 最快；WebGPU 则相反。界面默认
  batch=32 面向 WebGPU，WASM 用户应手动改小。

## 7. WebGPU 不可用时的降级验证

`scripts/verify-fallback.mjs` 通过 CDP 驱动一个禁用 WebGPU 的 Edge（`requestAdapter()`
返回 `null`），验证应用自动选择 WASM INT8、显示降级原因、并完成一次混合检索：

```bash
# 先以调试端口启动浏览器：
#   msedge.exe --headless=new --disable-gpu --disable-webgpu --disable-features=WebGPU \
#     --remote-debugging-port=9333 --user-data-dir=D:/obca/edge-nogpu
node scripts/verify-fallback.mjs
```

实测（`results/fallback-verification.json`）：`navigatorGpu=null`、后端 `WASM INT8`、
提示“requestAdapter() 返回空（无可用 GPU 适配器），自动降级到 WASM INT8”，
混合检索返回结果，首次 10.0 / 5.8 / 26.4 ms，热态 6.5 / 6.7 / 25.8 ms
（查询向量化 / seekdb / 端到端）。

## 8. 测试数据与复现

- `corpus/docs/*.md`：24 篇中文技术文档；`corpus/eval/queries.json`：26 条带 gold 文档的查询。
  由 `scripts/gen_corpus.py` 生成，可直接修改后重跑。
- 评测流程固定在 `/api/eval/fixture`：同一套分块、同一批查询、topK=10，文档级指标。
- 浏览器自动跑一次评测：`node scripts/run-eval-cdp.mjs wasm-int8 [bench]`（需 9333 调试端口）。
- 结果 JSON 由界面通过 `/api/results` 写入 `results/`；`results/README.md` 说明每份文件。

## 9. 目录

```
server/            Express API、seekdb 访问、分块、语料与评测 fixture
web/               React + Vite 前端；embedder.worker.ts 为端侧推理
scripts/           fetch-model / copy-wasm / seekdb-server / verify-fallback / run-eval-cdp
corpus/            24 篇文档 + 26 条查询 + 生成脚本
results/           实测快照与复现说明
```

## 10. 已知限制

- 服务端不做 embedding；所有向量必须由浏览器生成，因此无法在纯 curl 场景下导入新文档。
- 评测集只有 26 条查询、48 个分块，指标绝对值受小样本影响；结论以同设备横向对比为准。
- seekdb 启动脚本只负责拉起本地单机实例，未包含生产级备份/鉴权配置。
