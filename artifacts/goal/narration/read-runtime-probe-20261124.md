# 运行时探针：transformers.js WebGPU（2026-11-24）

## 配置

- @huggingface/transformers 4.3.2（Apache-2.0）+ onnxruntime-web WebGPU；Qwen2.5-0.5B-Instruct ONNX q4f16（`onnx-community`，483 MB，本地 `frontend/public/models/qwen25-0.5b-onnx`）。
- Edge headless，`--enable-unsafe-webgpu --ignore-gpu-blocklist`；适配器 nvidia/lovelace，`shader-f16` 可用。
- 探针：`.local/probe-transformers/`（静态服务 3190 + Playwright runner）。

## 结果

- 短提示（178 字符）：加载 14.0 s；prefill 1.65 s；30 tokens 解码 5.2 s；输出可读性差（0.5B）。
- 产品形状的长提示（2,400+ tokens）：ORT WebGPU 在 `BufferManager::Download` 失败（`MapAsyncStatus` 3，Invalid Buffer）。
- q4（非 f16）变体未测：需另下 ~400 MB；失败点在长上下文路径，不在 dtype 选择本身。

## 判定

- transformers.js WebGPU 在本机无法执行产品真实长度的提示，换运行时不解决移动档 60 秒问题。
- 结论：该运行时路线关闭（q4 变体可另测，但预期同一长上下文失败）。
- 依赖与探针文件保留在本地，供以后换模型/引擎时复用；不进入产品路径。
