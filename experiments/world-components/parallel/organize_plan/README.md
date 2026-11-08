# c3 · N3 组织计划（离线合法性校验与下游输入）

日期：2026-11-08。分支 `exp/c-organize-plan`，工作树 `.local/parallel/c-organize-plan`。

- **对应原设计**：R11（叙事只写玩家可知道、且值得说的世界事实）里的“先组织、再成句”一环。
- **当前档位**：**方案＋有实验结果（离线校验；模型能力臂未执行）**。没有训练、没有申请 GPU、没有改服务、没有改正式页面、没有改 N2/N4 模型。
- **本轮只做一件事**：把“计划本身是否合法”和“下游是否按计划写”拆成两个可分别检查的问题，并把第一问跑完、第二问做成可复跑的工具与输入。

## 1. 一句话结论

在这 9 个可追到提交记录的来源、18 份计划上，**计划合法性 18/18 通过，20 个故意写坏的负例全部被对应错误码拦下**；同一批事实的两份计划在文本层可以互相区分（自检 18/18 通过，交叉检查 18/18 失败），四个“固定策略”在 9 个来源上没有一个能同时满足两份计划（成对成功 0）。旧失败里的“两份计划都合法但输出相同”因此**不能归因于计划写错**；但本轮没有可用的计划训练检查点，**模型到底能不能执行计划仍无法判断**。

## 2. 先核查旧失败：0/10 到底失败在哪

旧记录：`artifacts/world-components/organize-wording/controllability-report-v1.md`、`controllability-audit-v1.json`、`controllability-freeze-v1.json`。

| 数字 | 含义 |
| --- | --- |
| 36 源，20 train / 6 dev / 10 固定留出 | 材料规模 |
| 固定留出成对成功 **0/10** | 同一源的两份计划都“事实可辨认＋计划实现＋有预期差异”的数量 |
| A 计划实现 **1/10**，B 计划实现 **6/10** | 人工逐条复核 |
| A/B 输出逐字相同 **8/10** | 模型没有在两份计划之间切换 |
| 20 条输出全部 EOS，22–52 token | 不是截断造成的失败 |

旧材料的致命设计问题：**B 在全部 36 源上都是“每条事实一句”的同一形状**。一个固定的“全拆”策略不需要读计划就能通过 B；A 的失败才是关键，而 A 也只有一个形状（原分组）。所以旧实验测不出“模型读了计划”，只能测出“模型没有按 A 换形状”。

本轮针对这一点做了两处改动：

1. **标签与形状解耦**：同一族里，P1 有时是“合并”、有时是“全拆”，P2 相反。固定策略只能命中其中一份。
2. **加一组两个合并候选**：另一族的事实是 `[f0,f1,f3,f4]`，P1 合并左边、P2 合并右边；固定“全合并”或“全拆”都失败。

## 3. 谁给了谁什么

```
主工作区已登记/已提交夹具                          c3 冻结                          c3 程序
artifacts/world-provenance/pairs/                 freeze/sources.json    ──►   plan_contract.py
  <source>-authorized.json  ──►  选事实+证据号     freeze/plans-v1.jsonl        （合法性）
  fixture.db / train.db     ──►  核对 delta        freeze/negative-cases.json
  pair-worlds.json          ──►  点序/前驱                                 ──►   reference_compose.py
                                                                                 （确定性参考文本）
artifacts/.../controllability-v1.jsonl ──► 场景上下文（只做提示词抬头）       ──►   text_conformance.py
                                                                                 （文本层是否按计划）
                                                                           ──►   render_input.py
                                                                                 （N4 模拟输入）
```

- **事实不是手写的**：每条事实都从 `*-authorized.json` 的 `units` 取出，再回到 SQLite 的 `world_evidence` 和 `world_points.delta_json` 核对。
- **场景上下文只用于拼提示词抬头**（地点、可见物、场景、视角），不参与事实来源。
- **结果在哪**：`freeze/`（冻结输入）、`runs/r1/`（本轮全部原始输出与日志）。

### 3.1 一条事实的完整追溯例子

以 `fixture-r1` 的 `f0` 为例：

