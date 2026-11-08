# 首批候选（6 条，待人工核验）

工作树 `7706026bb144`。来源是本次**新建**的评测专用注册夹具 `c8-eval-geothermal-v1`：作者 `Codex in this user-authorized C8 session`，创建时间 `2026-11-08T07:55:58.132062+00:00`，不是 R01 生成、不是历史玩家记录、没有改名复用旧世界。

六条全部通过 A 侧 Python 服务提交并读回（独立数据库 `fresh/source/authority.sqlite3`，读回校验 6/6）。**未冻结**，人工核验通过后才做一次性冻结。

## 场景一览

| 编号 | 场景 | 覆盖 | 视角 | 时长 | 页面投影 | 变化签名 |
|---|---|---|---|---|---|---|
| `c8e01` | 三项转运，各有起终点 | 多人物、多地点 | omniscient | 90s | 支持 | `moved*3|3|90s` |
| `c8e02` | 两栋建筑，视角只在校准间 | 多人物、多地点、可见性 | protagonist | 45s | 支持 | `moved*2|2|45s` |
| `c8e03` | 父子任务同时校准，另有人完成转移 | 任务、多人物、多地点 | protagonist | 180s | 支持 | `moved*2+personality_changed*1+sanity_changed*1+task_achieved*2|2|180s` |
| `c8e04` | 持有人与参照物，明确空间关系 | 关系、多人物 | protagonist | 30s | 不支持 | `moved*1+moved_entity*1|2|30s` |
| `c8e05` | 封签的持有转移和外貌变化 | 关系、多人物、外貌 | protagonist | 60s | 不支持 | `appearance_changed*1+moved*1+moved_entity*1|2|60s` |
| `c8e06` | 关注指令与世界事实分开 | 玩家关注、任务、多人物 | omniscient | 120s | 不支持 | `moved*2+task_achieved*1|2|120s` |

## 每个候选给了模型什么

模型输入只有三样：事实（必须表达的），现状（可提及的），视角与时间。完整状态不作为输入；未提供的状态不要求模型说出，也不因省略扣分。逐条见 `candidates-fresh/<id>/input.json`。

## 能力不支持的部分（单列，不算模型失败）

- `c8e04`：P1-non-character-delta — 物品位移不在页面叙事投影的支持范围内（`committed-narration.ts:28`）
- `c8e04`：P4-position-slot-or-relative — relativeTo 会被投影拒绝（unsupported_narration_position）（`committed-narration.ts:49`）
- `c8e05`：P1-non-character-delta — 物品位移不在页面叙事投影的支持范围内（`committed-narration.ts:28`）
- `c8e05`：P2-appearance-change — 实体外貌变化不在支持范围内（`committed-narration.ts:51`）
- `c8e06`：P3-incomplete-numeric-cause — 任务/人格/理智未同时出现，投影会拒绝（`committed-narration.ts:38`）

## 文件

```
candidates-fresh/
├── candidates.json     汇总（含提交证据与筛选结果）
├── report.md           逐条报告
├── review-table.md     人工核验表（待填）
└── <id>/
    ├── facts.json      原始 Δ / 变化事实 / 现状引用
    ├── input.json      模型实际输入
    ├── screening.json  R1 v1/v2、R2、R3
    └── checks.md       人工核验项
```

