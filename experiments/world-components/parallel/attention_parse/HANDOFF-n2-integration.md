# c1 → N2 集成交接（2026-11-08）

`exp/c-attention-parse` @ `a26228c`。当前状态：**有实验结果，独立过滤器接线已验证**。
正式 N2（`n2_perspective.classify_facts`）**尚未接入**，真实玩家表达覆盖能力**无法判断**。

本文件只定“下一步怎么接”，不改任何现有冻结文件，不改 `runs/r1/`，不跑集成样本。
集成样本必须由 N2 侧**独立冻结**后重跑（沿用 c1 的规矩：标签先于实现、样本 ≤10、证据带哈希和提交号）。

## 1. c1 交出去的是什么

`attention_parse_v2.parse(utterance, roster, prior, anchors, worldRef)` 返回：

```
{ state: resolved | ambiguous | unresolved | none,
  targets: [{ entityId, scope, part?, partAnchored?, surface, scopeCue }],
  ambiguousCandidates, unresolvedMentions, reason, traces }
```

- `resolved` 时 `targets` 非空；其余三态 `targets` 一律为空。
- `entityId` 是提交状态里的实体 id；`scope` 五档：`object / position / appearance / task / part`。
- `part` 是字面词，`partAnchored` 表示该词是否能在该实体的提交文本里找到。

## 2. 与 `classify_facts` 的映射

`classify_facts(facts, perspective, subject_tasks, may_policy, visible_other_actions, visible_other_personality)` 的产出是每条事实的 `class ∈ {must, may, invisible}` + `ground` + `selected`，以及 `stops` / `refusals`。

接入位置：**在 `classify_facts` 之后、交给成句之前**，只筛 `may` 一类。

```
classified = classify_facts(facts, perspective, subject_tasks,
                            may_policy="select",          # 关键：让 may 进入候选
                            visible_other_actions=...,
                            visible_other_personality=...)
final = [must facts in original order]            # 注意力不得删必述
      + [may facts that match any target]         # 只看关注范围
# invisible / refusals / stops 的语义完全不变
```

按 `scope` 决定哪些 `may` 事实能留下：

| target.scope | 可留下的 fact.kind | 与 `classify_facts` 的关系 |
| --- | --- | --- |
| `object` | 该实体全部 kind | 只筛实体，不筛种类 |
| `position` | `moved`、`positioned_at`、`position_relative`、`slot_changed` | 与 `MUST_POSITION_KINDS` 同集合 |
| `appearance` | `appearance_changed`、`appearance_removed` | `OBSERVABLE_KINDS` 的子集 |
| `task` | `task_achieved`、`subtask_added` | 与 `INNER_KINDS` 里的任务类区分：任务达成是可见结算 |
| `part` | `appearance_changed/removed` 且 `text` 含 `part` 字面 | 字面匹配，不做同义 |

必须遵守的四条（c1 已验证，集成时不得放宽）：

1. **`must` 不受关注影响**：`classify_facts` 判 `must` 的事实一律留下，哪怕关注对象是另一个实体。
2. **空 `targets` = 不选任何 `may`**：等价于 `may_policy="omit"`，不是“没有约束”，更不是全选。
3. **`invisible` / `refusals` / `stops` 不变**：注意力不能把不可见事实变可见；`stops`（must 无可见依据）仍然停线。
4. **同一事实被多个目标命中只留一次**，输出顺序沿用 `classify_facts` 的顺序。

## 3. 集成前必须先定的三件事

1. **缺 `personality` 范围。** 上一轮六条件里 G1-A/B 问的是“裴行舟现在是什么性子”，c1 的五档里没有对应档，现在会落到 `object`（放大到整人）。要么给契约加 `personality`（`personality_changed` / `personality_removed`），要么明确“问性子只能整人叙述”。**未定，不得默认。**
2. **`may_policy` 与关注是替代关系，不是叠加。** 现在产品管线默认 `may_policy="omit"`（只写必述）。若保留 `omit`，`targets` 永远不会被消费；要消费就必须切到 `"select"` + 范围筛选。这是产品决策，不是实现细节，需要 N2 负责人拍板并写进集成样本的判据。
3. **旧六条件（`attention-selection-v1.json`）的 `attentionTargets` 是词，不是目标对象。** 直接用它们跑新过滤器会得到和旧 `R-attention-v1` 不同的结果（旧规则拿词去匹配 `name/text/goal/from/to/at/scope`）。集成样本应重新冻结，不要拿旧条件里的人工选择当新判据。

## 4. 已知失败（随交接保留，正式接入前必须处理）

| 编号 | 输入 | 现在会怎样 | 为什么不能算通过 | 证据 |
| --- | --- | --- | --- | --- |
| KF-1 | “看看他手背”（局部请求没有“的”结构） | 落到 `object`，范围放大成整人 | 用户指定的已知失败；v2 的保守守卫只认 `的<X>` 形状 | `freeze/v2-extra-probes.json` X2 只覆盖 `的<X>`；`runs/v2-acceptance/score.json` |
| KF-2 | 词表外的局部（“手背”“划痕”没有进 part 词表） | 有“的”时报 `unresolved`（空目标），无“的”时同 KF-1 | 词表是固定清单，不是从提交文本抽出来的 | `freeze/contract-v1.md` §8 |
| KF-3 | 一句话里整人＋局部（“林川怎么样了，他的袖口呢”） | 只出一个范围（就近归属），另一个被忽略 | 合并/优先级规则没定 | `freeze/contract-v1.md` §8 |
| KF-4 | 同名实体（仓库里没有两个完全同名对象） | 只由合成 roster 覆盖 | 真实世界未验证 | `freeze/rule-cases.json` U1 |

KF-1 的修法不属于 c1：要么把“局部请求”的检测从 `的<X>` 扩成“部位名词表 + 未识别即空目标”，要么在 N2 侧把 `object` 范围限制为“整人问题”的显式线索（“怎么样了”“人呢”）。

## 5. 集成样本的冻结要求（给 N2 侧）

- 每条样本必须写清：`before/after/delta` 或事实包来源、`perspective`、`subject_tasks`、`may_policy`、`utterance`、`expectedSelectedFactIds`。
- 判据至少四条，且分开记录：
  1. `must` 全保留；
  2. `may` 里范围外的一条不选；
  3. 空目标时 `may` 一条不选；
  4. `invisible` / `forbidden` 零入选，`stops` 行为不变。
- 失败要分类：是解析错（c1）、还是分类错（`classify_facts`）、还是筛选取舍错（新过滤器）。三类不许合报。
- 样本 ≤10 条一批；标签在实现之前冻结；`runs/r1/` 与 c1 的 `freeze/` 不参与改写。

## 6. 证据索引（不改动，只引用）

| 内容 | 位置 | 说明 |
| --- | --- | --- |
| 对象层 v1 | `runs/r1/` | 10/10、6 单元、5 探针，sha256 `0f7abbac…`，保持原样 |
| 粒度契约 | `freeze/contract-v1.md` | 目标形状、scope→kind、三态、N2 空目标行为 |
| 标签校验 | `runs/contract-v1/` | 10/10 标签与夹具自洽 |
| v2 解析 | `runs/v2-acceptance/` | A01–A10 10/10；探针 X1/X2 2/2 |
| 独立过滤器 | `runs/wiring-v1/` | 8/8；必述全留；范围外排除 14 次；空目标 0 可选；forbidden 0 入选 |
