# 六条诊断的预期复核（自动生成，勿手改）

问题：预期里写的“必须／不得”，现有工具真的能判吗？下表按 `narration-alignment.ts`（sha256 309ca19f…）与 `n2_perspective.py` 的规则逐条核对。

| 项 | 预期 | 判定能力 | 依据 |
|---|---|---|---|
| `c8d01` | 移动方向（大堂→走廊），其余五人只写现状 | 可程序判定 | `narration-alignment.ts:364-369` 对 moved 做 direction_reversed；state_claim_without_fact 覆盖无事实的站位声明 |
| `c8d02` | 三条移动各自对应、不得互换 | 可程序判定 | direction_reversed + actor_swap（第 340-369 行）；换人物会被 actor_swap 拦下 |
| `c8d03` | N2 规则臂把视角外移动判为不可见 | 可程序判定（N2 侧） | 直接调用 `n2_perspective._visibility_ground({"kind":"moved","entityId":"person_a","at":"corridor"}, {person_c @ classroom1})` 实测返回 `(False, 'other-location')` |
| `c8d04` | 理智必须写成下降（30→26） | **不可程序判定** | `narration-alignment.ts:396-403` 的 wrong_number 只检查数字是否属于 {from,to}，“从26升到30”会通过；方向词没有检查。需人工核验或先扩展判定器 |
| `c8d05` | 必须写出时间流逝、不得编造变化 | 可程序判定 | `timeRequired` + `mentionsTime`（第 303、314、488 行）；无事实的主张走 state_claim_without_fact / added_event |
| `c8d06` | 只写父任务达成，不得表述为“全部任务完成” | **不可程序判定** | `narration-alignment.ts:439-444` 只要句子里绑上任意 task_achieved 事实就通过；不点人物的总结句被明确排除在范围外（第 433 行注释） |

## 结论

- 4 条预期可以被程序判定；`c8d04` 的“下降方向”和 `c8d06` 的“不得说全部完成”**目前只能人工核验**。
- 这不影响六条作为诊断材料的用途，但复核表里这两项的“通过”必须来自人，不能写成模型通过或判分器通过。
- 若要程序化，需先扩展判定器：理智方向词检查、任务树“全部完成”类总结句检查。扩展后必须重跑旧题基线，不能直接沿用现有结论。

## 边界

- 上表的“可程序判定”来自阅读 TS 规则并做过一次 N2 直接调用，未执行整条页面路径。
- 判定器是否在真实输出上误判，仍以实际运行为准；本批没有运行模型。
