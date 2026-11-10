# 07-candidate-prose handoff：把事实骨架写成正文

分支 `goal/local-07-sync`，工作树
`D:/others/Jity/.local/parallel-local-game/worktrees/07-sync`。
只新增 `narration-candidates/prose-composer/**`、`scripts/candidate-prose/**`
和本文件；04 的工作树、主页面、共享路由和依赖未改。

## 这是什么

04 已经能把一个已结算点位投影成只读事实骨架（地点、在场人物、物品、本回合
变化、许可细节），但骨架本身不是正文。本模块只负责语言：把骨架里的
move / task / personality / sanity / item / line / time 等事实，按可读顺序写成
段落，并保证：

- 每个必须表达的事实都出现在正文里（移动有方向、任务有结果、物品有位置）；
- 不新增输入里没有的人、地点、物品、天气、往事、线索、承诺；
- 不复制训练范文的句子；
- 相邻回合不重复上一轮的句子和段落开头。

它不读世界状态、不写世界状态、不调用模型，因此耗时是毫秒级，不需要
WebGPU，也不存在首 token 等待。

## 两个调用口

### 1. 04 的逐 beat 口（推荐）

04 的 `policy.composer` 直接收下这个函数，不需要跨线 import 类型：

```ts
import { createBeatComposer } from
  '.../narration-candidates/prose-composer/index';

const result = await generateCandidate({
  engine, committed, priorText,
  policy: {
    mode: 'program',
    composer: createBeatComposer(),
    requireTime: true,
    sanityStyle: 'direction',   // 本 composer 写体感，不写数字
    minChars: 60,
    maxChars: 800,
  },
});
```

`createBeatComposer()` 返回 `(request, options) => Promise<{text, source:'program', attempts:1, ms}>`，
正好是 04 `BeatComposer` 的结构。`options.signal` 已取消时抛 `AbortError`；
程序一次成文，**不会调用 `onProgress`**（把完成稿伪装成流式是谎报）。
04 现在的实现按 `source === 'model' | 'external'` 才发中间进度，
`source:'program'` 只发最后一条 accepted 状态，两边一致。

单 beat 也可以直接同步调用，便于测试和证据记录：

```ts
import { composeConstrainedBeat } from
  '.../narration-candidates/prose-composer/index';

const { text } = composeConstrainedBeat({ beat, scene, prior });
```

### 2. 02 / 06 的整段口

`generateCandidate(args)` 与 02 的 `generateCommittedNarration` 同形：

```ts
const out = generateCandidate({
  engine,                 // 收下但不使用
  committed,             // 02/运行器的 {anchor, facts}（可带 state/timeAdvance）
  state, beforeState,    // 可选：共享运行器已经传的已结算读；只作场景材料
  delta,                 // 可选：{timeAdvance}，作为时间事实
  priorText,
  policy: { scene },      // ProseScene 或运行器的 SceneGrounding，优先于 committed
});
out.text; out.accepted; out.rawAttempts; out.issues;
out.timings; out.strategyVersion;
```

返回里额外带 `attemptIndex`、`status`、`display`、`composed`、`sparse`，
02 的循环不需要读它们也能工作。`policy.scene` 可以是本 composer 的
`ProseScene`，也可以是共享运行器的 `SceneGrounding`（`location` 字符串、
`placeNotes`、`present`、`objects`）；后者会用 `committed.facts` 补事实、
用 grounding 补场景。没有 `policy.scene` 也没有 state 时，会用 02 的事实包
拼一个 `sparse: true` 的骨架（地点外观、对白、物品细节不可得），并在
`issues` 里明说，不假装信息完整。

如果调用方还能给出本轮已结算的 `state`（共享浏览器运行器就是这样：
`{engine, committed, state, before, delta, inputText, priorText, policy,
signal, onProgress}`），整段口会**只把 state 当场景材料**用：

- 地点名、地点外观、父地点；
- 在场人物的名字和已结算外貌；
- 房间里的物品和它们的外观；
- `delta.timeAdvance` 或 `committed.timeAdvance` 作为时间事实。

