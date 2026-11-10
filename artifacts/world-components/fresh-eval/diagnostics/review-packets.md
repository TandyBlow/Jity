# 六条诊断的人工核验包（自动生成，勿手改）

每条给出：来源与参数、before／原始 Δ／after、变化事实与现状引用、允许与禁止的表述、程序检查结果。标注者、日期、结论留空，由人工填写。

`c8d06` 是三个点，按点分节。程序检查里的“投影支持”是按 `committed-narration.ts` 的规则表判定的（见 report.json 的 projectionRuleSource），不是执行 TS 的结果。

## `c8d01` 单人移动 + 其余五人现状陈述

- 模块：页面已提交叙事路径（committed-narration）
- 类型：覆盖诊断
- 来源：`design/world-protocol/v1/fixtures/school.initial-state.json`（sha256 `285468a395bde87e…`），before 为 `root_0`，摘要 `9301b7992248a972…`
- 提交状态：not-committed: hypothetical point, no round/group/settle/points record
- 独立性：undetermined: fixture vocabulary appears in corpora and archives; no evidence shows these points were excluded from training or tuning
- 人工指定参数：时长 3 分钟（本轮人工指定）；目的地 corridor（夹具既有地点）

**允许的表述**

- person_a 的移动方向必须是大堂→走廊
- 其余五人只写现状，不写他们移动

**禁止的表述**

- 学生以外的人物
- 任何任务达成
- 任何人格或理智变化

### `c8d01_p1`（三分钟）

**before**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | lobby | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**原始 Δ**

```json
{
 "person_a": {
  "entityId": "person_a",
  "positionSet": {
   "containerId": "corridor",
   "slotId": null,
   "relativeTo": null
  }
 }
}
```

**after**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | corridor | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**变化事实**（进签名）

| 种类 | 实体 | 字段 | 从 | 到 |
|---|---|---|---|---|
| moved | person_a | `characters.person_a.position.containerId` | lobby | corridor |

**现状引用**（不进签名）

| 种类 | 实体 | 字段 | 值 |
|---|---|---|---|
| sanity | person_a | `characters.person_a.sanity` | 10 |
| at | person_b | `characters.person_b.position.containerId` | lobby |
| sanity | person_b | `characters.person_b.sanity` | 20 |
| at | person_c | `characters.person_c.position.containerId` | classroom1 |
| sanity | person_c | `characters.person_c.sanity` | 30 |
| at | person_d | `characters.person_d.position.containerId` | classroom1 |
| sanity | person_d | `characters.person_d.sanity` | 40 |
| at | person_e | `characters.person_e.position.containerId` | classroom1 |
| sanity | person_e | `characters.person_e.sanity` | 50 |
| at | person_f | `characters.person_f.position.containerId` | classroom1 |
| sanity | person_f | `characters.person_f.sanity` | 60 |

**程序检查结果**

- 内核：ok；after 摘要 `286e112598cc96b6…`
- 投影支持：全部支持
- 变化签名：`moved*1|1|180s`；全包签名（参考）：`at*5+moved*1+sanity*6|6|180s`
- R1 v1：source-bound；R1 v2：source-bound；R2 已登记复用 0 组；
- R3：无命中

**人工核验记录（待填）**

| 标注者 | 日期 | 结论 | 依据 |
|---|---|---|---|
|  |  |  |  |

## `c8d02` 三人三地同时变化（含跨父地点）

- 模块：页面已提交叙事路径
- 类型：覆盖诊断
- 来源：`design/world-protocol/v1/fixtures/school.initial-state.json`（sha256 `285468a395bde87e…`），before 为 `root_0`，摘要 `9301b7992248a972…`
- 提交状态：not-committed: hypothetical point, no round/group/settle/points record
- 独立性：undetermined: fixture vocabulary appears in corpora and archives; no evidence shows these points were excluded from training or tuning
- 人工指定参数：时长 90 秒（本轮人工指定）；三条目的地均为夹具既有地点

**允许的表述**

- 三条移动的起点与终点必须各自对应，不得互换
- person_e 的终点是它的父地点二楼，不是同层教室

**禁止的表述**

- 第四条移动
- 把三人写成同一目的地

### `c8d02_p1`（90秒）

**before**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | lobby | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**原始 Δ**

```json
{
 "person_a": {
  "entityId": "person_a",
  "positionSet": {
   "containerId": "corridor",
   "slotId": null,
   "relativeTo": null
  }
 },
 "person_c": {
  "entityId": "person_c",
  "positionSet": {
   "containerId": "classroom2",
   "slotId": null,
   "relativeTo": null
  }
 },
 "person_e": {
  "entityId": "person_e",
  "positionSet": {
   "containerId": "floor2",
   "slotId": null,
   "relativeTo": null
  }
 }
}
```

