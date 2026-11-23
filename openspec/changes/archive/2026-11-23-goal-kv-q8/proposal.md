# Proposal: goal-kv-q8

## Why

浏览器内存压力反复触发宿主回收。实测语义模型上下文 12,288 的 KV 缓存按 f16 约占 1.38 GB，而语义提示最大只有 1,965 tokens（近期）/ 6,674（20 输入旧记录）；wllama 支持量化 KV，可在不改上下文的前提下把这块减半。

## What Changes

- wllama 引擎透传 `cache_type_k` / `cache_type_v`（带引擎级测试）。
- 页面为语义 0.6B 打开 q8_0，叙事 1.7B 保持 f16（run119 显示叙事对量化可能敏感，单样本不作因果）。
- run119/run120 五回合验证：run120 5/5、40.1/34.0/49.1/46.9/34.8 s、检查器 0。

## Capabilities

（无；运行时内存参数与验证。）

## Impact

- `frontend/src/lib/world-engine/runtime/wllama-engine.ts`（+test）、`frontend/src/app/world-local/page.tsx`。
- 证据：`artifacts/goal/narration/run119-*.json`、`run120-*.json`、两份 prose-facts check、`read-kv-q8-20261123.md`。
