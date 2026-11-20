# c1 · 玩家原话 → 关注对象（固定规则基线）

日期：2026-11-08。分支 `exp/c-attention-parse`，工作树 `.local/parallel/c-attention-parse`。

- **对应原设计**：R11（叙事只写玩家当前可知道、且值得说的世界事实）的上游输入——先要知道玩家在关注什么。
- **当前档位**：对象层 **有实验结果**；关注粒度契约 v1 **已冻结**；v2 提取器 **已实现并通过 A01–A10**；N2 范围筛选 **已在独立夹具上跑通**（8/8）；**N2 集成交接稿已写**（映射与已知失败），正式 `classify_facts` 接入未做。未接入正式页面、未改服务端与 N2 规则、没有训练、没有模型。
- **补的缺口**：上一轮 [attention-selection-v1](../../../../design/world-engine-reports/components/attention-selection-v1.md) 的六个条件里，`attentionTargets` 是直接给定的输入，没有验证能否从玩家原话里得到它。c1 只做这一环。

## 1. 一句话结论

在这 10 条人写原话和两份提交夹具 roster 上，固定词面规则能把玩家原话变成“候选对象／歧义／无结果”三档输出，10/10 与事先冻结的标注一致，且没有任何一条回退成全选；但同一规则在 5 条预登记限制探针上全部按预测失败，说明它是机制可用的基线，**不是**能听懂真实玩家说话的提取器。

## 2. 谁给了谁什么

```
已登记夹具（提交状态）                 c1 冻结清单                规则程序
frontend/src/lib/.../                freeze/rosters.json  ──►  attention_parse.py
  narration-split-samples.ts   ──►   （对象/字段/行号/哈希）        │
  b3-short-samples.ts                                            ▼
                                                          候选 / 歧义 / 无结果
玩家原话（本实验新写）                freeze/samples.json   ──►  runs/r1/raw-output.json
  + 上一段已述文本            ──►    （10 条 + 人工标注）          runs/r1/score.json
```

- **对象从哪来**：`build_rosters.py` 逐行读取上面两个夹具文件，抽取 `initial.*.{locations,items,characters}` 里的 `id`、`name`、`initialAppearance`，以及角色 `tasks.*.goal`。每个对象都记了文件、1 基行号、字段路径和源文件 sha256；源文件哈希一变，`run_experiment.py` 直接拒绝运行，避免 roster 和夹具悄悄脱节。
- **玩家原话从哪来**：仓库里没有真实玩家原话记录，所以 10 条原话由本任务新写，`freeze/samples.json` 里逐条注明。它们只是输入，不代表世界上发生过什么。
- **规则做什么**：见第 3 节。程序不写世界、不调用模型、不联网。
- **结果在哪**：`runs/r1/raw-output.json`（每条原话的原始输出）、`runs/r1/score.json`（逐条比对与错误类别）、`runs/r1/input-hashes.json`（代码与输入哈希、提交、Python 版本）、`runs/r1/run.log`（人读表格）。

## 3. 规则怎么算（R-attention-parse-v1，跑之前固定）

输入：原话文本、可选“上一段已述文本”、当前世界的 roster（对象清单）。

按顺序做五件事，任何一步都不允许“拿不准就全选”：

| 步 | 机制 | 具体做法 | 命中后输出 |
| --- | --- | --- | --- |
| M1 | 名字/任务目标 | 原话里出现提交记录的 `name` 或任务 `goal` 原文 | 该对象 |
| M2 | 共用词干 | 两个以上名字共享 ≥2 字词干（如 `学生A`/`学生B` 的 `学生`），且词干本身不是完整名字 | 歧义组 |
| M3 | 描述词 | 把 `initialAppearance` 按标点切成短语，取与原话最长的公共子串（≥2 字、非纯虚词）；同一词只属于一个对象才算命中，属于两个就报歧义 | 该对象／歧义组 |
| M4 | 代词 | `我/自己` → 提交记录的 protagonistId；`他/她/它` 只有当上一段恰好提到一个角色时才解析，提到两个就报歧义；`他们/她们` 解析为上一段全部角色；`这里/那里/那边` 同理但只数地点 | 该对象／歧义组 |
| M5 | 未登记称呼 | `老/小/阿`＋一字（如 `老林`）没有对应记录，记成“无法解析” | 空候选 |

输出三档：

