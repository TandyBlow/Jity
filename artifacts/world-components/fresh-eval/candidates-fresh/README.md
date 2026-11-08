# 首批候选（6 条，待人工核验）

输入包版本 v3（2026-11-08 第二轮外部审查后修订，见 `report.md`）。
工作树 `d950018ffb4c`。来源是本次**新建**的评测专用注册夹具 `c8-eval-geothermal-v1`：作者 `Codex in this user-authorized C8 session`，创建时间 `2026-11-08T07:55:58.132062+00:00`，不是 R01 生成、不是历史玩家记录、没有改名复用旧世界。

六条全部通过 A 侧 Python 服务提交并读回（独立数据库 `fresh/source/authority.sqlite3`，读回校验 6/6）。**未冻结**，人工核验通过后才做一次性冻结。

## 场景一览

| 编号 | 场景 | 覆盖 | 视角 | 时长 | 必述/可提及/不进输入 | 页面路径 | 完整变化签名 |
|---|---|---|---|---|---|---|---|
| `c8e01` | 三项转运，各有起终点 | 多人物、多地点 | omniscient | 90s | 3/0/0 | 满足 | `moved*3\|3\|90s` |
| `c8e02` | 两栋建筑，视角只在校准间 | 多人物、多地点、可见性 | protagonist | 45s | 1/0/1 | 不满足 | `moved*2\|2\|45s` |
| `c8e03` | 父子任务同时校准，另有人完成转移 | 任务、多人物、多地点 | protagonist | 180s | 5/1/0 | 满足 | `moved*2+personality_changed*1+sanity_changed*1+task_achieved*2\|2\|180s` |
| `c8e04` | 持有人与参照物，明确空间关系 | 关系、多人物 | protagonist | 30s | 2/0/0 | 不满足 | `moved*1+moved_entity*1\|2\|30s` |
| `c8e05` | 封签的持有转移和外貌变化 | 关系、多人物、外貌 | protagonist | 60s | 3/0/0 | 不满足 | `appearance_changed*1+moved*1+moved_entity*1\|2\|60s` |
| `c8e06` | 关注指令与世界事实分开 | 玩家关注、任务、多人物 | omniscient | 120s | 2/0/1 | 不满足 | `moved*2+task_achieved*1\|2\|120s` |

## 模型看到什么、看不到什么

可见性不由本包自定，而是导入真实 N2 规则（`experiments/world-components/n2_perspective.py`，只读）逐条判定 must / may / invisible。
不可见的事实只写进 `answer.json`（核验答案），**不进 `input.json`**。唯一的非可见性排除是 `c8e06` 的玩家指令，单独标为 `player-instruction`。

## 能力不支持的部分（单列，不算模型失败）

- `c8e02`：P5-no-perspective-filter — 页面叙事路径不做视角过滤：N2 判为不可见或按指令推迟的事实仍会从世界状态被照写；本条只能由 N2 规则臂或人工判定（`committed-narration.ts:24-60`）
- `c8e04`：P1-item-or-location-delta — 物品/地点的位移与外貌变化都会被拒（world change 比较整块）（`committed-narration.ts:28`）
- `c8e05`：P1-item-or-location-delta — 物品/地点的位移与外貌变化都会被拒（world change 比较整块）（`committed-narration.ts:28`）
- `c8e06`：P3-incomplete-numeric-cause — 按人物逐一看：fe_shao 缺 personality_changed,sanity_changed，投影会拒绝（`committed-narration.ts:33-39`）
- `c8e06`：P5-no-perspective-filter — 页面叙事路径不做视角过滤：N2 判为不可见或按指令推迟的事实仍会从世界状态被照写；本条只能由 N2 规则臂或人工判定（`committed-narration.ts:24-60`）

## 文件

```
candidates-fresh/
├── candidates.json     汇总（提交证据、四段状态、筛选、修订记录）
├── report.md           逐条报告
├── review-table.md     人工核验表（待填）
└── <id>/
    ├── facts.json      原始 Δ / 变化事实 / 现状
    ├── answer.json     完整事实 + N2 逐条判定 + 被排除的事实
    ├── input.json      模型实际输入（含 withheld 计数，不含其内容）
    ├── screening.json  R1 v1/v2、R2、R3（完整变化集）
    └── checks.md       四段状态、排除事实、人工核验项
```

