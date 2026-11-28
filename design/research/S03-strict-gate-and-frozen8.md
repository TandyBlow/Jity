# S03 严格程序门与冻结八场景（goal 臂）

**Question.** 在 S01 严格标准下，`taskStage=goal` 臂在真实页面里会不会把“只完成目标一部分”的事实判成达成？冻结八场景跑下来与混合臂差多少？

**Method.** 单回合输入「我把胸前的护目镜戴好，确认镜片没有裂纹，再穿好演习背心，拿上自己的演习枪。」（`smoke-goal-achieve-20261128c.json`）；随后用从冻结证据提取的八场景输入（`turns-frozen-8.json`）跑 `?micro=1&taskStage=goal`，同一无头 Edge/单机环境。goal 臂启用 `requireProgramCoverage: true`：目标分解条件必须全部覆盖且事实结果为 completed，才进入模型打分；模型阈值 0.5。

**单回合结果**

| 指标 | 值 |
|---|---|
| 回合 | COMPLETED，0 problems |
| 等待 / accepted | 57.35 s / 13.73 s |
| tasks LLM 调用 | 0（三次 tasks 均为 program） |
| goal-tasks 调用 | 1 次，候选仅 `fingel/task_fingel_camera`（0.124） |
| 提交任务 | 无（护目镜与装备都 pending） |

结果事实 f2 实际是「路明非把胸前的护目镜戴好，确认镜片没有裂纹（达到目的）」，但该事实出现在**休息点**（`point_round_3_2`）的任务阶段；玩家点的任务阶段没有调用 goal 端口（本回合的 updates 任务调用只有休息点与两个自动点），所以 `task_lu_goggles` 没有进入候选。严格门在该休息点正确拒绝 `fingel_camera`。

**与前两次冒烟的差异**

- 无严格门时，同一条护目镜事实被行为克隆模型判 `task_lu_kit` 0.617 达成；严格门要求 item+action（拿到/装备）后把它排除。
- 跨人物 `task_lin_safe` 不再由路明非的事实触发（结构修复 + 单测）。
- 严格门把“目标条件不完整”的事实挡在模型之前，避免模型用语义相似度补齐不存在的子句。

**遗留**

- 玩家点的任务阶段为什么没有出现（更新调用只有休息点），需要按点级调用记录继续查；这影响“玩家自己的任务在同一回合达成”的能力。
- 严格门依赖 `decomposeTask` 的条件集；`task_nono_squad` / `task_fingel_help` 这类只有 target 条件的目标仍会把判断交给模型。
- 八场景结果见下节。

**Artifacts.** `smoke-goal-achieve-20261128c.json`；`turns-frozen-8.json`；`compare_scenarios.py`。S03。


## 冻结八场景结果（goal 严格臂）

证据 `smoke-goal-frozen8-20261128.json`：8/8 COMPLETED、0 problems、每回合 tasks 阶段均为 `program`（0 次 tasks LLM）。回合等待 40.8–92.8 s（turn1 68.3、turn6 69.8、turn8 78.7）；accepted 8.1–22.5 s。

与混合臂（`10-scenarios-pi-2026-11-28T1041-fbe4.json`）逐回合比较：

| 回合 | 混合臂新增 | 严格臂新增 |
|---|---|---|
| 1 | chu_line / lin_sent / lu_rules / shen_checked | 同左 |
| 2 | — | — |
| 3 | **lu_kit** | **—** |
| 4 | — | — |
| 5 | — | — |
| 6 | lu_route | lu_route |
| 7 | — | — |
| 8 | — | — |

最终任务集合唯一差异：混合臂多 `lu_kit`。严格臂保留了其余全部达成，只去掉了“走进器材棚即拿到护目镜与装备”的误判。这正是 S01 期望的行为；按旧 14/14 口径会少 1 条，需用户裁决是否把旧口径改为严格口径。

**结论**：任务阶段已经在冻结八场景上做到 0 次 LLM 调用，且严格标准只删掉一条语义错误达成。下一步是补齐严格金标正例、决定 14/14 口径，并把同样的“候选生成 + 严格门 + 微型裁决”推广到 subtasks / personality / sanity 等阶段。

**Artifacts.** `smoke-goal-frozen8-20261128.json`；`compare_scenarios.py`；S03。
