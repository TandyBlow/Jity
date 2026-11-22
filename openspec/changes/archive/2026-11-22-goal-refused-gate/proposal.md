# Proposal: goal-refused-gate

## Why

run40-e 暴露了正文检查器的盲区：结算已经判 `blocked`，正文仍把「把红色电台递给阿豹」写成已发生，现有类别（识别带/门/回声/占位/注记）全都没报。没有这条门，质量读数会漏掉一类硬错。

## What Changes

- `check-prose-facts.mjs` 新增 `unknown_entity_claim`：从玩家输入里取「给/向/让/跟 + 2–3 字」作为引入的实体名；若该名字不在叙事提示的已知名单里、且正文的相应句子没有否认/拒绝措辞，就报错并给出原句。
- 用它复跑 run37/run40 的证据：3 个 s06 全部命中（含 run40-e），s05 无误报。
- 更新 D-022 与 ledger R01/R11 的证据。
- 不改运行期、不改产品。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。纯开发期检查器；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `frontend/scripts/product-acceptance/check-prose-facts.mjs`
- `design/goal/decisions.md`、`design/goal/ledger.md`
- `artifacts/goal/narration/prose-facts-check-run37-40.json`