| 层 | 内容 |
| --- | --- |
| authorized 记录 | `factId=f0`、`entityId=person_a`、`name=林川`、`kind=appearance_changed`、`text=袖口沾了雨`、`pointId=fixture_r1_p1`、`evidenceId=fixture_r1_p1/person_a/appearance/fixture_r1_p1_1` |
| `world_evidence` 行 | `point_id=fixture_r1_p1`、`entity_id=person_a`、`kind=appearance`、`item_key=fixture_r1_p1_1`、`payload={"id":"fixture_r1_p1_1","text":"袖口沾了雨"}` |
| `world_points` 行 | `id=fixture_r1_p1`、`previous_point_id=root_3`、`time_json={"boundary":"elapsed","duration":{"amount":2,"unit":"second"}}`、`delta_json` 的 `person_a.appearanceChanges` 里有同 id、同 text 的条目 |
| `world_point_evidence` 行 | `sequence=1`、`previous_point_id=root_3`、`delta_status=recorded` |
| 授权关系 | `f2 before f3`，`verdict=pass`、`validatorVersion=world-relation-validator/1`、`elapsedSeconds=1`，证据号正好是 `f2`、`f3` 的 `evidenceId` |

`build_freeze.py` 对 9 个来源逐条做上述核对；**任何一条对不上就整体拒绝写出**。本轮 9/9 全部通过：每源 5 条事实、5 条证据、5 条 delta、5 条点链、1 条授权关系。

### 3.2 来源的“已登记”状态

- 事实与授权记录的**已提交副本**在 `exp/e-browser-regression` 工作树的 `artifacts/next-inputs/world-provenance/pairs/`，提交 `8afb540`。本轮逐文件比对 sha256，9 份被选中的 `*-authorized.json` 与 `pair-worlds.json` 都和主工作区一致（`train-r1` 没有上下文，未选）。
- **SQLite 数据库没有提交**，只在主工作区。本轮按哈希核对：`fixture.db` `c8fc383c…`、`train.db` `d09666d1…`；`pair-worlds.json` `533142df…`。
- 冻结时把选中的事实、点、授权关系整行复制进 `freeze/sources.json`，所以即使外部夹具不在，冻结件也能独立复跑校验。

## 4. 两份合法计划长什么样

计划只含事实编号，不含正文、动词、标点、连接词。形状固定为：

```json
{
  "groups": [
    {"facts": ["f0", "f1"], "links": ["continuation"]},
    {"facts": ["f2"], "links": []},
    {"facts": ["f3"], "links": []},
    {"facts": ["f4"], "links": []}
  ],
  "refs": {"f0": "name", "f1": "omit", "f2": "name", "f3": "name", "f4": "name"},
  "edges": [{"from": "f2", "to": "f3", "type": "before", "mode": "required"}]
}
```

- `groups`：按输入顺序切成连续的组，一组＝一次表达。
- `links`：组内相邻两条的关系。`continuation`＝同一个人合成一次表达；`parallel`＝不同人并列。**两者都不表示同时、先后或因果。**
- `refs`：每条事实怎么称呼。`name`＝写姓名；`omit`＝承前省略。省略只允许“同组前面已经用姓名介绍过、且最近一个姓名就是这个人”的情况。
- `edges`：只登记夹具已经授权过的 `before`。`mode=required` 表示成句时必须写出这个先后；`optional` 表示可以不写。**边本身不创造关系，只搬运授权记录。**

### 4.1 两个族

| 族 | 来源 | 用哪些事实 | 有无授权边 | P1 / P2 |
| --- | --- | --- | --- | --- |
| edge | `fixture-r1..r5` | 全部 5 条 | 有 `f2 before f3`（required） | 一份合并 `f0/f1`，一份全拆；哪个是 P1 按来源奇偶交换 |
| grouping | `train-r2..r5` | `f0,f1,f3,f4`（去掉 `f2`） | 无（`f2` 不在，授权边没有端点） | 一份合并左边 `f0/f1`，一份合并右边 `f3/f4`；哪个是 P1 按奇偶交换 |