- `resolved`：≥1 个候选，`attentionTargets` 给出对象。
- `ambiguous`：有一个说法同时指向 ≥2 个对象（或代词有多个前驱）。**此时 `attentionTargets` 为空**，被争用的对象放在 `ambiguousCandidates`，其余已解析对象放在 `resolvedCandidates` 里只做诊断，不交给下游。
- `unresolved` / `none`：前者是“提到了但匹配不上”（如 `老林`），后者是“根本没提对象”（如 `继续。`）。两种都输出空候选。

## 4. 10 条冻结样本与结果

标注在实现规则**之前**提交（`84d2bad`：`attention-parse: freeze 10 sample labels...`），规则实现在之后的 `0e841b8`。运行提交 `0df57f4`，`trackedDirty=False`。

| 编号 | 类别 | 原话（上一段） | 标注 | 实际 | 结果 |
| --- | --- | --- | --- | --- | --- |
| S01 | 完整人名 | 林川现在在哪儿？ | resolved / person_a | 同 | 通过 |
| S02 | 同义（描述词） | 穿灰衣的那个还在门口吗？ | resolved / person_a | 同 | 通过 |
| S03 | 同义＋两对象 | 黄铜钥匙还在走廊吗？ | resolved / item_key, corridor | 同 | 通过 |
| S04 | 代词单前驱 | 他还在门口吗？（前文：林川走进门厅。） | resolved / person_a | 同 | 通过 |
| S05 | 代词多前驱 | 他怎么了？（前文：林川走进门厅，周宁留在走廊。） | ambiguous / person_a+person_c | 同 | 通过 |
| S06 | 多人同称 | 学生还在走廊吗？ | ambiguous / person_a+person_b；走廊仅诊断 | 同 | 通过 |
| S07 | 无关语句 | 继续。 | none / 空 | 同 | 通过 |
| S08 | 未登记称呼 | 老林怎么想？ | unresolved / 空，记 `老林` | 同 | 通过 |
| S09 | 多对象 | 主角的任务「取回柜子里的东西」完成了吗？ | resolved / person_c, task_shelf | 同 | 通过 |
| S10 | 自称＋物件 | 我刚才打开盒盖了吗？ | resolved / person_c, box | 同 | 通过 |

**按类别**：exact_name 1/1、synonym_descriptor 2/2、pronoun_unique 1/1、pronoun_multi 1/1、shared_form 1/1、irrelevant 1/1、unknown_reference 1/1、multi_object 1/1、self_reference 1/1。

**底线检查**：`selectAllHits=0`；2 条 none/unresolved 样本的候选都是空集（没有“听不懂就全给”）。

> 这 10 条样本和规则是同一个人在同一天写的，所以 10/10 只证明“规则按声明工作”，不证明它能覆盖真实玩家说法。它的作用是把接口和三档输出固定下来。

## 5. 规则单元（合成 roster，不计入上面成绩）

`freeze/rule-cases.json` 用实验构造的 roster 单独测一条机制，6/6 通过：

| 编号 | 测什么 | 结果 |
| --- | --- | --- |
| U1 | 两个实体完全同名（都叫张伟） | 报歧义，不二选一 |
| U2 | 描述词同时属于两个实体 | 报歧义（见 §7 修正） |
| U3 | 无关语句 | none，空集 |
| U4 | 代词但上一段为空 | unresolved，空集 |
| U5 | 地点代词 + 唯一地点前驱 | resolved / hall |
| U6 | 没有任何匹配 | none，且候选数严格小于 roster（非全选） |

## 6. 预登记的失败：这规则不能做什么

`freeze/stress-probes.json` 是我在跑之前写下的“预计它会怎么错”。5/5 全按预测失败，`unexpected_pass=0`：

| 编号 | 情况 | 应有行为 | 规则实际 | 错因 |
| --- | --- | --- | --- | --- |
| P1 | 上一段用描述词指人（穿灰衣的走进门厅），原话用“他” | 解析为 person_a | unresolved | 规则只在上一段里找人名，不解析描述词 |
| P2 | 同名＋描述词（穿灰衣的张伟） | 解析为 dup_a | ambiguous | 同名先判歧义，描述词不参与消解 |
| P3 | 昵称（川哥） | 解析为 person_a | none | 提交记录里没有任何“川哥”字段，规则也不认这种形状 |
| P4 | 无所指的远指（上次说的那个呢） | unresolved | none | 规则没有指示词，把“没听懂”说成“没关注” |
| P5 | 否定句（别管林川，看看盒子） | 只选盒子 | 盒子＋林川 | 规则没有极性判断 |

