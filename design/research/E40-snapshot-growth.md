# E40 快照与历史增长：每回合 200KB，主因是逐点全量状态

**Question.** 连续游玩时存档与内存里的快照怎么长、长在哪？（goal 阶段二
"历史/快照/调试记录增长"项，离线可测部分）

**Setup.** `snapshot_growth.py` 与逐字段分析：env-11 的 12 回合真实证据
（`evidence-semantic-env-11-2026-11-27T1848-1519.json`），读取每回合
`snapshotAfterTurn` 的序列化体积并逐字段拆分。

**Results.**
- 快照体积 747KB → 2,949KB，均值 **+200KB/回合**；但 `transport.state`
  （当前世界状态）全程稳定在 **65KB**。
- 增长主因：`transport.pointStates` 327KB → 2,098KB（**+1.77MB**），
  `transport.idempotency` 289KB → 680KB（+0.39MB）。`pointStates` 每个提交点
  存 **一整份世界状态的拷贝**（`{version, state, stateDigest}`，约 65KB/点，
  32 点 ≈ 2.1MB）；`taskLedger` 只有 22KB 且基本不涨，叙事文本不到 10KB。
- 外推：100 点 ≈ 7–8MB、500 点 ≈ 30MB 量级的存档与同等的常驻内存（IndexedDB
  保存体 + 恢复时的解析对象）。

**Implication.** 这是"历史增长"的实体位置：每个点一份全量状态。候选修法
（都是存档格式变更，需版本化与迁移，属产品决策）：
1) 非 head/root 的点只保留 `stateDigest`，恢复与不变量检查按需用回放重建；
2) 仅 head 与 root 保留全量状态（现状检查用到这两处）；
3) 按字段差量存储（相对上一状态），压缩率取决于每回合变化量。
在接入任何修法前，需先验证回放路径（`replayWorld`）能等价重建逐点状态。

**Caveats.** 单世界、12 回合样本；快照含 harness 采集的附加字段的可能性
未逐项排除（已按字段拆分到 transport 内部）；未测手机端 IndexedDB 写入耗时。

**Artifacts.** `artifacts/goal/memory-baseline/snapshot_growth.py`、
`snapshot-growth.json`。E40。
