# S09 micro-only 冻结二十输入

**Question.** micro-only 配置（不加载 0.6B）在冻结二十输入上能否 20/20 完成、刷新恢复、并保持与混合臂相近的状态？

**Method.** `/world-local?semanticArm=micro-only`，无头 Edge、`--header-shim`，冻结 `turns-20.json`；证据 `results/product/evidence/smoke-micro-only-turns20-20261129.json`。

**结果（回合）**

- 20/20 回合完成、0 failures（每回合 `problems=none`）；
- 回合等待 18.7–43.4 s（首段可读 2.6–5.7 s 草稿；accepted 5.8–15.4 s）；
- 模型请求：仅 `qwen3-1.7b-narr-lora-Q4_K_M.gguf`；`Qwen3-0.6B` 请求 **0**；`__worldArm.semanticEngine=absent`；
- 语义调用：action/targets/results/updates/subtasks/continuation 全部 program/micro，**0 次语义模型**；narration 由 1.7B 生成。

**刷新恢复**

`refreshRestore`：20 → 20 条历史，`pageSaysRestored=true`，historyStable=true，任务快照稳定，恢复耗时 46.4 s（含 1.7B 重载）；重载后模型请求仍只有 1.7B。

**状态对照（与 `09-turns20-pi.json`）**

- 最终位置：**0 差异**；
- 任务集合：双方都是 73 条，无新增/缺失；
- 任务状态差异 3 条：`nono/task_nono_squad`、`fingel/task_fingel_camera`、`fingel/task_fingel_help` 在混合臂 achieved、micro-only pending。三条都是条件弱/含目的从句的目标；严格台账没有覆盖全部条件，按 S01 保守不达成。是否属于“被跳过的合法达成”需逐条事实核查（进入金标复核队列）。

**Caveats**

- NPC 行动为模板闭集；targets 有弃权空目标；position/appearance/personality/sanity 保守无变化（本次未逐条读评合法变化）；
- 任务最终裁决仍是行为克隆模型（S01 control）；严格金标模型未训练；
- 叙事仍用 1.7B（S06 范围）。
