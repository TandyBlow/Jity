# 首批候选（6 条，待人工核验）

输入包版本 v2（2026-11-08 按外部审查修订，见 `report.md` 末尾“修订记录”）。
工作树 `498164828cf6`。来源是本次**新建**的评测专用注册夹具 `c8-eval-geothermal-v1`：作者 `Codex in this user-authorized C8 session`，创建时间 `2026-11-08T07:55:58.132062+00:00`，不是 R01 生成、不是历史玩家记录、没有改名复用旧世界。

六条全部通过 A 侧 Python 服务提交并读回（独立数据库 `fresh/source/authority.sqlite3`，读回校验 6/6）。**未冻结**，人工核验通过后才做一次性冻结。

## 场景一览

| 编号 | 场景 | 覆盖 | 视角 | 时长 | 必述/可不提 | 页面路径 | 变化签名 |
|---|---|---|---|---|---|---|---|
| `c8e01` | 三项转运，各有起终点 | 多人物、多地点 | omniscient | 90s | 3/0 | 满足 | `moved*3\|3\|90s` |
| `c8e02` | 两栋建筑，视角只在校准间 | 多人物、多地点、可见性 | protagonist | 45s | 1/1 | 不满足 | `moved*1\|1\|45s` |
| `c8e03` | 父子任务同时校准，另有人完成转移 | 任务、多人物、多地点 | protagonist | 180s | 6/0 | 满足 | `moved*2+personality_changed*1+sanity_changed*1+task_achieved*2\|2\|180s` |
| `c8e04` | 持有人与参照物，明确空间关系 | 关系、多人物 | protagonist | 30s | 2/0 | 不满足 | `moved*1+moved_entity*1\|2\|30s` |
| `c8e05` | 封签的持有转移和外貌变化 | 关系、多人物、外貌 | protagonist | 60s | 3/0 | 不满足 | `appearance_changed*1+moved*1+moved_entity*1\|2\|60s` |
| `c8e06` | 关注指令与世界事实分开 | 玩家关注、任务、多人物 | omniscient | 120s | 2/1 | 不满足 | `moved*1+task_achieved*1\|1\|120s` |

## 每个候选给了模型什么

模型输入四块：`mustExpress`（必须表达）、`mayMention`（可以不提，提则受限）、`currentState`（可提及的现状）、视角与时间。完整状态不作为输入；输入未提供的状态不要求模型说出，也不因省略扣分。逐条见 `candidates-fresh/<id>/input.json`。

## 能力不支持的部分（单列，不算模型失败）

- `c8e02`：P5-no-perspective-filter — 页面叙事路径不做视角过滤：世界为真的远处变化会被照写，本条的限知/推迟要求只能由 N2 规则臂或人工判定（`committed-narration.ts:24-60`）
- `c8e04`：P1-non-character-delta — 物品位移不在页面叙事投影的支持范围内（`committed-narration.ts:28`）
- `c8e04`：P4-position-slot-or-relative — relativeTo 会被投影拒绝（unsupported_narration_position）（`committed-narration.ts:49`）
- `c8e05`：P1-non-character-delta — 物品位移不在页面叙事投影的支持范围内（`committed-narration.ts:28`）
- `c8e05`：P2-appearance-change — 实体外貌变化不在支持范围内（`committed-narration.ts:51`）
- `c8e06`：P3-incomplete-numeric-cause — 任务/人格/理智未同时出现，投影会拒绝（`committed-narration.ts:38`）
- `c8e06`：P5-no-perspective-filter — 页面叙事路径不做视角过滤：世界为真的远处变化会被照写，本条的限知/推迟要求只能由 N2 规则臂或人工判定（`committed-narration.ts:24-60`）

## 文件

```
candidates-fresh/
├── candidates.json     汇总（提交证据、四段状态、筛选结果、修订记录）
├── report.md           逐条报告
├── review-table.md     人工核验表（待填）
└── <id>/
    ├── facts.json      原始 Δ / 变化事实 / 必述 / 可不提 / 现状
    ├── input.json      模型实际输入
    ├── screening.json  R1 v1/v2、R2、R3
    └── checks.md       四段状态、能力说明、人工核验项
```

