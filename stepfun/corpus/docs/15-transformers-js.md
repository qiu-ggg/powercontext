# Transformers.js 使用要点

Transformers.js 让 JavaScript 直接加载 Hugging Face 上的 ONNX 模型，提供 pipeline、AutoTokenizer、AutoModel 等 API，浏览器和 Node 都能运行。它内置了 ONNX Runtime Web，支持 wasm 与 webgpu 两种设备，并通过 dtype 参数选择模型精度。

加载模型时可以指定 localModelPath 与 allowRemoteModels，把模型文件放在自己的静态目录里，避免依赖外部 CDN。首次加载会下载或读取模型并初始化会话，耗时明显高于后续请求；浏览器缓存命中后，第二次加载通常只需几百毫秒。

特征提取的调用方式是先创建 feature-extraction pipeline，再传入文本数组，并指定 pooling 与 normalize。返回的是张量对象，需要调用 tolist 转成普通数组。批大小影响吞吐和内存，太大可能触发显存或内存不足，太小则调度开销占比高。

版本升级会改变默认精度和缓存策略。生产项目应锁定版本，并在技术文档里记录模型标识、文件哈希和运行时版本，保证评测结果可复现。
