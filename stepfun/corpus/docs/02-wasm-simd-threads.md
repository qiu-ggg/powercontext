# WASM SIMD 与多线程

WebAssembly 是浏览器里的可移植字节码，WASM SIMD 提案让一条指令处理 128 位数据，也就是四个 float32 或十六个 int8。对神经网络推理来说，SIMD 能显著提升卷积、矩阵乘和量化反量化的吞吐。ONNX Runtime Web 的 wasm 执行提供器默认启用 SIMD，现代 Chrome 与 Edge 都支持。

多线程依赖 SharedArrayBuffer，而 SharedArrayBuffer 要求页面处于跨域隔离状态。服务端需要返回 Cross-Origin-Opener-Policy: same-origin 与 Cross-Origin-Embedder-Policy: require-corp 两个响应头，Vite 开发服务器也要配置同样的 header。没有隔离时，运行时只能退回单线程，推理延迟通常翻倍。

线程数不是越多越好。任务本身有并行开销，浏览器还要给渲染和主线程留资源，一般取硬件并发数的一半到三分之二，并设置上限。移动设备发热降频时，过多线程反而抖动更大。

WASM 的优势是兼容性：几乎所有现代浏览器、没有独立显卡的办公电脑、受限的企业环境都能跑。它也是 WebGPU 不可用时的可靠降级路径，因此 INT8 量化模型配合 WASM 是端侧应用的保底组合。