**after**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | corridor | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom2 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | floor2 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**变化事实**（进签名）

| 种类 | 实体 | 字段 | 从 | 到 |
|---|---|---|---|---|
| moved | person_a | `characters.person_a.position.containerId` | lobby | corridor |
| moved | person_c | `characters.person_c.position.containerId` | classroom1 | classroom2 |
| moved | person_e | `characters.person_e.position.containerId` | classroom1 | floor2 |

**现状引用**（不进签名）

| 种类 | 实体 | 字段 | 值 |
|---|---|---|---|
| sanity | person_a | `characters.person_a.sanity` | 10 |
| at | person_b | `characters.person_b.position.containerId` | lobby |
| sanity | person_b | `characters.person_b.sanity` | 20 |
| sanity | person_c | `characters.person_c.sanity` | 30 |
| at | person_d | `characters.person_d.position.containerId` | classroom1 |
| sanity | person_d | `characters.person_d.sanity` | 40 |
| sanity | person_e | `characters.person_e.sanity` | 50 |
| at | person_f | `characters.person_f.position.containerId` | classroom1 |
| sanity | person_f | `characters.person_f.sanity` | 60 |

**程序检查结果**

- 内核：ok；after 摘要 `0cbac3e6ce6b0c37…`
- 投影支持：全部支持
- 变化签名：`moved*3|3|90s`；全包签名（参考）：`at*3+moved*3+sanity*6|6|90s`
- R1 v1：source-bound；R1 v2：source-bound；R2 已登记复用 0 组；
- R3：无命中

**人工核验记录（待填）**

| 标注者 | 日期 | 结论 | 依据 |
|---|---|---|---|
|  |  |  |  |

## `c8d03` 视角外的人移动（N2 视角诊断）

- 模块：C 侧 N2 视角规则臂（narration_pipeline.select_facts）
- 类型：视角诊断
- 来源：`design/world-protocol/v1/fixtures/school.initial-state.json`（sha256 `285468a395bde87e…`），before 为 `root_0`，摘要 `9301b7992248a972…`
- 提交状态：not-committed: hypothetical point, no round/group/settle/points record
- 独立性：undetermined: fixture vocabulary appears in corpora and archives; no evidence shows these points were excluded from training or tuning
- 人工指定参数：时长 50 秒（本轮人工指定）；视角取夹具主角 person_c
- 视角：`person_c` @ `classroom1`

**允许的表述**

- N2 规则臂把 person_a 的移动判为不可见（invisible），理由记录观察依据缺失
- person_c 自身的现状可以进 must

**禁止的表述**

- 页面叙事臂的输出被当作视角过滤结果
- 把本项计入端到端能力成绩

### `c8d03_p1`（50秒）

**before**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | lobby | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**原始 Δ**

```json
{
 "person_a": {
  "entityId": "person_a",
  "positionSet": {
   "containerId": "corridor",
   "slotId": null,
   "relativeTo": null
  }
 }
}
```

**after**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | corridor | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**变化事实**（进签名）

| 种类 | 实体 | 字段 | 从 | 到 |
|---|---|---|---|---|
| moved | person_a | `characters.person_a.position.containerId` | lobby | corridor |

**现状引用**（不进签名）

| 种类 | 实体 | 字段 | 值 |
|---|---|---|---|
| sanity | person_a | `characters.person_a.sanity` | 10 |
| at | person_b | `characters.person_b.position.containerId` | lobby |
| sanity | person_b | `characters.person_b.sanity` | 20 |
| at | person_c | `characters.person_c.position.containerId` | classroom1 |
| sanity | person_c | `characters.person_c.sanity` | 30 |
| at | person_d | `characters.person_d.position.containerId` | classroom1 |
| sanity | person_d | `characters.person_d.sanity` | 40 |
| at | person_e | `characters.person_e.position.containerId` | classroom1 |
| sanity | person_e | `characters.person_e.sanity` | 50 |
| at | person_f | `characters.person_f.position.containerId` | classroom1 |
| sanity | person_f | `characters.person_f.sanity` | 60 |

**程序检查结果**

- 内核：ok；after 摘要 `067f3dbf15a7d742…`
- 投影支持：全部支持
- 变化签名：`moved*1|1|50s`；全包签名（参考）：`at*5+moved*1+sanity*6|6|50s`
- R1 v1：source-bound；R1 v2：source-bound；R2 已登记复用 0 组；
- R3：无命中

