# 段落级参照示例（三题）

日期：2026-11-08。作者：执行方（**不是模型输出**，也未经产品负责人验收）。
用途：给“合格段落”立一个可对照的标尺；只依据该题已授权素材写作，不新增动作、不添道具、不补时长。

选题理由：

| 样本 | 覆盖的难点 |
|---|---|
| `ns-loc-appear-1` | 地点外貌变化；素材少，考察“不靠编造撑长度” |
| `ns-multi-1` | 移动 ＋ 物品外貌 ＋ 任务达成；三件事要连成一段 |
| `ns-pers-1` | 个性变化 ＋ 理智方向 ＋ 任务达成；避免写数值面板 |

## 1. `ns-loc-appear-1`

> 大约一分钟过去，走廊两侧的储物柜都关上了。学生A谨慎地站在一边，学生B仍靠着窗；那把黄铜钥匙还搁在走廊里。主角要取回柜子里的东西。

逐句来源：

| 分句 | 来源 | 说明 |
|---|---|---|
| 大约一分钟过去 | `timeAdvance.duration=1minute` | Δ 的时间推进 |
| 走廊 | `after.characters.person_c.position.containerId=corridor` | 视角人物所在地点 |
| 两侧的储物柜都关上了 | `delta.corridor.appearanceChanges[chg_corr_1].text` | 本点唯一变化，原文即“两侧的储物柜都被关上了” |
| 学生A谨慎地站在一边 | `initial.characters.person_a.initialPersonality=谨慎`；`after.characters.person_a.position.containerId=corridor` | 个性与在场位置 |
| 学生B仍靠着窗 | `initial.characters.person_b.initialAppearance=靠窗站着` | 初始外貌原文 |
| 那把黄铜钥匙还搁在走廊里 | `initial.items.item_key.initialAppearance=一把黄铜钥匙`；`after.items.item_key.position.containerId=corridor` | 物品外貌与位置；本点未移动 |
| 主角要取回柜子里的东西 | `after.characters.person_c.tasks.task_shelf.goal=取回柜子里的东西`，`status=pending` | 待办任务，不带完成含义 |

为什么不再写长：该点可用素材只有“时间 1 分钟、地点、两个人、一把钥匙、柜子关了、一个待办”。再写就是添道具、添天气、添动作。长度应该到这里为止。

## 2. `ns-multi-1`

> 两分钟过去。学生A从走廊去了大厅。走廊里那把黄铜钥匙没有动，表面却蒙上了一层灰尘。主角已经把柜子里的东西取回来了。

逐句来源：

| 分句 | 来源 | 说明 |
|---|---|---|
| 两分钟过去 | `timeAdvance.duration=2minute` | Δ |
| 学生A从走廊去了大厅 | `delta.person_a.positionSet`（before `corridor` → after `hall`） | 本点位置事实；起点、终点都写出来 |
| 走廊里那把黄铜钥匙没有动 | `after.items.item_key.position.containerId=corridor`（本点无位置变化）；`initial.items.item_key.initialAppearance` | “没有动”即位置未变，是可核对的 |
| 表面却蒙上了一层灰尘 | `delta.item_key.appearanceChanges[chg_key_1].text` | 外貌变化原文 |
| 主角已经把柜子里的东西取回来了 | `delta.person_c.tasksAchieved=[task_shelf]`；`before.characters.person_c.tasks.task_shelf.goal` | 任务达成；只写达成，不写怎么取、何时取 |

注意：段落没有写“钥匙被谁挪走”“学生A把钥匙带过去”。本点没有这些提交行动。

## 3. `ns-pers-1`

> 一分钟过去。学生B变得健谈起来，话一句接一句，人也松快了些。他帮主角熟悉校园这件事，到这儿算完成了。

逐句来源：

| 分句 | 来源 | 说明 |
|---|---|---|
| 一分钟过去 | `timeAdvance.duration=1minute` | Δ |
| 学生B变得健谈起来 | `delta.person_b.personalityChanges[chg_b_1].text=变得健谈` | 个性变化原文 |
| 话一句接一句 | — | **推断**：由“变得健谈”展开的行为描述，非新事件；若不允许推断，删掉此句不影响必述 |
| 人也松快了些 | `delta.person_b.sanitySet=12`（before 10） | 理智方向为上升；按既有 u240 判据，允许用身体状态表达方向 |
| 他帮主角熟悉校园这件事，到这儿算完成了 | `delta.person_b.tasksAchieved=[task_intro]`；`before.characters.person_b.tasks.task_intro.goal` | 任务达成，目标文本作标识 |

**面板与正文的冲突（本轮发现，需在方案里解决）**：该题必述事实含“理智值 12”，但把“12”写进故事段落会破坏文体。参照文本只写方向（松快），数值应留给状态面板。现行判分器要求句内出现“12”，与“段落可读”直接冲突；这条要作为生成路线的约束重写。

## 三条参照共同的验收特征

1. **主语明确**：每个分句都能指出“谁/什么”。没有“变化变得健谈”这种把字段名当主语的句子。
2. **一条分句一件事**：时间、移动、外貌、任务各自成句，再靠时间和地点衔接，不把两件事塞进一个分句，也不给一件事补没提交的宾语。
3. **只写已提交内容**：没有新动作、新道具、新目的地；不确定的地方不写。
4. **长度由素材决定**：`ns-loc-appear-1` 素材少就写得短；没有靠气氛描写或动作填充。
5. **面板与正文分开**：数值、任务状态这类机械信息不进故事句，或只以“完成/没完成”的自然说法出现。
