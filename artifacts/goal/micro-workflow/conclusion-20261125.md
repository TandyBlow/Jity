# micro-workflow 第二轮（2026-11-25）

## 定向补采与标签审计

- 五轮采集（one/two/three/ab/four）共 559 条语义记录：targets 68、results 147、updates 136、action 180、reaction 14、continuation 14。
- 定向两轮（「蹲墙角擦护目镜不出声」/「脱下外套检查血迹」）均 COMPLETED，首读 19.4 s / 29.7 s；`after` 无结算错误。
- **skip 标签 0 条**：五个文件全部 action 原始输出里 `kind` 只有 `act`（本轮 33/33、31/31），没有一次模型 `skip`。现有 skip 全部来自程序规则（`offscreenPolicy` 的零调用分支，`actions/index.ts` 223/240/255），本来就是零成本。
- **外貌变化 0 条**：55 次带 `appearances` 的 updates 回答全部为空数组；92 条实体行全负例。第二轮输入里「脱下外套」指向的 `外套` 不是世界登记物品（登记的是「演习背心」），但「擦护目镜」指向的 `goggles_lu` 也没有触发操作。
- 结论：act/skip 头与外貌文本头在当前数据上没有可训练的正例；这不是采样不足，而是 0.6B 在现有提示下的决策分布退化为单一类。四类头里可训练的是 results 与 movement（外加共享编码器），外貌只剩「是否变化」这个二分类，但没有正例同样无法训练。
- 人工抽查（`human-review.json`）：movement 6 条中 5 条可从事实文本直接确认、1 条可信；results 5 条中 3 条可信、2 条存疑（`admitted=false` 却标 partial；「拦下长椅」标 partial）。results 标签来自模型自己的 fact，无法用独立状态差复核，只能判「可信/存疑」。

## 已接入

- `microUpdates`：位置阶段先问移动头（74 条样本，16 正/58 负），只接受「实体自己的事实点名了登记地点」的移动；缺目的地、条目被校验拒绝、事实点名移动未覆盖时回退 LLM，原因写入 `stageDetail.microAbstain`。
- 分阶段调用的外貌半边改为跨调用复用（BatchMemory）：此前每点固定两次外貌提问（合并位置回答一次 + 外貌阶段一次，录音 6/7/23 点全部成对），现在外貌阶段直接复用合并回答，每点少一次约 7.8k 字调用。
- `?seed=N` 注入确定性 d20，用于受控 A/B；`semanticCalls.source` 记录 model/micro/program。
- 测试：settlement 111 通过、全量 1300 通过、tsc 干净。

## 已补

- 受控 A/B 两臂已完成（见下）：LLM 99→86 次，回合 251.1→258.4 s，状态一致。
- 移动头真实回合命中/回退：17 次位置调用 0 命中、17 弃权（全部 `no_destination`），端口耗时合计约 3 s。

## 重训结果（四轮数据）

- results 5 类（跨回合留出）：four 35/51（69%）、one 20/28（71%）、three 48/72（67%）、two 17/22（77%）；混淆集中在 achieved↔partial、not_achieved→no_change。输入中位 64 token（max 141），int8 10,552,059 B。
- movement 二分类：four 留出 tp4/fp0/fn1/tn17（95%），其余三折全对；合计 16 正例中 15 命中、58 负例全对；输入中位 54 token（max 84），int8 10,549,906 B。
- act 头在 124 条全 `act` 数据上仍是平凡 100%，不作为能力。
- 浏览器探针（ORT-WASM 1 线程，int8，新权重）：加载 999 ms；results 7/8（p50 10.4 ms）、movement 6/6（p50 14.7 ms）、act 4/4（p50 15.4 ms）。

## 外貌机会扫描

- 55 次带外貌段的 updates 提示共列出 1,382 个实体行，接受答案里 0 个 add/remove/replace。
- 用「事实点名实体核心名 + 变化动词」保守扫描，候选仅 16 行（来自 8 个提示实例），集中在「把护目镜擦干净」（goggles_lu / lu）与「拆下红色识别带」（shen / shen_band），且是否算外貌变化本身可争议。
- 结论：外貌阶段在当前语料里是纯开销；即使做「是否变化」二分类也没有足够正例，暂不训练第四个头，外貌继续由 LLM 回答（合并位置回答的半边已复用，见上）。

## 受控 A/B（2026-11-25，`seed=11`，同输入「我把水壶递给诺诺。」）

- 基线 `?seed=11`：LLM 99 次、规则/程序 9 次；results 14 次 68.5 s、targets 22 次 35.2 s、action 38 次 115.6 s、updates 32 次 102.1 s、narration 2 次 6.1 s；首读 13.1 s/14.1 s（草稿/接受）；回合交还 251.1 s；正文 84 字。
- 微型 `micro=1&seed=11`：LLM 86 次、微型/规则 29 次；results 16 次 11.9 s（14 微型、2 回退）、targets 16 次 3.5 s（14 规则/程序、1 打分、1 回退）、action 41 次 133.2 s、updates 38 次 162.2 s、narration 3 次 12.1 s、continuation 1 次 7.6 s；首读 8.8 s/10.5 s；回合交还 258.4 s；正文 179 字。
- LLM 调用净减 13 次（99→86，−13%），模型任务耗时合计基本持平（327.7 s→330.5 s），完整回合 +7.3 s（+2.9%）。results 省 56.6 s、targets 省 31.7 s，被 updates 的 +60.1 s 与 action 的 +17.6 s 吃掉——微型 results 的事实改变了后续投影与点数（updates 32→38 次、action 38→41 次），这是工作流本身引起的轨迹分叉，不是骰点差异（seed 固定）。
- 移动头端口在 17 次位置调用上全部弃权（`no_destination`，端口耗时合计约 3 s），没有减少任何 updates 调用；这与离线复算的 0/55 一致。
- 状态：两臂 `after` 完全一致——`place=西侧服务巷`、`nearby=诺诺`、`sanity=43`、无已完成任务；本回合没有任务达成，状态正确率只覆盖位置/理智/任务集合的同一性，不覆盖任务达成质量。
- 证据：`evidence-seed-llm-2026-11-25T0152-0e18.json`、`evidence-seed-micro.json`、`ab-seed-report.json`、两臂日志。

## 集成统计（离线端口复算，真实录音输入）

