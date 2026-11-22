# 质量基线（开发门，2026-11-22）

## 范围

- 17 个 run、42 个回合：run27–run40 的语义证据 + run41 的 20 输入套件（chunk1–3、chunk3b 部分）。
- 检查器：`check-prose-facts.mjs`（input_echo、band_claim、door_claim、placeholder、meta_note、unknown_entity_claim）。

## 结果

| 指标 | 数值 |
|---|---|
| 回合数 | 42 |
| 至少命中一条门的回合 | **26 / 42** |
| input_echo | 11 |
| band_claim | 9 |
| unknown_entity_claim | 11（含 11/11 个 s06 合法失败回合） |
| meta_note | 2 |

按不同夹具看：

- **s06 合法失败**：所有重复样本都命中 `unknown_entity_claim`（11/11）；其中 4/5 的结算层也判成功（`goal-legal-rate`）。
- **s05 清点物品**：`input_echo` 稳定出现（复述「识别带和胸袋里的弹匣」），部分样本叠加 `band_claim`。
- 套件其他回合（s01–s04、s07–s14）多数干净；命中集中在 s05/s06 这两类夹具。

## 口径与偏差

- 这是**开发门**计数，不是验收门槛；G6 的 5/5 零硬错仍以 `acceptance.md` 为准。
- s05/s06 在多个 run 里重复，命中数不代表自然分布；按夹具看更可靠。
- 检查器只覆盖既有类别；`judgment/fact` 矛盾、结算层错误（`legal_failure_not_enforced`）由另外的门或人工读评负责。

## 用途

D-022 的任何路线（微调、自修复、换运行时、改门槛、收尾）都用同一套门与同一批夹具对照；基线是 26/42（回合口径）与 s06 11/11。


## 默认路径对照（G8 的 20 输入）

同一检查器跑 G8 默认调度的 20 个输入：**5/20 个回合命中**（input_echo 3、band_claim 2、unknown_entity_claim 1、meta_note 1）；其中 s06 合法失败命中 unknown_entity_claim。证据 `prose-facts-g8-default-20261122.json`。

两套口径不能直接相加：42 回合的 26/42 含大量重复的 s05/s06 夹具；20 输入的 5/20 是自然分布的单次采样。共同结论是 s06 合法失败在两套口径里都失败。
