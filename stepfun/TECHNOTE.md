# 端侧向量化 + seekdb 混合检索 · 一页技术说明

## 目标与边界

在浏览器内完成文本与查询的向量化，把向量、原文、`doc_id` 等元数据写入 seekdb，并由
seekdb 完成向量召回、全文召回与融合排序。服务端只做校验、转发和结果透传；没有云端推理
API，没有预计算向量回放，也没有用客户端内存检索替代数据库检索。

## 架构

前端 React/Vite，推理放在 Web Worker（Transformers.js 3.8.1 + ONNX Runtime Web），
模型文件由本站静态提供（`env.allowRemoteModels=false`），WASM 运行时本地化并通过
COOP/COEP 开启多线程。Worker 用 `Float32Array` transferable 把整批向量传回主线程，
避免结构化克隆。后端 Express 仅调用 seekdb-js；每个知识库对应一张
`c$v2$<id>` 表（`_id` / `document` / `metadata` / `embedding`），建 HNSW（cosine）
与 IK 全文索引。

混合检索没有在客户端拼两路结果，而是走 seekdb 的数据库内融合：

1. `SET @search_parm = ?`（全文条件 + 查询向量 + RRF 参数）
2. `SELECT DBMS_HYBRID_SEARCH.GET_SQL(...) FROM dual`
3. 执行生成的 SQL；其内部对全文排名与向量排名套 `1/(rank+k)` 后求和

UI 直接展示这三条实际 SQL，便于核验融合发生在数据库内。向量模式与全文模式也各走一条
seekdb SQL，便于对比单路效果。

## 模型与量化

`Xenova/bge-small-zh-v1.5`（BAAI bge-small-zh-v1.5 的 ONNX 版），512 维，CLS pooling +
L2 normalize。四种权重均来自模型仓库：

| 精度 | 体积 | 压缩比 |
| --- | ---: | ---: |
| FP32 | 90.46 MiB | 1.00× |
| FP16 | 45.30 MiB | 2.00× |
| INT8 | 22.80 MiB | 3.97× |
| q8 | 22.90 MiB | 3.95× |

默认：WebGPU 用 FP16，WASM/降级用 INT8。q8 仅保留作 A/B。

## 实测（固定条件）

Edge 156 / Windows 10 / NVIDIA Blackwell / seekdb 1.4.0；24 篇文档、48 块、26 条查询；
topK=10，文档级 Recall@5、nDCG@5、MRR；耗时取该次运行的中位数。

| 后端 | 48 块向量化 | 查询向量化 | seekdb | 端到端 | Recall@5 | nDCG@5 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| WebGPU FP16 | 204 ms | 9.8 ms | 6.3 ms | 19.8 ms | 80.77% | 79.41% | 0.942 |
| WASM INT8 | 3.97 s | 5.1 ms | 6.7 ms | 15.4 ms | 86.54% | 80.73% | 0.923 |
| WASM FP32 | 5.57 s | 7.4 ms | 7.0 ms | 18.2 ms | 80.77% | 79.41% | 0.942 |
| WASM q8 | 6.51 s | 8.9 ms | 8.2 ms | 20.2 ms | 75.00% | 75.48% | 0.923 |

- FP16 与 FP32 质量完全一致；FP16 把模型减半，WebGPU 批量吞吐达 235 块/s。
- INT8 把模型压到约 1/4，Recall@5 反而高于 FP32，但 MRR 从 0.942 降到 0.923，
  说明量化改变了排序细节，不能宣称全面优于基线。
- q8 在该评测集上明显更差，故切换到 `model_int8.onnx`。

## 性能优化与取舍

- **批处理**：WebGPU 上 batch=32 达 363.6 块/s，是 batch=1 的 3.5 倍；WASM 上相反，
  batch=1（INT8 19.9 块/s）快于 batch=32（11.2 块/s）。因此保留可选批大小，而不是
  固定大 batch。界面默认 32 面向 WebGPU，WASM 用户应调小。
- **模型加载**：483–827 ms（缓存后），冷启动推理 9–63 ms；加载进度按文件聚合展示。
- **写入**：48 块端到端 1.25 s，其中索引刷新 815 ms。增量更新先按 `doc_id` 删除旧块，
  再写入并 `refresh_index()`；可选每批刷新，但实测一次刷新更省。
- **检索**：seekdb 热态 6–7 ms；首次查询可能 130 ms 左右（计划/缓存冷启动），
  文档中区分首次与热态。向量模式与混合模式都只返回数据库排序结果。

## 降级

主线程探测 `navigator.gpu` 与 `shader-f16`；不可用或初始化失败时自动切 WASM INT8，
状态区显示实际设备、精度与降级原因。用禁用 WebGPU 的 Edge（`requestAdapter()` 返回
`null`）自动验证：应用选中 WASM INT8、显示原因、混合检索正常返回；首次
10.0 / 5.8 / 26.4 ms，热态 6.5 / 6.7 / 25.8 ms。

## 限制

评测集规模较小（26 条查询），指标受样本与 RRF 参数影响；绝对耗时依赖 GPU/驱动。
所有向量必须由浏览器生成，因此服务端无法脱离浏览器导入文档。
