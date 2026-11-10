# C6 侧 N4.0 输入适配原型

状态：**原型 + 交接规格**。不是产品代码，不修改 `experiments/world-components/n4_input_renderer/`，也不改 `backend/app`。
用途：把画夹三点样例里模型真正需要、但 N4.0 当前没有的上下文，做成可运行、可测试的输入格式，交给 C（world-components）合并。

## 1. 为什么需要这层

N4.0 现在装的是：事实（moved/outcome/…）、场景、人物、视角、分组。它能回答“世界变了什么”，但回答不了：

- 玩家刚才说了/要求了什么（`world_advances.input_text` 曾为 NULL）；
- 上一段正文是什么（第二点起要承接）；
- 这一轮发生了哪些说话、受阻、交付（事实类型里没有 speech / attempt_failed / item_transfer）；
- 哪些事件在视角人物视野内；
- 任务为什么卡住（`Task.status` 只有 pending/achieved）。

这个原型把上述五项显式放进输入，并且**缺字段就报错**，不靠模型猜。

## 2. 文件

| 文件 | 作用 |
|---|---|
| `adapter.py` | 确定性渲染器：`build_point_input()` / `build_fixture()`；失败抛 `AdapterError(code)` |
| `fixtures/art-room-three-points.json` | 画夹三点样例的世界、玩家输入、上一段正文、事件、事实、任务 |
| `run_adapter.py` | 生成 `out/p1.txt`、`out/p2.txt`、`out/p3.txt`、`out/report.json`（含 SHA-256） |
| `test_adapter.py` | 13 条测试：渲染、承接、顺序、可见性、失败关闭、确定性 |
| `out/` | 已生成的输入与报告，可直接对照 |

运行：

```bash
python -X utf8 test_adapter.py
python -X utf8 run_adapter.py
```

## 3. 输入格式（C6 提议）

每个点一份：

```json
{
  "id": "p2",
  "location": "corridor3",
  "perspective": "person_c",
  "present": ["person_c", "person_e", "person_d"],
  "visibleItems": ["item_key_room", "item_form"],
  "playerInput": "我问杜衡，布展要到什么时候，画夹能不能先拿出来。",
  "previousNarration": "（点 1 正文）",
  "task": {"goal": "拿回画夹", "status": "pending", "blockedReason": "需登记；登记处 17:00 关门"},
  "events": [
    {"id": "e1", "kind": "speech", "actor": "person_d", "text": "清场到六点……", "visible": true},
    {"id": "e4", "kind": "move", "actor": "person_d", "from": "corridor3", "to": "stairwell", "visible": true, "visibility": "open-passage"},
    {"id": "e5", "kind": "action", "actor": "person_d", "text": "从墙上的登记表夹抽出一张空白登记表", "visible": true}
  ],
  "facts": [{"id": "f1", "kind": "moved", "entityId": "person_d", "from": "corridor3", "to": "stairwell"}]
}
```

事件类型：`speech`、`move`、`attempt_failed`、`item_transfer`、`action`、`observe`、`wait`。
`visible` 必填；`visible:false` 时如果有 `observable`，渲染成“观察”，否则丢弃并记诊断。

渲染出的模型输入（点 2 摘录，完整见 `out/p2.txt`）：

```text
叙事任务。
视角：林川｜第三人称限知
玩家输入：我问杜衡，布展要到什么时候，画夹能不能先拿出来。
上一段正文：旧教学楼三层的走廊只开了一半的灯……
场景：三层走廊
地点外貌：灯只开一半；靠墙立着几块展板；尽头是楼梯间，声控灯；墙上挂着登记表夹
在场：林川、江屿、杜衡
可见物品：活动室钥匙=黄铜，单把；空白登记表=一页表格
人物：
林川｜性格=新成员，只按玩家输入行动｜外貌=校服，背着空书包
……
事件：
e1｜说话｜杜衡｜清场到六点，室内物品要统一登记，不能提前拿。
e6｜物品交接｜杜衡｜空白登记表：楼梯间→杜衡
……
任务：拿回画夹｜进行中｜受阻原因：需登记；登记处 17:00 关门
要求：只写正文；不写面板、数值、字段名；不新增未列人物、物品、地点；
不替玩家增加动作或台词；承接上一段正文；只写视角人物能感知的内容；事件顺序不得改动。
正文：
```

## 4. 可见性怎么处理

原型要求每个事件显式写 `visible`。两种落法：

- 本轮样例：楼梯间登记为“开放通道”，`visibility: "open-passage"`，所以点 2 抽表动作视为林川可见；
- 若定为不可见：事件设 `visible:false`，并提供 `observable`（例如“杜衡回来时，臂弯里夹着一张空白登记表”），渲染器丢弃直接动作、只保留观察结果，并输出 `event-offscreen-observable` 诊断。

测试覆盖了这两种情况（`test_offscreen_with_observable`、`test_offscreen_without_observable_is_dropped`）。

## 5. 受阻原因

`task.blockedReason` 只在 `status=pending` 时允许；`achieved` 同时带原因会报 `achieved-task-with-blocked-reason`。
原型不决定它存在哪：这是 A 的契约问题，方案见 §7。

## 6. 失败关闭

| code | 条件 |
|---|---|
| `player-input-missing` | 没有玩家输入 |
| `previous-narration-missing` | 第二点起没有上一段正文 |
| `first-point-has-previous-narration` | 第一点却带了前文 |
| `unknown-entity` / `unknown-location` | 引用了不存在的实体/地点 |
| `event-visibility-missing` | 事件没写 `visible` |
| `unsupported-event-kind` | 未知事件类型 |
| `task-status-unsupported` | 任务状态不是 pending/achieved |
| `achieved-task-with-blocked-reason` | 已完成任务还带受阻原因 |

## 7. 交接：每项输入从哪里来

| 输入 | 现在能拿到吗 | 应由谁补 |
|---|---|---|
| `playerInput` | `world_advances.input_text` 存在但曾为 NULL | **A**：保证提交时写入、回放可取；B 负责传进来 |
| `previousNarration` | `world_narrations.text` 按上一 `point_id` 可取 | **A/B**：确认取上一代文本的稳定查询，不取占位“（结算叙事）” |
| `events`（说话/失败/交接） | 目前只有 Δ 和 `resultText`，没有事件日志 | **A**：提交时落事件记录，或明确从哪张表派生；**C**：定义事件类型与输入格式 |
| `visible` / `observable` | N4 只有地点链可见性，没有视线/子区域标记 | **C**：定规则（`visibleTo`/`offscreen`/开放通道）；**A**：提供地点层级 |
| `task.blockedReason` | `Task` 无字段，只有 pending/achieved | **A**：决定加 `statusReason` 还是从失败事件派生；**C**：定输入口径 |

共享代码（`n4_input_renderer`、`backend/app/schemas`）由 C / A 维护，本原型不改；合并时把 `adapter.py` 的校验与渲染逻辑并入 N4.0，保留现有 fail-closed 与字节稳定性测试。

## 8. 本轮边界

- 不训练、不调用模型、不扩语料。
- 不修改画夹样例正文。
- 不把原型输出当作“N4.0 已适配”的证据；它只证明“这五项能被显式装进输入，并且缺了会报错”。
- 正式接入前还需：事件记录落库、`input_text` 持久化、可见性规则、受阻原因来源。