标签分配：edge 族里 P1=“合并”的有 3/5 个来源、P1=“全拆”的有 2/5；grouping 族里 P1=“合并右”2/4、P1=“合并左”2/4。所以不能靠记住“P1 总是合并”或“P2 总是全拆”过关。

**为什么 grouping 要去掉 `f2`**：原授权是 `f2 before f3`，规则要求 `f3` 单独成句。如果保留 `f2`，`f3/f4` 就不能合并，只剩“合并 f0/f1”和“全拆”两种，又回到旧材料的单一形状。去掉 `f2` 后授权边不适用，`f3/f4` 合并才是合法的；代价是这一族没有边，报告里单列。

### 4.2 一个来源的两份计划

`fixture-r1`（edge 族）：

| | P1 `merge-left` | P2 `split-all` |
| --- | --- | --- |
| 分组 | `[f0,f1] [f2] [f3] [f4]` | `[f0] [f1] [f2] [f3] [f4]` |
| 称呼 | `f1=omit`，其余 `name` | 全部 `name` |
| 边 | `f2 before f3，required` | 同 |
| 参考正文 | 林川的袖口沾了雨，指节发白。周宁的斗篷下摆湿了一片。随后，陈默的鞋底沾了泥。陈默的袖口湿到肘部。 | 林川的袖口沾了雨。林川的指节发白。周宁的斗篷下摆湿了一片。随后，陈默的鞋底沾了泥。陈默的袖口湿到肘部。 |

`train-r2`（grouping 族）：

| | P1 `merge-right` | P2 `merge-left` |
| --- | --- | --- |
| 分组 | `[f0] [f1] [f3,f4]` | `[f0,f1] [f3] [f4]` |
| 称呼 | `f4=omit`，其余 `name` | `f1=omit`，其余 `name` |
| 边 | 无 | 无 |
| 参考正文 | 沈砚的灯罩蒙了灰。沈砚的掌心出汗。叶知微的衣角结了盐霜，鬓发被雾打湿。 | 沈砚的灯罩蒙了灰，掌心出汗。叶知微的衣角结了盐霜。叶知微的鬓发被雾打湿。 |

18 份计划的全文在 `freeze/plans-v1.jsonl`。

## 5. 校验器：它到底检查什么

`plan_contract.py` 的 `validate_plan(facts, authorized_edges, plan)` 返回 `{ok, errors, stats}`。按顺序查：

| 检查 | 规则 | 错误码（示例） |
| --- | --- | --- |
| 事实不丢 | 计划覆盖的 factId 必须等于选中事实，每条一次 | `fact-missing` |
| 事实不重 | 同一个 factId 不能出现在两个组 | `fact-duplicate` |
| 事实不假 | 不能出现选中集合之外的 factId | `fact-unknown` |
| 顺序不变 | 把组摊平必须正好是输入顺序；组是连续切块 | `order-changed` |
| 组内衔接 | 同实体只能 `continuation`，不同实体只能 `parallel` | `link-entity-mismatch` |
| 称呼不歧义 | 首次出现不能省略；省略必须同组、最近姓名是自己；全表重名直接拒绝 | `ref-first-mention-omit`、`ref-ambiguous-omit`、`ref-ambiguous-name` |
| 关系只搬运 | 边必须来自授权记录，方向不能反，不能重复，不能漏掉已授权边 | `edge-unauthorized`、`edge-order`、`edge-duplicate`、`edge-missing-authorized` |
| 关系边界 | 边的目标端必须单独成组（沿用旧合同“目标端点单独成句”） | `edge-target-not-isolated` |
| 不造时间/因果 | 计划只允许 `groups/refs/edges` 三个键；组只允许 `facts/links`；边只允许 `from/to/type/mode`；任何中文自由文本都拒绝；`type` 只能是 `before`；`mode` 只能是 `required/optional` | `unknown-field`、`plan-free-text`、`edge-type`、`edge-mode` |
| 本轮不支持的事实 | `time`、`no_change` 这类没有实体的事实直接拒绝，不硬塞进组 | `unsupported-fact-kind` |

