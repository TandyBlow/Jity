# c3 · N3 组织计划（离线合法性校验与下游输入）

日期：2026-11-08。分支 `exp/c-organize-plan`，工作树 `.local/parallel/c-organize-plan`。

- **对应原设计**：R11（叙事只写玩家可知道、且值得说的世界事实）里的“先组织、再成句”一环。
- **当前档位**：**方案＋有实验结果（离线校验；模型能力臂未执行）**。没有训练、没有申请 GPU、没有改服务、没有改正式页面、没有改 N2/N4 模型。
- **本轮只做一件事**：把“计划本身是否合法”和“下游是否按计划写”拆成两个可分别检查的问题，并把第一问跑完、第二问做成可复跑的工具与输入。
- **本轮追加（v2 检查器）**：第一版文本检查器被三个篡改探针打穿，已补顺序、关系词作用域、新增内容三类检查，判据冻结在 `freeze/criteria-v2.json`。v1 的 `runs/r1` 保留为历史记录，**以 `runs/r2` 为准**。
- **交接状态**：见 [HANDOVER.md](HANDOVER.md)。c3 已停止扩展工具与实验；三项状态（留出/签认/检查点）全部未就绪，模型能力实验 BLOCKED。

## 1. 一句话结论

在这 9 个可追到提交记录的来源、18 份计划上：**计划合法性 18/18 通过，20 个故意写坏的负例全部被对应错误码拦下**；同一批事实的两份计划在文本层可以互相区分（自检 18/18 通过，交叉检查 18/18 失败）；四个“固定策略”没有一个能同时满足两份计划（成对成功 0）。**这 9 个重叠来源上的旧 A/B 计划也 18/18 通过本校验器**——不能外推到旧固定留出的全部 10 个来源。

**第一版文本检查器已经被三个篡改探针打穿**：倒转句序、在未授权位置加“随后”、新增“并拿走了一把刀”，v1 全部判为通过。所以 v1 不能当模型能力的验收门。**v2 检查器**补了顺序、关系词作用域、新增内容三类检查，11 个探针全部按预期处置（9 个硬判失败、2 个转人工核验），判据冻结在 `freeze/criteria-v2.json`。

限定结论：**计划合法性与参考执行已验证；模型执行能力仍然无法判断**（没有可用的计划训练检查点，本轮不训练）。

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

## 8.5 文本检查器 v2：三个探针、三类新检查、两级判据

### 8.5.1 v1 为什么不能当验收门

v1 只检查四件事：事实能不能在某个句子里认出来、同组事实是不是同一句、相邻两组是不是不同句、句数对不对。它**不看位置顺序、不看关系词落在哪、也不看有没有多出内容**。三个只读探针（用户提出，本节已复现）全部被 v1 判为通过：

| 探针 | 做法（以 `fixture-r1 / P1` 的参考正文为底） | v1 判定 |
| --- | --- | --- |
| P1 句序倒转 | 四句整体反过来：`陈默的袖口…。随后，陈默的鞋底…。周宁的…。林川的…。` | 通过 |
| P2 未授权位置加“随后” | 在第二句（周宁，不是边目标）前面加“随后，” | 通过 |
| P3 新增“并拿走了一把刀” | 末句追加“，并拿走了一把刀” | 通过 |

复现方式（本轮已跑）：`runs/r1` 的参考正文 + `text_conformance.py` 的 v1 代码，三例 `ok=True`。

### 8.5.2 v2 补的三类检查

| 类 | 检查 | 错误码 | 能拦住哪个探针 |
| --- | --- | --- | --- |
| 顺序 | 各组的句子序号必须递增；组内事实的字符位置必须递增 | `group-out-of-order`、`within-group-order` | P1（倒转）、交换两组、组内换位 |
| 关系词作用域 | “随后”只能出现在 required 边的目标句；要在目标事实之前；出现次数不能多于 required 边数；没有边时出现即错 | `sequence-wording-outside-scope`、`sequence-wording-after-fact`、`sequence-wording-excess`、`invented-sequence` | P2（未授权位置） |
| 新增内容 | 去掉姓名、事实文本、连接词、标点和功能字后，剩余内容分两类：含世界词汇表之外的字，或只用到场景可见清单 | `added-content-outside-vocabulary`、`added-content-visible-only` | P3（刀） |

**“剩余内容”怎么算**（可以手工复算）：从正文里删掉——① 所有实体名；② 所有选中事实的 `text`；③ “随后/同时/与此同时/因为/所以/因此/导致/于是/然后/接着/之后/之前”；④ 标点；⑤ 一张固定的功能字表（的了着过把被在从到向与和及也又就都还只更再很并且而或如若则其之一个两三十将让使对为是有无未不没这那如此）。剩下的连续字块就是“计划没有明说的内容”。

`fixture-r1 / P1` 的原句复算：`林川的袖口沾了雨，指节发白。` 去掉“林川”“袖口沾了雨”“指节发白”“的”“，”“。”后为空；所以参考正文不会产生任何新增内容告警（18/18 实测确实为空）。

P3 的复算：末句多出 `并拿走了一把刀` → 去掉“并”（功能字）后剩 `拿走` 和 `刀`，两个都不在“事实文本 + 实体名 + 场景可见清单（潮汐簿、铜灯、干纸、墨、天窗、长桌、门槛）”里 → 命中。

### 8.5.3 两级判据：硬判 + 人工核验

顺序和关系词是**位置/结构**问题，程序可以确定，定为 `hard`：出现即判该条不合格，不允许人工改判。

新增内容是**语义**问题：模型可能只是换了个说法（“湿了一片”→“湿透”），也可能真的编了新事件。程序分不清，所以定为 `review`：**该条不算通过，必须有人工结论**。人工结论三选一：`paraphrase-ok`（合法改写，通过）、`new-content-fail`（确有新内容，不合格）、`unsure`（不算通过）。

所以一条文本要被接受，必须同时满足：**没有 hard 发现**，且**所有 review 发现都有人工结论为 `paraphrase-ok`**。这正是你要求的“无法自动判定的部分加入人工核验”。

### 8.5.4 探针结果：11/11 按预期

探针集冻结在 `freeze/tamper-probes.json`（每例记录底稿、改动说明、改后全文、全文哈希、预期处置）。