## 7. 失败、修正与保留记录

1. **昵称正则吞字**：第一版 `老/小/阿`＋1~2 字把“老林怎”当成昵称。改成“＋1 字”，并在规则里声明三字昵称（老林头）本轮不覆盖。状态判定不变（仍是 unresolved），只修了记录的提及词。
2. **不唯一描述词被静默丢弃**：第一版按“非唯一就不算匹配”直接丢掉，`穿校服的呢？` 在 U2 得到 `none`。这会把“我听懂了但分不清”说成“玩家没关注”。改为报歧义组，两个候选都不选。主样本 10 条不受影响（S06 走的是词干机制）。
3. **U2 标注改写**：U2 原标签写的是 `unresolved`，改标签发生在第一次跑出 `none` 之后，理由和日期写在该 case 的 `note` 里；这是本任务唯一一处看过输出后改的标签，且改后行为更保守（两个候选都不选）。
4. **环境不是仓库文档里的 3.12**：实际跑在 Python 3.11.15（`uv` 自带解释器）。本轮只用标准库，结果文件里如实记录了版本，没有声称与 3.12 等价。

## 8. 关注粒度契约 v1（已冻结，未实现）

上一轮六条件里的 `attentionTargets` 不全是实体名：G2-B 的 `铜锁` 在 `loc_404.initialAppearance` 里，G3 的 `袖口`/`指节` 在人物外观文本里。c1 第一轮只输出对象 id 和对象名，没有“关注这个人的哪一部分”。

这一轮把粒度写死：

- **契约**：`freeze/contract-v1.md`。每个目标 = `entityId` + `scope`（`object`/`position`/`appearance`/`task`/`part`）+ `part`（仅局部）+ `partAnchored` + `surface` + `scopeCue`。每个 scope 列出 N2 可以保留哪些 kind 的事实。
- **锚点**：`freeze/anchors-v1.json`，由 `build_anchors.py` 从两个夹具里逐字抽取初始外观、外观变化、性格变化文本，带文件、行号、`changeId`、`sourcePointId`。用来判定“袖口是不是林川的”。 
- **验收样本**：`freeze/acceptance-v1.json`，10 条，在 v2 解析器存在**之前**冻结。覆盖三层：整人 1、字段 3（位置/外观/任务）、局部 3（初始外观里的盒盖、变化文本里的表面、提交文本里没有的袖口），以及歧义/无法解析/无关注三态。
- **本轮做了什么**：`validate_acceptance.py` 只校验标签与提交数据是否自洽（实体在 roster 里、部分词是否真能在该实体文本里找到、三态的字段约束、歧义候选是否真的共用形式）。10/10 通过；把 A07 的 `partAnchored` 故意改成 `true` 后报 9/10、错误项为 `target0_part_anchored_matches_fixture`，说明检查有效。
- **本轮没做**：v2 解析器、N2 接线、任何提取器运行。验收样本是下一轮“独立接线实验”的判据。

用户给的例子在这套契约下的结果：“林川的袖口湿了吗？”→ `person_a` / `part` / `袖口` / `partAnchored=false`。范围不会退回整人；N2 按字面匹配不到「袖口」就不选可选事实。

**r1 不受影响**：`runs/r1/` 保持原样，是对象层证据；v2 会改变带字段线索的原话的期望（r1 的 S01「在哪儿」应收窄为 position，S09 的任务目标提及应为 task），这属于粒度升级，记录在契约 §7。

## 8.1 v2 提取器：从原话到带范围的目标

`attention_parse_v2.py` 在 v1 的实体识别之上加范围层，规则全部来自 `freeze/contract-v1.md` §4：

1. 实体和歧义仍由 v1 的 M1–M5 给出（名字、词干、描述词、代词、昵称）。
2. 范围按固定优先级取第一个命中：`part`（词表词）→ `task`（线索词或目标原句）→ `appearance`（线索词）→ `position`（线索词）→ 都没命中则 `object`。
3. 线索词归属到原话里最近的那个实体区间（重叠优先，其次前一个，其次后一个），避免一句多对象时乱挂。
4. `part` 是否锚定查 `freeze/anchors-v1.json`：该实体的提交文本里有没有这个词。
5. 任务目标原句不再当成一个“任务对象”，而是转成 `负责人 + task 范围`。
6. **保守守卫**：如果检测到 `的<X>` 形式的局部请求，但 X 不在词表、也不是任何线索词或已登记名称，输出 `unresolved`（空目标），不退回 `object`。

