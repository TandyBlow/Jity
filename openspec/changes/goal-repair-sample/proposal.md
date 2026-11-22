# Proposal: goal-repair-sample

## Why

D-022 的候选之一是「模型自修复第二遍」。在改产品设计前，先用一个独立脚本验证：把失败的叙事草稿连同它自己的提示交回同一模型，要求只改与事实矛盾的地方，模型能不能把「被阻止的动作」改掉。成本一小时以内，不改产品路径。

## What Changes

- 新增 `repair-sample.mjs`：读取语义证据里的叙事提示与草稿，构造「上一稿 + 修订要求」提示，用产品同款 wllama + 1.7B 生成 3 次。
- 两个用例：run40-e s06（结算判 blocked、正文写成已发生——修复应有空间）与 run37 s06（结算本身判成功——修复救不了，用于标出边界）。
- 写证据与 D-022 结论。
- 不改产品、不改默认。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。独立原型脚本；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `frontend/scripts/product-acceptance/repair-sample.mjs`
- `artifacts/goal/narration/repair-sample-20261122.json`
- `design/goal/decisions.md`（D-022）