| 探针 | 改动 | 预期 | 实际 |
| --- | --- | --- | --- |
| T01 | 四句整体倒转 | 硬判 | `group-out-of-order` ×3 |
| T02 | 周宁句前加“随后，” | 硬判 | `sequence-wording-outside-scope`、`sequence-wording-excess` |
| T03 | 末句加“，并拿走了一把刀” | 人工 | review：`拿走`、`刀`（`added-content-outside-vocabulary`） |
| T04 | 交换第 1、2 句 | 硬判 | `group-out-of-order` |
| T05 | 组内两条事实换位 | 硬判 | `within-group-order`、`ref-not-omitted` |
| T06 | 末句再加“，随后，陈默退了出去” | 硬判 | `sequence-wording-outside-scope`、`sequence-wording-excess` |
| T07 | 中间插入“潮汐簿被合上了。” | 硬判 | `added-sentence`（另有 review：`合上`、`潮汐簿`） |
| T08 | 删掉 required 边的“随后，” | 硬判 | `sequence-wording-missing` |
| T09 | 末句加“，墨和干纸还在” | 人工 | review：`墨`、`干纸`（`added-content-visible-only`） |
| T10 | 把第一个“林川”换成“周宁” | 硬判 | `ref-name-missing`、`ref-missing-antecedent` |
| T11 | 在无授权边的 grouping 源加“随后，” | 硬判 | `invented-sequence`、`sequence-wording-excess` |

`runs/r2/tamper-probes.json` 是逐条原始结果；`run.log` 里有同一张表。

### 8.5.5 参考正文在 v2 下仍然 18/18 通过

v2 更严，但参考正文没有一条被误伤：18/18 `accepted`，0 条 hard、0 条 review。交叉检查仍然 18/18 失败。这说明新检查拦的是篡改，不是正常文本。

### 8.5.6 人工核验队列

`runs/r2/manual-review.json` 现在有 10 行（上限就是每批 10 行），每行带：队列号、来源、计划、错误码、剩余内容、原始正文、`verdict`（空）、`reviewerNote`（空）。

| 队列号 | 来源 | 错误码 | 剩余内容 | 需要回答的问题 |
| --- | --- | --- | --- | --- |
| T03…:拿走 | fixture-r1 P1 | added-content-outside-vocabulary | 拿走 | 这是改写还是新动作？ |
| T03…:刀 | fixture-r1 P1 | added-content-outside-vocabulary | 刀 | 世界里有没有刀？ |
| T06…:退 / :出去 | fixture-r1 P1 | added-content-outside-vocabulary | 退 / 出去 | 同上 |
| T07…:潮汐簿 / :合上 | fixture-r1 P1 | visible-only / outside | 潮汐簿 / 合上 | 描述现状还是新事件？ |
| T09…:墨 / :干纸 | fixture-r1 P1 | added-content-visible-only | 墨 / 干纸 | 只是提到道具还是发生了事？ |
| smoke:fixture-r1:P1/P2 | 基线 smoke | archived-output-hard-fail | — | 已硬判失败，仅登记 |

注意：这 10 行里有两行是**已经硬判失败**的归档输出，列进来只为留档；真正等人工结论的是前 8 行（见 §8.5.8，已填一轮 AI 复核）。

### 8.5.7 冻结的判据

`freeze/criteria-v2.json` 由 `build_criteria.py` 生成，记录了：检查器版本与代码哈希、探针文件与哈希、22 条 hard 规则、2 条 review 规则、接受定义、成对成功定义、门线、人工核验格式与取值、下一轮预登记。

生成方式避免手抄漂移：规则表从代码里的错误码逐条列出，哈希直接算当前文件。

**下一轮验收门的一句话定义**：新冻结留出上，**同一来源两份计划都“无 hard 且 review 全部人工判为合法改写”**，成对成功 ≥ 8/10，且严格高于四个固定策略的同批成绩。当前材料上固定策略成对成功都是 0，模型必须真的按计划切换才能过。

### 8.5.8 人工核验已收到一轮（AI 复核，待人工签认）

`runs/r2/manual-review.json` 的 10 行已填，文件顶部记录了复核者身份：

```json
"reviewer": {"identity": "Codex", "kind": "ai", "date": "2026-11-08",
             "reviewedCommit": "8a93f45", "humanSignoff": "pending",
             "scope": "AI逐条复核；不冒充人工签认，不改变冻结判据、程序硬判或模型能力结论。"}
```

逐行结论：

| 队列行 | 剩余内容 | 结论 | 理由（复核者原话摘要） |
| --- | --- | --- | --- |
| T03:拿走 | 拿走 | `new-content-fail` | 选中事实只有外观变化，没有拿物品的行动 |
| T03:刀 | 刀 | `new-content-fail` | 事实与可见清单都没授权“刀被拿走”；不外推为整个世界没有刀 |
| T06:退 | 退 | `new-content-fail` | 新增退场动作；原有的关系词硬判失败仍有效 |
| T06:出去 | 出去 | `new-content-fail` | 与“退”共同断言未经记录的移动/退场 |
| T07:潮汐簿 | 潮汐簿 | `new-content-fail` | 物件在可见清单里，但整个分句断言“被合上”；可见物存在不授权事件 |
| T07:合上 | 合上 | `new-content-fail` | 没有记录合上的动作；新增句的硬判失败仍有效 |
| T09:墨 | 墨 | `unsure` | 物件在可见清单，提到物品不等于编造事件；但“还在”的持续状态无法确认 |
| T09:干纸 | 干纸 | `unsure` | 同上，不因重复可见名词自动判错，但持续状态无法确认 |
| smoke:fixture-r1:P1 | — | `fail` | 归档输出本就硬判失败，列为留档 |
| smoke:fixture-r1:P2 | — | `fail` | 同上 |

**一处与冻结判据的偏差**：`freeze/criteria-v2.json` 只允许 `paraphrase-ok / new-content-fail / unsure` 三个取值，这里出现了第四个 `fail`，只落在两行**已经硬判失败**的归档输出上。

来源要写清：这两个值是**生成队列的脚本**写进去的（`run_experiment.py` 当时对 `archived-output-hard-fail` 行直接填了 `"fail"`），不是复核者新写的；复核者填其余 8 行时保留了这两个原值，当时也没有指出契约冲突。生成器现改为对这些行写 `verdict: null` 并加 `alreadyFailedHard: true`，重跑仍保留已填值。

处理办法不是改写冻结件，而是：

- `apply_review.py` 只在行的 `code == archived-output-hard-fail` 时接受 `fail`，把它当作 `new-content-fail`；
- 其它场合出现 `fail` 一律记为偏差并按“待定”处理；
- 偏差写进 `runs/r2/acceptance.json` 的 `deviations[]`，并另立 `freeze/criteria-v2-amendment-1.json` 说明来由，22 条 hard 规则、2 条 review 规则、接受定义、门线一个字没改。

### 8.5.9 复核后的验收结果

`apply_review.py` 把“程序的 hard 判定”和“人工结论”合成一个结论，写在 `runs/r2/acceptance.json`：