**人工核验记录（待填）**

| 标注者 | 日期 | 结论 | 依据 |
|---|---|---|---|
|  |  |  |  |

## `c8d04` 任务达成 + 人格变化 + 理智下降（回归诊断）

- 模块：页面已提交叙事路径
- 类型：回归诊断（针对已确认的‘下降写成上升’错误）
- 来源：`design/world-protocol/v1/fixtures/school.initial-state.json`（sha256 `285468a395bde87e…`），before 为 `root_0`，摘要 `9301b7992248a972…`
- 提交状态：not-committed: hypothetical point, no round/group/settle/points record
- 独立性：undetermined: fixture vocabulary appears in corpora and archives; no evidence shows these points were excluded from training or tuning
- 人工指定参数：时长 2 分钟（本轮人工指定）；理智 30→26（本轮人工指定；夹具 time-only 用的是 35）；人格文本＝夹具原文

**允许的表述**

- 必须写成下降（30→26）
- 任务目标原文必须逐字出现
- 人格文本按夹具原文

**禁止的表述**

- 升到了 26
- 把任务说成未完成
- 把人格写成相反意思

### `c8d04_p1`（两分钟）

**before**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | lobby | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**原始 Δ**

```json
{
 "person_c": {
  "entityId": "person_c",
  "tasksAchieved": [
   "task_wait_noon"
  ],
  "personalityChanges": [
   {
    "id": "c8d04_relief",
    "text": "暂时放松了对周围的警戒。",
    "supersedes": []
   }
  ],
  "sanitySet": 26
 }
}
```

**after**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | lobby | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 26 | task_c_root=pending、task_wait_noon=achieved |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**变化事实**（进签名）

| 种类 | 实体 | 字段 | 从 | 到 |
|---|---|---|---|---|
| sanity_changed | person_c | `characters.person_c.sanity` | 30 | 26 |
| task_achieved | person_c | `characters.person_c.tasks.task_wait_noon.status` | pending | achieved |
| personality_changed | person_c | `characters.person_c.personalityChanges` | None | c8d04_relief |

**现状引用**（不进签名）

| 种类 | 实体 | 字段 | 值 |
|---|---|---|---|
| at | person_a | `characters.person_a.position.containerId` | lobby |
| sanity | person_a | `characters.person_a.sanity` | 10 |
| at | person_b | `characters.person_b.position.containerId` | lobby |
| sanity | person_b | `characters.person_b.sanity` | 20 |
| at | person_c | `characters.person_c.position.containerId` | classroom1 |
| at | person_d | `characters.person_d.position.containerId` | classroom1 |
| sanity | person_d | `characters.person_d.sanity` | 40 |
| at | person_e | `characters.person_e.position.containerId` | classroom1 |
| sanity | person_e | `characters.person_e.sanity` | 50 |
| at | person_f | `characters.person_f.position.containerId` | classroom1 |
| sanity | person_f | `characters.person_f.sanity` | 60 |

**程序检查结果**

- 内核：ok；after 摘要 `b2e9b24144f5ed7f…`
- 投影支持：全部支持
- 变化签名：`personality_changed*1+sanity_changed*1+task_achieved*1|1|120s`；全包签名（参考）：`at*6+personality_changed*1+sanity*5+sanity_changed*1+task_achieved*1|6|120s`
- R1 v1：rejected；R1 v2：source-bound；R2 已登记复用 0 组；
- R3：无命中

**人工核验记录（待填）**

| 标注者 | 日期 | 结论 | 依据 |
|---|---|---|---|
|  |  |  |  |

## `c8d05` 空增量点（只有时间流逝）

- 模块：页面已提交叙事路径
- 类型：覆盖诊断
- 来源：`design/world-protocol/v1/fixtures/school.initial-state.json`（sha256 `285468a395bde87e…`），before 为 `root_0`，摘要 `9301b7992248a972…`
- 提交状态：not-committed: hypothetical point, no round/group/settle/points record
- 独立性：undetermined: fixture vocabulary appears in corpora and archives; no evidence shows these points were excluded from training or tuning
- 人工指定参数：时长 40 秒（本轮人工指定）

**允许的表述**

- 必须写出时间流逝
- 不得编造任何变化

**禁止的表述**

- 任何移动、任务、人格、理智变化

### `c8d05_p1`（40秒）

**before**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | lobby | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**原始 Δ**

```json
{}
```

**after**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | lobby | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**变化事实**（进签名）