**结果**（`runs/v2-acceptance/parse.json` 原始输出、`score.json` 逐条比对、`run.log` 表格）：

- 冻结的 A01–A10：**10/10** 状态与目标字段一致（含 A07 的 `袖口 / partAnchored=false`）。
- 额外预登记探针 X1/X2：**2/2**。X1 是任务原句 → `person_c / task`；X2 是“林川手背上的划痕” → `unresolved / part_outside_lexicon`，目标为空——这就是用户指定的“词表外局部不得退回整人”。

**实现期发现的 v1 缺陷**：v1 把“词干歧义”在包含关系之前就记成歧义组，导致“学生A现在在哪儿”会被 `学生` 词干误判为歧义。改用“先做包含抑制、再从存活匹配重建歧义组”后，W03/W07 恢复正常。v1 的 `runs/r1/raw-output.json` 重跑后 **逐字节不变**（sha256 仍是 `0f7abbac…`），因为 r1 的歧义样本里词干/代词匹配本来就会存活，证据没有被改写。

## 8.2 独立 N2 接线实验：范围筛选

**输入**：`freeze/facts-v1.json` 里 6 条事实，逐字取自提交样本的 `requiredFacts`（ns-pos-1 的移动、ns-appear-1 的钥匙灰尘、ns-loc-appear-1 的储物柜、ns-cont-2 的出汗、ns-task-1 的任务与时间），带样本 id、夹具行号、源文件哈希。`must/optional/forbidden` 是本实验作者标注，**不是**夹具自带，也不是真实 N2 判定。

**筛选器**：`n2_attention_filter.py` 按契约 §6 实现：
- `must` 一律选中；
- `forbidden/uncertain` 一律不选；
- `optional` 只有在“实体 + kind 在范围内 +（part 时）文本含 part 字面”同时成立时才选；
- `targets` 为空时空集，不选任何可选事实。

**结果**（`runs/wiring-v1/` 分开保存：`parse.json` 解析、`selection.json` 每条事实的取舍与原因、`score.json` 比对与汇总）：

```
W01 part 命中          保留 任务/时间/钥匙灰尘   排除 移动、储物柜
W02 走廊外观          保留 任务/时间/储物柜     排除 移动、钥匙灰尘
W03 学生A位置         保留 任务/时间/移动       排除 两个外观
W04 学生B鞋底(未锚定)  保留 任务/时间            排除 全部可选
W05 歧义              保留 任务/时间            排除 全部可选（空目标）
W06 无关注            保留 任务/时间            排除 全部可选（空目标）
W07 学生A整人         保留 任务/时间/移动       排除 两个外观
W08 学生B任务         保留 任务/时间            排除 全部可选（无对应事实）
```

- **8/8** 与冻结的期望选择一致。
- **必述在 8 个 case 里全部保留**（即使关注对象是钥匙或走廊）。
- **范围外可选事实被排除 14 次**（逐条记在 `selection.json` 的 `reason=out_of_scope`）。
- **空目标 2 例（W05/W06）选中可选事实数 = 0**。
- **forbidden 选中次数 = 0**。

## 9. 限制


- 原话是作者自写，不是真实玩家记录；没有覆盖口语、错别字、方言、长句、多轮上下文。
- 已登记夹具里**没有两个完全同名实体**，S06 用“共用词干”代替；完全同名路径只在合成 roster U1 里测过。
- roster 只含初始外观/任务，不含运行中的变化文本（`appearanceChanges`、`personalityChanges`）；真实回合里玩家更可能引用最近变化。
- 代词只认固定词表；`他/她` 不区分性别，`那个` 不算指示词。
- 描述词匹配是字面公共子串，不理解“戴眼镜的人”“刚才说话的”这类推断式指代。
- 规则没有否定、疑问、条件、比较等语义；P5 已证明会多选。
- 单次运行可复现（同输入两次输出字节一致，已验证），但只在本机 Windows + Python 3.11.15 跑过。

粒度契约（§8）与 v2 实现（§8.1–8.2）另外带来的限制：