| 结论 | 数量 | 是哪几条 |
| --- | --- | --- |
| `rejected-hard`（程序硬判失败） | 9 | T01、T02、T04、T05、T06、T07、T08、T10、T11 |
| `rejected-review`（无 hard、转入 review，人工判新内容） | 1 | T03（`刀`、`拿走`） |
| `pending-review`（无 hard、转入 review，人工 `unsure`） | 1 | T09（`墨`、`干纸`） |
| `accepted` | 0 | — |

对照：**只看程序**的话，11 条里有 2 条没有 hard 发现（T03、T09），但这**不等于通过**——冻结的接受定义本来就要求 review 项有人工结论，未核验的 review 不算通过。加入人工结论后：1 条被判新内容（T03），1 条停在 `unsure`（T09），**没有任何一条被算作通过**。这正是“程序 + 人工”两级判据的作用：程序只负责把可以机械判定的部分判死，剩下的必须由人补。

**门状态**：`acceptance.json` 的 `gateStatus` 是 `PROVISIONAL_AI_REVIEW_ONLY`，不是 `OPEN`。含义写在文件里：结论来自 AI 复核、人工签认为 `pending`，所以这份结论**不能**直接当作下一轮模型验收门；它只说明“这套判据 + 核验流程是可用的”，并给出每一行的具体理由供人工核对。

`apply_review.py` 的判定顺序（写死在代码里，可复算）：有 hard 发现 → `rejected-hard`；否则有 `new-content-fail` → `rejected-review`；否则有 `unsure` 或未填 → `pending-review`；全部 `paraphrase-ok` → `accepted`。

`acceptance.json` 不写时间戳，`identitySha256` 由三个输入文件的哈希算出，所以同样的输入重跑得到逐字节相同的文件（实测两次 `ab1cbcfa…`），两个复核者可以直接 `diff`。

### 8.5.10 重跑不会冲掉已填的结论

这一点单独修了：`run_experiment.py` 原先直接覆盖 `manual-review.json`，重跑会把 10 行人工结论清空。现在 `write_manual_review()` 按 `queueId` 合并——保留每行的 `verdict`、`reviewerNote` 和顶部的 `reviewer` 块；新队列里消失的行放进 `orphanedRows` 而不是静默丢弃。

实测：先备份当前文件，重跑 `run_experiment.py`，10 条 `verdict` 全部保留、`reviewer` 块一致、`summary.json` 记录 `manualReviewPreservedVerdicts: 10`、`manualReviewOrphaned: 0`。


## 8.6 检查点取证（决定 1：走 A，已结束）

工具 `recover_checkpoint.py`，只读。结果 `freeze/checkpoint-forensics.json`。

**已提交脚本没有落盘逻辑**：`train_controllability.py` 在所有已提交版本里都没有 `save_pretrained` / `torch.save`。它把最好的一轮 `state_dict` 克隆到内存，评估前 `load_state_dict` 回去，然后结束——没有落盘这一步。

由此能说的只有：**这份已提交的脚本跑一遍不会产生权重文件**；本地扫描也没发现可归因的权重。不能外推成“任何地方都不存在过”——例如某次运行用了未提交的脚本变体、或有人手工导出过权重，本轮的证据都覆盖不到。

配套核对：

| 检查 | 结果 |
| --- | --- |
| 冻结记录里的 trained-checkpoint 字段 | 无；`base_hashes` 只钉基座 `5cdc5721…` |
| 运行记录里的哈希字段 | 只有 `material_sha256`、`freeze_sha256`；没有权重 |
| 运行目录内容 | 只有 `results.json`、`run.log` |
| 名字匹配的目录（`ckpt-group`/`controllab`/`n4group`） | 10 个，全是运行记录目录，0 个含权重 |
| 本地 30 个权重目录 | 29 个哈希；能对上记录只有基座；可归因于计划训练 **0** |

一处引用更正：`权重未提交` 出自 `design/world-engine-reports/components/README.md`，讲的是 **A/B_h 句组臂**，不是 controllability。此前 `NEXT-ROUND.md` 把它当成 controllability 的自述，已改。

**口径**：**已提交训练脚本没有检查点落盘逻辑，本地未发现可归因检查点**。这是取证结论，不是模型能力失败，也不构成“接口无效”；它的边界就是“这份脚本 + 本地范围”，不外推到“任何地方都不存在”。按决定到此停止，不自动转 B 重训，C 不复跑。

## 8.7 新留出交接（决定 2）

契约 `HOLDOUT-HANDOFF.md`，接收工具 `validate_holdout.py`（只读）。分族校验：包结构、schema、点链、证据/`delta_json`、授权、**隔离**、双计划、数量门槛。

两个自检都跑了：

| 自检 | 结果 |
| --- | --- |
| `--self-test` 把现有 9 个来源当包 | schema/链/证据/授权/计划 0 错；隔离 45 条全判重；来源 9 < 10 → `not-admissible` |
| `--unit-test` 两条合成事实 | 全新事实 0 错；`袖口沾了雨`→`袖口沾了雨水` 被判 `I-near-duplicate-fact` |

隔离线是 bigram Jaccard ≥ 0.8，只比事实文本、不比姓名：换个名字但事实描述照抄会被抓。

## 8.8 人工签认（决定 3）

`build_signoff_form.py` 生成 `runs/r2/signoff-form.json`：10 行，AI 结论放在 `aiVerdict`/`aiNote`（只读），留 `humanVerdict`/`humanNote` 给负责人；表头钉 4 个哈希 + `acceptance.json` 的 `identitySha256`。

`apply_signoff.py` 校验完备性并生成 `runs/r2/signoff.json`；缺字段或哈希漂移直接拒绝（`--show` 现在报 `incomplete`）。`apply_review.py` 读到签认记录后改用人工结论，签认后无偏差则 `gateStatus` 变 `OPEN`；`unsure` 行进 `openItems`，**不计通过**。

现在：`gateStatus = PROVISIONAL_AI_REVIEW_ONLY`，`openItems = ["T09-props-only-addition"]`。

## 8.9 三个独立状态（当前）

`check_round_ready.py` 把三件事分开判，任何一项没到就不许跑模型；三项都到才退出码 0。

| # | 状态 | 就绪 | 依据 |
| --- | --- | --- | --- |
| 1 | **留出待交付** | NO | `freeze/holdout-v1-freeze.json` 不存在：A 的包未到，或未过 `--package` |
| 2 | **人工签认待完成** | NO | 有签认记录，但 `signerKind='ai'`、`signoffClass='audit-only'`：只作审计材料（`pi（AI 编码代理）`，2026-11-08，审阅 `4dd9df4`） |
| 3 | **计划训练检查点缺失** | NO | `freeze/checkpoint-adoption.json` 不存在；取证结论 `not-found-locally` |

命令行输出：

