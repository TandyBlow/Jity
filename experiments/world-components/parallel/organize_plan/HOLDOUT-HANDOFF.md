# 新留出的交接契约（A → c3）

日期：2026-11-08。基线：`3431678`。
状态：**契约与接收工具已就绪；材料未到。** c3 只读接收，不在本分支生成世界回合。

## 1. 分工

| 谁 | 做什么 | 不做什么 |
| --- | --- | --- |
| A（Python 侧） | 生成 ≥10 个新世界回合；提交点、`delta_json`、`world_evidence` 行、`world_point_evidence` 前驱链；产出 `world-relation-validator/1` 的授权记录；打包交付 | 不决定双计划形状、不判定隔离、不冻结判据 |
| c3（本分支） | 只读校验（来源、链条、证据、授权、隔离）；构造每个来源两份合法计划；在模型推理**之前**冻结包与计划 | 不改世界记录、不修补差、不只改姓名/措辞充当新来源 |

隔离与冻结是两道闸：**没过隔离就不构造计划；没冻结就不许跑模型。**

## 2. 交付包结构

```
<packageDir>/
  manifest.json
  pairs/
    <sourceId>-authorized.json      # 与 artifacts/world-provenance/pairs 同形
  world.db                          # 或 manifest.databases 指向的若干库
```

`manifest.json`：

```json
{
  "packageId": "holdout-<日期>-v1",
  "producedBy": "<A 的实现者标识>",
  "createdAt": "2026-11-XX",
  "baseCommit": "<A 侧提交 SHA>",
  "sources": ["h01", "h02", "..."],
  "databases": {"h": "world.db"},
  "isolationStatement": "这些来源未出现在任何旧训练/选点/复核材料中",
  "note": "可选"
}
```

`databases` 用**来源 ID 前缀**映射到库文件（可绝对路径，可相对包目录）；最长前缀优先，未命中则用包内 `world.db`。这样一份包可以带多个库。

## 3. 每个来源的 `*-authorized.json`

与现有夹具同形，字段含义不变：

| 字段 | 要求 |
| --- | --- |
| `worldId` | 必填，同一包内可不同 |
| `units[]` | `factId` 必须是 `f0..fn` 连续；每条含 `entityId`、`name`、`kind`、`text`、`pointId`、`evidenceId`、`sequence` |
| `kind` | 必须是有实体的事实（`appearance_changed`、`outcome`、`moved`、`positioned_at`、`task_achieved`、`personality_changed`、`sanity_changed`、`position_relative`）。`time`、`no_change` 本轮不收 |
| `points[]` | 每条含 `id`、`sequence`（严格递增）、`previousPointId`（首点可为 null）、`time` |
| `requestedRelations` | 申请的关系，必须与授权结果一一对应 |
| `authorization` | `verdict=pass`、`validatorVersion=world-relation-validator/1`、`relations[]` 里每条含端点、`evidence` 两端证据号、`elapsedSeconds > 0`、内层 `verdict=pass` |

没有 DB 时，每条 unit 必须带 `inlineDelta: {"text": "..."}`，否则链条无法核对（错误码 `E-no-db-no-inline`）。

## 4. c3 会跑什么

```bash
python -X utf8 validate_holdout.py --package <packageDir>          # 只校验
python -X utf8 validate_holdout.py --package <packageDir> --freeze # 校验通过才冻结
```

校验分族，任一族的错误都会拒绝：

| 族 | 查什么 | 典型错误码 |
| --- | --- | --- |
| PKG | 包结构、manifest | `PKG-no-manifest`、`PKG-missing-source` |
| P | schema、`f0..fn`、字段齐全、kind 白名单 | `P-fact-ids`、`P-missing-field`、`P-unsupported-kind` |
| C | 前驱链、序号严格递增、unit 顺序随点序 | `C-chain`、`C-sequence`、`C-unit-order` |
| E | `world_evidence` 行与 unit 对齐；`world_points.delta_json` 含同一条条目 | `E-missing`、`E-text`、`E-delta` |
| A | 授权 verdict/validator 版本、端点、证据号、`elapsedSeconds`、申请与结果一致 | `A-verdict`、`A-evidence`、`A-request` |
| I | **隔离**：与全部旧材料的事实文本比对 | `I-exact-fact`、`I-near-duplicate-fact` |
| M | 能构造两份合法且不同的计划 | `M-no-merge-pair`、`M-illegal-plan`、`M-identical-plans` |
| N | 数量门槛 | `N-too-few-sources`、`N-too-few-multi-group`、`N-too-few-edges` |