**为什么这能挡住“新增时间/因果”**：计划里没有可以写“然后/因为”的字段；能表达顺序的只有 `edges`，而 `edges` 必须逐条对上授权记录，多一条、少一条、反一条都报错。`links` 只有两个值，且校验器要求它和实体关系严格一致，不能拿 `parallel` 冒充“同时”。

### 5.1 合法性与负例结果

- 18 份正式计划：**18/18 合法**，没有一条错误。
- 20 个负例：**20/20 命中预期错误码**。每个负例都是从合法计划改一处，或明确标注的合成事实集。

| 负例 | 改了什么 | 实际错误码 |
| --- | --- | --- |
| N01 | 删掉 `f4` 的组 | `fact-missing` |
| N02 | `f4` 出现在两个组 | `fact-duplicate`, `link-count` |
| N03 | 把 `f4` 换成 `f9` | `fact-unknown`, `fact-missing` |
| N04 | 交换 `f2`、`f3` 两组 | `order-changed` |
| N05 | 把 `f0`、`f2` 放一组 | `order-changed`, `link-entity-mismatch`, `ref-cross-group-omit` |
| N06 | `continuation` 连接周宁和陈默 | `link-entity-mismatch` 等 |
| N07 | `parallel` 连接两个林川事实 | `link-entity-mismatch` |
| N08 | 第一条林川事实就 `omit` | `ref-first-mention-omit`, `ref-omit-without-name` |
| N09 | 在后一组省略陈默 | `ref-cross-group-omit` |
| N10 | 删掉授权边 | `edge-missing-authorized` |
| N11 | 新增 `f0 before f1` | `edge-unauthorized`, `edge-missing-authorized` 等 |
| N12 | 把 `f2 before f3` 反过来 | `edge-order`, `edge-unauthorized`, `edge-missing-authorized` |
| N13 | 把目标端 `f3` 和 `f4` 合并 | `edge-target-not-isolated` |
| N14 | 加一个 `then` 字段 | `unknown-field`, `plan-free-text` |
| N15 | 把 `before` 改成 `cause` | `edge-type` |
| N16 | 在组里加 `time` 字段 | `unknown-field`, `plan-free-text` |
| N17 | 把 `mode` 改成 `then` | `edge-mode` |
| N18 | 两个实体都叫“张伟” | `ref-ambiguous-name` |
| N19 | 甲/乙/甲，最后一条省略 | `ref-ambiguous-omit` |
| N20 | 混入一条 `time` 事实 | `unsupported-fact-kind` |

完整错误详情在 `runs/r1/negatives.json`。

## 6. 下游模拟输入

`render_input.py` 按旧 controllability 的提示词格式生成 18 条 N4 输入，存在 `runs/r1/downstream-inputs.jsonl`。格式与旧实验逐行一致：同样的抬头、同样的事实行、同样的要求，只把事实和计划换成本轮的。

`fixture-r1 / P1` 的实际输入：

```
叙事任务。
地点=潮汐档案馆>长桌
地点可见=潮汐簿、铜灯、干纸、墨、天窗、长桌、门槛
场景=夜；浓雾
视角=第三人称
授权关系=f2 before f3（required）
事实（按顺序）：
f0｜外观｜林川｜袖口沾了雨
f1｜外观｜林川｜指节发白
f2｜外观｜周宁｜斗篷下摆湿了一片
f3｜外观｜陈默｜鞋底沾了泥
f4｜外观｜陈默｜袖口湿到肘部
表达计划：
{"groups":[{"facts":["f0","f1"],"links":["continuation"]},{"facts":["f2"],"links":[]},{"facts":["f3"],"links":[]},{"facts":["f4"],"links":[]}],"refs":{"f0":"name","f1":"omit","f2":"name","f3":"name","f4":"name"},"edges":[{"from":"f2","to":"f3","type":"before","mode":"required"}]}
要求：按计划的组和衔接写；……
正文：
```

这不是模型输出，只是“交给下一环的输入”已经冻结好。

## 7. 参考执行与文本层一致性

`reference_compose.py` 是一个**确定性参考执行器**，不是 N4 模型：它只按 `groups/refs/edges` 把事实拼成中文，用来回答两个问题：