```
模型能力实验：BLOCKED（未就绪：留出待交付、人工签认待完成、计划训练检查点缺失）
```

门状态：`PROVISIONAL_AI_REVIEW_ONLY`。`acceptance.json` 的 `gateReason` 写明原因：`signerKind='ai'` 的签认不能替代人工签认。

**门 OPEN 不等于可以跑模型。** 门只说明“判据与核验流程已封版”；能不能跑还取决于留出和检查点。三项都在 `check_round_ready.py` 里，缺一即 BLOCKED。

### 8.9.1 AI 签认只作审计材料，不能开门

`runs/r2/signoff.json` 保留为审计记录，字段写实：

```json
{"signer": "pi（AI 编码代理，本机 pi harness）", "signerRole": "delegated-signer",
 "signerKind": "ai", "date": "2026-11-08", "reviewedCommit": "4dd9df4",
 "signed": true, "signoffClass": "audit-only",
 "satisfiesHumanSignoff": false, "auditOnly": true}
```

`humanVerdict` 是逐条结论，`aiVerdict`/`aiNote` 原样保留、没有覆盖；T09 两行仍是 `unsure`，记在 `openItems`，**不计通过**。

**门规则**（`gate_rules.py`，纯函数，可单测）：

| 条件 | 门状态 |
| --- | --- |
| 没有签认记录，且复核者是 AI | `PROVISIONAL_AI_REVIEW_ONLY` |
| 有签认记录，但 `signerKind != "human"` | `PROVISIONAL_AI_REVIEW_ONLY`（只作审计） |
| 没有签认记录，复核者也不是 AI | `BLOCKED_PENDING_HUMAN_SIGNOFF` |
| 人类签认，但有阻断性偏差/未决行 | `BLOCKED_REVIEW_INCOMPLETE` |
| 人类签认，全部行已决 | `OPEN` |

回归检查 `python -X utf8 gate_rules.py`（7/7）：`signerKind=ai`、`unknown`、空值、`robot` 都不能开门；`human` 还必须同时满足身份非代理、日期与审阅版本齐全、`iReviewedEachRow: true`。

**只把 `signerKind` 改成 `human` 不构成人工签认。** 实测：只改这一个字段后 `apply_signoff.py` 退出码 1，`missing: ["iReviewedEachRow"]`；即使绕过它写入，`gate_rules.py` 也会因缺 `iReviewedEachRow` 判 `BLOCKED_REVIEW_INCOMPLETE`，或因签名串带代理标识（`AI`/`代理`/`Codex`/`Claude`/`GPT`/`harness`/`bot`）判 `PROVISIONAL_AI_REVIEW_ONLY`。

**`humanVerdict` 现在是 AI 草稿。** 那 10 条（8 × `new-content-fail`、2 × `unsure`）是 AI 写下的判断，实际签认人必须逐条确认或改写，并留下身份、日期、审阅版本。

**人工身份只是必要条件。** `T09` 保留 `unsure` 时按冻结判据不通过，会继续留在 `openItems`；门 `OPEN` 只表示复核流程封版，不表示所有条目通过，也不解锁模型实验。不能为了开门把 `unsure` 改判成 `paraphrase-ok`。

### 8.9.2 检查点采纳：哈希必须被记录“指向”，不能只是“出现过”

规则在 `check_adoption.py`，`--explain` 会打印完整字段表。一份可采纳的记录必须把同一个 `modelSha256` 同时挂到三处：

| 挂到哪 | 字段 | 判法 |
| --- | --- | --- |
| 训练输入与计划格式 | `trainingInputs.{materialFile, materialSha256, planFormat, planCount}` | 材料文件存在且哈希相符；`planFormat` 说明模型消费过哪些计划字段 |
| 训练运行 | `trainingRun.{record, recordSha256, recordField, recipe}` | 打开该记录，按 `recordField` 取到的**值必须等于 `modelSha256`** |
| 选点结果 | `selection.{record, recordSha256, recordField, epoch, updates, metric}` | 同样按字段取值等于一个指向同一权重的哈希；且 `recordSha256` 必须与 `trainingRun.recordSha256` 相同（同一次运行） |

两个否定条件：

- **`modelSha256 == baseModel.modelSha256` 直接拒绝**；等于已知 77M 基座哈希 `5cdc5721…` 也拒绝，理由写在输出里：「匹配基座权重不是归因」。
- **哈希只在文件里“原文出现”不算**：必须能解析到字段值。字段名里带点（`model.safetensors`）时用“最长字面键优先”的解析，或用 JSON Pointer `/model/files/model.safetensors`。

三个负对照实测（临时记录，跑完删除）：

| 记录 | 结果 |
| --- | --- |
| A：哈希只作为文字出现在记录里，没有对应字段 | 拒绝：`recordField ... does not exist` |
| B：`modelSha256` 填成基座哈希 | 拒绝：`equals baseModel.modelSha256` + `is the known 77M base hash` |
| C：记录里 `model.files.model.safetensors` 与 `selection.selectedSha256` 都等于该哈希 | `adopted` |

### 8.9.3 留出验收的两道闸

`validate_holdout.py` 现在除了 bigram 筛查（`I-exact-fact` / `I-near-duplicate-fact`），还要求：

- `manifest.generationProcess` 五个字段（`method`/`worldRounds`/`dedupeMethod`/`producedAt`/`producerCommit`）齐全，否则 `PKG-no-generation-process`；
- 包里带 `semantic-review.json`，逐源人工结论（`independent` / `semantic-duplicate` / `unsure`），`reviewer.kind` 必须是 `human`；
- 语义判重一律整包拒绝（`I-semantic-duplicate`、`I-semantic-unsure`）；
- `--freeze` 额外要求这份语义复核存在，并把它的哈希写进冻结件。

一句话：**bigram 低于 0.8 不是独立性证明**，只是没被筛掉；独立性由人工逐源判定，且 c3 不能自己签这一栏（标成 `ai` 会被 `PKG-semantic-review-not-human` 拒绝）。

## 8.10 2026-11-08 审阅后的修正

外部审阅指出五处，逐条修在代码里，并补了回归检查 `test_regressions.py`（9/9）。

### 8.10.1 留出语义复核不能靠改一个字段放行（严重）

**原来的漏洞**：`validate_holdout.py` 读 `semantic-review.json` 的 `reviewer.kind` 与逐源 `verdict`。A 侧草稿已预填 12 个 `independent` 且理由同模板，所以把 `kind` 从 `ai` 改成 `human` 就足以解阻。

**现在**：

