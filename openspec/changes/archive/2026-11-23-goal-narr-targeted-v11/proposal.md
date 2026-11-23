# Proposal: goal-narr-targeted-v11

## Why

v10 的 6 条「交接失败 + NPC 看规则」尚未验证（训练被宿主回收）。复核 v9/v10 数据时发现两处提示缺陷：弧廊短讯机结算把林亦舟写成红色识别带与「她」，钟楼 H 的结算主体为空。用户要求继续手写数据并强调质量，先修缺陷再扩充。

## What Changes

- 修正 `TarcadeD`（红带/她 → 蓝带/他，正文同步改为发烫）与 `TtowerH`（删除空主语结算）。
- 新增 18 条手写样本：六个新基（等待 + NPC 看规则 ×3、等待 + NPC 短讯机、清点 + 秦越解钥匙、问话 + 林亦舟挪演习枪）与三场景「交接失败 + NPC 看规则」各 2 条变体。
- 检查器 `unknown_entity_claim` 否定线索补 `没找到|没见到`。
- `sft-v11` 328 行；检查器 0/18。

## Capabilities

（无；手写数据与开发期检查。）

## Impact

- `.local/narr-train/targeted-v11*`、`sft-v11.jsonl`（gitignored）。
- `frontend/scripts/product-acceptance/check-prose-facts.mjs`（否定线索一行）。
- 证据：`artifacts/goal/narration/read-v11-data-20261123.md`、`prose-facts-check-v11-data.json`。
- 训练未跑，交付判定不变（D-026）。
