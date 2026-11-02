# WebGPU 与浏览器端推理

WebGPU 是新一代浏览器图形与计算接口，它把 GPU 的计算能力以显式计算管线的方式暴露给 JavaScript。与 WebGL 只能通过纹理绕路做通用计算不同，WebGPU 提供 storage buffer、compute shader 和 command encoder，适合矩阵乘法、归一化等神经网络算子。Chrome 113 之后在 Windows 与 macOS 上默认开启，Edge 也同步支持。

在端侧推理里，WebGPU 的最大价值是把原本几十毫秒的矩阵运算压到几毫秒。对于 BERT 这类编码器模型，注意力层的 QKV 投影和 FFN 都是规整的 GEMM，GPU 并行度高，收益明显。但 WebGPU 也有代价：首次初始化要编译着色器、分配显存，小批量请求可能被调度开销吃掉。

工程上通常做双后端策略：能力探测 navigator.gpu 存在时尝试 WebGPU，初始化失败再回退到 WASM。回退必须自动且可观测，界面要明确显示当前使用的后端，否则用户会把 GPU 编译失败误判为应用卡死。WebGPU 还是实验性 API，浏览器版本、显卡驱动和电源模式都会影响可用性。

安全上，浏览器只允许安全上下文使用 WebGPU，本地开发需要用 localhost 或 HTTPS。跨域隔离的 SharedArrayBuffer 与 WebGPU 无关，但 WASM 多线程需要它，两者要分别配置。