- c3 **完全不读草稿的结论**，只读 `semantic-review-signoff.json`；
- 该文件必须带：`reviewer.identity`、`reviewer.date`、`reviewedCommit`、`iReviewedEachSource: true`，以及**绑定包摘要** `packageSha256`；
- `packageSha256` = manifest.json + 12 个 pair 文件的哈希集合再哈希；签认后再改任何一个 pair 文件 → `PKG-semantic-signoff-stale`；
- 每个来源必须有 `verdict` 与 `reason`，`reason` 不能为空、不能短于 8 字、**不能与草稿里那句模板相同**（`PKG-semantic-signoff-template-reason`）。

新增错误码：`PKG-no-semantic-signoff`、`PKG-semantic-signoff-not-human`、`PKG-semantic-signoff-incomplete`、`PKG-semantic-signoff-no-attestation`、`PKG-semantic-signoff-stale`、`PKG-semantic-signoff-template-reason`。

回归：T1（只改 kind 不放行）、T2（旧摘要=过期）、T3（照抄模板理由）、T4（缺 attestation / 缺身份）。

### 8.10.2 去重预检缺语料时不得“通过”（严重）

A 侧 `old_texts()` 原来遇到不存在的语料直接跳过。现在：三个语料缺任何一个、或任何一个抽出 0 条事实，**生成器直接拒绝运行**，不产出包。

`manifest.generationProcess` 新增 `dedupeCorpora`（每个文件的路径、sha256、事实条数）与 `dedupeFactTexts`（总数）。本次：120 + 137 + 45 = **302 条**。

### 8.10.3 检查器的事实类型要覆盖计划契约（较严重）

- `sanity_changed` 之前没有分支，会抛 `ValueError`；现在按冻结约定检查“症状词、无数字”，症状词表写在文件里。未知类型抛命名错误 `UnsupportedFactKind`。
- `moved` 之前把所有句子拼起来找 `from`/`to`，两句无关的句子也能凑成一次移动；现在要求**同一句内 from 在 to 之前**。

回归：T5 断言 `plan_contract.ENTITY_KINDS` 里每个类型都能被 `fact_span` 处理（防再漏），T6/T7 覆盖移动与理智。

检查器版本升为 `c3-text-conformance-v3`；判据另存 `freeze/criteria-v3.json`，`criteria-v2.json` 原样保留为 R2 记录。

### 8.10.4 冻结件要能发现材料变动（较严重）

`--freeze` 现在写入 `pairFiles`（manifest + 每个 pair 的哈希）、`packageDigest`、`semanticSignoff` 哈希。`check_round_ready.check_holdout()` 每次重算并比对：任一文件缺失或哈希不符 → `留出冻结件已过期`；签认文件哈希不符同样过期。

回归：T8（冻结后追加一个字节 → 不再就绪）。

### 8.10.5 12 源的门线在冻结时预登记

`--freeze` 写入：

```json
"gateRule": {"sources": 12, "minimumPairedSuccess": 10,
             "formula": "max(8, ceil(0.8 * N))", "mustUseAllSources": true,
             "noSubsetSelection": true, "preregisteredAtFreeze": true}
```

12 源对应 **10/12**，在冻结时登记，不允许看到结果后挑 10 个算。回归：T9。

### 8.10.6 A 侧生成日期

`createdAt` / `producedAt` 改为构建时的 UTC 时间（本次 `2026-11-08T07:51:38+00:00`）；游戏内时间单列 `worldInternalTime: 2027-01-16T05:00:00`。

### 8.10.7 适用范围（报告口径）

本轮实验只回答“**能否按计划组织事实并把它写成文字**”。12 个来源的事实类型全部是外观变化 + 一条时间先后关系，没有任务完成、位置移动、理智/个性变化、多线剧情。因此**不能**把结果外推为 Jity 的互动叙事能力；那需要在真实游戏回合里另做一轮（事实表达准确性 + 剧情连贯），与本轮是两个问题。

## 8.11 2026-11-08 第二次审阅后的修正

外部复审发现两处会阻断人工签认的缺陷、两处遗漏。逐条修，并新增 3 条回归检查（现共 12 条）。

### 8.11.1 包摘要的循环依赖（严重）

**原来**：A 侧先算 `package_digest()`（其中包含 `manifest.json` 的哈希），把结果写进 `manifest.packageSha256`，**然后才**写 manifest。c3 读的是写之后的 manifest，于是两边算的不是同一份内容。复算确认：模板预填 `7624273e…`，c3 重算 `72aea90a…`。

**现在**：

- `packageSha256` **不再写进 manifest**，只存在于 `semantic-review-signoff.template.json`；
- 摘要规则两侧同一套：`sha256` over `{相对路径: 文件哈希}`（manifest.json + `pairs/*.json`），JSON 按 key 排序；
- A 侧生成器在写完所有文件后**自己复算一遍**与模板比对，不一致就以退出码 1 失败（本次通过，摘要 `9dc96154…`）；
- `manifest.generationProcess.packageDigestRule` 写明规则。

回归 T10：读实际包，断言 manifest 里没有 `packageSha256`、模板值与 c3 重算值相等。本次 `digestMatch: true`，摘要 `9dc9615482fe…`。

### 8.11.2 R2 签认流程与 v3 检查器不兼容（阻塞）

**原来**：`build_signoff_form.py` 固定读 `criteria-v2.json`（钉 v2 检查器 `a4444195…`），而代码已是 v3（`714aeb46…`）。人工填完 R2 表单也会被判“文件已变”，`--force` 重生成仍然钉 v2。

**现在**：版本分开。

| 目录 | 检查器 | 状态 |
| --- | --- | --- |
| `runs/r1/` | v1 | 历史记录 |
| `runs/r2/` | v2 | 历史记录，判据 `criteria-v2.json`；它的 `signoff.json` 只作审计 |
| `runs/r4/` | v3 | **当前轮**，判据 `criteria-v3.json`，门与签认都在这里 |

- `run_experiment.py` 默认写 `runs/r4`；
- 四个脚本（`apply_review`/`apply_signoff`/`build_signoff_form`/`check_round_ready`）自动选取**版本号最高的** `criteria-v*.json`；
- `check_round_ready` 只认 `runs/r4/signoff.json`；`runs/r2/signoff.json` 在提示里注明“v2 历史审计记录，不用于当前门”。

`runs/r2` 的 `summary.json`/`input-hashes.json` 已恢复成 v2 运行时的内容，不再被 v3 覆盖。

### 8.11.3 冻结校验补上 world.db（遗漏）

`check_holdout()` 现在读 `manifest.files["world.db"]` 与 `manifest.databases`，比对数据库文件：缺失 → `world.db missing`，哈希不符 → `world.db changed`，都判“留出冻结件已过期”。

回归 T11：改一个字节 → 过期；删除 → 过期。

### 8.11.4 判据文件内容与生成器（遗漏）

