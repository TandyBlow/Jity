# 参照段落 v2：正文＋面板（三题）

日期：2026-11-08。状态：**状态播报基线**——不是叙事标尺，也不再往叙事方向打磨。v1（`reference-paragraphs.md`）保留为历史草稿，不删。
本版只做两件事：删掉语义越界；把数值与任务状态移到面板，正文不再承载面板信息。

## 输出契约 v2（本轮新增，旧冻结不受影响）

- **正文**：只写已提交的叙事内容；不写数值、字段名、任务状态；不写推断出的行为或连续性判断。
- **面板**：机器可读的精确信息（时间、地点、在场、物品状态、个性、理智数值、任务状态）。面板是实际交付内容，不是说明文字。
- **完整性检查**：正文 ＋ 面板合起来覆盖全部必述事实。数值只出现在面板。

## 1. `ns-loc-appear-1`

### 正文

> 大约一分钟过去。走廊两侧的储物柜都关上了。学生A和学生B都在走廊里，学生B靠着窗；那把黄铜钥匙也在走廊里。

### 面板

```
时间  12:00:02（本点经过约 1 分钟）
地点  走廊
人物  学生A（谨慎）／学生B（外向，靠窗）／主角（好奇）
物品  钥匙（黄铜，位于走廊）
理智  学生A 10／学生B 10／主角 10
任务  学生B—帮主角熟悉校园：进行中
      主角—取回柜子里的东西：进行中
```

### 来源

| 内容 | 来源 |
|---|---|
| 大约一分钟过去 | `timeAdvance.duration=1minute` |
| 走廊两侧的储物柜都关上了 | `delta.corridor.appearanceChanges[chg_corr_1].text`（原文“两侧的储物柜都被关上了”） |
| 学生A和学生B都在走廊里 | `after.characters.person_a/person_b.position.containerId=corridor` |
| 学生B靠着窗 | `initial.characters.person_b.initialAppearance=靠窗站着` |
| 钥匙在走廊里 | `after.items.item_key.position.containerId=corridor`；`initial.items.item_key.initialAppearance=一把黄铜钥匙` |
| 面板：个性 | `initial.characters.*.initialPersonality` |
| 面板：理智 10 | `after.characters.*.sanity=10` |
| 面板：任务进行中 | `after.characters.person_b.tasks.task_intro.status=pending`；`person_c.tasks.task_shelf.status=pending` |
| 面板：时间 | `after.time.dateTime=2026-09-01T12:00:02` |

## 2. `ns-multi-1`

### 正文

> 两分钟过去。学生A从走廊去了大厅。走廊里那把黄铜钥匙的表面蒙上了一层灰尘。

### 面板

```
时间  12:01:02（本点经过约 2 分钟）
地点  走廊；学生A已到大厅
人物  学生A（谨慎，大厅）／学生B（外向，靠窗）／主角（好奇）
物品  钥匙（黄铜，表面蒙灰，位于走廊）
理智  学生A 10／学生B 10／主角 10
任务  主角—取回柜子里的东西：已完成
      学生B—帮主角熟悉校园：进行中
```

### 来源

| 内容 | 来源 |
|---|---|
| 两分钟过去 | `timeAdvance.duration=2minute` |
| 学生A从走廊去了大厅 | `before.characters.person_a.position.containerId=corridor`；`after…=hall`（本点 `positionSet`） |
| 钥匙在走廊、表面蒙灰 | `after.items.item_key.position.containerId=corridor`；`delta.item_key.appearanceChanges[chg_key_1].text` |
| 面板：任务已完成 | `delta.person_c.tasksAchieved=[task_shelf]`；目标文本取自 `before…tasks.task_shelf.goal` |

### 本版删掉了什么

- ~~“钥匙没有动”~~：只有前后位置相同，没有全过程证据，不能断言期间没被移动。
- ~~“主角已经把柜子里的东西取回来了”~~：任务完成记录只证明任务状态为已完成，不能展开成“东西已到手”这一结果描述；该信息留在面板的“已完成”里。

## 3. `ns-pers-1`

### 正文

> 一分钟过去。学生B变得健谈起来。

### 面板

```
时间  12:00:02（本点经过约 1 分钟）
地点  走廊
人物  学生A（谨慎）／学生B（外向→变得健谈）／主角（好奇）
理智  学生B 12（本点由 10 上升）／学生A 10／主角 10
任务  学生B—帮主角熟悉校园：已完成
      主角—取回柜子里的东西：进行中
```

### 来源

| 内容 | 来源 |
|---|---|
| 一分钟过去 | `timeAdvance.duration=1minute` |
| 学生B变得健谈起来 | `delta.person_b.personalityChanges[chg_b_1].text=变得健谈` |
| （已删）~~也松了口气~~ | 10→12 的方向不足以支持具体行为，按 2026-11-08 判定删除；方向由面板承载 |
| 面板：理智 12 | `after.characters.person_b.sanity=12`，before 为 10 |
| 面板：任务已完成 | `delta.person_b.tasksAchieved=[task_intro]` |

### 本版删掉了什么

- ~~“话一句接一句”~~：由“变得健谈”推断出的已发生行为，素材里没有该行为记录。
- ~~“人也松快了些”~~ → 曾改写为“松了口气”，**本版连同它一起删除**：数值方向不足以支持具体行为；如以后要把数值变化转成情绪或动作，需要单独定义表达权限。

## 仍未解决

1. 面板的呈现形式（一行文本、状态栏还是分块卡片）未定，这里只固定“有哪些字段、值取自哪里”。
2. 数值变化转情绪/动作是否允许：目前一律不允许；要开这个口子需另立表达权限规则。
3. 三题仍只是草稿；标尺是否成立待确认，Q1–Q7 未冻结。
