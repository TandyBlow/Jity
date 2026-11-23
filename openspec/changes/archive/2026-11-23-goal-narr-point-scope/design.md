# Design: goal-narr-point-scope

## 规则

- 每个 point 只拿自己的结算文本；空 point 不回退。
- 行动原文只进玩家所在 point 的提示；instant point 只写自己 roster 的事实。
- plannedActors 在 beginSubmission 清空，pointId 每回合唯一。

## 结果

- run117：5/5、31.8–56.8 s 区间内（49.8/39.8/38.1/56.8/38.6），检查器 0；动作/结算句重复消失，s06 合法失败叙事正确。
- 剩余：两 point 各写一遍 NPC 状态、正文偏短。

## 判定

- 4.2 人工读 5/5 零硬错；4.3 重复与文风仍不过。D-026 不变。