- `criteria-v3.json` 的门线不再写死 8/10，改为“由冻结包写入的 `gateRule` 决定：`max(8, ceil(0.8N))`，必须用全部来源”；下一轮预登记改为引用 `runs/r4` 与 v3 检查器。
- `build_criteria.py` 不带 `--out` 时，输出名由检查器版本推导（现在是 `criteria-v3.json`），**不会覆盖 `criteria-v2.json`**。

回归 T12：断言默认输出名不是 `criteria-v2.json`。

### 8.11.5 门槛提醒

留出包仍未通过：`blockedBy = PKG-no-semantic-signoff, PKG-semantic-signoff-incomplete`。六族（结构/点链/证据/授权/隔离/双计划）仍是 0 错。在有人签 `semantic-review-signoff.json` 之前，不冻结、不跑模型。

## 8.12 2026-11-08 第三次审阅后的修正

外部复审发现 r4 签认表把「文件路径」写死成 v2/r2，而哈希取自 v3/r4；另有一条回归检查把跳过计成通过。

### 8.12.1 签认表里的路径、哈希必须是同一个文件（阻塞）

**原来**：`build_signoff_form.py` 里写的是

```json
"criteria":     {"file": "freeze/criteria-v2.json", "sha256": sha256(criteria-v3)}
"manualReview": {"file": "runs/r2/manual-review.json", "sha256": sha256(r4 的人工复核表)}
```

哈希对、路径错。`apply_signoff.py` 与 `check_round_ready.py` 也按 v2/r2 路径核验，人工填完必然哈希不匹配。你核对的三组差异（`c485bb45…` vs `762e6f66…`、`58a8ccf0…` vs `6dd99182…`、`bbcf35dc…` vs `2d7078af…`）都来自这一处。

**现在**：

- 新增 `pins.py`，规则只有一条：**核验时按记录里写的 `file` 去找文件，再比对 `sha256`**。路径写错就一定失败，不会“用对的哈希验了错的文件”。
- `build_signoff_form.py`、`apply_review.py` 写 pin 时由 `pins_mod.pin(path)` 生成，`file` 和 `sha256` 出自同一个 `Path`。
- 签认表里的三个 pin 与验收记录用**同一组文件**：`freeze/criteria-v3.json`、`runs/r4/tamper-probes.json`、`runs/r4/manual-review.json`。少一个或换一个，验收身份（`identitySha256`）就不同。
- `build_signoff_form.py` 生成前先复算验收身份，与 `acceptance.json` 不一致就**拒绝生成**（`status: refused`），避免发出过期表。
- `apply_signoff.py` 除了查 pin，还比对表里的 `acceptanceIdentity` 与当前 `acceptance.json`；对不上就报 `acceptance.json no longer matches the form's pinned inputs`。
- `check_round_ready.py` 的“签认已过期”判定改用同一函数，并新增一条：签认记录的 `acceptanceIdentity` 必须等于当前 `acceptance.json` 的身份。

实测（r4 重生成后）：

| 字段 | 值 |
| --- | --- |
| 判据 | `freeze/criteria-v3.json` `7cbda3b4…` |
| 探针结果 | `runs/r4/tamper-probes.json` `e0f353a5…` |
| 人工复核表 | `runs/r4/manual-review.json` `6dd99182…` |
| 验收身份 | `cb2cfa4e…`（与 `runs/r4/acceptance.json` 一致） |

端到端验证（临时目录，不动仓库）：填满一张人类签认表 → `apply_signoff.py` 退出 0、`signoffClass=human`；再把 `manual-review.json` 追加一个字节 → 退出 1，`drift` 明确写出 `runs/r4/manual-review.json changed since the record was written` 与 `acceptance.json no longer matches the form's pinned inputs`。

### 8.12.2 跳过不能算通过（回归检查可信度）

**原来**：`T10`（跨分支包摘要核对）找不到留出包时打印 skipped 并 `return`，统计仍是 `12/12 passed`。

**现在**：

- 引入 `SkipTest`，跳过单独计数与打印；
- 汇总行改成 `13 passed, 1 skipped, 0 failed (of 14 checks)`，并在下面列出跳过项及原因；
- `--strict-cross` 把跳过当失败（在有包的机器/CI 上用）。

实测：把测试包路径指向不存在的目录 → `13 passed, 1 skipped`，`--strict-cross` 退出 1；在有包的机器上 → `14 passed, 0 skipped`。

### 8.12.3 新增回归

| 编号 | 锁住什么 |
| --- | --- |
| T13 | r4 签认表的三个 pin 路径不含 `runs/r2`/`criteria-v2`、文件存在、哈希与 `acceptance.json` 一致、`pin_drift` 为空 |
| T14 | 哈希对但路径错（`b.json` 装 `a.json` 的哈希）必须被报出；pin 没有 `file` 字段也必须被报出 |

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
| 两份计划是否合法？ | **是。** 18/18 合法；20 个负例全部被对应错误码拦下；事实不丢/不重、称呼无歧义、边的方向和数量都对得上授权记录 | `runs/r2/legality.json`、`runs/r2/negatives.json` |
| 下游是否执行计划？ | **确定性参考执行器：是。** 18/18 自检通过，18/18 交叉失败（v2 复跑同结果）。**真实模型：无法判断。** 没有可用的计划训练检查点；4 条基线 smoke 0/4，但基线本来就没学过计划 | `runs/r2/conformance.json`、`runs/r1/model-smoke.json` |

对旧失败的直接结论，范围限定为：**在这 9 个有完整证据链的重叠来源上，旧 A/B 计划 18/18 通过本校验器**（只去掉边上的内联 `authorized: true`，授权改由夹具记录提供）。这只覆盖旧固定留出 10 个来源中的 `fixture-r5`、`train-r4` 两源；其余 8 源没有可追的点和证据记录，**不包含在“计划没写错”这个判断里**。能说的只有：这 2 个留出源加 7 个其它有证据来源的旧计划结构是合法的。旧实验本身还缺一个“固定策略”对照，本轮把它补上了。

## 11. 失败、限制与不确定

