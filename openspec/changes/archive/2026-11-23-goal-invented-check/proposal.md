# Proposal: goal-invented-check

## Why

run77 的 `trained` 候选在 3B 上表面通顺，却凭空写了「夕阳、风声、汗、泥土、焦糊味」——这些都不在已结算事实里，撞「无捏造」硬门；现有检查器只查识别带/门/回声/未知实体/占位/注记，漏掉这一类。定向微调的数据过滤也需要这条门。

## What Changes

- `check-prose-facts.mjs` 新增 `invented_detail`：一组窄域氛围词（夕阳、风声、汗、泥土、焦糊、气味等）若出现在正文、且不在叙事提示中，就报错并给出上下文。
- 用 run75（builtin）与 run77（trained）验证：run77 命中 6 条，run75 不误报。
- 不改运行期、不改产品。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。纯开发期检查器；`.openspec.yaml` 设 `skip_specs: true`。

## Impact

- `frontend/scripts/product-acceptance/check-prose-facts.mjs`
- `artifacts/goal/narration/prose-facts-check-invented.json`