- 语料：55 个真实合并场景点（55 次 position+appearance 合并调用，55 次成对外貌调用），来自五轮回合。
- 移动头端口按浏览器同一输入格式与规则在 int8 ONNX 上复算：55/55 点弃权，原因全部是 `no_destination`——头判为移动的实体在自己的事实里没有「移动动词 + 已登记地点」。真实接受答案里的位置变化多为物品换槽/贴身（如 `lin@west_arcade/slot_pillar3`、`tang@yard/slot_east_cover`），事实文本只说「在……旁」或「拦下……」，端口无法从事实里取出容器。
- 因此本轮移动头对 LLM 调用的减少是 0/55；它不改变状态（弃权后原 LLM 答案继续生效）。
- 外貌复用：每个点固定少一次外貌调用（55 点/55 次），五轮共省 55 次 LLM 调用，约 11 次/回合。录音里两半的外貌操作都是 0，复用后的状态与原来一致。
- 完整回合墙钟未取得：受控 A/B 被系统内存回收终止（见上），此数字仍缺。
- 结论：位置任务需要结构化的「谁/什么 → 去哪」字段；仅靠事实文本的二元移动头不能承担位置结算。下一步应把微 results 的事实模板扩展为带 `目的地=` 的结构字段，或在动作阶段直接产出结构化移动意图。

## 结构化去向通道（实现与覆盖）

- 微 results 的事实模板新增 `去向=实体id:容器id[/槽位]`；微 updates 端口优先读取该字段，缺失时才回退到「移动动词 + 登记地点」规则。链路单测 5 条通过（transfer/walk/未登记物品/读回/无标签）。
- 真实动作文本覆盖扫描（147 次 results、173 个成员行动）：可解析的去向 **0/173**。5 条「递给」全部因别名失败——玩家说「水壶」，世界登记名是「休息区饮水杯」；「红色电台」也不是登记名。173 条行动里没有一条「走进+登记地点」。
- 结论：结构化通道的代码路径成立，但当前语料里行动文本与登记实体名之间存在别名鸿沟，微型链路仍拿不到目的地。下一步需要别名解析（或由 LLM/targets 阶段给出实体 id），否则位置结算无法离开 LLM。

## 试点头（人工标签，2026-11-25）

- 数据：`pilot-act.jsonl` 80 条（40 act / 40 skip）与 `pilot-appearance.jsonl` 40 条（20 变化 / 20 无变化），全部 `source: authored`；情境/事实与标签由同一作者手写，没有独立测试集。
- 训练在 HPC（作业 `278935`，`crf` 环境，torch 2.5.1+cu124）；集群无 onnx，远端保存 `.pt`，本地导出 ONNX 并量化 int8（各 10,549,929 B）。
- act-skip 头：5 折 CV 0.812（act→act 28、act→skip 12、skip→skip 37、skip→act 3）；输入中位 274 token（max 370），服务截断 192。
- appearance 头：5 折 CV 0.925（变化→变化 19、变化→无 1、无→无 18、无→变化 2）；输入中位 88 token（max 117）。
- 浏览器（ORT-WASM 1 线程，int8，192 token）：加载 764 ms；act p50 41.2 ms/p95 74.1 ms，appearance p50 17.4 ms/p95 22.8 ms；探针 10+10 条训练样本全对，只作延迟证据。
- 边界：skip 在产品里由程序规则零调用决定，没有模型调用点；外貌操作在真实语料 1,382 行里为 0，这个头没有可验证的产品效果，也未接入 `?micro=1`。这两项是人工标签试点头，不是产品能力。

## 位置阶段的语料复算（2026-11-25）

- 55 个真实场景点、64 条成员事实：只有 12 条事实点名了已登记地点；程序规则（地点名 + 槽位标签 3 字重叠）在 12 条上给出位置，10 条与 LLM 接受答案一致（8 精确、2 只对容器）、2 条不一致。逐点全部一致的点 10/55。
- 经济性：位置调用约 6 s/次（11.5k 字的大提示约 37 s）；规则只覆盖 18% 的点，且跳过合并位置调用会另付一次外貌调用（约 4 s），净收益接近 0。未接入。
- A/B 分阶段：基线 updates 里 14 次位置调用只有 5 次真调用（9 次程序跳过），微型臂 15 次全是真调用；位置阶段 87.3 s→137.6 s。原因是微型 results 改变了轨迹（点数/行动者集合），不是端口本身的开销。
- 下一步若要替代位置阶段，需要「结构化事实 + 投影」：让 updates 直接用 results 的 actorId/targetId/去向，而不是从事实文本猜受影响实体；否则规则覆盖不足，模型也没有可训练的目的地标签。

## 两 seed 受控 A/B（2026-11-25）

| seed | 臂 | LLM 次 | results | targets | action | updates | 回合交还 | 首读 |
|---|---|---|---|---|---|---|---|---|
| 11 | 基线 | 99 | 68.5 s | 35.2 s | 115.6 s | 102.1 s | 251.1 s | 14.1 s |
| 11 | 微型 | 86 | 11.9 s | 3.5 s | 133.2 s | 162.2 s | 258.4 s | 10.5 s |
| 17 | 基线 | 122 | 74.3 s | 43.1 s | 109.5 s | 91.1 s | 261.3 s | 24.7 s |
| 17 | 微型 | 97 | 10.7 s | 9.2 s | 143.0 s | 95.9 s | 208.3 s | 15.6 s |

- results 头两 seed 都稳定：68.5/74.3 s → 11.9/10.7 s（每次 14 次微型、2 次回退），单阶段省 56–64 s、12–13 次 LLM 调用。
- targets 规则/scorer：35.2/43.1 s → 3.5/9.2 s，省 32–34 s、12–14 次调用。
- action 两 seed 都变慢（+18/+34 s），updates 一慢一平（+60/+5 s）；微型 results 改变轨迹，回合净差 −2.7 s（seed 11）与 −53 s（seed 17），两 seed 合计 −56 s、LLM −38 次。
- 两 seed 的 `after` 完全一致（西侧服务巷、诺诺、理智 43、无已完成任务），没有观察到状态回退。
- 结论：results 头是第一个真正替代高耗时 LLM 调用的微型模型（阶段省 56–64 s、12–13 次调用、状态一致）；回合收益受轨迹方差影响，两 seed 平均约 −28 s（−11%）、−19 次调用/回合。下一步优先把 action 的 +18–34 s 与位置阶段的结构化事实对齐，而不是继续加分类器。

## action 结构化与固定输入回放（2026-11-25）

- action 臂（`structuredActions`，随 `?micro=1` 开启）在接受的行动文本上生成 `category/actorId/targetIds/itemIds/destination/conditions`：类别与去向用规则，目标用现有指代规则，物品用词面候选匹配；提到「水壶」而世界登记名是「休息区饮水杯」时返回空，不强行匹配。
- 结构随 `discover_group` 进入 `groupActions`，results 输入与提示都带 `结构：类别/目标/物品/去向`；微 results 的事实据此写 `去向=实体:容器`，updates 端口直接读取，不再从自然语言猜。
- 固定输入回放（147 次真实 results 调用、173 名成员，同一提示同一输入）：results 头在 144/147 次调用上可以整体替换（3 名成员低置信回退），成员标签与 LLM 一致 153/170（90.0%；four 49/2、one 23/4、three 60/10、two 21/1）。这是**样本内**回放——头在这些 run 上训练过；跨 run 留出准确率仍是 67–77%。
- 测试：action 结构 6 条、action 臂 2 条、settlement 结构透传 1 条；全量 1314 通过、tsc 干净。

