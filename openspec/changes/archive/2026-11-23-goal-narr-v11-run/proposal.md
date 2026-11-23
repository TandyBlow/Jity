# Proposal: goal-narr-v11-run

## Why

v11 数据（328 行）在本地训练两次被宿主内存回收。集群恢复后改在 GPU 分区完成训练，需要在真实页面验证；run113 又暴露了未知实体门的合法失败漏洞（重试丢名字后写成功）。

## What Changes

- 集群训练作业 276262（5 epoch）+ 构建 276264；按约 85 KB/s 的实测带宽改用 70 MB 适配器回传，本地合并/转换/量化，评估臂 Q4_K_M sha `f6b01bc1…`。
- 页面与驱动增加逐点叙述 prompt 抓取（`pointPrompts`），定位正文填充的根因。
- 未知实体门加严：组成员动作点名未知实体时，未带否定线索的成功 fact（即使丢了名字）也拒绝；有 blocked 判词则按其改写。单测 102 passed。
- 检查器两处误报修正：`unknown_entity_claim` 补 `没找到|没见到`；`band_claim` 不把「记下别人的识别带颜色」当成主角佩戴。
- 两轮五回合 run113 / run114 与产物入库。

## Capabilities

（无；训练数据验证与开发期门。）

## Impact

- `frontend/src/lib/world-engine/local/semantics/settlement/results.ts`、`settlement.test.ts`。
- `frontend/src/app/world-local/page.tsx`（arm sha、pointPrompts）；`accept-world-local.mjs`、`check-prose-facts.mjs`。
- 证据：`artifacts/goal/narration/run113-*.json`、`run114-*.json`、两份 prose-facts check、`read-v11-run-20261123.md`。
