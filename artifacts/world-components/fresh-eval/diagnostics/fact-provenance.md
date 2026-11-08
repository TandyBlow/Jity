# 事实来源对账表（自动生成，勿手改）

三列分开存：**原始 Δ**（设计者给的变化）、**变化事实**（Δ 产生的叙事事实）、**现状引用**（未变化实体的读数）。只有变化事实参与签名。

## `c8d01` 单人移动 + 其余五人现状陈述

### `c8d01_p1`（三分钟）

- 原始 Δ 键：person_a
- 变化事实 1 条：
    - `moved` person_a · `characters.person_a.position.containerId` · lobby → corridor
- 现状引用 11 条（不进签名）：
    - `sanity` person_a · `characters.person_a.sanity` = 10
    - `at` person_b · `characters.person_b.position.containerId` = lobby
    - `sanity` person_b · `characters.person_b.sanity` = 20
    - `at` person_c · `characters.person_c.position.containerId` = classroom1
    - `sanity` person_c · `characters.person_c.sanity` = 30
    - `at` person_d · `characters.person_d.position.containerId` = classroom1
    - `sanity` person_d · `characters.person_d.sanity` = 40
    - `at` person_e · `characters.person_e.position.containerId` = classroom1
    - `sanity` person_e · `characters.person_e.sanity` = 50
    - `at` person_f · `characters.person_f.position.containerId` = classroom1
    - `sanity` person_f · `characters.person_f.sanity` = 60
- 变化签名：`moved*1|1|180s`
- 全包签名（含现状，仅参考）：`at*5+moved*1+sanity*6|6|180s`

## `c8d02` 三人三地同时变化（含跨父地点）

### `c8d02_p1`（90秒）

- 原始 Δ 键：person_a, person_c, person_e
- 变化事实 3 条：
    - `moved` person_a · `characters.person_a.position.containerId` · lobby → corridor
    - `moved` person_c · `characters.person_c.position.containerId` · classroom1 → classroom2
    - `moved` person_e · `characters.person_e.position.containerId` · classroom1 → floor2
- 现状引用 9 条（不进签名）：
    - `sanity` person_a · `characters.person_a.sanity` = 10
    - `at` person_b · `characters.person_b.position.containerId` = lobby
    - `sanity` person_b · `characters.person_b.sanity` = 20
    - `sanity` person_c · `characters.person_c.sanity` = 30
    - `at` person_d · `characters.person_d.position.containerId` = classroom1
    - `sanity` person_d · `characters.person_d.sanity` = 40
    - `sanity` person_e · `characters.person_e.sanity` = 50
    - `at` person_f · `characters.person_f.position.containerId` = classroom1
    - `sanity` person_f · `characters.person_f.sanity` = 60
- 变化签名：`moved*3|3|90s`
- 全包签名（含现状，仅参考）：`at*3+moved*3+sanity*6|6|90s`

## `c8d03` 视角外的人移动（N2 视角诊断）

### `c8d03_p1`（50秒）

- 原始 Δ 键：person_a
- 变化事实 1 条：
    - `moved` person_a · `characters.person_a.position.containerId` · lobby → corridor
- 现状引用 11 条（不进签名）：
    - `sanity` person_a · `characters.person_a.sanity` = 10
    - `at` person_b · `characters.person_b.position.containerId` = lobby
    - `sanity` person_b · `characters.person_b.sanity` = 20
    - `at` person_c · `characters.person_c.position.containerId` = classroom1
    - `sanity` person_c · `characters.person_c.sanity` = 30
    - `at` person_d · `characters.person_d.position.containerId` = classroom1
    - `sanity` person_d · `characters.person_d.sanity` = 40
    - `at` person_e · `characters.person_e.position.containerId` = classroom1
    - `sanity` person_e · `characters.person_e.sanity` = 50
    - `at` person_f · `characters.person_f.position.containerId` = classroom1
    - `sanity` person_f · `characters.person_f.sanity` = 60
- 变化签名：`moved*1|1|50s`
- 全包签名（含现状，仅参考）：`at*5+moved*1+sanity*6|6|50s`

## `c8d04` 任务达成 + 人格变化 + 理智下降（回归诊断）

### `c8d04_p1`（两分钟）

- 原始 Δ 键：person_c
- 变化事实 3 条：
    - `sanity_changed` person_c · `characters.person_c.sanity` · 30 → 26
    - `task_achieved` person_c · `characters.person_c.tasks.task_wait_noon.status` · pending → achieved
    - `personality_changed` person_c · `characters.person_c.personalityChanges` · None → c8d04_relief
- 现状引用 11 条（不进签名）：
    - `at` person_a · `characters.person_a.position.containerId` = lobby
    - `sanity` person_a · `characters.person_a.sanity` = 10
    - `at` person_b · `characters.person_b.position.containerId` = lobby
    - `sanity` person_b · `characters.person_b.sanity` = 20
    - `at` person_c · `characters.person_c.position.containerId` = classroom1
    - `at` person_d · `characters.person_d.position.containerId` = classroom1
    - `sanity` person_d · `characters.person_d.sanity` = 40
    - `at` person_e · `characters.person_e.position.containerId` = classroom1
    - `sanity` person_e · `characters.person_e.sanity` = 50
    - `at` person_f · `characters.person_f.position.containerId` = classroom1
    - `sanity` person_f · `characters.person_f.sanity` = 60
