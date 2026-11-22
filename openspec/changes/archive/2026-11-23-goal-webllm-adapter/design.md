# Design: goal-webllm-adapter

## Context

见 proposal。`InferenceEngine` 只有 load/complete/dispose；页面已有 `resilientEngine` 的端口包装，WebLLM 版本照抄形状。模型用 WebLLM 预置列表里的 `Qwen3-4B-q4f16_1-MLC`（同列表还有 0.6B/1.7B/8B 可换）。

## Goals / Non-Goals

- Goals：让 4B 在浏览器里真正跑起来，给出时间与质量数据。
- Non-Goals：不切默认、不做 JSON schema 约束、不做离线缓存策略、不改移动门槛。

## Decisions

1. **4B 同时承担语义与叙事**：质量瓶颈在结算层（0.6B），只换叙事救不了；一个引擎两个角色也最省内存。
2. **类型映射而不是 patch node_modules**：wllama 与 web-runtime 的全局声明冲突用 tsconfig paths 指向 d.ts，配合 `skipLibCheck`；npm 重装不会回退。
3. **流式 + 可取消**：`chat.completions.create({stream:true})`，取消调 `interruptGenerate()`；否则页面停止键对 WebLLM 无效。

## Risks / Trade-offs

- [首次下载] 模型从 HF 拉取，2–3 GiB；冒烟把回合超时放到 10 分钟，只测可行性。
- [输出格式] WebLLM 不接 wllama 的 jsonSchema 选项；结算任务的 JSON 校验仍由现有 codec 负责，可能增加重试。
- [内存] 4B + 页面 + 浏览器可能触发宿主回收；冒烟一次一回合。

## Migration Plan

不适用（评估运行时）。

## Open Questions

- 4B 的结算质量是否达到零硬错；下一批 s05/s06 数据回答。