- `part` 词表是固定清单。**已知失败**：v1 遇到词表外的局部会退回整人；v2 只对 `的<X>` 形状的请求做了保守守卫（X2 已验证），没有 `的` 的说法（“看看他手背”）仍会落到 `object`，范围照样被放大。这条仍是已知失败，不是已解决。
- scope 只靠线索词：没有线索词的问法（“他看起来怎么样”）一律落到 `object`。
- 一句话里既有整人又有局部时的合并规则没定；同一实体的 `appearance` 与 `part` 同时命中也没定；一个实体只出一个范围。
- 任务 `goal` 原句 → `ownerId / task` 已实现，但只有探针 X1 一条证据，没进 A01–A10 的正式验收。
- 接线实验只用 6 条事实、一个世界、作者标注的 must/optional/forbidden；没有跑真实 N2 的 `n2_perspective.classify_facts`，也没有重跑 R-attention-v1 的六个旧条件（它们的 `attentionTargets` 里含“袖口/铜锁”，需要先补 `personality` 等范围）。
- 描述词识别仍只用初始外观；变化文本只用于 part 锚定，没有用于实体识别。

## 10. 结论分类

- **已证明（对象层）**：给定两份提交夹具和 10 条原话，v1 规则能稳定输出“候选／歧义／无结果”三档，三档都不回退全选；M1–M5 按声明工作（单元 6/6）。
- **已证明（标签层）**：粒度契约的 10 条验收标签与提交数据自洽（10/10 结构、锚点、三态检查）。
- **已证明（解析层）**：v2 提取器在冻结的 A01–A10 上 10/10 命中状态与目标字段；两条额外探针 2/2（任务原句→task、词表外局部→空目标）。
- **已证明（筛选层）**：契约 §6 的筛选在 6 条提交事实、8 个 case 上 8/8；必述全保留、范围外可选事实排除 14 次、空目标不选可选事实、forbidden 零选中。
- **已失败**：作为通用提取器，v1 在 5 个预登记点上失败（描述词前驱、同名消解、昵称、指示词、否定）；**词表外局部在无 `的` 结构时仍会退回整人**（v2 只覆盖 `的<X>` 形状）。
- **无法判断**：真实玩家原话上的覆盖率；同名实体的真实世界；真实 N2（`classify_facts` 与 R-attention-v1 六条件）在新目标下的行为；接页面后的叙事收益与浏览器耗时（本轮没有模型）。

## 11. 复跑

```bash
cd experiments/world-components/parallel/attention_parse
python -X utf8 build_rosters.py        # 从夹具重建 roster（校验字面与哈希）
python -X utf8 run_experiment.py       # 跑 r1 的 10 样本 + 6 单元 + 5 探针
python -X utf8 build_anchors.py        # 从夹具抽取 part 锚点文本
python -X utf8 validate_acceptance.py  # 校验 v2 验收标签（不跑提取器）
python -X utf8 run_v2_acceptance.py    # v2 解析器跑 A01–A10 + 探针 X1/X2
python -X utf8 build_facts.py          # 从夹具构建接线事实包
python -X utf8 run_wiring.py           # 解析 -> 范围筛选，写 runs/wiring-v1/
```

只跑引擎看单条：

```bash
python -X utf8 attention_parse.py --out /tmp/raw.json   # 输出全部样本原始结果
```

注意：重跑会用**当前提交**重写 `runs/r1/input-hashes.json`、`run.log`、`score.json`（里面记录的是运行时的提交号）。本轮已验证重跑后 `raw-output.json` 逐字节不变，变动的只有这三份元数据的提交号字段。

## 12. 产物清单

