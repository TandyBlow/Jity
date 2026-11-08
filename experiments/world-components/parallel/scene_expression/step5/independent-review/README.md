> **状态（2026-11-08 起）：评审已停止。** 产品负责人判定整批玩家文案验收不合格（见 `step6/verdict-stop-naturalness.md`），不再邀请自然度偏好投票；本目录空白模板保留，映射不揭示。若将来恢复，按本文件流程另起样本，不复用这批选票位。

# 独立评审（与执行方初审分开）

## 边界

- 执行方初审：`step5/clauses.jsonl`、`step5/adjudication.json`、`step5/summary.md`。**只读，不改。**
- 独立评审记录写在本目录，不覆盖初审；改判写 `differences.md`，保留理由。
- 自然度评审者只看 `step5/review-packet.md`；提交选票前不提供 `step4/ballot/order.json`、`step4/scores.json`、`step5/clauses.jsonl`。

## 分句事实核验

1. 打开 `clause-review.jsonl`，逐行填 `decision`（`supported` / `unsupported` / `undetermined`）、`sourceId`、`reason`。
2. `sourceId` 只写实际依赖的来源：`initial.*` / `after.*` 字段路径、素材来源 ID（`item:` `loc:` `char:` `program:`）或 `delta.*`。
   自动候选只在 `step5/clauses.jsonl` 里，供执行方使用；独立评审请自行核对状态，不要照抄候选。
3. 判据：句子断言能否从已提交状态、Δ 或授权素材逐项找到来源；任务目标、物品可见不授权新动作。
4. 与初审不一致的，在 `differences.md` 按“分句 → 初审结论 → 独立结论 → 理由”登记。

## 自然度

1. 只读 `step5/review-packet.md`，按题填写 `naturalness-return.json` 的 `choice`（`甲`/`乙`/`丙`/`看不出差别`）与可选 `reason`。
2. 十题全部作答后再提交；提交前不打开映射。
3. 提交后由执行方运行 `reveal_naturalness.py` 揭示 `order.json` 映射并统计（缺答会拒绝统计）。

## 门槛

有效配对 6 题（四题仅程序输出）＜10，自然度门槛维持 `not_evaluable`；独立评审完成也不改变该状态，只能补充“六题配对内的比较”。
