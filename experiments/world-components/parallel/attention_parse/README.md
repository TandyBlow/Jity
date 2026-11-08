# c1 · 玩家原话 → 关注对象（固定规则基线）

日期：2026-11-08。分支 `exp/c-attention-parse`，工作树 `.local/parallel/c-attention-parse`。

- **对应原设计**：R11（叙事只写玩家当前可知道、且值得说的世界事实）的上游输入——先要知道玩家在关注什么。
- **当前档位**：**有实验结果**。离线固定规则基线，没有训练、没有模型、没有改服务端、没有改 N2 选择规则、未接入正式页面。
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

## 8. 接口影响（未验证，留给下一轮）

上一轮六条件里的 `attentionTargets` 不全是实体名：G2-B 的 `铜锁` 在 `loc_404.initialAppearance` 里，G3 的 `袖口`/`指节` 在人物外观文本里。c1 现在输出的是**对象 id 和对象名**（`attentionTargets` / `targetNames`），不是字段级词。

所以：

- 若把 c1 直接接到**未改动的** R-attention-v1（拿对象词去事实字段里做子串匹配），需要把 `targetNames` 传下去，不能用 id；
- 若玩家关注的是“袖口”这种部位/属性，c1 只能给到“沈砚”，事实级筛选仍要靠 N2；
- 这两点都**没有跑过**，列在下面待办，不算通过。

## 9. 限制

- 原话是作者自写，不是真实玩家记录；没有覆盖口语、错别字、方言、长句、多轮上下文。
- 已登记夹具里**没有两个完全同名实体**，S06 用“共用词干”代替；完全同名路径只在合成 roster U1 里测过。
- roster 只含初始外观/任务，不含运行中的变化文本（`appearanceChanges`、`personalityChanges`）；真实回合里玩家更可能引用最近变化。
- 代词只认固定词表；`他/她` 不区分性别，`那个` 不算指示词。
- 描述词匹配是字面公共子串，不理解“戴眼镜的人”“刚才说话的”这类推断式指代。
- 规则没有否定、疑问、条件、比较等语义；P5 已证明会多选。
- 单次运行可复现（同输入两次输出字节一致，已验证），但只在本机 Windows + Python 3.11.15 跑过。

## 10. 结论分类

- **已证明**：给定这两份提交夹具和 10 条原话，固定规则能稳定输出“候选／歧义／无结果”三档，三档都不回退全选；M1–M5 五条机制按声明工作（单元 6/6）。
- **已失败**：作为通用提取器，规则已在 5 个预登记点上失败（描述词前驱、同名消解、昵称、指示词、否定），失败方式与预测一致。
- **无法判断**：真实玩家原话上的覆盖率；同名实体的真实世界；接 N2 之后的叙事收益；对浏览器的性能影响（本轮没有模型）。

## 11. 复跑

```bash
cd experiments/world-components/parallel/attention_parse
python -X utf8 build_rosters.py     # 从夹具重建 roster（会校验字面与哈希）
python -X utf8 run_experiment.py    # 跑 10 样本 + 6 单元 + 5 探针，覆盖 runs/r1/
```

只跑引擎看单条：

```bash
python -X utf8 attention_parse.py --out /tmp/raw.json   # 输出全部样本原始结果
```

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

## 13. 下一轮建议（不扩大本轮结论）

1. **先定粒度**：`attentionTargets` 到底是对象 id、对象名，还是字段级词（袖口、铜锁）。这决定 c1 接 N2 时传什么，也决定是否需要第 6 类机制。
2. **换真实原话**：从正式页面的行动记录里取真实玩家输入（只读），替换自写样本，重新冻结一批 ≤10 条。
3. **补同名实体**：找一个或构造一个**已提交**世界，里面真的有两个同名对象，再测 M1/M2 的组合，而不是靠合成 roster。
4. **补变化文本**：把 `appearanceChanges` / `personalityChanges` 当前值纳入描述词来源，看能否覆盖“刚才那个变了的”这类指向。