| 文件 | 内容 |
| --- | --- |
| `freeze/samples.json` | 10 条冻结样本、人工标注、原话来源说明（sha256 `e853f127…`） |
| `freeze/rosters.json` | 两份 roster，含 `entityId`、`name`、描述词、夹具文件、行号、字段路径、源文件哈希 |
| `freeze/rule-cases.json` | 6 条规则单元（合成 roster） |
| `freeze/stress-probes.json` | 5 条预登记限制探针 |
| `build_rosters.py` | 从提交夹具抽取 roster 并校验 |
| `attention_parse.py` | 规则引擎 + CLI |
| `run_experiment.py` | 跑批、比对、错误分类、写结果 |
| `runs/r1/raw-output.json` | 原始输出（sha256 `0f7abbac…`） |
| `runs/r1/score.json` | 逐条比对、错误类别、接口与输入哈希 |
| `runs/r1/input-hashes.json` | 提交、分支、Python 版本、代码与输入哈希 |
| `runs/r1/run.log` | 人读表格 |
| `freeze/contract-v1.md` | c1 → N2 关注粒度契约：目标形状、5 个 scope 对应的事实 kind、三态、N2 空目标行为 |
| `freeze/anchors-v1.json` | part 锚点文本（初始外观、外观变化、性格变化），带行号、`changeId`、`sourcePointId` |
| `freeze/acceptance-v1.json` | 10 条粒度验收样本（对象/字段/局部 + 三态），在 v2 解析器之前冻结 |
| `build_anchors.py` | 从夹具抽取并校验锚点文本 |
| `validate_acceptance.py` | 校验验收标签与提交数据是否自洽（不跑提取器） |
| `runs/contract-v1/validation.json` | 逐条检查、哈希、汇总 |
| `runs/contract-v1/run.log` | 人读表格 |
| `attention_parse_v2.py` | v2 提取器：实体 + 范围 + part 锚定 + 保守守卫 |
| `run_v2_acceptance.py` | v2 跑 A01–A10 与 X1/X2，写 `runs/v2-acceptance/` |
| `freeze/v2-extra-probes.json` | 两条额外预登记探针（任务原句、词表外局部） |
| `build_facts.py`、`freeze/facts-v1.json` | 接线事实包：6 条提交 `requiredFacts` + 作者标注的授权 |
| `freeze/wiring-v1.json` | 8 个接线 case 与冻结的期望选择 |
| `n2_attention_filter.py`、`run_wiring.py` | 契约 §6 的范围筛选与跑批 |
| `runs/v2-acceptance/parse.json`、`score.json`、`run.log` | v2 解析原始输出、比对、表格 |
| `runs/wiring-v1/parse.json`、`selection.json`、`score.json`、`run.log` | 解析结果与事实筛选结果分开保存 |
| `HANDOFF-n2-integration.md` | 交接稿：与 `classify_facts` 的映射、三件待定事项、四条已知失败、集成样本冻结要求 |
| `freeze/integration-handoff-v1.json` | 机器可读交接：映射表、invariants、KF 清单、证据文件哈希与记录提交 |
| `build_handoff.py` | 生成交接 JSON（哈希取自文件，不手抄） |

## 13. 下一轮建议（不扩大本轮结论）

1. **补范围合并规则**：一句话里整人＋局部、同实体 appearance＋part、多实体多范围时的取舍，现在没有定义。
2. **把任务原句纳入正式验收**：X1 只是探针，需要进 A 系列样本并冻结。
3. **用 v2 目标重跑 R-attention-v1 六条件**：先补 `personality` 等范围，再比较旧规则与范围筛选在同批事实上的取舍差异。
4. **换真实原话**：从正式页面的行动记录里取真实玩家输入（只读），替换自写样本，重新冻结一批 ≤10 条。
5. **补同名实体**：找一个或构造一个**已提交**世界，里面真的有两个同名对象，再测 M1/M2 的组合，而不是靠合成 roster。

## 14. 交接：N2 集成（2026-11-08）

交接稿：`HANDOFF-n2-integration.md`；机器可读版：`freeze/integration-handoff-v1.json`（含每个冻结文件的 sha256 与记录提交）。两份都不改现有冻结文件与 `runs/r1/`。

交接的核心是一个接法，不是一段代码：

```
classify_facts(may_policy="select")
  → 保留全部 must
  → may 只保留被 target 命中的（实体 + scope 对应的 kind + part 字面）
  → invisible / refusals / stops 语义不变
```

四条不许放宽的底线（c1 已用 8 个 case 验证过）：

1. 必述不受关注影响；
2. 空目标 = 不选可选事实（等价 `may_policy="omit"`），不是无约束、不是全选；
3. 注意力不能把不可见事实变可见，`stops` 仍然停线；
4. 同一事实只留一次，顺序沿用 `classify_facts`。

集成前必须由 N2 侧定的三件事（写在交接稿 §3）：

- **缺 `personality` 范围**：上一轮六条件问“什么性子”，现在会落到 `object`；
- **`may_policy` 与关注是替代关系**：产品默认 `omit`，保留 `omit` 就永远不消费 targets；
- **旧六条件的 `attentionTargets` 是词不是目标对象**，不能直接当新判据，集成样本要重冻。

已知失败随交接保留：`KF-1`“看看他手背”仍会扩大为整人（v2 的守卫只认 `的<X>`），正式接入前必须处理；`KF-2` 词表外局部、`KF-3` 整人＋局部同句、`KF-4` 完全同名实体，见交接稿 §4。
