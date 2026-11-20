# N2 事实选择 v2：受控关注／已述实验（2026-11-06）

**状态：支持 R11；当前处于「有实验结果」档。离线规则对照，无模型、未训练、未接线。**

分支 `exp/c-fact-selection`，基线 `6440534`。旧 v1 报告和 JSON 未改；本目录是 v2，旧数据只读。

## 0. 结论

1. **v1 的 6/6 确实是混淆的。** 用「保留全部 must；去掉 forbidden／uncertain／已述／time／no_change；其余 optional 全留，完全不读关注」的规则，在 v1 的六个条件上同样是 **6/6**。原因是每个 v1 条件的 prior 都把**另一个** optional 标成已述；竞争项被 prior 拿掉，选择自然只剩目标项。
2. **把 prior 拿掉后，不读关注的规则立刻失效。** 受控 9 例里它只过 **2/9**（P3、P4，仍靠 prior 拿掉竞争项）；P1/P2、C1/C2/C3、H1/H2 都因为同时选了两个竞争 optional 而失败。
3. **词面规则能修同地点误选，但修不了间接指代。** v1 的 `at` 匹配在 P2、C3 把同地点另一个人物的可选事实也选进来（6/9）；去掉 `at/scope` 的 `lexical_content` 升到 **8/9**，仍漏 C2 的「他／小心翼翼」→「裴行舟／谨慎」。
4. **给定关注结构时，语义选择 9/9。** 但 `semantic` 臂拿到的是人工给定的 `focus`（实体＋属性），不是解析器输出；这是上限参考，不是可部署的解析器或模型。
5. **旧 D1 的 `mustPrecision ≥ 0.85` 不适用于 c2。** 人工 oracle 自己也只有 **0.667 / 0 / 0.667，均值 0.533**，10/10 全部不达标；`semantic` 0.567、`lexical` 0.567、`lexical_content` 0.600、`no_attention` 0.450，全部不达标。这个指标奖励「少选 optional」，正好和本任务要研究的「选哪些 optional」相反。
6. **没有模型结论。** 本轮没有跑任何模型：Qwen3-0.6B 已按既有记录退役（N2 选择约 24 秒，远超交互目标），没有批准的新候选；不训练、不接线。真实玩家自由表达也没有记录（`world_advances.input_text` 为 NULL），R1 只覆盖到真实页面命令，不覆盖自由提问。

## 1. 输入：10 个冻结条件

事实来自已登记材料，不是手写世界记录：

| 组 | 条件 | 事实包 | 关注来源 | prior | 用途 |
| --- | --- | --- | --- | --- | --- |
| P | P1/P2/P3/P4 | `n2-13`（构造 N2 包） | 人工实验输入 | 无 / 无 / f4 / f3 | 2×2：关注（沈拾／铜锁）× prior（无／另一个 optional 已述） |
| C | C1/C2/C3 | `n2-09`（构造 N2 包） | 人工实验输入 | 无 | 直接／间接指代／同地点两个不同人物事件 |
| H | H1/H2 | `train-r1`（真实管线回合） | 人工实验输入 | 无 | held-out 包；两条竞争外观事实，f2–f4 为 uncertain |
| R | R1 | `interaction-sample-v1` 的 `point_19` | **真实页面命令**「完成压力试验」 | 无 | 真实输入覆盖；不是自由提问 |

- 事实来源与 `entityId`／`factId`／`pointId`／字段路径逐条写在 `cases-v2.json` 的 `facts[].source`。`n2-13`／`n2-09`／`train-r1` 是构造或已登记包，`pointId` 为空；R1 有 `point_19`，但它的 `world.db` 只在本机、未进本分支，R1 的事实取自**已提交的 `interaction-sample-v1.md` §2**，该报告已写 `input_text` 为 NULL、原始命令在 `page-run.json`。
- `attention`、`attentionTargets`（词面臂的输入）和 `focus`（语义臂的输入）都是**冻结实验输入**，不是解析器输出。C2 的「他」依赖「小心翼翼→谨慎」被人工解析为裴行舟；这是本实验的一个明确歧义，不是已验证的指代能力。
- 旧 v1 的六条条件不修改，只读重算；`v1_recheck.py` 产出 `v1-recheck.json`。

**人工复核表**（详细理由在 `cases-v2.json` 的 `manualReasons`）：

