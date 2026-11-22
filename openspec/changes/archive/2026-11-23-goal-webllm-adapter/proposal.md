# Proposal: goal-webllm-adapter

## Why

用户 2026-11-22 批准「WebLLM 适配器原型」：质量与移动两端共用的一把钥匙是换运行时。wllama 的 blob 路径装不下 2.3 GiB 的 4B，而 WebLLM 自带缓存分片，且预置了 `Qwen3-4B-q4f16_1-MLC`。先做评估运行时，不改默认。

## What Changes

- 新增 `WebLlmInferenceEngine`（`runtime/webllm-engine.ts`）：实现现有 `InferenceEngine` 端口，流式输出、可取消、记录首次 token。
- 页面新增 `runtime=webllm` 评估开关：语义与叙事共用同一个 WebLLM Qwen3-4B 引擎；默认仍是 wllama。
- `tsconfig` 把 `@wllama/wllama` 类型映射到 `esm/index.d.ts`，解决与 `@mlc-ai/web-runtime` 的全局 `Navigator.crossOriginStorage` 声明冲突。
- 证据记录 `runtime` 与 `webllmModel`。
- 先跑单回合冒烟，再跑 s05/s06 与移动模拟档。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。评估运行时；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `frontend/src/lib/world-engine/runtime/webllm-engine.ts`（新增）
- `frontend/src/app/world-local/page.tsx`、`frontend/tsconfig.json`
- `frontend/package.json`、`package-lock.json`（`@mlc-ai/web-llm@0.2.89`，Apache-2.0）
- 证据：`artifacts/goal/semantics/run44-*`
