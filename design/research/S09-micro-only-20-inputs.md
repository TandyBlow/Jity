# S09 micro-only 冻结二十输入

**Question.** micro-only 配置（不加载 0.6B）在冻结二十输入上能否 20/20 完成、刷新恢复、并保持与混合臂相近的状态？

**Method.** `/world-local?semanticArm=micro-only`，无头 Edge、`--header-shim`，冻结 `turns-20.json`；证据 `results/product/evidence/smoke-micro-only-turns20-20261129.json`。

**结果（回合）**

- 20/20 回合完成、0 failures（每回合 `problems=none`）；
- 回合等待 18.7–43.4 s（首段可读 2.6–5.7 s 草稿；accepted 5.8–15.4 s）；
- 模型请求：仅 `qwen3-1.7b-narr-lora-Q4_K_M.gguf`；`Qwen3-0.6B` 请求 **0**；`__worldArm.semanticEngine=absent`；
- 语义调用：action/targets/results/updates/subtasks/continuation 全部 program/micro，**0 次语义模型**；narration 由 1.7B 生成。

**状态对照**

- 与二十输入混合臂 `09-turns20-pi.json` 的最终位置/任务集合比较见下（跑完后补）；
- 预期差异仍集中在严格任务标准（kit）与被程序略过的子任务/保守 no-change；需要逐项列出。

**Caveats**

- NPC 行动为模板闭集；targets 有弃权空目标；position/appearance/personality/sanity 保守无变化（本次未逐条读评合法变化）；
- 任务最终裁决仍是行为克隆模型（S01 control）；严格金标模型未训练；
- 叙事仍用 1.7B（S06 范围）。
