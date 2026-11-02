# 测量结果

本目录保存 2026-11-02 在本机 Edge 156 + seekdb 1.4.0 上的一次完整测量快照。
汇总数据见 [benchmark-summary.json](benchmark-summary.json)，原始单次运行见下列文件。

| 文件 | 内容 |
| --- | --- |
| `eval_webgpu_fp16_mvyziy6y.json` | WebGPU + FP16 的 26 条查询评测（Recall@5 / nDCG@5 / MRR、分阶段耗时） |
| `eval_wasm_int8_mvyzg5rl.json` | WASM + INT8（`model_int8.onnx`）评测 |
| `eval_wasm_fp32_mvyzhkgj.json` | WASM + FP32（质量基线）评测 |
| `eval_wasm_q8_mvyz68d6.json` | WASM + q8（`model_quantized.onnx`）A/B 对照；最终未采用该模式 |
| `batch_webgpu_fp16_*.json` | WebGPU 下批大小 1/8/16/32 的吞吐 |
| `batch_wasm_int8_*.json` | WASM INT8 下批大小 1/8/16/32 的吞吐 |
| `batch_wasm_fp32_*.json` | WASM FP32 下批大小 1/8/16/32 的吞吐 |
| `batch_wasm_q8_*.json` | WASM q8 的批大小对照（归档） |
| `ingest_webgpu_fp16_1793607572687.json` | 24 篇文档 / 48 块的全量导入实测 |
| `ingest_webgpu_fp16_1793606682816.json` | 单块导入实测（含首次索引刷新） |
| `fallback-verification.json` / `fallback-wasm.png` | 无 WebGPU 环境下自动降级到 WASM INT8 的检索证据 |

## 读法

- 所有 embedding 均在浏览器 Web Worker 中完成；服务端只接收向量、原文和元数据。
- 检索质量来自 seekdb 的混合检索（`DBMS_HYBRID_SEARCH.GET_SQL` + RRF），文档级指标，
  topK=10 取前 5 计算 Recall@5 / nDCG@5，MRR 取首个相关文档排名。
- `dbMs`、`queryEmbedMs`、`e2eMs` 是该次运行 26 条查询的中位数；`embedChunksMs` 是 48 个块的整批耗时。
- 量化质量不是单调关系：INT8 在本评测集上的 Recall@5 高于 FP32，但同时 MRR 略低（0.923 vs 0.942），
  属于 RRF 融合后排序变化，不能简单表述为“INT8 全面优于 FP32”。WebGPU FP16 与 WASM FP32 的
  三项质量指标完全一致。
- 浏览器与 GPU 驱动版本会影响绝对耗时；复现时请记录设备，并按 `README.md` 的固定流程重跑。
