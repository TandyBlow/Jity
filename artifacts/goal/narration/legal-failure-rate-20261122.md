# s06 合法失败的层间失败率（2026-11-22，run40）

## 条件

- 同一夹具 s05/s06，base 1.7B，`schedHandback=player`、`offscreenPolicy=skip`，复跑 5 次。
- 判据：`expect:'legal_failure'` 门（results 出现 `completed`/`achieved`）＋人工读正文。

## 结果

| 运行 | settlement | 正文 | 交还时间（s05 / s06） |
|---|---|---|---|
| a | 判成功（completed + achieved） | 照抄成功 | 39.5 / 44.1 s |
| b | 判成功（achieved） | 照抄成功 | 38.2 / 29.7 s |
| c | 判成功（completed + achieved） | 照抄成功 | 40.8 / 45.2 s |
| d | 判成功（completed + achieved） | 照抄成功 | 46.3 / 44.4 s |
| e | 判 blocked（not_achieved / partial） | **仍写成已发生**（「阿豹接住后转交给了裁判」） | 39.2 / 25.5 s |

- 结算层误判：**4/5**。
- 剩下 1 次结算判 blocked，但叙事仍把被拒动作写成已发生——**叙事层错 1/5**。
- 合计：**5/5 个回合在某一层失败**；s06 从未干净通过。
- 早交还臂的 10 个回合全部 ≤60 s（25.5–46.3 s）。

## 对 D-022 的含义

1. 这不是偶发采样：结算误判是高频（4/5），叙事层另有独立失败（1/5）。
2. 质量路线必须同时覆盖结算（G5）与叙事（G6）；只修叙事或只修结算都不够。
3. 开发期需要两条门：已有的 `legal_failure_not_enforced`（结算）＋一个「被拒动作写成已发生」的正文门（还没有，正文检查器当前漏掉 run40-e 这类）。
4. 早交还的时间口径稳定：15 个回合（run37/38/40）全部 ≤60 s。
