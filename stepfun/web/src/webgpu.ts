export interface WebgpuInfo {
  available: boolean;
  fp16: boolean;
  reason: string;
}

export async function detectWebgpu(): Promise<WebgpuInfo> {
  const gpu = (navigator as any).gpu;
  if (!gpu) {
    return { available: false, fp16: false, reason: "当前浏览器未提供 navigator.gpu" };
  }
  try {
    const adapter = await gpu.requestAdapter();
    if (!adapter) {
      return { available: false, fp16: false, reason: "requestAdapter() 返回空（无可用 GPU 适配器）" };
    }
    const fp16 = adapter.features.has("shader-f16");
    const info = (adapter as any).info;
    const name = info?.description || info?.vendor || "GPU adapter";
    return {
      available: true,
      fp16,
      reason: fp16 ? `WebGPU 可用（${name}，支持 shader-f16）` : `WebGPU 可用（${name}，不支持 shader-f16）`,
    };
  } catch (error) {
    return { available: false, fp16: false, reason: `WebGPU 探测失败：${(error as Error).message}` };
  }
}