## 完整状态对比（两 seed，全部字段）

- `diff_states.py` 比较两臂 `snapshotAfterTurn.transport.state` 的所有人物位置/理智/任务状态/外貌与个性记录、全部物品位置与地点外貌，而不是 `after` 摘要。
- seed 11：**0 个差异字段**；唯一不同是世界时间（15:21 vs 15:22，两臂推进的分钟数不同）。
- seed 17：**1 个差异字段**——凯撒各新增一条待办子任务，基线 `task_24=让红方地图桌确认地图状态`，微型 `task_22=确认地图信息并达成目的`；两条都是 pending，编号与措辞不同，微型臂的措辞更泛。
- 结论：两 seed 的完整状态没有出现位置、物品归属、理智或任务完成度退化；seed 17 的差异是子任务提案措辞，属于叙事/任务质量差异，不是状态回退。该对比仍只覆盖一回合输入；扩大输入与 seed 仍在进行。
- 更正：两 seed 回合平均节省 =（−2.7 −53.0）/2 ≈ **−22.9 s**，此前口述的「约 −28 s」有误。

## 结构化臂 A/B（seed 11，action 结构开启）

- 基线：LLM 125 次；results 110.2 s、targets 44.3 s、action 116.6 s、updates 45.5 s（44 次里多数是程序跳过）；回合 252.9 s；首读 11.7 s。
- 微型（`micro=1`，含结构化 action）：LLM 86 次；results 12.9 s（14 微型/2 回退）、targets 3.6 s、action 132.8 s、updates 166.2 s（38 次全是真调用）、narration 14.2 s、continuation 7.9 s；回合 266.2 s（+13.3 s）；首读 10.4 s。
- 完整状态：仅 1 个差异字段——凯撒新增两条待办子任务（`task_21`/`task_23`，均 pending），基线没有；其余人物位置/理智/任务、全部物品位置与地点外貌一致；时钟差 1 min。
- 诊断：回合差异仍由「基线大量位置调用被程序跳过、微型臂点数更多」造成（updates 45.5→166.2 s），不是 results/targets 头本身；结构化 action 在这次输入上没有产生 `去向`（水壶对不上登记名「休息区饮水杯」），移动头端口继续弃权。
- 下一步：实体候选检索 + 语义匹配（允许无匹配）解决别名，否则位置阶段无法离开 LLM；然后扩大输入与 seed，用固定输入回放比较 action/updates 的阶段收益。

## 意图 / 结果 / 状态变更分离（2026-11-25）

- 修复：微 results 之前对成功、失败、受阻一律附加 `去向=`，且 `partial` 被映射成 `completed`。现在只有 `achieved` 才允许写去向（`settledDestination`），partial/failed/blocked/no_change 一律不产生状态变更；outcome 词表新增 `partial`（results 派生、提示、narration 类型与措辞同步）。
- 测试：achieved 才返回去向 5 例；partial 判断派生 `outcome=partial` 1 例；全量 1314 通过、tsc 干净。

## updates 耗时拆解（结构化臂，seed 11）

- 基线：44 次调用 = 33 次程序跳过 + 11 次真推理；重试 4 次；真推理 45.5 s（position 27.9、tasks 10.4、subtasks 7.2）；提示中位 2,718 字、最大 3,368。
- 微型：38 次 = 20 次跳过 + 18 次真推理；重试 2 次；真推理 166.2 s（position 136.1、tasks 17.9、subtasks 12.1）；提示中位 2,912 字、最大 11,583。
- 结论：耗时上涨不是调用次数（38<44）、也不是重试（2<4），而是真推理从 11 次升到 18 次，且其中包含两次 11.5k 字的大位置提示；基线这一轮跳过了那些点。下一步要减少「无实际移动却被激活」的位置点，并拆分大合并提示。

## 实体匹配数据与训练

- `matcher-pairs.jsonl`：890 对（131 正 / 759 负），74 个物品，按物品留出 14 个（237 条测试）；「水壶/外套/电台」等未登记提法与全部候选配成 no-match，禁止默认水壶=饮水杯。
- 训练在 HPC（`item_matcher` 作业），MiniRBT 句对打分，阈值 0；集群无 onnx，取回 `.pt` 后本地导出。指标与浏览器延迟待作业完成。

## 实体匹配模型结果（2026-11-25）

- 数据：890 对（131 正/759 负），74 个物品，按物品留出 14 个（237 条测试）；未登记提法（水壶/外套/电台/头盔/钥匙串/地图册/长柄手电）与全部候选配 no-match。
- 模型（MiniRBT 句对，HPC `item_matcher`）：测试对 0→0 169、0→1 18、1→0 **42**、1→1 **8**；留出物品的正例几乎全被判 no-match（8/50）。未登记提法全部 no-match（最高分约 −7.73），水壶没有被强行匹配到饮水杯。
- 词面基线在同一测试集上正例 50/50，负例 118/187（误报是同一归属的兄弟物品：红/蓝识别带、备用弹匣等）。
- 结论：模型没有超过词面基线，不集成；`matchItems` 继续用词面 + 无匹配。要匹配别名需要别名的监督数据，当前语料没有。模型报告与数据已留档，`item-matcher.pt` 只在本地。
- 仍待办：复合行动/多物品/多状态变化；用修复后的 outcome 重跑 A/B；扩大输入与 seed。

## 复合子动作与结构化场景阶段（2026-11-25）

- action 结构新增 `subActions`：每个子动作有独立 id、order、dependsOn；按「，然后/接着/再/同时/并」切分，第二句主语是他人时不切分。类别、目标、物品、去向按子动作分别推导。
- 微 results 对每个子动作单独跑头：只有该子动作 `achieved` 才写 `去向=`；同一成员可以有多条事实；成员总体 judgment 由子动作聚合（全同取该标签，否则 partial）。这解决了「两件物品一件成功一件被拒，partial 整体压掉成功变更」。
- results 提示打印每个子动作；指令允许同一成员多条事实，失败/受阻的子动作要写清没有生效。
- updates 新增 `programScene`：事实带 `去向=`、没有外貌变化词、且所有移动语言都有去向或明确失败时，直接应用位置并把外貌半边置空复用；任一条不确定就回退 LLM。目标是把结构化事实直接变成状态变更，不再让 updates 读 11.5k 字长文。
- 测试：结构切分 2 条、程序场景 2 条（命中不调模型 / 外貌词回退）、子动作门禁；全量 1320 通过、tsc 干净。
- A/B：`walk-turn.json`（「我走进庭院。」，lu→yard，无外貌词）正在跑 seed 11 两臂，验证程序场景是否真的跳过位置调用。

