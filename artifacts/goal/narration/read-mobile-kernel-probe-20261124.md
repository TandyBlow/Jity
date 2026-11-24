# 探针 A：wllama 内核升级对比（2026-11-24）

## 条件

- Edge headless，`--enable-unsafe-webgpu --ignore-gpu-blocklist`，无 `--force_high_performance_gpu`（核显），CPU 4× 限速。
- 模型 `Qwen3-0.6B-Q4_K_M.gguf`（396 MB）；提示 2,780 字符 ≈ 2,196 tokens（position 量级）；`n_ctx 4096`、全层 offload、`cache_prompt: true`、32 tokens 解码。

## 结果

| 版本 | libllama 构建 | prefill | 解码 | 备注 |
|---|---|---|---|---|
| wllama 3.8.1 | b11364-46ca246 | 18.55 s（118 tok/s） | 14.7 tok/s | 基线 |
| wllama 4.0.0 | b12637-0b51bb2 | 23.10 s（95 tok/s） | 16.4 tok/s | 核显 Flash Attention 不支持，prefill 慢 20% |

- 两者都在 Intel gen-12lp 核显 WebGPU 上运行；4.0.0 的新内核在这块核显上不占优。
- 结论：**升级路线未达 ≥2× 目标**（0.80×）。当前 llama.cpp WebGPU 内核在本机核显上没有可用的快路径；Flash Attention 缺失限制了 prefill。

## 判定

- 探针 A 记为证伪（未达 ≥2×），证据保留；不据此改产品默认。
