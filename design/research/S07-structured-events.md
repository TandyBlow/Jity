# S07 结构化事件兼容层（设计）

**Question.** 语义工作流能否直接输出一份结构化事件，让叙事与状态更新共享，而不重新理解自然语言事实串？如何在不改 `WorldState` schema 的前提下落地？

**现状**

- 结果事实已是半结构化文本：`（达到目的/只完成一部分/没有成功/被阻止/没有变化）`、`去向=entity:container[/slot]`、`环境=entity:状态`、`信息=entity:分句`、`涉及=id`。
- 事实记录本身带 `memberIds` 与 `actorId`（results lane），但叙事投影仍以文本为主；E51 的“事实缺主语”就是从这里来的。

**兼容层设计**

新增只读适配器 `local/structured-events.ts`：

```
输入：已提交的 results facts + S_{t-1} → S_t 状态差分 + 世界初态
输出：Event[]（不写回 WorldState）
Event = {
  id, actorId, targetIds[], action, objectIds[], result: completed|partial|failed|blocked|unaffected,
  degree?, cause?, location?, info?, envChanges?, relations[{kind, eventId}], source: {factId, turn, text},
  evidence: 'present'|'absent'|'insufficient'|'conflict'
}
```

- `action/object` 优先取结构化标记与登记实体 id；没有标记时保留原文片段，不臆造。
- `result` 取事实尾注；无尾注 → `insufficient`。
- `info` 取 `信息=` 标记；`envChanges` 取 `环境=`；`location` 取 `去向=`/位置差分。
- `evidence` 规则：有已提交事实且实体/动作可对齐 → present；明确否定/失败 → absent；只有动作未结算或未核验 → insufficient；与既有状态矛盾 → conflict。
- 四态不参与负例训练；insufficient/conflict 保留在事件流里供复核。

**用途**

1. 叙事侧按事件选择与排序，不再解析事实串；事件到正文仍需微叙事模型（另一 Agent）。
2. 任务台账可用事件条件对齐（S01/S06），减少重复理解。
3. 验收可逐事件核对状态差分与任务达成。

**不做**：不改 `WorldState`、不改 transport、不把事件提交为世界事实；事件是派生视图，可由事实与状态随时重建。

**验收**：真实回合事件重建与事实逐条对齐；同一事实集多次重建 digest 一致；叙事侧读取事件不改变正文边界（D-004）。S07。