（本点没有变化事实）

**现状引用**（不进签名）

| 种类 | 实体 | 字段 | 值 |
|---|---|---|---|
| at | person_a | `characters.person_a.position.containerId` | lobby |
| sanity | person_a | `characters.person_a.sanity` | 10 |
| at | person_b | `characters.person_b.position.containerId` | lobby |
| sanity | person_b | `characters.person_b.sanity` | 20 |
| at | person_c | `characters.person_c.position.containerId` | classroom1 |
| sanity | person_c | `characters.person_c.sanity` | 30 |
| at | person_d | `characters.person_d.position.containerId` | classroom1 |
| sanity | person_d | `characters.person_d.sanity` | 40 |
| at | person_e | `characters.person_e.position.containerId` | classroom1 |
| sanity | person_e | `characters.person_e.sanity` | 50 |
| at | person_f | `characters.person_f.position.containerId` | classroom1 |
| sanity | person_f | `characters.person_f.sanity` | 60 |

**程序检查结果**

- 内核：ok；after 摘要 `29e512d6533a6550…`
- 投影支持：全部支持
- 变化签名：`none|0|40s`；全包签名（参考）：`at*6+sanity*6|6|40s`
- R1 v1：source-bound；R1 v2：source-bound；R2 已登记复用 0 组；
- R3：无命中

**人工核验记录（待填）**

| 标注者 | 日期 | 结论 | 依据 |
|---|---|---|---|
|  |  |  |  |

## `c8d06` 三点链：移动 → 空点 → 父任务达成＋人格＋理智

- 模块：页面已提交叙事路径
- 类型：覆盖诊断（含任务树边界）
- 来源：`design/world-protocol/v1/fixtures/school.initial-state.json`（sha256 `285468a395bde87e…`），before 为 `root_0`，摘要 `9301b7992248a972…`
- 提交状态：not-committed: hypothetical point, no round/group/settle/points record
- 独立性：undetermined: fixture vocabulary appears in corpora and archives; no evidence shows these points were excluded from training or tuning
- 人工指定参数：三段时长 4 秒 / 2 分钟 / 3 分钟（本轮人工指定）；理智 30→28（本轮人工指定）；人格文本＝夹具原文

**允许的表述**

- 第三点只写父任务 task_c_root（安全度过校园中的这段时间）达成
- 理智 30→28 为下降

**禁止的表述**

- 把 28 写成上升

**不要求模型写出（输入未提供，不得因省略扣分）**

- 子任务 task_wait_noon 的 pending 状态：本点事实包不提供，不得要求模型写出，也不得因省略扣分

**超出输入支持的断言**

- “全部任务完成”“两个任务都已完成”这类断言：输入只支持 task_c_root 达成，超出即没有输入支持，可作为人工判定项

**仅作人工依据**

- 若用完整状态核对：task_wait_noon=pending，与“全部完成”矛盾；该矛盾单列为人工核验依据，不由判定器判、也不算模型漏述

### `c8d06_p1`（四秒）

**before**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | lobby | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**原始 Δ**

```json
{
 "person_a": {
  "entityId": "person_a",
  "positionSet": {
   "containerId": "corridor",
   "slotId": null,
   "relativeTo": null
  }
 }
}
```

**after**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | corridor | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**变化事实**（进签名）

| 种类 | 实体 | 字段 | 从 | 到 |
|---|---|---|---|---|
| moved | person_a | `characters.person_a.position.containerId` | lobby | corridor |

**现状引用**（不进签名）

| 种类 | 实体 | 字段 | 值 |
|---|---|---|---|
| sanity | person_a | `characters.person_a.sanity` | 10 |
| at | person_b | `characters.person_b.position.containerId` | lobby |
| sanity | person_b | `characters.person_b.sanity` | 20 |
| at | person_c | `characters.person_c.position.containerId` | classroom1 |
| sanity | person_c | `characters.person_c.sanity` | 30 |
| at | person_d | `characters.person_d.position.containerId` | classroom1 |
| sanity | person_d | `characters.person_d.sanity` | 40 |
| at | person_e | `characters.person_e.position.containerId` | classroom1 |
| sanity | person_e | `characters.person_e.sanity` | 50 |
| at | person_f | `characters.person_f.position.containerId` | classroom1 |
| sanity | person_f | `characters.person_f.sanity` | 60 |

**程序检查结果**