| 条件 | 关注 | prior | 目标 optional | 人工保留 | 说明 |
| --- | --- | --- | --- | --- | --- |
| P1 | 沈拾刚才在忙什么？ | 无 | f3 | f1,f2,f3 | f4 是铜锁外观，不回答沈拾 |
| P2 | 西栅桥的铜锁怎么了？ | 无 | f4 | f1,f2,f4 | f3 是沈拾任务，不回答铜锁 |
| P3 | 沈拾刚才在忙什么？ | f4 已述 | f3 | f1,f2,f3 | f4 已述；这是旧 G2-A 形状 |
| P4 | 西栅桥的铜锁怎么了？ | f3 已述 | f4 | f1,f2,f4 | f3 已述；这是旧 G2-B 形状 |
| C1 | 裴行舟现在是什么性子？ | 无 | f3 | f1,f2,f3 | 直接点名 |
| C2 | 他刚才那副小心翼翼的样子是怎么回事？ | 无 | f3 | f1,f2,f3 | 「他」人工解析为裴行舟；「小心翼翼」对「谨慎」 |
| C3 | 旧钟铺里，沈拾现在是什么性子？ | 无 | f4 | f1,f2,f4 | 同地点还有裴行舟的 f3，不能因为同在旧钟铺就选 |
| H1 | 我刚才袖口是不是湿了？ | 无 | f0 | f0 | 无 must；f1 是指节，f2–f4 uncertain |
| H2 | 我刚才指节怎么了？ | 无 | f1 | f1 | 无 must；f0 是袖口 |
| R1 | 完成压力试验（真实命令） | 无 | 无 | r3_sanity,r3_task,r3_personality | 人格是 related，不是 target；任务与人格同点不等于因果 |

## 2. 五个对照臂

| 臂 | 做什么 | 读关注吗 |
| --- | --- | --- |
| `manual` | 人工选择，oracle | 人读 |
| `no_attention` | 全部 must；去掉 forbidden／uncertain／已述／time／no_change；其余 optional 全留 | **不读** |
| `lexical` | v1 `R-attention-v1` 原样：目标词匹配 `name/text/goal/from/to/at/scope` | 读目标词 |
| `lexical_content` | 同上，但匹配字段去掉 `at/scope`（诊断变体，不是 v1 规则） | 读目标词 |
| `semantic` | 目标词换成人工给定的 `focus`（实体＋属性）；按 kind／实体／物件匹配 | 读 focus（oracle） |

`semantic` 不是模型，也不是从原话解析关注；它证明的是「如果关注结构已经正确，选择逻辑可以做到什么」，不是「程序能从真实玩家话里得到这个结构」。本轮没有模型臂。

## 3. 判分

- **hardPass**：不漏 must、不选 forbidden／uncertain、不重述已述。这是任务卡原来的硬条件。
- **lenientPass**（主指标）：hardPass ＋ 目标 optional 全选 ＋ 没有 unrelated optional。`related` optional 允许保留，不罚。
- **strictPass**（诊断）：lenientPass ＋ 选中的 optional 恰好只有 target，连 related 也不多选。
- **mustPrecision**（旧 D1 指标，只作诊断）：must 命中数 / 全部选中数，阈值 0.85。它把每个被选中的 optional 都算进分母，正是本任务要研究的对象，因此不拿它做 c2 的通过标准。
- `target`／`related`／`unrelated` 在每条 case 里冻结；`unrelated` 是「与当前关注无关的竞争 optional」。

## 4. v1 重算：6/6 可以由「不读关注」复现

`v1-recheck.json` 对旧 JSON 逐条重算：

| 条件 | prior | no_attention 选中 | 人工选中 | 相同 | mustPrecision |
| --- | --- | --- | --- | --- | --- |
| G1-A | f4 | f1,f2,f3 | f1,f2,f3 | 是 | 0.667 |
| G1-B | f3 | f1,f2,f4 | f1,f2,f4 | 是 | 0.667 |
| G2-A | f4 | f1,f2,f3 | f1,f2,f3 | 是 | 0.667 |
| G2-B | f3 | f1,f2,f4 | f1,f2,f4 | 是 | 0.667 |
| G3-A | f1 | f0 | f0 | 是 | 0 |
| G3-B | f0 | f1 | f1 | 是 | 0 |

**6/6 相同；旧 v1 规则也是 6/6；no_attention 的 mustPrecision 均值 0.444，六条全部低于 0.85。** 每个条件都恰好有一个 optional 被 prior 标成已述；把竞争项拿掉后，「全留剩余 optional」自然等于人工选择。旧实验没有把「关注变化」和「prior 去重」分开，所以 6/6 不能证明关注驱动。

## 5. 受控 9 例：结果