1. 一份合法计划是不是足以确定一段文本？（是，18/18 都能生成。）
2. 两份计划在文本层能不能被区分？（能，见下。）

`text_conformance.py` 检查一段文本有没有按计划组织事实：

| 检查 | 做法 |
| --- | --- |
| 事实覆盖 | 每条事实文本在某个句子里 3-gram 召回 ≥ 0.5（沿用旧检查器的阈值，便于和旧数字比较） |
| 组内合并 | 同一组的事实必须落在同一句 |
| 组间分开 | 相邻两组交界的两条事实必须在不同句 |
| 句数 | 句数必须等于组数 |
| 称呼 | `name` 的句子必须出现姓名；`omit` 的句子不能把姓名紧贴在事实文本前；首次出现不能省 |
| 边 | 两端必须不同句；`required` 的目标句必须有“随后”；`optional` 的“随后”不能跑到别的句子 |
| 不造关系 | 出现“同时/与此同时”→ `invented-simultaneity`；没有授权边却出现“随后/然后/接着/之后/之前”→ `invented-sequence`；出现“因为/所以/因此/导致/于是”→ `invented-causality` |
| 不造指代 | 出现“他/她”→ `invented-pronoun` |

结果（`runs/r1/conformance.json`）：

| 检查 | 结果 |
| --- | --- |
| 自己对自己（18 条） | **18/18 通过** |
| 交叉：P1 文本拿 P2 计划检查，P2 文本拿 P1 计划检查（18 条） | **18/18 失败** |
| 负例：删掉 required 边的“随后，” | 被 `edge-wording-missing` 抓到 |

交叉失败的典型错误：

- edge 族：`groups-merged` 或 `group-split` ＋ `sentence-count-mismatch`；如果省略的位置不对，再加 `ref-not-omitted`。
- grouping 族：`group-split` ＋ `groups-merged` ＋ `ref-not-omitted`。

这说明两份计划不是“写法不同但文本一样”，而是**同一段文本不可能同时满足两份计划**。

## 8. 固定策略对照：旧漏洞有没有被堵上

`controls.json` 里定义了四个不看计划的固定策略，并对每个来源检查它是否同时等于 P1、P2：

| 策略 | 规则 |
| --- | --- |
| `split-all` | 每条事实一句，全部写姓名 |
| `merge-all-adjacent` | 相邻同实体全部合并（避开边的目标端） |
| `merge-first-pair` | 只合并第一个可合并的相邻同实体对 |
| `merge-last-pair` | 只合并最后一个可合并的相邻同实体对 |

结果：**36 行全部是合法计划，但没有一行同时等于 P1 和 P2；每个来源的成对成功都是 0。**

- edge 族 5 个来源：`split-all` 命中“全拆”那份，三个 merge 策略命中“合并”那份；每个策略都只命中一份。
- grouping 族 4 个来源：`merge-first-pair` 命中“合并左边”，`merge-last-pair` 命中“合并右边”，`merge-all-adjacent` 和 `split-all` 两份都不命中。

这正是旧材料缺的东西：旧 B 在所有源上都是同一个“全拆”，固定策略可以白拿；现在没有固定策略能同时通过两份计划。

## 9. 真实模型 smoke：只证明测量路径能跑

`model_smoke.py` 在 CPU 上加载**冻结基线** Randeng-T5-77M（`model.safetensors` sha256 `5cdc572109cf…`，与旧 controllability 的起点同一个哈希），跑 4 条提示（fixture-r1、fixture-r2 × 两份计划），greedy，`max_new_tokens=128`。

| 项 | 结果 |
| --- | --- |
| 调用 | 4 次，全部 EOS，63 new token |
| 单次耗时 | 6.7–11.7 s（CPU，只记录，不作为性能结论） |
| 文本一致性 | **0/4** |
| 输出 | 4 条都复读了提示词里的“要求：把全部事实写成一段连贯中文……”这一行，没有写事实 |

这**不是**缺失的能力臂：旧 controllability 的检查点没有保存到本地，本轮又不允许训练，所以“计划训练过的模型能不能执行”仍然无法判断。这个 smoke 只证明：输入能被真实模型读进去、输出能被检查器判为不合格，测量路径是通的。

