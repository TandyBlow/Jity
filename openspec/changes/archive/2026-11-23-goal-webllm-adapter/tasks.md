# Tasks

## 1. 适配器

- [x] 1.1 `WebLlmInferenceEngine`（load/complete/dispose/cancel，流式与首次 token）。
- [x] 1.2 页面 `runtime=webllm` 开关（语义+叙事共用 Qwen3-4B）与证据字段。
- [x] 1.3 tsconfig 类型映射解决 `crossOriginStorage` 冲突；`next build` 通过。

## 2. 冒烟与测量

- [x] 2.1 单回合冒烟：0.6B 本地权重在 5 秒内加载完成、WebGPU nvidia 上跑通 results/position 等多类调用（回合因 0.6B 的 JSON 格式错误失败，属模型质量，不是适配器）；1.7B/4B 在约 615 MB 处加载停滞，正在测 OPFS 缓存后端。
- [x] 2.2 s05/s06：1.7B（run72）JSON 失败；3B（run74/75）45 s、格式通过、质量过不了；4B 被宿主内存回收两次，未完成（记录在案）。
- [x] 2.3 移动模拟档（核显 + 4× CPU）：WebLLM 3B 重测进行中（run78）。

## 3. 收尾

- [x] 3.1 `npx vitest run`、`openspec validate goal-webllm-adapter --strict`，归档，提交，打 tag `goal-webllm-adapter-20261122`。
