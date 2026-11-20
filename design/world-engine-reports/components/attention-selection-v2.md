# 玩家关注驱动的 N2 选择 v2：受控实验与指标修正（2026-11-06）

**状态：支持 R11；当前处于「有实验结果」档。离线规则对照；无模型、未训练、未接线；旧 v1 报告和 JSON 未改。**

分支 `exp/c-fact-selection`，基线 `6440534`。详细输入、人工理由和逐例输出在
[`experiments/world-components/parallel/fact_selection/README.md`](../../../experiments/world-components/parallel/fact_selection/README.md)；
证据在 `artifacts/world-components/parallel/fact-selection-v2/`。

## 1. 为什么要重做

v1 的六组「关注变化」实验同时改变了关注和上一段已述内容，而且每次都把**另一个**可选事实标成已述。用一条完全不读关注内容的规则——保留全部 must，去掉 forbidden／uncertain／已述／time／no_change，其余 optional 全留——在 v1 的六个条件上同样得到 **6/6**。旧 v1 规则也是 6/6；两条规则没有差别。因此 v1 的 6/6 不能证明程序使用了关注。

v2 把关注和 prior 拆开：prior 为空时保留两个互相竞争、都未叙述的 optional；另设 prior 变化的条件；再加直接／间接／同地点三种关注表达，以及一个 held-out 包和一个真实页面命令覆盖。

## 2. 输入与对照臂

10 条冻结条件（9 条受控＋1 条真实命令覆盖）：

- P1–P4：`n2-13`，2×2——关注「沈拾在忙什么」／「西栅桥的铜锁」× prior 无／另一个 optional 已述；
- C1–C3：`n2-09`，直接「裴行舟的性子」／间接「他……小心翼翼」／同地点「旧钟铺里，沈拾的性子」；
- H1–H2：`train-r1` held-out 包，袖口／指节两条竞争外观，f2–f4 为 uncertain，prior 为空；
- R1：已提交 `interaction-sample-v1.md` 的真实 R3 命令「完成压力试验」，`point_19`，只作真实输入覆盖。

事实逐条带 `entityId`／`factId`／`pointId`／字段路径；关注、`attentionTargets` 和 `focus` 都是冻结实验输入，不是解析器输出。

| 臂 | 关注输入 | 说明 |
| --- | --- | --- |
| `manual` | 人工 | oracle |
| `no_attention` | 不读 | must ＋ 全部 eligible optional |
| `lexical` | `attentionTargets` | v1 原规则，匹配含 `at/scope` |
| `lexical_content` | `attentionTargets` | 诊断变体，匹配去掉 `at/scope` |
| `semantic` | 人工 `focus`（实体＋属性） | 上限参考，不是解析器／模型 |

## 3. 指标

- **hardPass**：不漏 must、不选 forbidden／uncertain、不重述已述。
- **lenientPass**（主指标）：hardPass ＋ 目标 optional 全选 ＋ 没有 unrelated optional；related 允许。
- **strictPass**（诊断）：lenient ＋ 选中的 optional 恰好只有 target。
- **mustPrecision**（旧 D1，诊断）：must 命中 / 全部选中，阈值 0.85。它把每个选中的 optional 都算进分母，和本任务要研究的「选哪些 optional」相反。

## 4. 结果

### 4.1 v1 重算

`v1-recheck.json`：不读关注的规则在 v1 六条上 **6/6**，与 v1 规则相同；六条 prior 都恰好拿掉竞争 optional；`mustPrecision` 均值 **0.444**，G1/G2 0.667、G3 0，全部低于 0.85。

### 4.2 受控 9 例

| 臂 | hard | lenient | strict | 与人工完全相同 | mustPrecision 均值 |
| --- | --- | --- | --- | --- | --- |
| manual | 9/9 | **9/9** | 9/9 | 9/9 | 0.519 |
| no_attention | 9/9 | **2/9** | 2/9 | 2/9 | 0.426 |
| lexical | 9/9 | **6/9** | 6/9 | 6/9 | 0.519 |
| lexical_content | 9/9 | **8/9** | 8/9 | 8/9 | 0.556 |
| semantic | 9/9 | **9/9** | 9/9 | 9/9 | 0.519 |

- `no_attention` 的 hardPass 9/9，原任务卡的「不越权、不漏 must、不重述」全过；但 prior 为空时它把两个竞争 optional 都选进来，lenient 只剩 2/9。
- `lexical` 在 P2、C3 因 `at` 同地点把另一个人的可选事实也选进来；C2 因「他／小心」与「谨慎」无词面匹配而漏目标。
- `lexical_content` 修好 P2/C3（8/9），仍漏 C2。
- `semantic` 在给定人工 focus 时 9/9；这是「关注结构已知」的上限，不是解析能力。

### 4.3 2×2 的机制