事实仍然只来自 `committed.facts`，不会从 state 里另行推断。这样页面不需要
04 的逐 beat 计划也能得到带场景的正文；`sparse` 会变成 `false`。逐 beat 口
（04 的 `policy.composer`）不走这条路径，它直接用 04 的 `SceneSkeleton`。

## beat 的字段约定

| 字段 | 作用 |
|---|---|
| `kind` | `move` / `task` / `subtask` / `personality` / `appearance` / `item` / `line` / `action` / `stay` / `leave` / `arrive` / `scene` / `time` / `silence` / `noChange` / `sanity` |
| `factText` | 可选。04 已经写好的忠实句子，原样采用（仍过 guard） |
| `move.entityKind` | `'item'` 时按物品写，不要求它在 cast 里 |
| `item.container` / `note` / `discovered` | 物品所在位置和许可细节 |
| `appearance.subjectName` / `entityKind` / `removed` | 外貌变化，人物/物品/地点共用 |
| `task.label` | 目标原文。正文写成“「目标」，某人做完了。”，不造句式变形 |
| `subtask.goal` | 新增待办，不写成完成 |
| `scene.detail` | 许可的场景细节，作为段落锚点 |
| `priorText` | 上一轮正文，只用于避重，不用来补事实 |

04 的 `SceneFact` 由 `from-beat.ts` 映射成这些 beat，映射规则写在文件顶部。
未来 04 加新 fact kind 时，未识别 kind 会得到空文本，由 04 回退到它自己的
`realizeBeat`，不会静默编造。

## 语言规则（可检查的部分）

- **指代**：第一次出现用全名；之后只有“同性别在场角色唯一”时才用他/她，
  否则重复姓名。不知道性别就重复姓名，绝不猜。
- **方向**：移动句永远是“从 A 到 B”，`verifyBeats` 会检查 B 不在 A 前面。
- **物品移动**：如果起点是某个角色（电池在芬格尔口袋里），正文只写
  “被带到了 B”，不把角色名字放进同一分句——否则 04 的旧对齐门槛会把这段
  判成那个人在移动。
- **场景锚点**：每轮最多一段，优先“本回合变化的细节”，其次地点外观，
  再其次人物外观；上一轮用过的细节会跳过。锚点截到 44 字内的完整分句，
  不会把整段景物倒进正文。
- **对白**：说话人变化才加提示语；问句用“问”，答句可先写一句停顿
  （“没有立刻答。”）；长对白在句号处拆成两段引号。
- **节奏**：默认整段不少于 60 字；纯 `noChange`/`time` 的静场下限降到 16 字，
  免得为了凑字数编动作。段落超过 120 字按句拆到约 70 字。
- **收束**：别人离开后只剩一人时写一句“某地只剩某人一个人”；有未变的
  可见物品时写“某物还在原来的地方”。这两句都由事实推出，且上一轮说过
  就不再重复。

## 防护

`guard.ts` 在成段前逐句检查：未许可的道具/天气词（椅子、盒子、门、雨…）、
往事标记（当年、记得、上次…）、承诺标记（答应、明天、下次…）、固定惊讶
动作（愣住、不由得、叹了口气…）。命中即整句丢弃并记 `hard` issue；
与上一轮 bigram 重叠超过 0.72 的句子也记 `hard`，不会被当成新回合。

## 实跑结果

### 09 共享页面（真实驱动，3/3 accepted）

运行器把 `committed` 事实包、`state`、`before`、`delta` 和一份
`SceneGrounding`（`location` / `placeNotes` / `present` / `objects` /
`inventory`）一起交给候选。整段口直接吃这份输入，三次都 accepted，
`issues=[]`，页面回传的正文如下（原文）：

```text
巷口的黄黑绳已放下，进入即算踏入演习区。

身边还有诺诺，红发用发圈束在脑后，红色识别带缠在左臂。

演习规则牌还在西侧服务巷。牌面写明：使用弗里嘉演习弹。

赛区路线图还在西侧服务巷。图上画出庭院、东西回廊、跨溪小桥、钟楼与白线撤离路。

路明非把目光落到赛区路线图上。
```