| 臂 | hard 9 | lenient 9 | strict 9 | 与人工完全相同 9 | mustPrecision 均值 |
| --- | --- | --- | --- | --- | --- |
| manual | 9/9 | **9/9** | 9/9 | 9/9 | 0.519 |
| no_attention | 9/9 | **2/9** | 2/9 | 2/9 | 0.426 |
| lexical | 9/9 | **6/9** | 6/9 | 6/9 | 0.519 |
| lexical_content | 9/9 | **8/9** | 8/9 | 8/9 | 0.556 |
| semantic | 9/9 | **9/9** | 9/9 | 9/9 | 0.519 |

`no_attention` 的 hardPass 是 9/9——任务卡原来的「不越权、不漏 must、不重述」它全过；只有加上 target／unrelated 的质量条件才暴露它没有读关注。它过的 2 例正是 P3/P4，靠 prior 拿掉竞争项。

### 5.1 2×2：关注与 prior 分开

| 关注 | prior 无 | prior 另一个 optional 已述 |
| --- | --- | --- |
| 沈拾 | P1：no_attention `f1,f2,f3,f4`；lexical／content／semantic `f1,f2,f3` | P3：四臂都 `f1,f2,f3` |
| 铜锁 | P2：no_attention `f1,f2,f3,f4`；lexical `f1,f2,f3,f4`；content／semantic `f1,f2,f4` | P4：四臂都 `f1,f2,f4` |

- 读关注：`lexical` 在 P1/P2（prior 都为空）从 `f3` 切到 `f4`；`semantic` 同样切换。`no_attention` 在 P1/P2 完全一样（都选两个），说明它没有读关注。
- 读 prior：`no_attention` 在 P1→P3 从「两个」变成「一个」，变化只因为 f4 被标已述；`lexical`／`semantic` 的 P1→P3 目标保持 f3。
- **P2 的 `at` 误选**：f3 是沈拾的任务（`at=西栅桥`），f4 是铜锁外观（`name=西栅桥`、`text=铜锁`）。v1 词面规则把 `at` 当内容证据，两个都选；`lexical_content` 和 `semantic` 只选 f4。旧 G2-B 之所以过，是因为 f3 已被 prior 标成已述；prior 一拿掉，问题就出现。
- **C3 的同地点**：f3 是裴行舟在旧钟铺的性子，f4 是沈拾在旧钟铺的性子；v1 规则因为两者 `at=旧钟铺` 都选，`lexical_content`／`semantic` 只选 f4。
- **C2 的间接指代**：关注是「他……小心翼翼」，词面目标是「他／小心」，事实文本是「变得谨慎」；`lexical`／`lexical_content` 都选不到 f3，只剩 must；`semantic` 用人工 focus（裴行舟／personality）选到 f3。这里「他」是谁本身有歧义，人工复核按「小心翼翼→谨慎」解析为裴行舟；这是解析层的未定项，不是选择规则已经解决。
- **H 的 held-out**：H1/H2 的 prior 为空，f0/f1 两条外观都未述；`no_attention` 两条都选，`lexical`／`semantic` 各选目标。旧 v1 的 G3 两条之所以都过，是旧条件把另一个外观标成已述；新条件把 prior 拿掉后，`no_attention` 失败。

## 6. R1 真实命令覆盖（不计入受控通过率）

R1 用已提交 `interaction-sample-v1.md` §2 的真实 R3：`point_19`，真实页面命令「完成压力试验」，事实为理智 10→8、任务达成、人格变化、时间 1 秒。手工保留 must（理智、任务）＋ related（人格）；时间省略。

结果：`no_attention` 选中 `r3_sanity,r3_task,r3_personality`，与人工完全相同；`lexical`／`lexical_content`／`semantic` 只选 must。四臂 lenient 都过（人格是 related，不罚）；strict 是 `lexical`／`lexical_content`／`semantic` 过，`manual`／`no_attention` 因为多选了 related 人格而不过。

**它不证明关注选择**：命令是动作，不是问题，没有第二个竞争 optional；人格只是 related。它只证明这条真实命令的 must 和 related 没有被规则破坏。真实玩家自由表达、间接指代、同地点不同事件在真实输入上的表现仍无法测：服务端 `input_text` 是 NULL，页面只存解析后的动作；要测，需要页面／协议记录玩家原话，这不在 c2 边界内。

## 7. 指标冲突：旧 D1 判据会把 oracle 判失败

| 臂 | mustPrecision 各例 | 均值 | D1≥0.85 通过 |
| --- | --- | --- | --- |
| manual（oracle） | P/C 0.667；H 0；R1 0.667 | 0.533 | **0/10** |
| no_attention | P1/P2 0.5；P3/P4 0.667；C 0.5；H 0；R1 0.667 | 0.450 | 0/10 |
| lexical | P2/C3 0.5；C2 1.0；R1 1.0；其余 0.667/0 | 0.567 | 2/10（C2/R1） |
| lexical_content | 同类；H 0；R1 1.0 | 0.600 | 2/10（C2/R1） |
| semantic | P/C 0.667；H 0；R1 1.0 | 0.567 | 1/10（R1） |

