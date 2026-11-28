# E30 规划数据集 v0：事实从句的选择与顺序

**Question.** 把"选择哪些事实、按什么顺序写"变成可训练任务（goal 阶段三的
规划模型 0.1–5M 的任务定义）：给定一回合的事实从句，预测正文实际表达的子集
及其顺序。

**Setup.** 语料 `.local/narr-train/sft-v13.jsonl`（348 条人写目标正文）。
`build_planning_data.py`：按 `。；` 切分结算事实为从句；从句含任一 ≥2 字
内容词出现在正文即记"表达"；输出顺序取该从句首个命中词在正文中的位置。
产物 `planning-examples.jsonl`（每段：clauses + selected 顺序 +
selectionRate）与 `planning-summary.json`。

**Results.** 348 段、5,043 个事实从句、2,966 个被表达：
- 从句选择率的加权值 **58.8%**、段落均值 59.5%——叙事丢掉了约四成的事实
  从句，选择是真正的建模难点，与 E28 的遗漏率结论一致。
- 顺序信号清晰：玩家行动 → 移动/位置 → 同行 NPC 结果 → 环境外观，例如
  id 1 的顺序 `[0,2,4,5,1,6,...]`（玩家行 0/2 → 位置 4 → 场景 5 → NPC 1）。
- 时间从句（"时间到了15:21"）几乎从不进入正文——类型级的强先验。

**Caveats（v1 修正项）.**
- 结算事实里玩家行动被登记两次（请求行 + 结算回显），同词命中共计，选择率
  因此偏高；v2 需按内容去重并按类型标注（player_action / actor_result /
  time / location_state / appearance）。
- 表达判定用"任一内容词命中"，对改写的召回不足（改写词不命中）；v2 应结合
  E28 的词级对齐（改写词也计表达）。
- 同一事实集的多表达语料（alt-targets-all.jsonl）尚未纳入顺序多样性统计。

**Principle.** 规划任务在真实人写数据上可定义、可导出、有强类型先验；
选择（约四成事实被丢弃）与顺序是微型规划模型的核心学习目标。

**Artifacts.** `build_planning_data.py`、`planning-examples.jsonl`、
`planning-summary.json`。E30。