```text
廊柱连接器材区与钟楼西门，腰高石栏可作掩体。

一分钟过去，路明非从西侧服务巷走到西回廊。

诺诺从西侧服务巷来到西回廊。

身边还有林亦舟，蓝色识别带沾着灰，左脚踝在鞋帮上方肿起。

林亦舟放下的演习枪还在原来的地方。枪躺在第三根廊柱旁，保险合上，弹匣内剩4发；与坐着的林亦舟相隔一臂，已离开他的手。
```

```text
过了三分钟，「向诺诺问清当前红蓝两方局势和自己是否可以保持中立」，路明非做完了。

路明非不再等别人替他决定，愿意先迈出一步。

身边还有诺诺，红发用发圈束在脑后，红色识别带缠在左臂。
```

136 / 151 / 92 字，页面内 4–11 ms。证据：
`artifacts/prose-composer/browser-07.json`。

共享短场景 `--set short` 也 3/3 accepted（49 / 37 / 34 字）：
`artifacts/prose-composer/browser-07-short.json`。短场景材料少，整段口在
grounding 输入下的地板是 30 字，而不是 60 字；否则两个合法短场景会被
`too_short` 误杀。

这次用的是 **program-only 装载器**（`scripts/candidate-prose/stub-engine-loader.ts`），
因为本 composer 从不调用模型；共享运行器仍要求一个 engine 槽，所以用 stub
满足它，证据里 `backend` 明确写着 `program-only stub (no model)`，不冒充模型运行。
第一次用真实模型租约时 06 正在跑，本线没有抢锁。

复现：

```bash
cd <09 worktree>/frontend && node scripts/quality-candidates/run-browser-candidates.mjs   --lane 07-prose --candidate 07-prose=<07 worktree>/frontend/src/lib/world-engine/local/narration-candidates/prose-composer/index.ts   --candidate-loader "07-prose=<07 worktree>/frontend/scripts/candidate-prose/stub-engine-loader.ts::loadCandidateModel"   --candidate-model-id 07-prose=none --set free-day --max-runs 3 --no-lease   --model /models/stub.gguf --model-dir <dir with stub.gguf>   --out <07 worktree>/artifacts/prose-composer/browser-07.json
```

### 复跑（2026-11-10，04 `f97c90bc` + 任务句地点锚点）

04 的事实包改成 `{anchor, facts}` 之后，01 的检查器也收紧了：只有任务+时间的
回合，句子被剥掉人名和 goal 后只剩“三分钟过去/做完了”，重新被判
`style.status_panel`。改法是：整段口里每一条任务句都先用一句未读过的地点细节
开头（同一条叙述里已经当过纹理的细节不重复用）；04 的逐 beat 口保持“主语在
最前”的契约，不受影响。

同输入复跑：

- `review-01-gate.ts`：10 回合 **0/10 regenerate**，任务回合
  （turn 2）从 `hold_for_review` 变成 `accept_as_model_prose`，0 条事实发现；
- `chain-10.ts`（20 回合）：20/20 accepted，逐字重复 0，20 个收尾互不相同；
- `sweep-free-day.ts`：14/14，全部 beat 由本 composer 产出；
- 09 共享页面 `--set free-day` 3/3、`--set short` 3/3 accepted，
  `browser-07-after.json` / `browser-07-after-short.json` 已按本轮重跑
  （program-only stub，证据里仍是 `no model`）。

free-day-task 现在是 80 字：

```text
三分钟过去，第三根廊柱脚下有一条折断的蓝布带，「向诺诺问清当前红蓝两方局势和自己是否可以保持中立」，路明非做完了。

路明非不再等别人替他决定，愿意先迈出一步。
```

### 04 逐 beat 全流程（14/14 accepted）

