# 分析补充：N arm 用全部子集，不用种子前缀

日期：2026-11-10。写于 b01 已分析、b02/v2 尚无任何 arm 结果之前。

## 问题

原预注册只写“对 N=1/2/4 做配对比较”，没有定义每个 N 取哪几个候选。初版实现取 `samples.slice(0, N)`：

- N=1 永远是 seed 17；
- N=2 永远是 17+29；
- N=4 永远是 17+29+43+61；
- seed 79/97 在 N=1/2/4 里从未被测试。

这样“N 越大越好”可能只是“换到了后面的种子”，不是多候选的收益。b01 因为 0 事实合格、arm gate 未通过，没有产生任何 arm 数字，所以现在修正不会篡改已看到的收益。

## 补充定义

对每个 case 的 6 个候选，N arm 评估**全部大小为 N 的子集**，每个子集是一次 trial：

- N=1：C(6,1)=6 次 trial；
- N=2：C(6,2)=15 次 trial；
- N=4：C(6,4)=15 次 trial。

每次 trial 用同一个确定性选择器在该子集内选一份；trial 的调用成本是该子集实际调用耗时之和。每个 arm 汇总：

- `selectedFactQualifiedRate`：选中事实合格的比例；
- `selectedPassRate`：选中可读合格（`decision=pass`）的比例；
- `meanSelectedCoverage`、`meanSelectedRepetition`、`meanSelectedPriorEcho`；
- `meanCallWallMs`、`meanCheckerMs`、`meanSelectionMs`；
- `trialCount` 和 `totalCalls`。

跨 case 汇总时按 trial 数加权，不按 case 等权。选择器顺序不变：事实合格 > 必述覆盖 > 文内重复 > priorEcho > 种子；不看字数、不看 LLM 自评分。

## 不改变什么

- 不改变预注册的重复/合格/收益/停止规则；
- 不改变 N=1/2/4 的 arm 集合；
- 不改变选择器；
- 不把 b01 的 4 簇/0 合格当收益；
- 不因为补充定义而放宽 arm gate（仍需至少 2 个 case 过多样性门）。

## 限制

- 全部子集之间共享同一批候选，trial 不独立；报告只做描述性汇总，不做显著性检验。
- N=1 的 6 个 trial 各自包含首调用冷启动差异；`meanCallWallMs` 会把冷启动摊进 N=1，比较时同时看每个 trial 的原始耗时。
- 这是 HPC 离线成本，不是浏览器时序；60 s/300 s 仍由 09 实测。