## 10. 两个问题，分开回答

| 问题 | 本轮结论 | 证据 |
| --- | --- | --- |
| 两份计划是否合法？ | **是。** 18/18 合法；20 个负例全部被对应错误码拦下；事实不丢/不重、称呼无歧义、边的方向和数量都对得上授权记录 | `runs/r1/legality.json`、`runs/r1/negatives.json` |
| 下游是否执行计划？ | **确定性参考执行器：是。** 18/18 自检通过，18/18 交叉失败。**真实模型：无法判断。** 没有可用的计划训练检查点；4 条基线 smoke 0/4，但基线本来就没学过计划 | `runs/r1/conformance.json`、`runs/r1/model-smoke.json` |

对旧失败的直接结论：**旧失败不是“计划写错”造成的**。把旧材料里 A/B 两份计划原样拿进本轮校验器（只去掉边上的内联 `authorized: true`，授权改由夹具记录提供），9 个重叠来源 × 2 份 = **18/18 合法**；失败发生在下游没有按计划切换形状。旧实验本身还缺一个“固定策略”对照，本轮把它补上了。

## 11. 失败、限制与不确定

1. **旧 10 条固定留出没有全部复用。** 旧留出是 `v07/v18/t22/fixture-r5/t03/t08/t24/train-r4/v14/v20`；有完整 `authorized.json`＋DB 证据的只有 `fixture-r5` 和 `train-r4`。其余 8 条没有可追的点/证据记录，本轮不拿来冒充实测。本轮的 9 个来源来自 `fixture-r1..r5` 与 `train-r2..r5`，其中 `fixture-r5`、`train-r4` 与旧留出重叠。
2. **事实种类单一。** 9 个来源共 45 条事实，本轮选中 41 条（grouping 族各去掉 1 条 `f2`），全部是 `appearance_changed`。校验器支持其它有实体的事实类型，但本轮没有用它们跑；`time`、`no_change` 被显式拒绝，没有假装支持。
3. **省略规则偏保守。** 只允许同组承前省略；跨组省略一律拒绝。这样不会把“省略”误判成“指代明确”，但也漏掉了合法的跨句省略。
4. **参考正文不是质量结论。** `reference_compose.py` 是机械模板，`fixture-r3` 这种“被雨打湿半幅”的谓词片段只能拼成“林川被雨打湿半幅”，不保证自然。它只用来验证计划可执行、两份计划可区分。
5. **文本检查器是启发式。** 3-gram 召回 0.5 沿用旧检查器；只按 `。！？` 断句；不理解同义改写、倒装、长定语。它适合本轮的参考文本和下一轮的受控模型输出，不是通用 N5。
6. **基线 smoke 不是能力结论。** 77M 基线没有学过计划块，0/4 只能说明“不训练的模型不会读计划”，不能说明“计划接口无效”，也不能说明旧检查点会失败。
7. **外部夹具的提交位置。** 已提交副本在 `exp/e-browser-regression` 的 `8afb540`，不在本分支；SQLite DB 没有提交。本轮的冻结件已经把选中行复制进来，但“在别的机器上只靠 git 复跑”需要先拿到那份提交或 DB。
8. **没有浏览器、没有服务、没有页面。** 本轮全部离线；N4 的浏览器适配、真实页面接入、耗时预算都未测。

## 12. 下一轮预登记（模型能力臂）

要回答“计划训练过的模型能不能执行计划”，下一轮必须满足：

1. **检查点身份**：训练配方、基座哈希、选中 epoch、权重 sha256、解码参数全部记录；不能再用“同一个模型”这种说法。
2. **固定输入**：直接使用本轮的 `runs/r1/downstream-inputs.jsonl` 18 条，不重新生成、不改提示词。
3. **固定判据**：先用 `text_conformance.py` 的同一套检查；事实覆盖仍用 3-gram 0.5；成对成功的定义是“同一源两份计划都通过文本一致性”。
4. **固定对照**：必须同时报告 `split-all`、`merge-all-adjacent`、`merge-first-pair`、`merge-last-pair` 四个固定策略的成对结果（本轮均为 0），否则无法说明模型不是靠固定形状过关。
5. **停止条件**：如果模型成对成功不高于固定策略，先查“是否读了计划”（交换 P1/P2 标签后输出是否跟着变），再判断接口；不自动换基座、不追加训练步数。
6. **新留出**：本轮的 9 个来源只用于协议与工具验证；正式能力结论需要另建未参与过任何训练/选点的留出，且不能再用同一批 `fixture-*/train-*`。