## 结构化步行 A/B（walk-turn，seed 11）

- 输入「我走进庭院。」，结构为 `lu→yard`，无外貌词；两臂都 COMPLETED，完整状态零差异（只有时钟差 1 min）。
- 基线：LLM 125 次；updates 42 次（33 程序跳过 + 9 真推理、4 重试）45.6 s，position 33.3 s，提示最大 3,369 字；回合 207.0 s；首读 15.3 s。
- 微型：LLM 87 次；updates 38 次（21 跳过 + 17 真推理、2 重试）147.1 s，position 129.1 s，提示最大 11,583 字；程序场景命中 1 次（updates source=micro），外貌阶段仍有一次 2.1 s 的回退；回合 254.7 s；首读 10.2 s。
- 结论：`programScene` 的毫秒级路径在命中的点上成立（位置调用为 0），但本轮只有 1 个点满足「去向全覆盖 + 无外貌词」；其余点仍走 11.5k 字大提示，且微型臂激活的点更多。要真正压缩 updates，需要按受影响实体/属性做局部输入，并把「确认无变化」的外貌判断也程序化；仅靠整段事实的 `去向=` 覆盖不足。
- 复合子动作代码已合入，但还没有端到端回合验证（本轮输入是单动作）。

## 步行未移动：原因与修复（2026-11-25）

- 原因链：group_12 的微 results 首答被拒，因为诺诺的事实文本「拦下唐骁的演习枪」点名了组外角色唐骁；整组回退 LLM。LLM 为路明非写的事实是「看懂了规则牌」，与「我走进庭院」无关，results 的 rules-reading 检查把它当无依据事实丢弃；位置阶段没有可依据的移动，最后只把凯撒放回红方集结点。玩家没有移动，状态一致掩盖了结算错误。
- 修复 1：微 results 在事实文本里把组外角色名替换成「对方」，避免整组因一条事实被拒。
- 修复 2：移动头端口即使一个实体都没判为移动，也先读取事实里的 `去向=`；命中且都在扫描范围内就直接产出位置，不再返回空位置。
- 修复 3：子动作依赖进入输入与提示——微 results 的子动作输入带 `前序：sa1=…`，results 提示打印 `依赖=sa1`，并要求前序失败/受阻时后续子动作写清未执行。
- 验证：修复后重跑 `walk-turn` 微型臂（seed 11），检查玩家是否真的从服务巷进入庭院；结果待写。

## 步行修复验证（walkfix3，seed 11）

- 根因：世界地点登记名是「中央庭院」，玩家说「庭院」；action 结构与 updates 的 `destinationOfFact` 都要求完整名字匹配，所以结构里 `destination=null`，results 只能按 partial 处理，位置阶段没有可执行去向。
- 修复：`matchLocation` 支持唯一的地点名后缀（庭院→中央庭院；西回廊/东回廊这类同后缀地点判歧义返回 null），action 结构与 `destinationOfFact` 共用。
- 验证：`walk-turn` 微型臂 COMPLETED，路明非最终位置 `yard/slot_east_cover`，`after=中央庭院`、旁边唐骁；这是本轮输入应有的状态变化（此前两臂都停在西侧服务巷）。
- 仍有 1 次 `group_12#position` 7.36 s 记录，且在抓到的 15 条位置提示里找不到对应 prompt（其余 15 条都是 NPC 组）；需要下一轮把调用键与点位一起记录，确认这次调用是重试、另一分组还是程序路径未命中。
- 该修复只解决「登记名 vs 口语简称」的一个实例；别名（水壶/饮水杯）仍然不强行匹配，按弃权处理。

## 局部状态计算准备（2026-11-25）

- `matchLocation` 改为完整名优先：完整名匹配永远压过后缀匹配（西回廊不会被东回廊的「回廊」后缀覆盖）；后缀必须唯一（庭院→中央庭院可用，回廊歧义返回 null）。3 条测试。
- `programMove` 不再无条件成功：要求类别 move、目的地是登记地点、行动者是主角、当前不在目的地、文本无「被阻止/拦住/锁/关着/无法/没有/失败」等受阻词，且没有失败的前序依赖；否则交给 results 头判断。4 条测试。
- 子动作依赖实际执行：前序 `blocked/not_achieved` 时，依赖它的后续子动作直接判 blocked、不写去向；部分成功仍交给头判断。
- 组外人物保留结构化 id：事实正文用「对方」，同时追加 `；涉及=tang` 之类的 id 标记，不再只留泛称。
- 语义调用证据新增 `attempts/stages/stageMs/scope`，连同 key、promptChars、ms、source 一起记录每项任务的触发与推理次数。
- 全量 1329 测试通过、tsc 干净；复合行动验收（护目镜递给诺诺→走进庭院）正在跑。

## 复合行动验收（第一轮）

- 「我把护目镜递给诺诺，然后走进庭院。」：路明非最终 `yard`，`after=中央庭院`，第二子动作生效。
- 第一子动作未移动护目镜：世界有两个带「护目镜」的物品（路明非的护目镜、备用护目镜），词面同分，匹配器按规则弃权，结构里 `itemIds=[]`，所以没有 `去向`。
- 修复（不训练新模型）：同分时只按归属消歧——候选全名以「行动者名+的」开头且唯一时才命中；否则继续弃权。护目镜→路明非的护目镜现在唯一。测试 2 条；全量 1331 通过。
- 验收重跑进行中，预期护目镜归属变为诺诺、路明非在庭院。

## 复合行动验收（第二轮，通过）

- 「我把护目镜递给诺诺，然后走进庭院。」：`goggles_lu` → `nono`，路明非 → `yard`，`after=中央庭院`、旁边唐骁；两个子动作都按预期落到状态。事实为「路明非把护目镜递给对方（达到目的）；去向=goggles_lu:nono；涉及=nono」，结构化 id 保留。
- 归属消歧后，护目镜不再与备用护目镜同分弃权；物品转移、连续移动、子动作依赖在同一条行动里生效。
- 证据：`evidence-compound2-micro.json`（COMPLETED，回合 256.1 s，首读 7.5 s）。
- updates 任务现在总会带 task 级 source（model/micro/program），程序场景与跳过不再显示为 null。

## 局部位置输入与复合 LLM 基线（2026-11-25，seed 11）

- 复合输入「我把护目镜递给诺诺，然后走进庭院。」两臂同 seed：
  - LLM 基线：回合 261.3 s、首读 19.2 s、LLM 108 次；路明非在庭院（east_cover），但**护目镜仍在路明非身上**（转移没有生效）。
  - 微型 + 局部位置：回合 **191.1 s**（−70.2 s，−26.9%）、首读 **7.3 s**（−62%）、LLM 73 次；路明非在庭院、**护目镜归诺诺**。完整状态仅 2 个差异字段，且都是微型臂更符合输入（护目镜归属；庭院槽位基线有、微型无）。