| 关注 | prior 无 | prior 另一个 optional 已述 |
| --- | --- | --- |
| 沈拾 | P1：no_attention 选 f1,f2,f3,f4；lexical/semantic 选 f1,f2,f3 | P3：四臂都 f1,f2,f3 |
| 铜锁 | P2：no_attention 选 f1,f2,f3,f4；lexical 也选四个；content/semantic 选 f1,f2,f4 | P4：四臂都 f1,f2,f4 |

prior 为空时，`no_attention` 在 P1/P2 的选择**完全一样**；prior 出现后它才变成「只选一个」。这变化来自 prior，不来自关注。词面规则和语义规则则在 P1/P2 之间从 f3 切到 f4。

### 4.4 真实命令覆盖

R1 的真实命令「完成压力试验」没有第二个竞争 optional；`no_attention` 选中 must＋related 人格，与人工相同；`lexical`／`lexical_content`／`semantic` 只选 must；四臂 lenient 都过。它只证明这条真实命令的 must/related 没被破坏，不证明关注选择。真实自由提问仍未记录：服务端 `input_text` 是 NULL，页面只存解析后的动作；C2 的「他」按「小心翼翼→谨慎」人工解析为裴行舟，这是未验证的指代。

## 5. 指标冲突

人工 oracle 的 `mustPrecision`：P/C 0.667，H 0，R1 0.667，均值 **0.533**，**10/10 全部低于 0.85**。`semantic` 0.567、`lexical` 0.567、`lexical_content` 0.600、`no_attention` 0.450，也全部低于 0.85。旧 D1 会把正确的 oracle 判失败；`lexical`／`lexical_content` 的 C2/R1 通过和 `semantic` 的 R1 通过，恰恰来自**漏选目标或少选 related**。旧指标不能用于 c2；新指标 `lenientPass` 才能表达「must 全留＋目标 optional 选对＋不选无关项」。

## 6. 已证明 / 已失败 / 无法判断

**已证明**

- v1 6/6 可由不读关注的规则复现；v1 的 prior 每次都拿掉竞争项。
- prior 为空时，不读关注的规则会多选；v1 词面规则在 P2/C3 因 `at` 误选，在 C2 漏选。
- 去掉 `at/scope` 能修同地点，不能修间接指代。
- 给定人工 focus，语义选择 9/9。
- 旧 `mustPrecision≥0.85` 会把 oracle 判成 0/10。

**已失败**

- v1 6/6 作为「关注驱动」的证据。
- v1 词面规则作为独立选择器（同地点／间接／prior 为空都会失败）。
- D1 `mustPrecision` 作为 c2 的通过标准。
- 把 `no_attention` 的 hardPass 当成选择正确。

**无法判断**

- 真实玩家自由表达下的关注提取；C2 的「他」在真实上下文里指谁。
- 是否需要独立选择模型：本轮没有模型臂；没有批准的新候选；Qwen3-0.6B 已退役（N2 约 24 秒）。
- 10 例之外是否稳定；H 的 `train-r1` 在 v1 出现过，v2 只当 held-out 包使用；R1 的权威 `world.db` 不在本分支，事实取自已提交报告。

## 7. 决定

- **不训练 N2 模型，不接线正式叙事流程，不改注意力解析器、后端、页面或现有 N2 接口。** 旧 v1 未改。
- 下一步不是直接训练，而是：① 在页面／协议记录玩家原话或明确关注字段（c2 边界外）；② 用本实验的 10 条冻结 cases 和 `lenientPass`／`unrelated` 指标，测一个候选解析器或零样本模型；③ 真实关注提取稳定后，才讨论是否需要独立选择模型。10 条构造/小样本不足以支持训练决定。
- 若继续用规则：优先内容字段匹配（`lexical_content` 一类），不要把 `at` 当内容，也不要把「同地点」当选材依据。

## 8. 产物

| 文件 | 内容 |
| --- | --- |
| `experiments/world-components/parallel/fact_selection/README.md` | 完整报告、人工复核表、逐例结果 |
| `.../cases-v2.json` | 10 条冻结输入与来源、人工选择、target/related |
| `.../selector.py`、`run_selection.py`、`test_selector.py`、`v1_recheck.py` | 规则、运行器、20 个测试、v1 重算 |
| `artifacts/world-components/parallel/fact-selection-v2/selection-v2.json` | 每臂每例选中 ID、检查、汇总 |
| `.../v1-recheck.json` | v1 六条重算 |
| `.../freeze.json`、`index.json`、`run.log` | 冻结哈希、证据索引、原始输出 |

复现：

```bash
cd experiments/world-components/parallel/fact_selection
python -X utf8 -m unittest -v test_selector.py
python -X utf8 run_selection.py
python -X utf8 v1_recheck.py
```