## 13. 产物与复跑

| 文件 | 内容 | sha256 前缀 |
| --- | --- | --- |
| `freeze/sources.json` | 9 个来源的选中事实、点、授权关系、逐条核验记录 | `e1c58c2c…` |
| `freeze/plans-v1.jsonl` | 18 份计划（P1/P2、形状、事实集） | `2d0876d1…` |
| `freeze/negative-cases.json` | 20 个负例及预期错误码 | `da8d754b…` |
| `freeze/contexts.json` | 场景上下文（只用于提示词抬头） | `def4fe67…` |
| `freeze/source-hashes.json` | 输入/输出哈希、提交、Python 版本 | `d96abcd3…` |
| `runs/r1/legality.json` | 18 份计划的逐条校验结果 | — |
| `runs/r1/negatives.json` | 20 个负例的实际错误详情 | — |
| `runs/r1/legacy-plans.json` | 旧 A/B 计划用本轮校验器复检（18/18 合法） | — |
| `runs/r1/reference-output.jsonl` | 18 条确定性参考正文 | — |
| `runs/r1/conformance.json` | 自检/交叉/负例的文本检查 | — |
| `runs/r1/controls.json` | 4 个固定策略 × 9 个来源 | — |
| `runs/r1/downstream-inputs.jsonl` | 18 条 N4 模拟输入 | — |
| `runs/r1/model-smoke.json` | 4 条基线 smoke 原始输出与判据 | — |
| `runs/r1/model-smoke.jsonl` | 同上，逐行原始输出 | — |
| `runs/r1/summary.json` | 头部数字 | — |
| `runs/r1/input-hashes.json` | 代码/冻结/提交/环境的哈希 | — |
| `runs/r1/run.log` | 人读表格 | — |

复跑（在 `experiments/world-components/parallel/organize_plan/` 下）：

```bash
python -X utf8 build_freeze.py      # 重新核对夹具并重建 freeze/（会改时间戳与哈希）
python -X utf8 run_experiment.py    # 合法性 + 负例 + 参考正文 + 一致性 + 固定策略
python -X utf8 render_input.py --out runs/r1/downstream-inputs.jsonl
python -X utf8 model_smoke.py       # 可选：4 条基线 smoke（CPU，约 40 秒）
```

只跑校验器看单条计划：直接 `import plan_contract`，调用 `validate_plan(facts, authorized_edges, plan)`。

> 注意 1：仓库 `.gitignore` 忽略了整个 `experiments/`。本目录的文件需要 `git add -f` 才会进入提交；这不是文件丢失。
>
> 注意 2：`runs/r1/input-hashes.json` 里的 `runtimeHead`/`runtimeStatus` 是运行时的 HEAD 与工作区状态，复跑会变；代码与冻结输入的 sha256 不随复跑改变，交付提交见 `git log`。

## 14. 结论分类

- **已证明**：在这 9 个可追溯来源、18 份计划上，合法性校验 18/18 通过；旧材料 A/B 计划复检 18/18 合法；20 个负例全部按预期被拦下；确定性参考执行器 18/18 按计划生成，交叉检查 18/18 能区分两份计划；四个固定策略在 9 个来源上没有一对能同时通过两份计划。
- **已失败**：不训练的 77M 基线在 4 条 smoke 上 0/4 通过文本一致性（只说明基线不读计划，不是接口结论）。
- **无法判断**：计划训练过的模型（旧 controllability 检查点或新检查点）能否执行计划；真实浏览器端到端质量；更长计划、更多事实类型、跨组省略、真实玩家回合下的表现。