`scripts/candidate-prose/sweep-free-day.ts` 用 04 的真实内核和
`projectConstrainedScene` 跑公开世界 14 个点位，每个 beat 都由本 composer
产出，没有回退到 04 的 `realizeBeat`。覆盖：走到器材棚、两人移动一人留下、
任务达成并掉精神、外貌与个性变化、电池被带出、新增小任务、纯时间、校园移动
带两名目击者、两人反向移动、精神恢复、物品外貌变化、四事实复合、一秒过去、
简报后的续写。

### 整段口 + 真实 state（283 字）

用 04 的事实包加本轮已结算的 state 调本 composer 的整段口（不是 04 的
beat realizer），得到 283 字、`sparse=false`、`issues=[]`：

```text
推拉门可回服务巷。

过了五分钟，路明非从西侧服务巷走进器材棚。

「把胸前护目镜戴好并确认镜片没有裂纹」这件事，路明非收了尾。

路明非不再把选择推给别人。

身边还有芬格尔，头盔歪扣着，食指蹭了油。

近处还有秦越，灰色器材背心套在校服外，胸前挂着领用牌。

开盖演习弹药箱还在器材棚。箱内两只已装填的通用短枪弹匣各有8发弗里嘉演习弹；黄色封套上写明不得与实弹混用。

器材领用台还在器材棚。台上夹着领用簿，笔尖尚湿；台下留有放备用护具的位置。

器材笼挂锁还在原来的地方。挂锁扣住笼门插销，锁眼朝外，锁梁完整；器材笼钥匙能开。
```

复现：`LANE04_ROOT=../04-settlement ./node_modules/.bin/jiti ./scripts/candidate-prose/sample-committed-state.ts`

耗时：整段 0.2–7.8 ms，单 beat 0.15–1.1 ms（含进程内首次 JIT 抖动）。
按 `QUALITY-TEAMS.md` 的口径，首段和整段都远在 60 s / 300 s 以内，
且不依赖模型、WebGPU 或网络。

## 已知限制

1. 只写事实骨架里有的东西。输入只有“移动 + 任务”时，正文就是短、直白，
   不会自己长出对白或环境戏；那是 04 的 `licensed.details` / action / line
   beat 该补的素材。
2. 整段口会对连续以同一人名开头的段落做代词替换（同性别在场角色唯一时才换）；
   04 的逐 beat 口看不到别的 beat，所以跨 beat 的重复人名只能靠 04 在拼装时
   处理，或给 `ScenePerson` 补性别后由 04 合并。
3. 同一回合两个角色都掉精神值时，可能选中同一句体感（“把手指收紧了”）。
   已按角色 id 混入变体盐，但更长回合仍可能重复句式。
4. `sanityStyle: 'number'` 不支持：本 composer 写体感。若页面仍要旧
   `alignNarration` 的数字口径，请在 04 侧把 sanity fact 从 packet 里去掉，
   或继续用 04 自带的数字 realizer。
5. 02 事实包直连时是 `sparse` 骨架：没有地点外观、对白和物品细节，
   只保证移动/任务/个性/精神状态方向不走样。
6. 段落合并是启发式（短句、代词/地点开头才并段）。遇到特别长的许可细节，
   仍可能出现一段景物描写偏密。
7. 没有做风格评分器，也没有对训练范文做句子级检索；只吸收节奏和结构。
8. 一个点位里出现两个以上“同一事实类别”的纹理（两件物品、两个在场人物）
   时，只按 04 的 beat 预算展开；不会主动挑最有戏的一件。

## 下一步（按优先级）

1. 09 的共享页面已经 3/3 accepted；下一步是把这三个场景之外的 free-day
   点位也跑一遍，逐段看“哪里像流水账、哪里缺衔接”，在同一 beat 契约内改
   模板；不改 04 的映射和校验。
2. 按角色给 sanity/personality 句式加去重盐，消除同回合重复体感。
3. 若 04 提供 `action` / `line` fact（例如玩家动作的已结算结果），把
   `from-beat.ts` 的映射扩到这些 kind，并保持同一 guard。
4. 04 的 `beat.minChars/maxChars` 目前未用于裁剪；若 04 开始按 beat 卡长度，
   再在 `composeConstrainedBeat` 里加“超长先丢可选细节”的收束。