- 局部位置：每个有结算事实的受影响实体发一条小问题（实体、当前位、该条事实、地点表 + 相关槽位），不再发整场景提示；任一条被拒或遗漏移动就回退合并场景。14 次真实位置调用里仍有 1 次 11.5k 字合并回退（37 s），其余为小提示。
- updates 时间 80.0→98.2 s（局部小调用次数多），但 results 81.6→7.9 s、targets 49.6→3.6 s，整回合净省 70 s。
- 微型模型任务覆盖率（`coverage_report.py`）：results 15/16 次走微型头（micro_share 1.00）；targets 14/16 走程序、1 次 LLM；updates 21 次程序、21 次 LLM（局部位置）、0 次微型；action 14 次 LLM + 27 次尝试；总体 micro 15 / model 36 / program 36，micro_share 0.29。规则收益与微型收益分开统计。

## action 重试分析与 NPC 行为头（2026-11-25）

- 重试原因（两轮 action 任务级记录）：`action_is_task_goal` 22 次、`absent_character_in_action` 10、`absent_item_in_action` 3、`repair_requested` 24、`repair_failed` 2。主因是模型把待办目标当行动句，修一次仍复读。
- 行为头（124 条真实 NPC 行动，7 类：move/assist/guard/communicate/observe/use/other）：按 run 留出 41/41、17/17、43/47、13/19。准确率偏高是因为训练行动里大量行动句本身就是待办目标的复述，头学到的是「目标动词→类别」的先验，不是通用行为模型；输入中位 131 token（截断 96），int8 10,551,229 B。HPC 连接超时，改在本地 4060 训练并量化。
- 模板行动（类别→一句话，槽位来自待办里的登记地点/物品/可见人物）接入 action 臂：第一轮 8 条模板、4 次 LLM、回合 **58.8 s**，但模板把苏茜、唐骁移到了目标里只是被引用的钟楼，行为不合理。
- 加可行性门禁（move 只有目标里出现「前往/去/走向…」且不在原地才成立）后复跑：4 条模板、9 次 LLM、2 次回退，回合 200.0 s；状态与基线的差异只剩 2 个字段，且微型臂更符合复合输入（护目镜→诺诺）；NPC 位置与基线一致。模板文本仍偏泛、多样性低，开放式行为仍回退 LLM。
- 覆盖率（behavior2）：action micro 4 / model 9（micro_share 0.31），results 13/13 micro，updates 18 程序/22 LLM，整体 micro 18 / model 32 / program 32（micro_share 0.36）。

## 三个行为评分头（候选对照实验，2026-11-25）

- 数据：`judge-data.jsonl`，14 个 NPC、56 个场景（同一人物/任务，四种现场：物品在手/不在、目标在场/缺席、道路畅通/受阻+刚重复），244 个候选-场景行；标签由规则生成且允许多正例（task 132/112、personality 204/40、scene 111/133）。
- 模型：MiniRBT 共享编码 + task/personality/scene 三个 1-logit 头，按人物留出 caesar/lin/qin/tomiyama（72 行测试）。留出集：task 72/72、personality 57/72、scene 67/72（场景标志放在输入最前，截断 128 不再切掉现场信息；此前放末尾时 scene 只有 51/72）。
- 四臂离线对比（16 个留出场景）：类别头选中 12 个、合理 5（0.42，4 个场景无对应类别候选）；单 task 评分头合理 8/16（0.50）；三头合计合理 12/16（0.75）；oracle（每个场景至少一个合理候选）16/16。三头协同明显优于单头与类别头。
- 边界：标签是规则生成，不是人工语义判断；三头在同一编码器里联合训练，不是三个独立模型；LLM 臂未离线跑（需要真实浏览器动作提示），下一步用真实回合 A/B 对照。
- 模型 int8 10,553,112 B，分片存 `judge-model/`（README 里一行拼回，sha256 已记）。

## 三评分头真实回合（compound，seed 11）

- 微型臂（judge 启用）：回合 253.8 s、首读 14.8 s；action 69.1 s、results 1.2 s、targets 6.3 s、updates 111.1 s、continuation 51.0 s、narration 33.4 s。
- 对照 LLM 基线：回合 261.3 s、首读 19.2 s；action 116.1 s、results 81.6 s、targets 49.6 s、updates 80.0 s、continuation 11.6 s、narration 13.5 s。
- action 的 LLM 调用 40→13，12 次由三个评分头选中候选；judge 每次 2–7 对、0.2–0.9 s，加载 518 ms。
- 完整状态只差 1 个字段：护目镜归诺诺（微型正确），其余人物/物品/任务一致。
- 覆盖率：micro 28 / model 30 / program 41（micro_share 0.48）；action micro 12/model 13（0.48）、results 17/17、targets 16 程序。
- 结论：离线多评分头合理率 0.75（单头 0.50、类别头 0.42），真实回合 action 阶段省 47 s、状态更符合预期；但 continuation（+39 s）与 narration（+20 s）因轨迹变长吃掉了收益，回合只省 7.5 s。下一步需要约束连续回合/叙事触发，而不是继续动 action。

## 四臂对照与回合流分析（2026-11-25 修正版）

- 统一用 16 个留出场景作分母（未选出算失败）：类别头 5/16（0.312，4 个场景无对应候选）、单 task 头 8/16（0.50）、三头合计 12/16（0.75）、手写规则 11/16（0.688）、oracle 16/16。规则臂按类别/个性/现场规则重算，不看训练标签；三头只比规则高 1 个场景，不能据此宣称超越规则。
- 流分析（judge 臂 vs LLM 基线）：judge 臂 5 个点（4 normal/1 instant、3 automatic、4 rounds），基线 4 个点（3/1、2 automatic、3 rounds）；continuation 4 次 51.0 s vs 2 次 11.6 s，narration 5 次 33.4 s vs 4 次 13.5 s；judge 臂行动文本 16 条中 3 条重复，continuation 候选里「唐骁听到远处枪声后…」「路明非听到远处枪声后…」跨轮重复。多出的自动轮与被重复接纳的候选是 47 s action 收益被吃掉的主因。
- 人工评价：`human-eval-sheet.md` + `human-eval-template.json`，16 个留出场景、候选逐条勾选，允许一个场景多个合理行为；尚未有人工标签，三头的泛化能力仍待该数据回答。
- 三头共享同一编码器，属于多任务模型；独立模型架构的对照保留，未拆。

## Continuation 微型工作流（2026-11-25）