人工 oracle 的 10 条全部低于 0.85；`semantic` 只在 R1 过，因为它**少选了 related 人格**；`lexical` 在 C2/R1 过，因为 C2 漏了目标、R1 少选 related。这个指标奖励「少选 optional」，不能用来评价「该选哪些 optional」。c2 需要的是 `lenientPass`（hard＋target＋unrelated）；`mustPrecision` 只保留为 D1 兼容诊断，不参与本任务的通过判断。

## 8. 已证明 / 已失败 / 无法判断

**已证明**

- v1 六条全部满足「prior 恰好拿掉竞争 optional」；一个完全不读关注的规则在 v1 上 6/6，与 v1 规则相同。
- 在 prior 为空的受控例里，不读关注的规则会同时选两个竞争 optional；v1 词面规则在 P2/C3 因 `at` 同地点误选，在 C2 因无词面匹配漏选。
- 去掉 `at/scope` 的 `lexical_content` 修好同地点误选（8/9），但修不了 C2 的间接指代。
- 给定人工 focus 的 `semantic` 在受控 9 例全过；这是「关注结构已知」的上限。
- 旧 D1 `mustPrecision≥0.85` 会把人工 oracle 判成 0/10；新 `lenientPass` 才能表达「must 全留＋目标 optional 选对＋不选无关项」。

**已失败**

- 旧 v1 的 6/6 作为「关注驱动选择」的证据。
- v1 词面规则作为独立选择器：同地点、间接指代、prior 为空时都会失败。
- 用 D1 的 `mustPrecision` 作为 c2 的通过标准。
- 把 `no_attention` 的 hardPass 10/10 当成选择正确；它只是没越权、没漏 must。

**无法判断**

- 真实玩家自由表达下的关注提取；C2 的「他」在真实上下文里指谁。
- 是否需要独立选择模型：本轮没有模型臂；只证明了规则在给定关注结构下的能力边界，以及真实输入记录的缺口。
- `semantic` 在 10 例之外是否稳定；10 例是人工材料，不是能力验收。
- R1 的权威数据库不在本分支；R1 的事实取自已提交报告，`world.db` 未用于本实验。
- H 的 `train-r1` 在 v1 出现过；v2 只把它当 held-out 包使用，规则在看到 H 结果前固定，但它不是全新世界。

## 9. 决定

- **不训练 N2 模型，不接线正式叙事流程，不改注意力解析器、后端、页面或现有 N2 接口。** 旧 v1 报告／JSON 未改。
- 规则的缺口已经定位：同地点需要「内容字段而不是 at」，间接指代需要「实体＋属性」而不是词面；这两点都可以在选择逻辑里表达，但**从真实玩家话里得到实体＋属性**没有验证。
- 下一步不是直接训练，而是：① 在页面／协议记录玩家原话或明确关注字段（c2 边界外）；② 用本实验的冻结 cases 和 `lenientPass`／`unrelated` 指标，测一个候选解析器或零样本模型；③ 只有在真实关注提取上稳定后，才讨论是否需要选择模型。10 个构造/小样本条件不足以支持训练决定。
- 如果继续用规则：优先 `lexical_content` 一类的内容字段匹配，再加实体/属性槽；不要把 `at` 当内容，也不要把「同地点」当选材依据。

## 10. 复现

```bash
cd experiments/world-components/parallel/fact_selection
python -X utf8 -m unittest -v test_selector.py
python -X utf8 run_selection.py
python -X utf8 v1_recheck.py
```

产物：

| 文件 | 内容 |
| --- | --- |
| `cases-v2.json` | 10 条冻结输入、事实来源、人工选择、target/related、理由 |
| `selector.py` | 四个规则臂＋判分；无模型／网络／后端 |
| `run_selection.py` | 读取 cases，写 `selection-v2.json` |
| `test_selector.py` | 20 个不变式／结果回归测试 |
| `v1_recheck.py` | 只读 v1 JSON，重算 6/6 与 mustPrecision |
| `../../../../artifacts/world-components/parallel/fact-selection-v2/selection-v2.json` | 每臂每例的选中 ID、检查、汇总 |
| `.../v1-recheck.json` | v1 六条重算 |
| `.../freeze.json` | cases／code／source 哈希与规则冻结 |
| `.../index.json` | 证据逐文件 sha256 |
| `.../run.log` | 测试、选择、v1 重算的原始输出 |

报告：[`attention-selection-v2.md`](../../../../design/world-engine-reports/components/attention-selection-v2.md)
