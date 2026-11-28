# E55 任务达成数据与验证器基线（第一轮）

**Question.** 任务达成判断能否用真实回合数据训练/评测一个不依赖 0.6B 的裁决器？现有程序条件门、条件头、对验证器与 LLM 裁决器各差在哪？

**Method.** 从 `artifacts/goal/micro-workflow/evidence-*.json`（主工作树 253 个证据文件，含 env-1..11 / info-1..24 路由与单回合实验）导出任务阶段数据；冻结八场景与二十输入只作 `eval_frozen`，不进入训练或阈值调整。导出与复算脚本：

- `artifacts/goal/semantic-micro/export_calls.py`：把 `semanticPrompts` 按签名分类，与 `semanticCalls` 尝试行/结果行配对，输出 per-task JSONL；自检 `--selftest`。
- `build_task_pairs.py`：`(goal, fact)` 对；正例来自提交后 `achieved` 且答案/覆盖引用的事实；负例来自同回合 `待办` 且词面相关的事实；`完成`+高重叠但未达成记 `conflict_missed`（人工复核队列，不训）。
- `build_verifier_cases.py`：验证器 prompt 的 `(owner, task, goal, fact)` 与同点 `judgments` 按 key 集合配对；accepted support 取 `coverage.supports.basisText` 与条件列表。
- `build_task_dataset.py`：合并、去重、按证据文件分组切分（train/val/test），冻结数据单独 `eval_frozen`。
- `eval_task_baselines.py`、`eval_support_gate.py`：基线。

**结果（第一版数据）**

| 集合 | 行数 | yes | no | 组 |
|---|---|---|---|---|
| train | 177 | 37 | 140 | 45 |
| val | 47 | 20 | 27 | 9 |
| test | 79 | 20 | 59 | 8 |
| eval_frozen | 3 | 3 | 0 | — |
| review | 228 | — | — | 103 |

验证器案例（未去重）：319 行；`llm_verifier` yes 149、no 18；accepted_support yes 147；去除重复后 clean 303 行。`review` 中 40 条是「LLM 验判 yes 但任务未提交」，177 条是「完成事实 + 高重叠但任务仍待办」。

基线与程序门（val/test/eval_frozen）：

| 方案 | test acc | test yes P/R | 备注 |
|---|---|---|---|
| program 条件覆盖 + completed | 0.772 | 0.625 / 0.250 | 条件分解常漏项 |
| lexical 0.35 + completed | 0.747 | 0.500 / 0.100 | 只看词面 |
| condition head（task-condition-int8） | 0.456 | 0.171 / 0.300 | 输入是 goal 而非单条件，口径不对，仅参考 |
| pair verifier（task-match-int8） | 0.544 | 0.346 / 0.900 | 偏接受，precision 低 |
| logistic（char 2–3gram） | 0.899 | 0.929 / 0.650 | 训练集 177 行，易过拟合 |
| program gate（支持条件逐项） | — | 接受已提交支持 206/261（79%），拒绝未提交支持 27/40（67.5%） | 条件缺项/同义改写给 52 条假阴性 |

**Findings**

1. **根因是条件分解，不是裁决器本身。** accepted support 的条件列表经常只剩一项：`task_lu_kit` 只分解出 `action：进入`，走进任何房间即“达成”；`task_nono_squad` / `task_fingel_help` 只分解出 `target：路明非`，任何提到主角的事实都满足。0.6B 验证器对这 40 条也全判 yes（未提交），说明「让 LLM 再看一遍」不是修复路径。
2. **程序条件门有真实信号但召回不够**：79% 接受正确支持、67.5% 拒绝错误支持，52 条已提交支持因同义改写被拒。把字面包含换成短语相似度/条件级模型是下一步。
3. **现有条件头不能直接当 goal 级裁决器**：它在同条件内训练（`条件：item：护目镜`），本次用 goal 输入属于错口径；要比较必须在条件级数据上跑，或改训 goal 级。
4. **数据量仍是主要限制**：clean 303 行、37 个训练正例，不足以训练新网络；需要定向采集（设计任务达成的真实回合）或把 accepted support 的 `basisText` 作为正例扩到条件级。

**下一步**

1. 定向采集任务达成回合：每个任务设计「达成 / 部分 / 未达成 / 否定」四类事实，跑真实页面；冻结八场景与二十输入不进训练。
2. 条件级裁决器：先把 goal 分解成完整条件集（程序 + 小型抽取头），再按条件逐项判定；用 accepted/uncommitted support 作硬负例。
3. 在微模型之外保留程序门作为拒绝门：证据不足 → 不达成并记 `abstain_reason`；已提交支持被拒的 52 条进人工复核，区分同义改写与真错误。

**Caveats.** 数据来自 2026-11-24–27 多版提示的混合证据；负例是银标（待办 + 词面相关），不是人工逐条确认。冻结 eval 只有 3–10 条，不能单独支撑泛化结论。env/info 证据共 1.5 GB，留在主工作树，不提交仓库。

**Artifacts.** 本文件；脚本同上；数据 `experiments/semantic-micro/{task-pairs,verifier-cases}.jsonl`、`dataset/`（gitignored）。E55，对应 D-145 第 2/6 条。
