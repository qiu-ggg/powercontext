import type { HealthInfo, ModelInfo } from "../api";
import { Card, Chip } from "../components";
import { formatBytes } from "../metrics";

export default function AboutPanel({
  models,
  health,
}: {
  models: ModelInfo | null;
  health: HealthInfo | null;
}) {
  const bytes = (key: string) => models?.files?.[key]?.bytes ?? null;
  const ratio = (key: string) => {
    const base = bytes("fp32");
    const target = bytes(key);
    return base && target ? base / target : null;
  };
  const tokenizer = models?.tokenizerBytes ?? null;

  return (
    <div className="stack">
      <Card
        title="系统结构"
        subtitle="浏览器负责全部 embedding；seekdb 负责存储、向量索引、全文索引与融合排序。"
      >
        <div className="flow">
          <div className="flow-step">
            <span className="flow-index">1</span>
            <strong>导入</strong>
            <p>文本分块（360 字目标 / 60 字重叠），在 Web Worker 内用 Transformers.js 编码。</p>
          </div>
          <div className="flow-arrow">→</div>
          <div className="flow-step">
            <span className="flow-index">2</span>
            <strong>写入</strong>
            <p>浏览器把向量、原文、doc_id / 标题 / 分块序号写入 seekdb 集合，随后 refresh_index。</p>
          </div>
          <div className="flow-arrow">→</div>
          <div className="flow-step">
            <span className="flow-index">3</span>
            <strong>查询</strong>
            <p>查询文本在本地编码；一条 DBMS_HYBRID_SEARCH SQL 完成向量 + 全文召回与 RRF 融合。</p>
          </div>
          <div className="flow-arrow">→</div>
          <div className="flow-step">
            <span className="flow-index">4</span>
            <strong>展示</strong>
            <p>返回排序结果与原文，并显示查询向量化、seekdb 检索、端到端耗时及实际 SQL。</p>
          </div>
        </div>
      </Card>

      <div className="grid grid-2">
        <Card title="模型与量化" subtitle="Xenova/bge-small-zh-v1.5（BAAI bge-small-zh-v1.5 的 ONNX 转换版）">
          <table className="kv">
            <tbody>
              <tr>
                <th>来源</th>
                <td className="mono tiny">huggingface.co/Xenova/bge-small-zh-v1.5</td>
              </tr>
              <tr>
                <th>结构</th>
                <td>4 层 BERT，hidden 512，最大 512 tokens，CLS pooling + L2 normalize</td>
              </tr>
              <tr>
                <th>维度</th>
                <td>{models?.dim ?? 512}</td>
              </tr>
              <tr>
                <th>FP32</th>
                <td>
                  {formatBytes(bytes("fp32"))}
                  <span className="muted"> · 基线</span>
                </td>
              </tr>
              <tr>
                <th>FP16</th>
                <td>
                  {formatBytes(bytes("fp16"))}
                  {ratio("fp16") ? <span className="muted"> · {ratio("fp16")!.toFixed(2)}× 压缩</span> : null}
                </td>
              </tr>
              <tr>
                <th>INT8</th>
                <td>
                  {formatBytes(bytes("int8"))}
                  {ratio("int8") ? <span className="muted"> · {ratio("int8")!.toFixed(2)}× 压缩</span> : null}
                </td>
              </tr>
              <tr>
                <th>Tokenizer 等</th>
                <td>{formatBytes(tokenizer)}</td>
              </tr>
            </tbody>
          </table>
          <p className="fine-print">
            FP16 为权重半精度版本；INT8 采用 model_int8.onnx（8-bit 权重、fp32 激活的量化导出）。
            仓库内同时保留 Transformers.js 默认的 model_quantized.onnx（q8）作 A/B 对照。体积按实际文件
            字节统计，压缩比 = FP32 体积 ÷ 量化后体积。
          </p>
        </Card>

        <Card title="端侧运行时" subtitle="Transformers.js 3.8.1 + ONNX Runtime Web">
          <ul className="bullets">
            <li>
              优先 <strong>WebGPU + FP16</strong>：主线程探测 <span className="mono">navigator.gpu</span> 与{" "}
              <span className="mono">shader-f16</span>，显式传入 <span className="mono">device: "webgpu"</span>。
            </li>
            <li>
              不可用或初始化失败时，自动降级为 <strong>WASM + INT8</strong>，右侧状态栏与顶栏会明确标注后端。
            </li>
            <li>可手动强制 WASM FP32 作为质量基线，或强制 WASM INT8 / WebGPU FP16 做 A/B 对比。</li>
            <li>
              WASM 在 COOP/COEP 跨源隔离下启用多线程（最多 4 线程）；模型、tokenizer 与 wasm 二进制均由本地服务提供，
              推理不离开设备。
            </li>
            <li>
              所有 embedding 在 Web Worker 中执行，避免阻塞界面；同一批文本一次前向，批大小可调。
            </li>
          </ul>
        </Card>
      </div>

      <Card title="seekdb 数据层" subtitle="seekdb 1.4.0，本地 server 模式，MySQL 协议端口 2881">
        <div className="grid grid-3">
          <div>
            <h3>集合与索引</h3>
            <ul className="bullets">
              <li>每个知识库一个集合，schema 固定为：全文索引 <span className="mono">ik</span>（smart 模式）+ HNSW 向量索引（cosine，512 维）。</li>
              <li>行字段：<span className="mono">_id / document / metadata / embedding</span>；metadata 存 doc_id、标题、分块序号、来源。</li>
              <li><span className="mono">kb_registry</span> 与 <span className="mono">kb_docs</span> 两张普通表登记知识库与文档，支撑切换与会话恢复。</li>
            </ul>
          </div>
          <div>
            <h3>混合检索</h3>
            <ul className="bullets">
              <li>seekdb-js <span className="mono">hybridSearch()</span> 写入 <span className="mono">@search_parm</span>，调用 <span className="mono">DBMS_HYBRID_SEARCH.GET_SQL</span>。</li>
              <li>返回的单条 SQL 同时包含 <span className="mono">MATCH ... AGAINST</span> 与向量近邻条件，RRF（k=60）在库内融合。</li>
              <li>客户端只发送查询向量与文本，不做两路结果拼接；界面可查看实际执行的 SQL。</li>
            </ul>
          </div>
          <div>
            <h3>刷新与状态</h3>
            <ul className="bullets">
              <li>写入按批（8–128）执行，结束后统一 <span className="mono">refresh_index()</span>；也可选择每批刷新做对比。</li>
              <li>同名文档重导会先删除旧分块再写入，保证增量更新不重复。</li>
              <li>当前知识库、批大小、后端偏好与评测记录持久化在 localStorage，刷新页面后自动恢复。</li>
            </ul>
          </div>
        </div>
      </Card>

      <Card title="复现与测试口径" subtitle="固定设备 / 浏览器 / 语料 / 查询集，分别测试 WebGPU 与 WASM">
        <div className="grid grid-2">
          <div>
            <h3>启动</h3>
            <pre className="code">npm install
npm run setup:seekdb      # 或 docker compose up -d seekdb
npm run fetch-model       # 下载 bge-small-zh-v1.5 的 ONNX 文件
npm run build &amp;&amp; npm start  # http://127.0.0.1:8787</pre>
            <p className="fine-print">
              运行环境：Chrome / Edge 最新版；Node.js ≥ 20。seekdb 连接参数见 <span className="mono">server/src/config.mjs</span>，
              当前连接 {health ? `${health.db.config.host}:${health.db.config.port}/${health.db.config.database}` : "127.0.0.1:2881/test"}。
            </p>
          </div>
          <div>
            <h3>指标</h3>
            <ul className="bullets">
              <li>检索质量：固定 24 篇中文技术文档、26 条带标注查询，文档级 Recall@5 / nDCG@5 / MRR。</li>
              <li>分阶段计时：模型加载、冷启动推理、文档向量化吞吐、写入 + 刷新、查询向量化、seekdb 检索、端到端。</li>
              <li>首轮与热态分开；评测表取中位数，原始逐条数据可导出 JSON。</li>
              <li>降级验证：在支持 WebGPU 的浏览器使用 Auto；在禁用 WebGPU（chrome://flags 或启动参数）的环境重复同一流程。</li>
            </ul>
          </div>
        </div>
        <div className="env-line">
          <Chip tone="accent">seekdb {health?.db.version ?? "—"}</Chip>
          <Chip tone="neutral">Embedding 维度 {health?.dim ?? 512}</Chip>
          <Chip tone="neutral">本地推理 · 无云端 API</Chip>
          <Chip tone="good">向量与检索均落在 seekdb</Chip>
        </div>
      </Card>
    </div>
  );
}