- 内核：ok；after 摘要 `42e1bc7833716c8a…`
- 投影支持：全部支持
- 变化签名：`moved*1|1|4s`；全包签名（参考）：`at*5+moved*1+sanity*6|6|4s`
- R1 v1：source-bound；R1 v2：source-bound；R2 已登记复用 0 组；
- R3：无命中


### `c8d06_p2`（两分钟）

**before**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | corridor | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**原始 Δ**

```json
{}
```

**after**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | corridor | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**变化事实**（进签名）

（本点没有变化事实）

**现状引用**（不进签名）

| 种类 | 实体 | 字段 | 值 |
|---|---|---|---|
| at | person_a | `characters.person_a.position.containerId` | corridor |
| sanity | person_a | `characters.person_a.sanity` | 10 |
| at | person_b | `characters.person_b.position.containerId` | lobby |
| sanity | person_b | `characters.person_b.sanity` | 20 |
| at | person_c | `characters.person_c.position.containerId` | classroom1 |
| sanity | person_c | `characters.person_c.sanity` | 30 |
| at | person_d | `characters.person_d.position.containerId` | classroom1 |
| sanity | person_d | `characters.person_d.sanity` | 40 |
| at | person_e | `characters.person_e.position.containerId` | classroom1 |
| sanity | person_e | `characters.person_e.sanity` | 50 |
| at | person_f | `characters.person_f.position.containerId` | classroom1 |
| sanity | person_f | `characters.person_f.sanity` | 60 |

**程序检查结果**

- 内核：ok；after 摘要 `7139e6d7fc906b1e…`
- 投影支持：全部支持
- 变化签名：`none|0|120s`；全包签名（参考）：`at*6+sanity*6|6|120s`
- R1 v1：rejected；R1 v2：rejected；R2 已登记复用 0 组；
- R3：none|0|120s ← nv-cont-2


### `c8d06_p3`（三分钟）

**before**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | corridor | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 30 | task_c_root=pending、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**原始 Δ**

```json
{
 "person_c": {
  "entityId": "person_c",
  "tasksAchieved": [
   "task_c_root"
  ],
  "personalityChanges": [
   {
    "id": "c8d06_relief",
    "text": "暂时放松了对周围的警戒。",
    "supersedes": []
   }
  ],
  "sanitySet": 28
 }
}
```

**after**

| 实体 | 位置 | 理智 | 任务 |
|---|---|---|---|
| person_a | corridor | 10 | task_a_root=pending |
| person_b | lobby | 20 | task_b_root=pending |
| person_c | classroom1 | 28 | task_c_root=achieved、task_wait_noon=pending |
| person_d | classroom1 | 40 | task_d_root=pending |
| person_e | classroom1 | 50 | task_e_root=pending |
| person_f | classroom1 | 60 | task_f_root=pending |

**变化事实**（进签名）

| 种类 | 实体 | 字段 | 从 | 到 |
|---|---|---|---|---|
| sanity_changed | person_c | `characters.person_c.sanity` | 30 | 28 |
| task_achieved | person_c | `characters.person_c.tasks.task_c_root.status` | pending | achieved |
| personality_changed | person_c | `characters.person_c.personalityChanges` | None | c8d06_relief |

**现状引用**（不进签名）

| 种类 | 实体 | 字段 | 值 |
|---|---|---|---|
| at | person_a | `characters.person_a.position.containerId` | corridor |
| sanity | person_a | `characters.person_a.sanity` | 10 |
| at | person_b | `characters.person_b.position.containerId` | lobby |
| sanity | person_b | `characters.person_b.sanity` | 20 |
| at | person_c | `characters.person_c.position.containerId` | classroom1 |
| at | person_d | `characters.person_d.position.containerId` | classroom1 |
| sanity | person_d | `characters.person_d.sanity` | 40 |
| at | person_e | `characters.person_e.position.containerId` | classroom1 |
| sanity | person_e | `characters.person_e.sanity` | 50 |
| at | person_f | `characters.person_f.position.containerId` | classroom1 |
| sanity | person_f | `characters.person_f.sanity` | 60 |

**程序检查结果**

- 内核：ok；after 摘要 `be6c0fcc291b5b62…`
- 投影支持：全部支持
- 变化签名：`personality_changed*1+sanity_changed*1+task_achieved*1|1|180s`；全包签名（参考）：`at*6+personality_changed*1+sanity*5+sanity_changed*1+task_achieved*1|6|180s`
- R1 v1：source-bound；R1 v2：source-bound；R2 已登记复用 0 组；
- R3：无命中

**人工核验记录（待填）**

| 标注者 | 日期 | 结论 | 依据 |
|---|---|---|---|
|  |  |  |  |