- 结构化事件记录：`micro/events.ts` 把每个 committed point 的 `positionSet/appearanceChanges/sanitySet/tasksAchieved/subtasksAdded` 变成事件行。重复判定用 `actorId + 规范化文本 + worldDigest`：只有「同一世界里的原句重放」在编码前拒绝；世界已变后的同句警戒/观察允许，仍受连续重复上限（2 次）约束。这直接回应「不要简单禁止重复行为」。
- 四头模型：`continuation-heads-int8.onnx`（MiniRBT 共享编码 + novelty/unfinished/necessity/intervene）。候选来自现有 `behaviorCandidates`（任务/地点/物品/可见人物），同世界重复与 `wait` 先拒绝；每个角色取总分最高候选，四门共同决定继续与行动角色；涉及主角的候选把 intervene 抬到 0.75，交还玩家。模型缺失/异常返回 null，回退原 LLM 提案+判断；`?microContinuation=0` 保留上一版微型工作流作对照。
- 数据/训练：`continuation-data.jsonl` 432 行 / 84 场景 / 14 人物（base/event/repeat_same/continuous/player_present/idle），标签规则生成且允许多正例；按人物留出 caesar/lin/qin/tomiyama。留出行混淆：novelty 102/107、unfinished 107/107、necessity 102/107、intervene 107/107（留出正例只有 3 条）；决策层与规则臂 24/24 场景同角色。边界：模型在复现规则标签，不是语义泛化证据，也不能据此说它优于 LLM。
- 真实录音固定输入回放（39 次 continuation 调用）：micro 与录制 LLM 接受的 character set 一致 39/39；但录制 LLM 38/39 都继续，回放只说明「同样会继续」，不证明文本质量。
- 四臂完整回合 A/B（同输入「我把护目镜递给诺诺，然后走进庭院。」，seed=11，`evidence-continuation-{llm2,off3,rule3,micro3}.json`）：

  | 臂 | 回合 | 接受任务调用 | continuation | 自动点 | 结束原因 |
  |---|---|---|---|---|---|
  | LLM-only | 257.7 s | 104 | 0（未到边界） | 0 | turn_budget |
  | micro 无 continuation | 150.8 s | 119 | 4 次 36.3 s | 3 | no_progress |
  | micro 直接规则 | 153.6 s | 119 | 4 次 0.0 s | 3 | no_progress |
  | micro 四头 | 99.2 s | 109 | 3 次 0.7 s | 2 | no_progress |

- 规则 vs 四头（同候选、同 policy、同输入）：四头 −54.4 s、少一个自动点，完整状态只差路明非 yard 槽位（rule=east_cover，heads=无）；两者都把护目镜转给诺诺。直接规则的 continuation 本身是 0 ms，但选出的角色/轨迹让 updates 与 narration 多跑一轮，整回合没有更快。这是单输入结果，不能证明四头普遍优于规则。
- off→on（上一版微型工作流 vs 四头）：−51.6 s、少一个自动点；continuation 36.3→0.7 s；updates 76.2→64.7 s。完整状态只差 yard 槽位与 1 min 时钟。
- LLM 基线本轮（llm2）在玩家回合即被 turn_budget 截断（257.7 s、2 个点、0 个自动点）；同输入同 seed 的上一轮（llm1）跑到 2 个自动点、261.0 s。LLM 路径的方差本身就是证据：它不能稳定地在预算内走完自动链。相对 llm1/llm2，四头臂约 −158 s；护目镜在四头臂已转给诺诺，LLM 臂没转。
- 指标（micro3 每次玩家操作）：微型 task calls 52；共享编码器 137 次（推理规模以此计）；头输出 488 个（不是 488 次推理）；候选逐项评分 137 行。continuation 3 次/17 编码/68 头输出；results 16/16/80；judge 15/88/264；behavior 10/10/70；targets 8/6/6。任务来源：program 37、micro 29、model 33；另有 10 次 model attempt 单列，已从接受调用中剔除，未标注接受调用为 0。
- 两 seed 规则 vs 四头（同输入；seed 11/17，`evidence-continuation-{off3,rule3,micro3,off-seed17,rule-seed17,micro-seed17}.json`）：

  | seed | LLM continuation 臂 | 直接规则 | 四头 | 自动点（LLM/规则/四头） | 四头 vs 规则状态 |
  |---|---|---|---|---|---|
  | 11 | 150.8 s | 153.6 s | 99.2 s | 3/3/2 | 1 字段（yard 槽位） |
  | 17 | 153.7 s | 95.7 s | 91.5 s | 3/2/2 | 0 字段 |

- 两 seed 合计四头 vs 规则 −29.3 s，但差异全部来自 seed 11 多出的一个自动点；seed 17 只差 4.2 s、完整状态相同。**直接规则 vs 四头没有被证明有稳定差异**；四头当前的价值是替换 LLM continuation 与结构化重复过滤，不是胜过训练规则。
- 四头相对 LLM continuation 两 seed 分别省 51.6/62.2 s；直接规则在 seed 17 省 58.0 s，在 seed 11 反而慢 2.8 s（自动点少了，但 updates/narration 轨迹更慢）。完整状态只差路明非 yard 槽位。
- 人工评价：`continuation-human-eval-sheet.md` + `continuation-human-eval-template.json`，4 个留出人物 × base/continuous/player_present/idle 共 50 行，标签隐藏，待独立评价者。assistant 抽查 12 行（`continuation-assistant-spotcheck.json`，非独立）与规则/模型总体一致 10/12；分歧是「查看短讯机是必要第一步」与「泛化求助不推进待办」——两条都说明规则标签漏了语义判断。LLM 离线臂（Qwen3-0.6B，逐候选、同 context）50 行中继续 47 次，规则/微型 14 次，human-LLM 总体一致 5/12；LLM 明显更宽松，不能把它当质量上界。

## Reaction 微型工作流（2026-11-25）

- `micro/reaction.ts`：触发事件理解（offer / question / threat / move / other）→ 意图候选（避开、护住、观察、接过、迟疑、回答、回避、让开、注意）→ 复用 judge 三头打分；合理性门要求意图与触发类匹配、task≥0.5、scene≥0.5、不与发起者行动连续重合 8 字。任何一项不过返回 null，LLM 继续写反应。没有训练专用反应头，这一版是"触发理解 + 意图选择 + 评分头 + 规则门"。
- 真实威胁回合（输入「我推倒唐骁。」，seed 2，`evidence-reaction-micro3.json`）：roll `lu|nono|trigger_19` 14/11 准入；reaction 端口给 3 个候选打分（857 ms），选中「诺诺蹲下寻找掩体，同时看他下一步。」，`source=micro`，LLM reaction 调用 0 次。同一输入的上一轮（`evidence-reaction-micro2.json`）微型端口低置信弃权，LLM 写了「诺诺的红色识别带在推倒唐骁时…」，`reaction_invents_character` 命中并回退——这正是微型端口要避免的失败模式。
- 指标口径：reaction 的 3 对 judge 评分计入 `judge` 端口，`reaction` 端口只记任务调用、候选数和选择耗时，避免重复计算编码器运行。
- 输入完善：reaction 的 judge 上下文保留训练时的现场标志，再追加 `触发行动：<发起者行动>` 与 `发起者：<姓名>`。`evidence-reaction-rich.json`（seed 2，同一威胁回合）仍 source=micro、3 候选 764 ms；但 judge 三头原本按 action 候选训练，专用反应头与更多关系字段（世界没有关系表）仍未做。
- 边界：候选是模板句，judge 三头原本为 action 候选训练；真实效果需要更多威胁回合和多 seed A/B，专用反应头仍未训练。