### 4.1 隔离怎么判

旧材料指纹来自三处，合并去重后 45 条事实文本（`freeze/sources.json` 的 41 条 + 旧材料里其余的）：

1. `freeze/sources.json`（本轮 9 个来源的 41 条选中事实，含未选中的 `train-r1`）；
2. `artifacts/world-components/organize-wording/controllability-v1.jsonl`（36 源）；
3. `artifacts/world-components/organize-wording/pairs-v2.jsonl`（44 源）。

判据：

- 新来源某条事实文本**与旧文本完全相同** → `I-exact-fact`；
- 与任一旧文本的**bigram Jaccard ≥ 0.8** → `I-near-duplicate-fact`（这就是“只改一两个字”的拦截线）；
- 只比对事实文本，不比对姓名：换名字、换地点但事实描述不变，仍会被抓。

`--unit-test` 是这条规则的对照：一段全新事实通过；把“袖口沾了雨”改成“袖口沾了雨水”被判 `I-near-duplicate-fact`。

### 4.2 隔离**不检查**什么

- 不判断世界设定是否“新场景”。同一个世界观里出现新人物、新地点是允许的，只要事实文本没出现过。
- 不判断语义等价（“湿透了”与“湿了一片”不算重复，除非 bigram 相似度过线）。这条由人工在复核里补。

### 4.3 两份计划怎么构造

`validate_holdout.py` 的 `plans_for()` 对每个来源构造：

- **P1**：合并第一个可合并的相邻同实体对（避开授权边的目标端），其余各自成组；
- **P2**：每条事实单独成组。

两份都必须通过 `plan_contract.validate_plan`（事实不丢不重、顺序不变、衔接与实体一致、省略合法、边只搬运授权），且两份不能相同；否则该来源判 `M-*`。这一步就是为了避免旧材料“两份计划同一形状”的漏洞。

### 4.4 数量门槛

| 项 | 门槛 | 理由 |
| --- | --- | --- |
| 来源数 | ≥10 | 门线是 8/10，需要分母 |
| 含多事实组的来源 | ≥3 | 否则测不到分组 |
| 带授权边的来源 | ≥2 | 否则测不到关系词作用域 |

## 5. 冻结

只有 `status=admissible` 且带 `--freeze` 时才写 `freeze/holdout-v1-freeze.json`，内容包括：包内每个文件的哈希、manifest、隔离指纹哈希、逐源两个计划、事实、边、计数。冻结后**再改包或改计划**都必须重新冻结，否则模型结果不可归因。

## 6. 现在的状态

- `validate_holdout.py --self-test`：用现有 9 个来源搭一个包，schema/链/证据/授权/计划全过（0 错），隔离把 45 条事实全部判重、来源数 9 未达 10 —— 说明“现有材料不能当留出”这件事是**机器判出来的**，不是我口头说的。
- `validate_holdout.py --unit-test`：全新事实通过、改一字被判近似重复。
- 还没有真实的新包；本分支不会自己生成世界回合。

## 7. 到货后 c3 的固定动作

1. `--package` 跑一遍，把输出原样存档；有错就退回给 A，不自行修补。
2. 通过后 `--freeze`，记录冻结件哈希。
3. 用 `render_input.py` 生成下游输入（每条计划一条），再冻结一份。
4. 只有在检查点到位后，才允许跑模型；跑之前先确认 `freeze/criteria-v2.json` 与 `holdout-v1-freeze.json` 的哈希都还在记录里。
