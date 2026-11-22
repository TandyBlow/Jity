# Tasks

## 1. 适配器

- [x] 1.1 `WebLlmInferenceEngine`（load/complete/dispose/cancel，流式与首次 token）。
- [x] 1.2 页面 `runtime=webllm` 开关（语义+叙事共用 Qwen3-4B）与证据字段。
- [x] 1.3 tsconfig 类型映射解决 `crossOriginStorage` 冲突；`next build` 通过。

## 2. 冒烟与测量

- [ ] 2.1 单回合冒烟（`turns-semantics-s02-only`，10 分钟回合上限）。
- [ ] 2.2 s05/s06 各 2 次，量结算门与交还时间。
- [ ] 2.3 移动模拟档（核显）重测；写证据与 D-022/D-023。

## 3. 收尾

- [ ] 3.1 `npx vitest run`、`openspec validate goal-webllm-adapter --strict`，归档，提交，打 tag `goal-webllm-adapter-20261122`。
