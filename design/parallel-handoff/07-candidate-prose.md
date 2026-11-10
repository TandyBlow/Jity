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
  policy: { scene },      // 04 的整段骨架，优先于 committed
});
out.text; out.accepted; out.rawAttempts; out.issues;
out.timings; out.strategyVersion;
```

返回里额外带 `attemptIndex`、`status`、`display`、`composed`、`sparse`，
02 的循环不需要读它们也能工作。没有 `policy.scene` 时，会用 02 的事实包
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

`frontend/scripts/candidate-prose/compose-samples.ts` 从公开世界
`data/worlds/dragon-raja-free-day.world.json` 读真实人名、地点、物品，
跑整段口和逐 beat 口。当前输出（原文，未润色）：

```text
过了四分钟，路明非还在西侧服务巷。

路明非从西侧服务巷走到器材棚。

相机备用电池被带到了器材棚。器材棚里，推拉门可回服务巷，领用台在门内右侧。

路明非身上，护目镜的带子在手腕上绕了一圈。

路明非完成了「把护目镜戴好并确认镜片没有裂纹」。

路明非把话咽了回去，喉咙发紧。

芬格尔的呼吸紧了一下。

芬格尔还在器材棚，头发乱着，手指在机身上敲了两下。

路明非没有马上再动，芬格尔也没有动。
```

同一份素材在 04 的 `generateCandidate` 里（`policy.composer = createBeatComposer()`）
得到 `accepted: true`、`composers` 全是 `program:prose-composer`、`issues: []`，
每个 beat 都通过 04 的 `verifyBeatText`。复现：

```bash
cd frontend
./node_modules/.bin/jiti ./scripts/candidate-prose/compose-samples.ts
LANE04_ROOT=../04-settlement ./node_modules/.bin/jiti ./scripts/candidate-prose/run-04-beats.ts
LANE04_ROOT=../04-settlement ./node_modules/.bin/jiti ./scripts/candidate-prose/sweep-free-day.ts
./node_modules/.bin/vitest run src/lib/world-engine/local/narration-candidates/prose-composer/ --maxWorkers=1
./node_modules/.bin/tsc -p tsconfig.world-contract.json --noEmit
```

`sweep-free-day.ts` 在公开世界的 14 个真实点位上各跑一遍 04 全流程
（移动到器材棚、两人同时移动、任务完成+精神下降、外貌+个性、物品转移、
新增待办、纯时间流逝、中央庭院移动、两人反向移动、精神回升、物品外貌变化、
任务+待办+个性+精神同点、只过一秒、带上一轮正文的续写）。当前 14/14 都是
`accepted`，每个 beat 都来自本 composer，没有回退到 04 自己的 realizer。
其中两段：

```text
过了一分钟，路明非还在西侧服务巷。

西侧服务巷里，巷口的黄黑绳已放下，进入即算踏入演习区。

诺诺从西侧服务巷走到红方集结点，芬格尔从器材棚走进西侧服务巷。

身边还有芬格尔，头盔歪扣着，食指蹭了油；旧相机挂在脖子上，左臂没有阵营布带。

路明非没有马上再动，芬格尔也没有动。
```

```text
过了一分钟，路明非还在西侧服务巷。

赛区路线图还在西侧服务巷，图上画出庭院、东西回廊、跨溪小桥、钟楼与白线撤离路；地下检修通道用虚线标注，未标门闩状态。
```

这两段暴露过的两个坑已经修掉，代码里保留了注释：

1. 场景纹理不能写“某人也在地点”，否则 04 的旧对齐门槛会把它读成
   对主角位置事实的冒名（actor swap）。改用“身边还有某人，……”。
2. 物品说明只有在整段（含物品名）都被 04 的 license 覆盖时才能用。
   路线图这类会列出别的房间的说明，要么连名带注一起许可，要么不用；
   不能用半段无主语的“图上画出……”。

浏览器入口检查（不加载模型、不占推理锁）：

```bash
cd <09 worktree>/frontend
node scripts/quality-candidates/run-browser-candidates.mjs \
  --candidate 07-prose=<本工作树>/frontend/src/lib/world-engine/local/narration-candidates/prose-composer/index.ts \
  --inspect --out <本工作树>/inspect-07.json
# [inspect] 07-prose: export=generateCandidate ... documented=true
```

这证明共享页面运行器能在真实 Edge 里导入本模块并认出文档化的
`generateCandidate` 导出；真正逐点出正文仍要走 04 注入 composer 的那条路径。

整段口接 04 的 facts + 真实 state 的一段（器材棚，移动 + 任务 + 个性 + 精神），
实际输出 285 字，`sparse=false`、`issues=[]`：

```text
推拉门可回服务巷。

过了五分钟。

路明非从西侧服务巷走进器材棚。

「把胸前护目镜戴好并确认镜片没有裂纹」这件事，路明非收了尾。

路明非不再把选择推给别人。

身边还有芬格尔，头盔歪扣着，食指蹭了油。

近处还有秦越，灰色器材背心套在校服外，胸前挂着领用牌。

开盖演习弹药箱还在器材棚。箱内两只已装填的通用短枪弹匣各有8发弗里嘉演习弹；黄色封套上写明不得与实弹混用。

路明非看了一眼开盖演习弹药箱。

器材领用台还在器材棚。台上夹着领用簿，笔尖尚湿；台下留有放备用护具的位置。

器材笼挂锁还在原来的地方。挂锁扣住笼门插销，锁眼朝外，锁梁完整；器材笼钥匙能开。
```

复现：`LANE04_ROOT=../04-settlement ./node_modules/.bin/jiti ./scripts/candidate-prose/sample-committed-state.ts`

耗时：整段 0.7–5.3 ms，单 beat 0.15–1.1 ms（含进程内首次 JIT 抖动）。
按 `QUALITY-TEAMS.md` 的口径，首段和整段都远在 60 s / 300 s 以内，
且不依赖模型、WebGPU 或网络。

## 已知限制（等 09/04 真实回传再改）

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

1. 用 09 在真实页面上跑出的正文，逐段对比“哪里像流水账、哪里缺衔接”，
   在同一 beat 契约内改模板；不改 04 的映射和校验。
2. 按角色给 sanity/personality 句式加去重盐，消除同回合重复体感。
3. 若 04 提供 `action` / `line` fact（例如玩家动作的已结算结果），把
   `from-beat.ts` 的映射扩到这些 kind，并保持同一 guard。
4. 04 的 `beat.minChars/maxChars` 目前未用于裁剪；若 04 开始按 beat 卡长度，
   再在 `composeConstrainedBeat` 里加“超长先丢可选细节”的收束。