1. **旧 10 条固定留出没有全部复用。** 旧留出是 `v07/v18/t22/fixture-r5/t03/t08/t24/train-r4/v14/v20`；有完整 `authorized.json`＋DB 证据的只有 `fixture-r5` 和 `train-r4`。其余 8 条没有可追的点/证据记录，本轮不拿来冒充实测。本轮的 9 个来源来自 `fixture-r1..r5` 与 `train-r2..r5`，其中 `fixture-r5`、`train-r4` 与旧留出重叠。
2. **事实种类单一。** 9 个来源共 45 条事实，本轮选中 41 条（grouping 族各去掉 1 条 `f2`），全部是 `appearance_changed`。校验器支持其它有实体的事实类型，但本轮没有用它们跑；`time`、`no_change` 被显式拒绝，没有假装支持。
3. **省略规则偏保守。** 只允许同组承前省略；跨组省略一律拒绝。这样不会把“省略”误判成“指代明确”，但也漏掉了合法的跨句省略。
4. **参考正文不是质量结论。** `reference_compose.py` 是机械模板，`fixture-r3` 这种“被雨打湿半幅”的谓词片段只能拼成“林川被雨打湿半幅”，不保证自然。它只用来验证计划可执行、两份计划可区分。
5. **文本检查器仍是启发式，只是补了三类漏洞。** 事实覆盖仍用 3-gram 召回 0.5；只按 `。！？` 断句；组内顺序用字符位置近似（同义改写会扰动位置）；“剩余内容”按固定功能字表切分，功能字表本身是人工定的。**它会把合法改写里的新词当成新增内容**（例如“湿透”不在事实里），所以新增内容一律转人工，不做自动定罪。它适合本轮的参考文本与受控模型输出，不是通用 N5。
6. **v2 只堵了已知的三类漏洞，没有穷举。** 探针集只有 11 条，全部由参考正文机械修改而来；没有覆盖：改名后仍能对上 n-gram 的换位、长距离远指、数量/时间单位替换、把两句合并成一句再重复事实等。新增漏洞应继续以“先写探针、再改检查器”的方式处理，不改判据去迁就输出。
7. **基线 smoke 不是能力结论。** 77M 基线没有学过计划块，0/4 只能说明“不训练的模型不会读计划”，不能说明“计划接口无效”，也不能说明旧检查点会失败。
8. **外部夹具的提交位置。** 已提交副本在 `exp/e-browser-regression` 的 `8afb540`，不在本分支；SQLite DB 没有提交。本轮的冻结件已经把选中行复制进来，但“在别的机器上只靠 git 复跑”需要先拿到那份提交或 DB。
9. **没有浏览器、没有服务、没有页面。** 本轮全部离线；N4 的浏览器适配、真实页面接入、耗时预算都未测。

## 12. 下一轮预登记（模型能力臂）

要回答“计划训练过的模型能不能执行计划”，下一轮必须满足：

1. **检查点身份**：训练配方、基座哈希、选中 epoch、权重 sha256、解码参数全部记录；不能再用“同一个模型”这种说法。
2. **固定输入**：直接使用本轮的 `runs/r2/downstream-inputs.jsonl` 18 条（与 r1 逐字节一致），不重新生成、不改提示词。
3. **固定判据**：用 `text_conformance.py` 的 v2（`c3-text-conformance-v2`，代码哈希见 `freeze/criteria-v2.json`）；**该条没有任何 hard 发现**，且所有 review 发现都有人工结论 `paraphrase-ok`，才算该条通过；成对成功＝同一源两份计划都通过。
4. **固定对照**：必须同时报告 `split-all`、`merge-all-adjacent`、`merge-first-pair`、`merge-last-pair` 四个固定策略的成对结果（本轮均为 0），否则无法说明模型不是靠固定形状过关。
5. **停止条件**：如果模型成对成功不高于固定策略，先查“是否读了计划”（交换 P1/P2 标签后输出是否跟着变），再判断接口；不自动换基座、不追加训练步数。人工核验每批不超过 10 条，`unsure` 不计通过。
6. **新留出**：本轮的 9 个来源只用于协议与工具验证；正式能力结论需要另建未参与过任何训练/选点的留出，且不能再用同一批 `fixture-*/train-*`。

## 13. 产物与复跑

| 文件 | 内容 | sha256 前缀 |
| --- | --- | --- |
| `freeze/sources.json` | 9 个来源的选中事实、点、授权关系、逐条核验记录 | `e1c58c2c…` |
| `freeze/plans-v1.jsonl` | 18 份计划（P1/P2、形状、事实集） | `2d0876d1…` |
| `freeze/negative-cases.json` | 20 个负例及预期错误码 | `da8d754b…` |
| `freeze/contexts.json` | 场景上下文（只用于提示词抬头） | `def4fe67…` |
| `freeze/tamper-probes.json` | 11 个篡改探针（底稿、改动、改后全文、哈希、预期处置） | `75cad427…` |
| `freeze/criteria-v2.json` | 冻结的 v2 判据：22 条 hard 规则、2 条 review 规则、接受定义、门线、预登记 | 见文件 |
| `freeze/source-hashes.json` | 输入/输出哈希、提交、Python 版本 | `d96abcd3…` |
| `runs/r1/*` | v1 的历史记录（**已被 v2 取代**，保留用于对照） | — |
| `runs/r2/legality.json` | 18 份计划的逐条校验结果 | — |
| `runs/r2/negatives.json` | 20 个负例的实际错误详情 | — |
| `runs/r2/legacy-plans.json` | 旧 A/B 计划用本校验器复检（9 源 × 2 = 18/18 合法） | — |
| `runs/r2/reference-output.jsonl` | 18 条确定性参考正文 | — |
| `runs/r2/conformance.json` | 自检/交叉/负例的文本检查（v2，18/18 接受、交叉 18/18 失败） | — |
| `runs/r2/tamper-probes.json` | 11 个探针在 v2 下的逐条结果 | — |
| `runs/r2/manual-review.json` | 人工核验表（10 行，已填一轮 AI 复核，`humanSignoff: pending`） | 见文件 |
| `runs/r2/acceptance.json` | 程序硬判 + 人工结论合成的逐条验收结果与门状态 | — |
| `freeze/criteria-v2-amendment-1.json` | `fail` 取值的窄口修正记录（不改冻结件） | — |
| `freeze/checkpoint-inventory.json` | 30 个本地权重目录的清点（29 个哈希，0 个可归因计划训练） | — |
| `freeze/checkpoint-forensics.json` | 取证记录：脚本无保存调用、记录无可比哈希、目录与文件系统扫描 | — |
| `freeze/criteria-v2-amendment-1.json` | `fail` 取值的来源与窄口映射（生成器所致，非复核者） | — |
| `recover_checkpoint.py` | 只读取证脚本（git 各版本 + 文件系统） | — |
| `validate_holdout.py` | 留出包接收校验（8 族，含隔离与双计划） | — |
| `HOLDOUT-HANDOFF.md` | 留出交接契约：A 交付什么、c3 怎么查、怎么冻结 | — |
| `build_signoff_form.py` / `apply_signoff.py` | 生成/校验人工签认表 | — |
| `runs/r2/signoff-form.json` | 签认表（10 行，已填，含 AI 原结论 + 逐条人工结论） | — |
| `runs/r2/signoff.json` | 签认记录（委托签认，含哈希与逐条结论） | — |
| `check_round_ready.py` | 三状态就绪检查（留出/签认/检查点），含冻结材料重校验 | — |
| `test_regressions.py` | 三轮审阅发现的 14 条回归检查（跳过单独计） | — |
| `pins.py` | pin 的路径/哈希一致性规则，四个脚本共用 | — |
| `freeze/criteria-v3.json` | v3 检查器的判据（v2 保留为 R2 记录） | 见文件 |
| `gate_rules.py` | 门规则纯函数 + 7 条回归检查（AI 签认、仅改 signerKind 都不能开门） | — |
| `HANDOVER.md` | 交接页：三项状态、两条保留点、只接收三类外部进展 | — |
| `check_adoption.py` | 检查点采纳规则（三处挂接、拒绝基座哈希、`--explain`） | — |
| `NEXT-ROUND.md` | 三项决定的执行状态与下一步 | — |
| `runs/r2/controls.json` | 4 个固定策略 × 9 个来源 | — |
| `runs/r2/downstream-inputs.jsonl` | 18 条 N4 模拟输入（与 r1 逐字节一致） | — |
| `runs/r2/summary.json` | 头部数字 | — |
| `runs/r2/input-hashes.json` | 代码/冻结/提交/环境的哈希 | — |
| `runs/r2/run.log` | 人读表格 | — |

