# N11 八场景与二十输入：rules 臂 8/8 与 17/20 无异常，验收被内存守护中断

**Question.** 零参数叙事臂在真实页面上能通过多少既定验收？不加载叙事模型时，八场景、
二十输入、刷新恢复各是什么结果？

**Setup.** `?narrationCandidate=rules`，产品服务器 3177，验收驱动
`accept-world-local.mjs --allow-program`；两组输入：`scenarios-independent.json`
（8 个场景）与 `turns-20.json`（20 个输入）。

**Results.**
- **八场景：8/8 回合，0 problems、0 turnFailures，status COMPLETED。** 每回合正文
  456–703 字，等 34–70 秒（全是 0.6B 结算）。刷新恢复：entries 8→8、state/history
  一致、`overallRestored=true`；网络只请求 `Qwen3-0.6B-Q4_K_M.gguf`（加载与刷新各
  一次），**没有任何 1.7B 请求**。
- **二十输入：17/20 回合完成、0 problems、0 failures。** 正文 480–628 字/回合，等
  35.6–71.2 秒；每回合 `source=program`、`narrationModel=rules`、叙事任务
  `source=rule`（每回合 2–4 次）。跑到第 18 个回合时，系统内存守护同时终止了产品
  服务器与验收进程，证据按回合落盘，保留 17 个回合。
- 未完成：二十输入最后 3 个回合、刷新恢复、`--regenerate-last`、离线、移动端仿真。
  这些都依赖重新启动 3177 服务器；内存守护要求先报告、不自动重启。

**Interpretation.**
- 八场景门禁在“零叙事模型”下已经通过：回合、恢复、网络请求三类证据都成立。二十输入
  的前 17 个回合同样没有异常，中断原因是机器内存而不是代码或叙事臂。
- 目前唯一可见的失败类型仍是表达质量（电报体、NPC 结果一句一条），没有事实类失败：
  17 个回合里没有空正文、没有结算失败、没有 source 变化。
- 剩余验收项在服务器重启后即可继续；离线与移动端仿真各约 4 分钟，二十输入补跑约 4 个
  回合。重生成已经接进驱动，规则臂是确定性的，判定以“叙事事件数增加”为准。

**Caveats.** 二十输入是 17/20 的部分结果；八场景来自同一世界；结算仍用 0.6B
（本阶段允许）；`--allow-program` 是驱动实验开关，不等于产品默认切换。

**Artifacts.** `artifacts/goal/narration-rules/{scenarios8-rules-b-slim.json,
turns20-rules-slim.json}`（精简证据；原始 6.6MB/8MB 文件同目录未入库）。N11。