## 移动端代理（2026-11-25）

- CPU 4× + GPU lite、Edge headless，`micro=1`，compound 输入（`evidence-mobile-micro.json`）：回合 284.3 s、`turn_budget`、只到 2 个点、0 个自动点。微型总计 110 次共享编码、382 个头输出、累计端口时间 15.45 s；单端口加载 targets 2.10 s、judge 0.70 s、behavior 0.67 s、results 0.49 s、updates 0.45 s；JS heap 111 MB（不是 GPU VRAM）。微型弃权 4 次（993 ms），模型 fallback 1 次 16.1 s。
- 结论：多个微型模型同时驻留没有崩溃，加载约 4.4 s（串行、各端口独立 runtime）；但这是桌面 CPU 降速 + GPU lite 的代理，不是真机，也没有 VRAM/温度数据；60 s 仍未达到，主要成本仍是 LLM 阶段。下一步真机 + 共享 runtime/共享编码器加载，避免每个端口各自加载 tokenizer/会话。

## updates 剩余成本（四头臂 seed 11）

- 44 次接受 updates 调用的 stage 时间：tasks 3 次 22.3 s、position 14 次 20.1 s、subtasks 3 次 15.1 s、appearance 3 次 7.2 s。位置阶段已被局部小提示和程序场景压过一轮，但仍是调用次数最多的；tasks/subtasks 只有 6 次调用却占 37.4 s，是下一个高耗时目标。
- 这两个阶段是质量敏感的"任务是否达成/是否需要新增子任务"判断，不能直接用现有 results 头替代；需要先补真实正例与反例，再训练专用头并保留 LLM 回退。

## tasks/subtasks 微型工作流（2026-11-25，pilot）

- 条件分解：`micro/task-progress.ts` 把任务目标拆成时间/地点/物品/对象/确认/动作六类条件（`decomposeTask`），并把结果词的 `（达到目的）/（只完成一部分）/（没有成功）` 作为确定性结果门。
- pair 模型：MiniRBT 句对编码 + `relevance` + `satisfaction`（yes/partial/no），数据 `task-match-data.jsonl` 80 对（20 个任务 × 正/部分/否 + 20 条无关事实），作者手写，非规则生成。留出 5 个任务 20 行：relevance 18/20，satisfaction 9/15（yes 3/5、partial 1/5、no 5/5）；全量 73/80 是样本内数字。Qwen3-0.6B 逐对核验 63/80 可解析、其中 40 正确。模型只有 60% 的留出满意度，不能替代 LLM 核验器。
- 接入：`verifyTaskAchievements` 支持 `microTaskVerifier`；低 relevance/低置信一律返回 null，LLM 核验器继续作为权威；不做"用模型直接判定达成"。页面只在 `?taskVerifier=micro` 时创建该端口，`micro=1` 默认仍用 LLM 核验器。
- 真实回合（「我把护目镜戴好，检查镜片有没有裂纹」「我向诺诺问清红蓝局势…」，`taskVerifier=micro`）：tasks 阶段两次都返回空 `achieved`，micro 端口没有输入；问题在**任务阶段不提出达成候选**，不是核验器太慢。护目镜任务仍是 pending。
- subtask 过滤：`readSubtaskProposals` 新增 `subtask_duplicates_existing`，拒绝与父任务或任何现有任务同文的子任务；测试 `settlement.test.ts` 覆盖。开放式子任务生成仍由 LLM 负责。
- 下一步：补独立人工标签与更多任务/事实对；先做"达成候选提出"头（严格高精度），再做子任务必要性/重复性头；在 tasks 阶段能稳定提出候选之前，不把核验器换成微型模型。

## 连续三回合（micro=1，seed 11，`evidence-multi-turn-micro.json`）

- 「我把护目镜递给诺诺。」→「我走进庭院。」→「我观察庭院里唐骁的位置。」三回合全部 COMPLETED、0 失败；回合 88.4 / 118.0 / 122.8 s；点 4 / 8 / 12；微型编码 136 / 153 / 143 次，端口累计 4.96 / 4.47 / 4.26 s；JS heap 146 / 109 / 147 MB。桌面 60 s 仍未达到，三回合都靠 LLM updates 主导。
- **状态不一致（需要定向排查）**：第一回合输入「我把护目镜递给诺诺。」，状态里 `goggles_lu` 仍在 `lu`，没有转给诺诺；同回合正文写「巷里却没有诺诺」，但 `after.nearby=诺诺`、诺诺就在西侧服务巷。相同转移在复合输入「我把护目镜递给诺诺，然后走进庭院。」的微型臂此前成功（护目镜→诺诺）。这说明单动作转移的 target/item 结构或 results 判定存在方差，不是 continuation 的问题；下一轮用固定输入回放 probe 结构、targets、results 与 facts。
- 第二回合路明非到达庭院（yard），第三回合仍能在庭院观察唐骁；位置推进本身一致。三回合的自动链都在 `continuation_policy_no_progress` 结束。

## 单动作转移与叙事一致性修复（2026-11-25）

