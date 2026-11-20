# 叙事判分器 v1 评测报告（自动生成）

- 正例（已审目标正文）：0/132 被误判 fail；uncertain 45
- 合法变体：0/528 被误判 fail；uncertain 182
- 单点负例：532/734 按预期规则判出
- 真实输出对照草稿标注：3/24 一致，误报 0，严格漏报 1，人工存疑但机器放行 8，abstain 12
  矩阵（行=人工，列=机器）：{"humanPass": {"checkerPass": 2, "checkerUncertain": 3, "checkerFail": 0}, "humanUncertain": {"checkerPass": 8, "checkerUncertain": 2, "checkerFail": 0}, "humanFail": {"checkerPass": 1, "checkerUncertain": 7, "checkerFail": 1}}

- drop-fact: 判出 42/84，uncertain 24，漏 18
- explicit-duration: 判出 132/132，uncertain 0，漏 0
- goal-leak: 判出 55/55，uncertain 0，漏 0
- inner-thought-other: 判出 132/132，uncertain 0，漏 0
- invented-name: 判出 0/132，uncertain 132，漏 0
- numeric-panel: 判出 132/132，uncertain 0，漏 0
- reverse-direction: 判出 28/29，uncertain 1，漏 0
- swap-actor: 判出 11/38，uncertain 23，漏 4