## 路线定位（2026-11-10 充值恢复后）

按 `RESTART-AFTER-REVIEW.md` 的 07 条：**prose-composer 是备选/标注降级，不是默认
叙事路线，也不占本地 GPU 队列。** 它的用途有两个：

1. 真实模型回合失败时，页面能标着“程序按已结算事实成文”给出可读的一段；
2. 作为逐拍语言层插进 04 的 `policy.composer`，让 04 的受约束路线有一条不调模型的对照。

它不参与默认候选竞争，不申请 09 的推理租约，也不另起一套主叙事生成器；模型正文的
质量结论仍由 02 生成、01 独立复核。

## 适用范围、来源与限制（交 02 / 04 / 06）

**这是程序成文备选，不是模型正文。** 每一句都由已结算事实加已授权场景材料
确定性地写出，不调用任何模型；页面用 stub loader 跑出的文字只能当程序路径
证据，不能算目标文风模型正文通过，也不能算产品质量通过。

- 适用：04 的逐 beat 口（`createBeatComposer`）与 02/06 的整段口
  （`generateCandidate`）；输入必须是已结算事实（`committed.facts` 或 04 的
  `SceneFact`）+ 已结算状态里的场景材料（地点/在场人物/外貌/房间物品）。
- 不适用：需要模型自由写作的桥段、04 未授权的动作/对白、任何“补一段往事/
  线索/悬念”的要求。缺素材时它写短，不补造。
- 事实边界：只写 packet 里的事实；场景纹理只来自 state/grounding 的已结算
  文本；没有人物外貌、物品细节、对白来源时就不写这些。
- 与 02 的关系：02 的分拍校验/修复仍是主线；本模块可作为“程序拍”或回退
  文案来源，但**不得**把它的输出标成模型生成，也不得用它替换模型拍后宣称
  质量提升。
- 与 04 的关系：04 保留受事实约束的分段叙事；本模块只提供语言层。04 的
  `verifyBeatText` 仍逐拍校验，不合格时按 04 的规则修复/回退。

### 用 01 的独立审查器复核（2026-11-10）

`frontend/scripts/candidate-prose/review-01-gate.ts` 把二十回合链（与
`chain-10.ts` 共用 `chain-turns.ts` 的同一份历史）的每个点转成 01 的 dataset 行
（视角/上回合状态/本回合变化/本回合状态），用 01 的 `reviewNarration` +
`gateNarration` 读本模块自己的输出。结果：

- 20/20 由本模块 accepted；01 的审查器 **0 条事实发现**（没有编造动作/声音/物品/往事，
  没有漏移动/时间/任务/个性/精神，没有方向反转）；
- 20 回合 **0/20 regenerate**；多数回合的门槛判定是 `hold_for_review` 而不是 `regenerate`：程序正文会复述已结算事实，01 的
  `fallbackSuspicion` 会因此要求人工确认来源，这是对的——它本来就不该被当模型正文；
- “只有个性变化”和“只有任务达成”两类回合都会被判 `style.status_panel`。第一次只加
  地点名不够：01 会把地点名一起当名字剥掉；改成“时间 + 一句有主谓的地点细节 +
  个性/任务句”同一句后，0/10 regenerate。试过按每个逗号切地点细节，会切出
  “但要同时暴露给两边的窗口”这种残句，已回退成只取每句地点描写的第一个分句；
  同一段叙述里已经当过纹理的细节也会被排除，避免一句话印两遍。

这是自动检查，不是人工复核，也不是产品质量通过。

### 按 02 的真实页面兜底复核（同输入，2026-11-11）

02 在 `results/quality/page-narration-review-02.md` 里复核了 09 真实页面的一次
程序兜底（输入「我沿着服务巷往里走，先看清墙上的演习规则牌。」），找出三个问题：
正文里混进结算状态句、108 字拆成 5 段每段一句、最后一句「在原地站了一会儿」没有
事实依据。原始回合和页面正文在
`results/product/evidence/09-product-10turn.json`。

