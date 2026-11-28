# S02 目标级任务阶段首次浏览器冒烟

**Question.** `taskStage=goal` 臂能否在真实页面里接管任务阶段、不调用 0.6B，并给出可检查的分数与状态？

**Method.** 单回合冒烟：输入「我把胸前的护目镜戴好，对着光检查镜片有没有裂纹。」；`?micro=1&taskStage=goal`；无头 Edge、单机、`--header-shim`；证据 `results/product/evidence/smoke-goal-taskstage-20261128d.json`。对照组是同一输入、同一环境下的混合臂（`smoke-goal-taskstage-20261128b.json`）。

**结果**

| 指标 | goal 臂（d） | 混合臂（b） |
|---|---|---|
| 回合状态 | COMPLETED，0 problems | COMPLETED，0 problems |
| 等待 / accepted | 71.6 s / 23.8 s | 103.8 s / 14.5 s |
| tasks 阶段来源 | 3 次 `program`，0 次 model | 1 次 model（LLM 验证器） |
| goal-tasks 统计 | 1 次，2 个候选对 | — |
| 达成任务 | 无 | `task_fingel_deal`（LLM 验证器） |
| `task_lu_goggles` | pending | pending |

goal 阶段的候选与分数（`taskScope.goalTasks.scored`）：

- `fingel/task_fingel_camera`：fact f6，p(yes)=0.124
- `lin/task_lin_call`：fact f7，p(yes)=0.142

两者都低于 0.5，未达成。玩家输入对应的 `task_lu_goggles` 没有进入候选：结果事实「路明非检查了护目镜。」与目标「把胸前护目镜戴好并确认镜片没有裂纹」的词面重叠不足 0.2，被 `sharesGoalWording` 预筛掉。

**Findings**

1. 端到端打通：任务阶段可以在真实页面用 10.5MB int8 模型完成候选打分，且 tasks 的 LLM 调用为 0。
2. 同一输入下混合臂把 `task_fingel_deal` 判达成（“检查相机备用电池、准备拍摄” vs 目标“用路线情报换到拍摄机会”），goal 臂拒绝——按 S01 严格标准，goal 臂更接近正确，但这不是行为等价。
3. 候选预筛 `sharesGoalWording ≥ 0.2` 会漏掉语义相关但词面差异大的事实（护目镜戴好 vs 检查了护目镜）；需要按条件/实体生成候选，而不是只看整句重叠。
4. 该回合没有真正达成任何任务，不能证明“严格语义下能正确提交达成”；需要设计一个明确达成的输入再跑，再跑冻结八场景。

**Next**

1. 设计「明确达成 / 部分 / 未达成」三类输入各一条，跑 goal 臂；检查 `goalTasks.scored` 与提交状态。
2. 候选生成改为「任务条件实体/动作 × 事实」的交集，不只用整句重叠；阈值仍用 0.5。
3. 八场景夹具在 goal 臂跑一遍，报告严格达成、旧标准一致率与被跳过变化。

**Artifacts.** 本文件；两份冒烟证据；`inspect_smoke.py`。S02。

## 追加：明确达成输入（同日）

输入「我把胸前的护目镜戴好，确认镜片没有裂纹，再穿好演习背心，拿上自己的演习枪。」，证据 `smoke-goal-achieve-20261128.json`：

- 结果事实 f1 只有「路明非把胸前的护目镜戴好，确认镜片没有裂纹（达到目的）」，没有背心/枪。
- goal 阶段候选与分数：`lu/task_lu_kit` 0.705、`lu/task_lu_goggles` 0.533、`lin/task_lin_safe` 0.546，三者都提交达成。
- 按 S01：`task_lu_goggles` 正确；`task_lu_kit` 错误（目标还要求演习装备）；`task_lin_safe` 错误（用了路明非的事实，事实没有点名林亦舟）。

两个结论：

1. **跨人物缺陷是结构性的，已修**：`micro/goal-verifier.ts` 现在只允许其他人物的事实支持某任务当事实点名该任务负责人（与旧 reader 一致），并有单测。
2. **行为克隆模型会接受只满足目标一部分的事实**：`task_lu_kit` 0.705 高于 `task_lu_goggles` 0.533，正是 S01 警告的旧错误。该模型保持 control 定位，不用于严格标准；严格裁决需要严格金标训练或程序条件门。

**Artifacts.** `smoke-goal-achieve-20261128.json`；跨人物修复与测试。S02 追加。