- 根因链（`evidence-multi-turn-micro.json` → 修复后 `evidence-transfer-single9.json`）：action structure 正确（assist、target=nono、item=goggles_lu、destination=goggles_lu:nono），targets 正确（nono）；results 事实也正确（`去向=goggles_lu:nono`）。失败在 updates：projection 只按事实**文本**扫实体，两个「护目镜」同名歧义导致 `goggles_lu` 不在 `affectedMovable`；`programScenePositions` 又因为「递给」是移动词而该事实没有 **member** 的 `去向` 直接弃权；localPosition 只问路明非，返回 `{"changes":[]}`，物品不动。
- 修复：projection 读取 `去向=`，把物品和容器加入 affected entities；`programScenePositions` 把「事实自己的去向」视为已覆盖；micro results 新增 `programTransferAllowed`（物品在行动者手上 + 目标同房间 + 转移动词 + 无阻止词）直接判 achieved 并写去向，`factContradictsPresence` 阻止「在场人物被说成不在」。
- 叙事一致性：`alignNarration` 新增 `presence_contradiction`（在场人物被写缺席）和 `item_ownership_contradiction`（把别人的物品收进自己口袋）；candidate 路径和 instruct 路径都跑同一检查。instruct 路径首次矛盾时用**已结算事实草稿**重写一次；成功则保留模型正文，失败才回落程序草稿。`factualNarration` 不再输出 `去向=`/`涉及=` 标记，零时长不再写「0秒」。
- 验证：`transfer-single9` 状态 `goggles_lu→nono`、正文「路明非向诺诺递了护目镜…」、source=model、problems=0；`evidence-multi-turn-micro2.json` 三回合护目镜都在诺诺，未再出现「没有诺诺/收进胸袋」。单测：projection 包含去向物品、settlement programScene 应用物品去向、results 转移/在场守卫、alignment 两类矛盾、task 条件覆盖。
- 仍存在：多回合后两回合正文夹带结果台账（「凯撒：查看红方短讯机。（只完成一部分）」）和「从中央庭院走到中央庭院」空移动；「放下护目镜」在状态为诺诺持有时仍有歧义；重写失败的回合会回落程序草稿，驱动报 `program_text_not_model`（`evidence-transfer-single7/8`）。

## 共享资源（2026-11-25）

- `micro/shared.ts` 按 vocab URL 缓存 tokenizer，targets/results/behavior/judge/updates/continuation/task-progress 七个端口共用一次词表加载；ORT 模块本来已是单例。模型会话仍按端口/权重文件各自持有，`loadMs` 仍是各端口自己的统计。
- 未做：共享 runtime 的会话池、批量推理、跨端口编码复用。原因：当前瓶颈仍是 LLM updates/narration，而不是微型端；共享 tokenizer 先去掉确定性的重复加载。移动端多模型驻留的 4.4 s 加载需要下一轮复测。

## 叙事回归：台账泄漏与空移动（2026-11-26）

- `alignNarration` 新增 `ledger_leak`：括号结果词（达到目的/只完成一部分/没有成功/被阻止/没有变化）或「人物：动作」行进入正文即判矛盾；candidate/instruct 两条路径都受同一 FATAL 集约束。
- `alignmentPacket`：同一地点内的槽位变化记为 `at`，不再生成 `moved` 事实；`factualNarration` 同样只在容器真正变化时写「走到」，避免「从中央庭院走到中央庭院」。
- 回归测试：`committed-narration.test.ts` 的台账行；`game-model-alignment.test.ts` 的同地点槽位 vs 真实换地点。全量 1379 passed / 17 skipped，tsc 干净。

## task proposer 三回合达成（2026-11-26，micro9）

- 输入「我拿起护目镜。」→「我把护目镜戴好。」→「我检查镜片有没有裂纹。」，`micro=1&microContinuation=heads&microReaction=1&taskProposer=micro`。三回合 COMPLETED、0 failures；回合等待 123.5 / 107.7 / 121.4 s，首段正文 9.1 / 17.7 / 18.4 s，正文 171 / 170 / 490 字。
- 护目镜任务条件进度 1/3 → 2/3 → 3/3；第 3 回合 proposer 提出 support（item/confirmation/action 全 satisfied），LLM verifier 判 yes；快照 `state.characters.lu.tasks.task_lu_goggles.status=achieved`，页面回合后待办列表已移除该任务。`task_lu_kit` 保持 1/2，`action：进入` 未被「拿起护目镜」满足。
- personality 第 3 回合输出 `<f1>` + 复述事实的文本；实体映射到 lu，复述/命名实体的行被独立拒绝，sanity 走 program；任务达成未被丢弃。第 3 回合 tasks 阶段 2.1 s，personality 6.5 s。
- 微型推理：task-proposer 每回合 1 次调用、18/11/7 次编码与头输出、0.72/0.07/0.05 s；整回合微型编码 153/142/142、头输出 520/496/509、3.7–11.1 s。剩余时间仍由 LLM 结算/叙事主导。
- 下一步：台账写入本地存档（刷新/切换/回滚、失效条件）、共享 runtime/批推理/会话回收、后续子任务提案。

## task 台账刷新恢复（2026-11-26，refresh1）

- 输入同上三回合，但第 2 回合 `refreshAfter=true`：页面 reload 后 `restored=true`、history 2→2、同地点同理智。第 3 回合 proposer 仍拿到前两回合的 item/action 条件，最终 3/3、verifier yes、快照 `task_lu_goggles=achieved`。
- 台账随 `LocalGameSnapshot.taskLedger` 保存/恢复，`seenFacts` 去重；物品条件按当前持有链失效/恢复，其余条件保持历史成立。单测覆盖导出/导入、重复事实、物品失效/恢复与会话快照回传。
- 成本：第 3 回合 accepted 139.5 s，触发 `accepted_over_60s`；tasks 阶段在最终 support 前有重复调用，刷新本身 34.2 s。下一轮优先共享 runtime/批推理/重试收敛。

## 共享会话与批推理（2026-11-26，batch1）

- ORT session 按 URL 全页共享（refcount），task proposer 条件行 padding 后一次推理。`evidence-task-accum-batch1.json` COMPLETED、0 failures；护目镜仍 1/3→2/3→3/3 并 `achieved`。
- proposer：17 行 344 ms（micro9 18 行 721 ms，−52%）；8 行 90 ms、11 行 66 ms，比旧 72/47 ms 慢——小批 padding 成本超过省下的 session.run 开销，下一版按行数阈值切换。
- 回合等待 84.2 / 90.0 / 124.9 s，JS heap 149 / 137 / 128 MB。共享 cache 没有重复 session 可省，heap 基本不变；内存主项仍是 narration/semantic GGUF。自动空闲驱逐/端口 release 未做。

## 整回合性能：动作模板回退与资源（2026-11-26）

- 时间轴（9 回合）：均值 107.6 s；action 24.1 s（97 次语义、41 次重试 70.5 s）、position 14.9 s、tasks+subtasks 22.0 s、正文尾 26.5 s；无完全重复 prompt、无重复 session。
- 动作修复：任务目标照抄首次被拒后用已校验模板候选，不再两次 repair。action1 等待 69.2/85.3/100.8 s，action LLM 8/8/8（旧 16/16/19）、attempt 6/6/7（旧 11/10/12）；perf1 68.0/88.2/119.2 s，护目镜仍 `achieved`。
- 资源：叙事 ctx 4096→2048；不再保留 GGUF Blob（最多省 1.4 GiB Blob 配额）；tab 隐藏且无回合时释放 worker，可见预热。verifier 同 prompt memo 在这三回合 0 命中。60 s 仍未达到；下一步正文双跑、position 批处理、专用子任务/反应头、独立场景与移动端。