`frontend/scripts/candidate-prose/fallback-same-input.ts` 把这一回合重放成本模块的
输入（同一世界、同一地点、同一可见状态、正文里写的一分钟），用 01 的审查器读两份
文本：

| | 02 记录的页面兜底 | 本模块同一回合 |
|---|---|---|
| 正文 | 5 段，108 字，含「路明非：本组结算未能确认新的结果。」和「路明非在原地站了一会儿。」 | 1 段，92 字，只有地点纹理、时间、在场者、未变物品 |
| 01 门槛 | `regenerate`，1 条硬发现 `style.meta` | `hold_for_review`，0 条硬发现 |
| 无依据内容 | 状态句 + 无依据动作 | 0（脚本按“结算/未能确认/：/站在原地”检查，均未出现） |

重放同时暴露了本模块自己的两个无依据句子：人物离开后写「X 的脚步声往 Y 那边去了」、
人物进场时写「X 里没有别的声音」。两处都已删除；`leave-alone` 的第三个变体也从
“脚步声听不见了”换成事实内的“走出了 X”。

顺带按同一份语料把短回合改成**单段**：整段口在 158 字以内且不含对白时，把各拍
合成一段（人话语料 71 条全部单段、61–158 字、中位数 97）。超过 158 字或含对白的
回合仍分段。

这是程序成文、没有模型，也不是产品验收；它只回答“同一个已结算回合，换成本模块
会写出什么，01 怎么判”。

同一份记录里的第 2 回合在“继续判断”阶段超时、页面只显示「…」。对这种情况，
本模块的契约是：续写回合（有上文）但本轮没有任何已结算事实、也没有时间推进时，
返回空文本 + `empty_scene`，由页面显示可恢复的重试，而不是拿未变的场景描写作正文。
开场回合（没有上文）和只走了时间的回合不受影响。

### 本轮按 02/01 实际失败类型做的修改（同输入前后对照）

问题取自 02 的真实失败记录（编造事件、漏已结算移动、超时后只剩退回短句、
时间句复读）和产品对“跨回合同结尾/状态列表腔/无意义填充”的要求。

| 失败类型 | 修改前（同一输入） | 修改后 |
|---|---|---|
| 跨回合同一结尾 | 04 的 close 拍每回合都是“X没有马上再动，Y也没有动。” | 5 种同为无事件的收束，按拍种子选，且剔除上一回合已出现过的那句 |
| 状态列表腔 | 开场后连续“身边还有诺诺，…”+“演习规则牌还在…”+“赛区路线图还在…”+“路明非把目光落到…” | 在场人物合成一句；一回合最多一个未变物品；续写回合不再重列在场者；删掉“看一眼物品”填充 |
| 无意义填充 | `还在原来的地方` 追加行、`看了一眼X` | 两者都删除；短回合宁短不凑 |
| 同一句被印两遍 | 截断后的场景锚点与原文各出现一次 | 锚点按截断子句匹配源 beat，只出现一次 |
| 续写回合重开场景 | 每回合都用地点说明开头 | 续写时地点句若与上一回合重合，就改用事实拍开头 |
| 无依据的声音 | 人物离开后补一句“X 的脚步声往 Y 那边去了”；进场写“没有别的声音”（02 的真实页面兜底失败类型） | 两句都删除；离开/进场只用移动事实本身，`leave-alone` 改用“走出了 X” |
| 每句一段的模板形状 | 108 字拆 5 段、每段一句（02 指出人话语料是单段 61–158 字） | 07 的整场入口在 158 字以内且无对白时合成一段；**页面兜底走 06 的 constrained 候选：场景/动作/收尾句由 07 的拍接口写（`result` 拍除外），拼装用 `joinText` 逐拍空行拼接（`constrained/index.ts:476`），拼装层不在 07 的成文模块里；形状部分已给提案补丁 `07-fallback-shape.patch`（06 cf3d027e 上五个补丁一起 tsc 0、646 passed）**；长回合或含对白仍分段 |
| 任务句像状态栏 | “过了三分钟，「goal」，X 做完了。” 只报告已结算字段 | 整段口先在任务句前放一句未读过的地点细节；逐 beat 口保持主语最前 |

