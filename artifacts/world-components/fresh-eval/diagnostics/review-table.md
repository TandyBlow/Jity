# 人工核验表（六条诊断，逐项，待核验）

**本轮没有模型输出**，所以只能核验“题目与预期是否成立”，不能填写模型表现。结论列只允许：`待核验`（默认）／`通过`／`不通过`／`无法判断`。`无法判断` 不算通过。

核验者不得是参与调参的人。依据一栏要写清引用了哪份材料（夹具路径、字段、行号）。

| 编号 | 项 | 类型 | 内容 | 依据（事实／字段） | 核验者 | 日期 | 结论 |
|---|---|---|---|---|---|---|---|
| `c8d01` | 1 | 必须成立 | person_a 的移动方向必须是大堂→走廊 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId` |  |  | 待核验 |
| `c8d01` | 2 | 必须成立 | 其余五人只写现状，不写他们移动 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId` |  |  | 待核验 |
| `c8d01` | 3 | 必须不出现 | 学生以外的人物 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId` |  |  | 待核验 |
| `c8d01` | 4 | 必须不出现 | 任何任务达成 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId` |  |  | 待核验 |
| `c8d01` | 5 | 必须不出现 | 任何人格或理智变化 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId` |  |  | 待核验 |
| `c8d02` | 1 | 必须成立 | 三条移动的起点与终点必须各自对应，不得互换 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId`、`characters.person_c.position.containerId`、`characters.person_e.position.containerId` |  |  | 待核验 |
| `c8d02` | 2 | 必须成立 | person_e 的终点是它的父地点二楼，不是同层教室 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId`、`characters.person_c.position.containerId`、`characters.person_e.position.containerId` |  |  | 待核验 |
| `c8d02` | 3 | 必须不出现 | 第四条移动 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId`、`characters.person_c.position.containerId`、`characters.person_e.position.containerId` |  |  | 待核验 |
| `c8d02` | 4 | 必须不出现 | 把三人写成同一目的地 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId`、`characters.person_c.position.containerId`、`characters.person_e.position.containerId` |  |  | 待核验 |
| `c8d03` | 1 | 必须成立 | N2 规则臂把 person_a 的移动判为不可见（invisible），理由记录观察依据缺失 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId` |  |  | 待核验 |
| `c8d03` | 2 | 必须成立 | person_c 自身的现状可以进 must | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId` |  |  | 待核验 |
| `c8d03` | 3 | 必须不出现 | 页面叙事臂的输出被当作视角过滤结果 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId` |  |  | 待核验 |
| `c8d03` | 4 | 必须不出现 | 把本项计入端到端能力成绩 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId` |  |  | 待核验 |
| `c8d04` | 1 | 必须成立 | 必须写成下降（30→26） | `school.initial-state.json` @ `root_0`；字段 `characters.person_c.tasks.task_wait_noon.status`、`characters.person_c.personalityChanges`、`characters.person_c.sanity` |  |  | 待核验 |
| `c8d04` | 2 | 必须成立 | 任务目标原文必须逐字出现 | `school.initial-state.json` @ `root_0`；字段 `characters.person_c.tasks.task_wait_noon.status`、`characters.person_c.personalityChanges`、`characters.person_c.sanity` |  |  | 待核验 |
| `c8d04` | 3 | 必须成立 | 人格文本按夹具原文 | `school.initial-state.json` @ `root_0`；字段 `characters.person_c.tasks.task_wait_noon.status`、`characters.person_c.personalityChanges`、`characters.person_c.sanity` |  |  | 待核验 |
| `c8d04` | 4 | 必须不出现 | 升到了 26 | `school.initial-state.json` @ `root_0`；字段 `characters.person_c.tasks.task_wait_noon.status`、`characters.person_c.personalityChanges`、`characters.person_c.sanity` |  |  | 待核验 |
| `c8d04` | 5 | 必须不出现 | 把任务说成未完成 | `school.initial-state.json` @ `root_0`；字段 `characters.person_c.tasks.task_wait_noon.status`、`characters.person_c.personalityChanges`、`characters.person_c.sanity` |  |  | 待核验 |
| `c8d04` | 6 | 必须不出现 | 把人格写成相反意思 | `school.initial-state.json` @ `root_0`；字段 `characters.person_c.tasks.task_wait_noon.status`、`characters.person_c.personalityChanges`、`characters.person_c.sanity` |  |  | 待核验 |
| `c8d05` | 1 | 必须成立 | 必须写出时间流逝 | `school.initial-state.json` @ `root_0`；字段 — |  |  | 待核验 |
| `c8d05` | 2 | 必须成立 | 不得编造任何变化 | `school.initial-state.json` @ `root_0`；字段 — |  |  | 待核验 |
| `c8d05` | 3 | 必须不出现 | 任何移动、任务、人格、理智变化 | `school.initial-state.json` @ `root_0`；字段 — |  |  | 待核验 |
| `c8d06` | 1 | 必须成立 | 第三点只写父任务 task_c_root（安全度过校园中的这段时间）达成 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId`、`characters.person_c.tasks.task_c_root.status`、`characters.person_c.sanity` |  |  | 待核验 |
| `c8d06` | 2 | 必须成立 | 必须保留子任务 task_wait_noon 仍为 pending 的事实：不得表述为‘全部任务完成’ | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId`、`characters.person_c.tasks.task_c_root.status`、`characters.person_c.sanity` |  |  | 待核验 |
| `c8d06` | 3 | 必须成立 | 理智 30→28 为下降 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId`、`characters.person_c.tasks.task_c_root.status`、`characters.person_c.sanity` |  |  | 待核验 |
| `c8d06` | 4 | 必须不出现 | 把两个任务都写成已完成 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId`、`characters.person_c.tasks.task_c_root.status`、`characters.person_c.sanity` |  |  | 待核验 |
| `c8d06` | 5 | 必须不出现 | 把 28 写成上升 | `school.initial-state.json` @ `root_0`；字段 `characters.person_a.position.containerId`、`characters.person_c.tasks.task_c_root.status`、`characters.person_c.sanity` |  |  | 待核验 |

## 逐条提示

- `c8d04`：明查**数值方向**（30→26 是下降，不是上升）。判定器目前不查方向词，所以这一项只能由人给结论。
- `c8d06`：明查**父任务达成与子任务 pending 是否同时保留**（`task_c_root=achieved` 且 `task_wait_noon=pending`），不得只写“完成任务”或“全部完成”。事实包只带父任务那条 `task_achieved`，子任务状态不在包里，所以这项也必须由人核。
- `c8d03`：只核 N2 规则臂的判定与理由，不核页面视角过滤，不计入端到端成绩。
- `c8d05`：时间必述可程序检查；“没有编造”只能部分检查（见 `expectation-review.md`）。

## 汇总（待人工填写）

| 编号 | 已核项 | 通过 | 不通过 | 无法判断 | 待核验 | 备注 |
|---|---|---|---|---|---|---|
| `c8d01` | 0/5 | 0 | 0 | 0 | 5 |  |
| `c8d02` | 0/4 | 0 | 0 | 0 | 4 |  |
| `c8d03` | 0/4 | 0 | 0 | 0 | 4 |  |
| `c8d04` | 0/6 | 0 | 0 | 0 | 6 |  |
| `c8d05` | 0/3 | 0 | 0 | 0 | 3 |  |
| `c8d06` | 0/5 | 0 | 0 | 0 | 5 |  |

## 结论口径

- 全部项目核完才可把该条从“待核验”移出；缺项按“待核验”记，不合并成“通过”。
- 核验通过不等于可以冻结：来源独立性仍是 `undetermined`。
- 本表不含模型输出；模型表现另开记录，且不得回填到本表。