- 变化签名：`personality_changed*1+sanity_changed*1+task_achieved*1|1|120s`
- 全包签名（含现状，仅参考）：`at*6+personality_changed*1+sanity*5+sanity_changed*1+task_achieved*1|6|120s`

## `c8d05` 空增量点（只有时间流逝）

### `c8d05_p1`（40秒）

- 原始 Δ 键：空
- 变化事实 0 条：
- 现状引用 12 条（不进签名）：
    - `at` person_a · `characters.person_a.position.containerId` = lobby
    - `sanity` person_a · `characters.person_a.sanity` = 10
    - `at` person_b · `characters.person_b.position.containerId` = lobby
    - `sanity` person_b · `characters.person_b.sanity` = 20
    - `at` person_c · `characters.person_c.position.containerId` = classroom1
    - `sanity` person_c · `characters.person_c.sanity` = 30
    - `at` person_d · `characters.person_d.position.containerId` = classroom1
    - `sanity` person_d · `characters.person_d.sanity` = 40
    - `at` person_e · `characters.person_e.position.containerId` = classroom1
    - `sanity` person_e · `characters.person_e.sanity` = 50
    - `at` person_f · `characters.person_f.position.containerId` = classroom1
    - `sanity` person_f · `characters.person_f.sanity` = 60
- 变化签名：`none|0|40s`
- 全包签名（含现状，仅参考）：`at*6+sanity*6|6|40s`

## `c8d06` 三点链：移动 → 空点 → 父任务达成＋人格＋理智

### `c8d06_p1`（四秒）

- 原始 Δ 键：person_a
- 变化事实 1 条：
    - `moved` person_a · `characters.person_a.position.containerId` · lobby → corridor
- 现状引用 11 条（不进签名）：
    - `sanity` person_a · `characters.person_a.sanity` = 10
    - `at` person_b · `characters.person_b.position.containerId` = lobby
    - `sanity` person_b · `characters.person_b.sanity` = 20
    - `at` person_c · `characters.person_c.position.containerId` = classroom1
    - `sanity` person_c · `characters.person_c.sanity` = 30
    - `at` person_d · `characters.person_d.position.containerId` = classroom1
    - `sanity` person_d · `characters.person_d.sanity` = 40
    - `at` person_e · `characters.person_e.position.containerId` = classroom1
    - `sanity` person_e · `characters.person_e.sanity` = 50
    - `at` person_f · `characters.person_f.position.containerId` = classroom1
    - `sanity` person_f · `characters.person_f.sanity` = 60
- 变化签名：`moved*1|1|4s`
- 全包签名（含现状，仅参考）：`at*5+moved*1+sanity*6|6|4s`

### `c8d06_p2`（两分钟）

- 原始 Δ 键：空
- 变化事实 0 条：
- 现状引用 12 条（不进签名）：
    - `at` person_a · `characters.person_a.position.containerId` = corridor
    - `sanity` person_a · `characters.person_a.sanity` = 10
    - `at` person_b · `characters.person_b.position.containerId` = lobby
    - `sanity` person_b · `characters.person_b.sanity` = 20
    - `at` person_c · `characters.person_c.position.containerId` = classroom1
    - `sanity` person_c · `characters.person_c.sanity` = 30
    - `at` person_d · `characters.person_d.position.containerId` = classroom1
    - `sanity` person_d · `characters.person_d.sanity` = 40
    - `at` person_e · `characters.person_e.position.containerId` = classroom1
    - `sanity` person_e · `characters.person_e.sanity` = 50
    - `at` person_f · `characters.person_f.position.containerId` = classroom1
    - `sanity` person_f · `characters.person_f.sanity` = 60
- 变化签名：`none|0|120s`
- 全包签名（含现状，仅参考）：`at*6+sanity*6|6|120s`

### `c8d06_p3`（三分钟）

- 原始 Δ 键：person_c
- 变化事实 3 条：
    - `sanity_changed` person_c · `characters.person_c.sanity` · 30 → 28
    - `task_achieved` person_c · `characters.person_c.tasks.task_c_root.status` · pending → achieved
    - `personality_changed` person_c · `characters.person_c.personalityChanges` · None → c8d06_relief
- 现状引用 11 条（不进签名）：
    - `at` person_a · `characters.person_a.position.containerId` = corridor
    - `sanity` person_a · `characters.person_a.sanity` = 10
    - `at` person_b · `characters.person_b.position.containerId` = lobby
    - `sanity` person_b · `characters.person_b.sanity` = 20
    - `at` person_c · `characters.person_c.position.containerId` = classroom1
    - `at` person_d · `characters.person_d.position.containerId` = classroom1
    - `sanity` person_d · `characters.person_d.sanity` = 40
    - `at` person_e · `characters.person_e.position.containerId` = classroom1
    - `sanity` person_e · `characters.person_e.sanity` = 50
    - `at` person_f · `characters.person_f.position.containerId` = classroom1
    - `sanity` person_f · `characters.person_f.sanity` = 60
- 变化签名：`personality_changed*1+sanity_changed*1+task_achieved*1|1|180s`
- 全包签名（含现状，仅参考）：`at*6+personality_changed*1+sanity*5+sanity_changed*1+task_achieved*1|6|180s`

