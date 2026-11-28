# S05 行动与目标识别的 template-only 实验（设计）

**Question.** 行动族是语义 LLM 调用最多的一类（二十输入 136 次引擎调用、1,182 s）。如果完全禁止 action/targets 调 LLM，只用现有判定头、行为头与已校验模板，冻结八场景的状态、任务与 NPC 行动会差多少？

**现状（E54）**

- action：程序/判定头/行为头/模板之后仍会调 LLM；136 次尝试里只有 23 次产出模型结果，其余被拒或落模板/fallback。
- targets：规则在否定、缺席人名、代词歧义时弃权 → LLM；二十输入 32 次引擎调用。
- 现有模板候选集是闭集（`actions/candidates.ts`），每个候选都过 `checkActionText`；判定头给 task/personality/scene 三项分数。

**实验臂**

- `?action=template`：判定头/行为头失败后，取 `judgedFallback`（判定头排序后的首个合法模板）；没有合法模板则 `skip`，记 `action_abstained`。不调用 LLM。
- `?targets=rule`：规则点名命中时用规则结果；规则弃权（否定/代词/缺席）时返回空目标并记 `targets_abstained`；不调用 LLM。
- 两个臂都保留 `source` 与拒绝原因，回合证据可逐条审计。

**测量**

- 冻结八场景：状态断言、任务集合、每回合行动来源计数（program/micro/template/skip）、NPC 行动数、被跳过的合法行动；
- 与混合臂比较叙事正文中的行动一致性（只读检查，不改正文）；
- 延迟：action/targets 阶段耗时与回合等待；
- 明确报告“为消除 LLM 而减少 NPC 行动/拒绝玩家行动”的数量，不把 skip 当成功。

**风险**

- 模板闭集可能让 NPC 行为单调；必须先量化，再决定是否扩模板或用专用排序头。
- targets 空目标会减少被迫反应与共同结算；需要单独统计连锁影响。

**Artifacts.** 计划：`actions/index.ts` 的 template-only 分支、页面臂、冻结八场景证据。S05。
