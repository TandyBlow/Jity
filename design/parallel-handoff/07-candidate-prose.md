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

这次用的是 **program-only 装载器**（`scripts/candidate-prose/stub-engine-loader.ts`），
因为本 composer 从不调用模型；共享运行器仍要求一个 engine 槽，所以用 stub
满足它，证据里 `backend` 明确写着 `program-only stub (no model)`，不冒充模型运行。
第一次用真实模型租约时 06 正在跑，本线没有抢锁。

复现：

```bash
cd <09 worktree>/frontend && node scripts/quality-candidates/run-browser-candidates.mjs   --lane 07-prose --candidate 07-prose=<07 worktree>/frontend/src/lib/world-engine/local/narration-candidates/prose-composer/index.ts   --candidate-loader "07-prose=<07 worktree>/frontend/scripts/candidate-prose/stub-engine-loader.ts::loadCandidateModel"   --candidate-model-id 07-prose=none --set free-day --max-runs 3 --no-lease   --model /models/stub.gguf --model-dir <dir with stub.gguf>   --out <07 worktree>/artifacts/prose-composer/browser-07.json
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