复跑（在 `experiments/world-components/parallel/organize_plan/` 下）：

```bash
python -X utf8 build_freeze.py        # 重新核对夹具并重建 freeze/ 的四个输入文件
python -X utf8 build_tamper_probes.py # 从 runs/r1 的参考正文机械生成 11 个探针
python -X utf8 build_criteria.py      # 生成冻结判据（自动带入检查器/探针哈希）
python -X utf8 run_experiment.py      # 合法性 + 旧计划复检 + 参考正文 + 探针 + 人工队列 + 固定策略
python -X utf8 render_input.py --out runs/r2/downstream-inputs.jsonl
python -X utf8 apply_review.py        # 把 manual-review.json 的结论并进 acceptance.json
python -X utf8 inventory_checkpoints.py  # 只读清点本地权重（约 35 秒，不算模型）
python -X utf8 recover_checkpoint.py     # 只读取证旧检查点（约 60 秒）
python -X utf8 build_signoff_form.py     # 生成人工签认表（已签时拒绝覆盖）
python -X utf8 apply_signoff.py          # 校验签认表并写 signoff.json（AI 签认会标 audit-only）
python -X utf8 gate_rules.py             # 门规则回归检查（7 条）
python -X utf8 check_adoption.py --explain  # 检查点采纳需要哪些字段
python -X utf8 test_regressions.py        # 三轮审阅修正的 14 条回归
python -X utf8 test_regressions.py --strict-cross  # 跨分支检查缺包时判失败
python -X utf8 validate_holdout.py --self-test   # 留出接收器自检（现有材料必须被拒）
python -X utf8 validate_holdout.py --unit-test   # 隔离规则对照（新事实过、改一字判重）
python -X utf8 model_smoke.py         # 可选：4 条基线 smoke（CPU，约 40 秒，写到 runs/r1）
```

只跑计划校验器看单条计划：`import plan_contract; validate_plan(facts, authorized_edges, plan)`。

只跑文本检查器看一段文本：

```bash
python -X utf8 text_conformance.py --texts runs/r1/reference-output.jsonl
```

手工验一个探针：`import text_conformance; check_text(facts, authorized_edges, plan, text, context=ctx)`，看返回的 `hard` / `review` 两个列表。

> 注意 1：仓库 `.gitignore` 忽略了整个 `experiments/`。本目录的文件需要 `git add -f` 才会进入提交；这不是文件丢失。
>
> 注意 2：`runs/*/input-hashes.json` 里的 `runtimeHead`/`runtimeStatus` 是运行时的 HEAD 与工作区状态，复跑会变；代码与冻结输入的 sha256 不随复跑改变，交付提交见 `git log`。
>
> 注意 3：`build_criteria.py` 会把当时的 `text_conformance.py` 哈希写进判据。**改了检查器就必须重新生成判据并重跑探针**，否则 `criteria-v2.json` 里的哈希会和代码对不上；`build_freeze.py` 与 `build_tamper_probes.py` 不依赖检查器，可单独重跑。

## 14. 结论分类

- **已证明**：在这 9 个可追溯来源、18 份计划上，合法性校验 18/18 通过；20 个负例全部按预期被拦下；确定性参考执行器 18/18 按计划生成，交叉检查 18/18 能区分两份计划；四个固定策略没有一对能同时通过两份计划；v2 文本检查器 11/11 探针按预期处置（9 硬判、2 转人工）。
- **已证明（限定范围）**：上述 9 个重叠来源上的旧 A/B 计划 18/18 合法；这不等于旧固定留出 10 源全部合法（其中只有 2 源有证据链）。
- **已失败**：不训练的 77M 基线在 4 条 smoke 上 0/4 通过文本一致性（只说明基线不读计划，不是接口结论）。
- **已证明（判据层面，AI 复核待人工签认）**：v2 判据加人工核验后，11 条篡改探针 10 条被判失败、1 条（T09“墨/干纸”）停在 `unsure`；只看程序时有 2 条没有 hard、转入 review，加入复核后没有任何一条被算作通过。门状态 `PROVISIONAL_AI_REVIEW_ONLY`，尚不能当模型验收门。
- **取证结果（不是能力失败）**：本地 30 个权重目录里，没有一个能证明“训练时读过计划块”（29 个算了哈希，只有基座 `5cdc5721…` 出现在旧记录里）。旧训练脚本本身没有保存权重的调用，所以这批权重从未落盘；这属于“取证未发现”，不能记成模型能力失败。
- **无法判断**：计划训练过的模型（旧 controllability 检查点或新检查点）能否执行计划；真实浏览器端到端质量；更长计划、更多事实类型、跨组省略、真实玩家回合下的表现。
- **留出待交付**：新留出不能从现有材料产生——9 个来源全部在旧训练/选点/复核里出现过，`validate_holdout.py --self-test` 已机器判出这一点。新留出由 A 在 Python 侧生成 ≥10 个新来源，c3 只读接收；契约见 `HOLDOUT-HANDOFF.md`，两道闸（生成过程 + 人工语义复核）已实现并自检。
- **计划训练检查点缺失**：本地未发现可归因检查点，路线 A 结束；是否批准 B 重训需另行决定，不会自动进入。
- **签认已完成（委托签认）**：`runs/r2/signoff.json`，签认人写成 AI 代理，8 条 `new-content-fail`、2 条 `unsure`；门状态 `OPEN`，T09 仍在 `openItems`。门 OPEN **不**解锁模型实验，`check_round_ready.py` 仍报 BLOCKED。