同一三个 free-day 输入、同一顺序（open → move → task，后者以前者正文为
`priorText`）经 09 的共享运行器实跑：

```text
free-day-open（78 字）
巷口的黄黑绳已放下，进入即算踏入演习区。
不远处是诺诺，红发用发圈束在脑后，红色识别带缠在左臂。
演习规则牌还在西侧服务巷。牌面写明：使用弗里嘉演习弹。

free-day-move（91 字）
廊柱连接器材区与钟楼西门，腰高石栏可作掩体。
一分钟过去，路明非从西侧服务巷走到西回廊。
诺诺从西侧服务巷来到西回廊。
不远处是林亦舟，蓝色识别带沾着灰，左脚踝在鞋帮上方肿起。

free-day-task（63 字）
过了三分钟，「向诺诺问清当前红蓝两方局势和自己是否可以保持中立」，路明非做完了。
路明非不再等别人替他决定，愿意先迈出一步。
```

三条都 `accepted=true`、`issues=[]`，
页面内 2–11 ms。短场景 `--set short` 三条 38/37/31 字同样 accepted。

证据：`artifacts/prose-composer/browser-07-after.json`、
`artifacts/prose-composer/browser-07-after-short.json`。修改前同输入：
`artifacts/prose-composer/browser-07.json`（含被删掉的列表腔与重复锚点）。

仍未解决：以上只有 3+3 个共享输入，不等于十/二十回合连续游玩；本模块没有
在真实 `/world-local` 页面上由 06 接线运行；没有模型参与，因此不能说明模型
正文质量。真正的连续游玩与质量结论由 06/09/01 按各自职责给出。

### 二十回合连续检查（同一世界、同一条状态链）

三个独立样本看不出跨回合复读，所以补了一条长链：
`frontend/scripts/candidate-prose/chain-10.ts`（名字保留，实际已是 20 回合）用
04 的内核依次结算二十个点——移动、任务达成、同伴跟进、个性+精神变化、原地
过时间、到庭院、第三个人进场、外貌变化、精神回升、回服务巷、物品移动、两人
同时进场、一句对白、子任务完成、精神下降、两次纯时间回合、物品被带走、同伴
离开、相对位置变化、再移动。每回合把上一回合正文作为 `priorText`、把更早的
正文作为 `policy.avoidText` 传进来。

修改前（只有 `priorText`，没有静态纹理去重）：

- 同一句地点/物品说明复读 5 次，其中一句收尾重复 2 次；
- 数量很少的回合出现“过了一分钟 + 同一件物品”的固定搭配；
- 物品被带走、同伴离开这两类已结算事实**被整段丢掉**（被当成不在场的角色移动，
  校验直接报 `unknown_reference`，句子没有生成）；
- 纯时间回合只有 6 个字，被长度下限判成失败。

修改后（提交 `4e7e9a79`）：

- **20/20 accepted**，逐字重复句 0，20 个收尾互不相同；
- 物品移动、同伴离开都用事实里的名字讲出来，不用代词；
- 纯时间回合就是一句时间，加一条 `time_only` 软标记，不靠编动作凑长度；
- 只有时钟走的回合，用读者还没见过的一件在场物品，而不是重复上一件；
- 物品细节不会再同时作为开场锚点和物品句出现一次。

这里的关键接线要求：**06 需要把本局的正文记录作为 `policy.avoidText` 传进来**
（只传 `priorText` 只能防上一回合）。没有它，模块只能保证不重复上一回合。

仍未覆盖的：相对位置变化（`positionChanges`，例如“后退半步”）在 04 投影出的
committed 事实里没有对应记录，本模块因此只能输出时间；这不是成文层能修的，
需要 04 在事实包里补这一项。十/二十回合的真实页面运行仍归 09。

需要说明：长链是开发检查，不是产品验收；它用的是程序正文、没有模型，也没有经
过真实页面，因此不能替代 09 的十/二十回合真实运行，也不能作为质量通过。
