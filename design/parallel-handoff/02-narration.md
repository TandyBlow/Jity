# 02-narration 交接：已结算事实约束下的叙事生成策略

分支 `goal/local-02-narration`，工作树
`D:/others/Jity/.local/parallel-local-game/worktrees/02-narration`，基线
`865ae64e0901a70c3db4f1d0eb2af60268943c53`。本文件随本线提交一起交付；实际提交哈希见
`results/02-narration/completion.json`。

## 结论

- 已实现可执行策略 `generateCommittedNarration(...)`，接入现有
  `InferenceEngine` 与 `CommittedNarration`，不写世界状态、不重建事实序列化。
- CPU 小测试 57 项通过（`npx vitest run src/lib/world-engine/local/narration-generation/ --maxWorkers=1`），
  `npx tsc -p tsconfig.world-contract.json` 通过，ESLint 本目录无告警。
- 真实浏览器模型（Edge headless + wllama）：三个叙事检查点各 3 个代表性点，共 18 次真实生成全部被拒（legacy v2 0/3，instruct v1 0/3，1.5B v2 0/3）。模型能写出通顺中文，但仍在编造动作和往事、漏掉已结算移动、不写时间。这是真实模型限制的证据，不是本策略的通过证明；正文质量未达到训练范文水平。
- 主 agent 需要接线的只有 `game-model.ts` 里的 `narration()` 一处（见下），
  不需要改本模块或另写序列化。

## 问题

旧路径每次只生成一稿：要么整段接受，要么整段落回状态摘要；既没有围绕已结算事实的
有依据修复，也没有视角、回声、循环、提前收尾的生成后检查，取消/超时只留下一个
错误字符串。小模型常见的失败是：写出输入里没有的往事（旧报纸、1987 年的书）、
把别人的动作写反方向、重复同一句、只写很短一段就收尾。

## 实现

目录 `frontend/src/lib/world-engine/local/narration-generation/`：

| 文件 | 职责 |
|---|---|
| `types.ts` | 公开输入/输出、策略、进度显示状态、证据类型 |
| `ledger.ts` | 只读事实许可账本：必述变化、可选背景事实、许可人名/地点/事件、时间要求、隐藏知识 |
| `verify.ts` | 生成后校验：复用 `alignNarration`，补必述覆盖、视角、回声、循环、截断、提前收尾、未许可实体 |
| `guidance.ts` | 只从已结算事实和问题类型生成修复要求，不写成品答案，不泄露隐藏知识 |
| `prompt.ts` | 只在调用方序列化串的正文标记前插入指令/上一稿/修复要求，不重建状态序列化 |
| `index.ts` | 编排：流式调用 → 校验 → 有界重试 → 选择最佳稿 → 证据与显示状态 |

### 1. 输入串与事实包分离

`inputText` 必须由调用方（01 线/主 agent）用现有序列化器生成并注入，本模块不写第二份
兼容序列化。`committed` 是只读 `CommittedNarration`：每个事实的 id、人物、方向、任务
目标、个性文本、理智 from→to。两者都不在生成过程中被修改。

账本把事实分成：

- **必述**：`moved`、`task_achieved`、`personality_changed`、`sanity_changed`。
  未写进正文就是 `fact_omitted`，硬失败。
- **可选**：`at`、静态 `sanity`。它们是场景背景，不要求点名报到；但一旦写了，
  仍需与事实一致（交给 `alignNarration` 判）。

许可名字来自：事实包里的人名/地点、调用方显式给的 `visibleEntities`、注入的
`inputText` 里出现过的已知实体、以及 `priorText` 里已经合法出现过的已知实体。
`knownEntities` 里其余名字一旦出现就是 `unlicensed_entity`，防止小模型从预训练里
拉一个同题材人物进来。

### 2. 真实流式与显示状态

`engine.complete` 的 `onProgress` 原样转发为 `NarrationDisplayState`：

- `streaming`：`verified: false`，文本是尚未校验的流式片段；
- `accepted`：本次尝试通过全部硬检查，`verified: true`；
- `rejected` / `failed` / `cancelled`：`verified: false`，附问题列表。

没有假打字；每个 `streaming` 事件都对应真实 engine 回调。只有 `accepted` 的文本允许
作为该点的最终叙事提交。

### 3. 生成后校验（全部可执行）

- `alignNarration` 的硬违规：人物互换、方向反转、数字错误、时长错误、未达成任务却说
  完成、无事实的移动/站位、凭空事件。
- 必述事实覆盖：`alignment.coverage` 逐个对账本里的必述事实求交。
- 时间：`elapsed` 且数量大于 0 时默认必须写出这一时长；`wrong_time` 仍按事实判。
- 长度：低于 `minChars` 为 `too_short`；`finishReason=length` 或正文不以句末标点结束为
  `truncated`；短稿末尾出现收束句式为 `premature_closure`。
- `priorText` bigram 重叠超过阈值 → `echo_prior`；稿内同句重复 → `loop_repeated_sentence`；
  同分句重复 3 次以上 → `loop_repeated_clause`。
- 非视角人物的“心想/心里/觉得/知道/记得……” → `perspective_leak`；对每个非视角人物
  只扫到他/她之后、下一个已知人名之前，避免把下一句别人的心理算到前一个人物头上。
- `forbiddenKnowledge` 子串命中 → `knowledge_leak`；模型复述写作要求 → `prompt_echo`。
- 输入/前文里没有的明确承诺（答应/承诺/保证/发誓/许诺/约好/说好）→ `promise_without_fact`；
  输入/前文里没有的强往事标记（小时候/童年/当年/十年前/从前/曾经/很久以前/那一年）→
  `past_without_fact`。调用方可以用 `licensedEvents` 追加玩家动作里出现的承诺词，
  或让上一段已接受正文携带该往事；隐藏秘密不会进入修复提示。
- 无事实绑定、也不矛盾的句子记 `unverified_sentence`（软提示，不影响 `accepted`）。
  这是上游判分器的既有口径：词表外表达是人工复核线索，不是捏造定罪。

对上游判分器已知过严处做了三处**局部收窄**（不改上游文件）：

1. 直接带否定的动词（`没有推开门`）不算新增事件；
2. `从十降到八` 被上游移动动词表里的“到”误判为移动时，改按理智数值检查；
3. 句子里出现与理智无关的数字（`周宁接过来，是一本旧书`）不再当成理智数字错误；
   真正提到精神/理智/变化的数字错误仍保留。

### 3.5 物品状态词与“假数字吞掉事件”

上游判分器的事件动词表是有限的，模型会用同义词绕开（`盒子缓缓开启` 不在
`打开/关上` 表里）；而句子里只要出现一个与理智无关的数字（`一张纸条` 的“一”），
上游会先报 `wrong_number` 并跳过该句，后面的 `打开` 就再也查不到。真实 1.5B
运行的 elapsed 场景曾因此被接受，正文里盒子被打开、出现古董。

现在的处理：

- 非理智语的 `wrong_number` 不再直接放过整句，而是把该句用**空事实包**重跑一次
  事件检查；否定的动词（`没有打开`）仍不误报。
- 调用方给出的可见物品（`policy.scene.objects` / `visibleEntities`）与“打开/开启/
  掀开/拿出/取出/放进/递给/接过/放下/拿起/合上/锁上……”同句出现时，没有
  `licensedEvents` 就记 `fact_event_added`。这覆盖了上游词表没有的 `开启`。
- 新增回归测试直接使用 1.5B 那次被接受的原文；当前代码会把该拍拒掉，最终只剩
  明确的时间兜底句，而不是模型编的古董。

### 3.6 同义表达：理智/个性不逼模型报数字或复述原句

`alignNarration` 对 `sanity_changed` 要求句子里出现 from/to 数字，对
`personality_changed` 要求接近原句；真实好场景常用“呼吸比刚才浅”“这次没有把话
推回去”这类写法。现在：

- 理智变化：句子里有该人物 + 身体反应（呼吸/手指/声音/视线/肩/脚步…）+ 变化标记
  （比刚才/下来/浅/停…）时，不再直接判 `fact_omitted`；若句子写了方向词，方向与
  已结算 from→to 相反仍硬拒（如精神值降了却写“稳了下来”）。
- 个性变化：句子里有该人物 + 一个行为/态度动词 + 变化标记时，不再判遗漏。
- 两者都返回 `unverified_sentence` 软提示，交人工复核；`metrics` 仍记录上游 coverage
  的原始 false。移动/任务/时间仍要求可核对内容，不放宽事实。

这样不会因为“没逐字写出精神值/没复述个性原句”把忠实的短场景误拒；但软提示不是
质量通过，最终仍需用户读评。

### 3.7 对 01 短场景语料的兼容检查（71/71）

新增手工测试 `corpus-compat.test.ts`（默认跳过）：

```bash
cd frontend
NARRATION_CORPUS=D:/others/Jity/.local/parallel-local-game/worktrees/01-input/experiments/narration-quality/corpus-short/rows.jsonl NARRATION_CORPUS_REPORT=D:/others/Jity/.local/parallel-local-game/results/quality/corpus-compat-02.json npx vitest run src/lib/world-engine/local/narration-generation/corpus-compat.test.ts
```

它把 01 的 71 条手工短场景的目标正文送进同一套 `verifyNarration`，用每行的
`requiredFacts` 组事实包。当前 **71/71 全过**。中途发现的唯一硬矛盾
`short2-0034-carved-line-worn`（输入把方既白放在天台楼梯间，目标却写「方既白还在
天台」）已由 01 改成「方既白在楼梯间里」；`requests-02.json` 的 `req-02-06` 已解决。
71 行共产生 187 条 `unverified_sentence` 软提示（每行约 2.6 条），交人工读评，
不是硬错误。

为了不把人类金标准误杀，本轮修了以下**表达形式**误判（不放松事实内容）：

- 时间：上游把「二十分钟」里的「十分钟」、把「九八年」的年份当错误时长；
  当**要求的**时长本身已写出时，不再保留 `wrong_time`。真正写错时长仍由
  `time_missing`/`wrong_time` 拒绝。
- 静态 `at` 事实：不再送进对齐器当断言，改由 `knownPositions` 授权站位。否则
  句子开头的「旧刊堆放区」会被当成 actor，产生假 actor_swap / 假移动。
- 分号：对齐前把 `；` 归一成句号，两个人物各占一句时不再互相借动作。
- 多人物/代词：任务目标或个性原文逐字出现时，允许代词主语并返回软提示；
  多人物并列主语（`A、B和C都办完了「…」`）不再报 actor_swap。
- 地点前缀：`天台` 是 `天台楼梯间` 的前缀；移动事实到后者时，不再报「移动到
  天台无事实」。
- 物品：`打开/开启/拿出/取出/…` 仍是硬事件；`合上/拿起/放下/推开/翻开` 等
  具体小动作不再当凭空事件（用户要求允许细微动作）。
- 跨人物数字：同一句里 A 的精神值数字属于 B 时，不再把 B 的数字算到 A 头上。
- 理智/个性：见 §3.6，反应式表达返回软提示。

这些修复都有单元测试（57 项）；语料兼容测试本身是手工入口，不进入默认 CI。

### 4. 有界重试

默认 `maxAttempts = 2`（可配 1–4）。第二稿的提示只在正文标记前加入：

- 已结算事实的原样短语（如 `林川从走廊走到门厅`）；
- 视角、时间、长度、重复等一行要求；
- 可选 `revisionMode: 'revise'` 时附上上一稿，默认重新生成而不是只改上一稿。

`truncated` 会把下一次 `maxTokens` 增长（有上限）。引导语只来自事实账本，不包含
任何成品段落、隐藏知识或参考答案；重试是否“修好”由同一套校验判断，不靠调用次数。

### 5. 取消、超时与证据链

每次尝试记录：完整 prompt、原始 raw、清洗后文本、`finishReason`、错误、单次耗时、
首个 token 时间、流式事件数、`accepted/cancelled/timedOut`、全部问题、对齐结果、
指标。整体 `timings.totalMs` 从调用开始算到返回，包含所有重试；`attemptsMs` 是各次
之和。外部 `AbortSignal` 直接转发给 engine；端到端 `deadlineMs` 由本模块自己的
计时器兜底。取消/超时不会重试，也不会把部分文本标成接受。

## v3：按“已结算的一件事”分拍写（产品路径）

一次生成整段场景在真实小模型上反复失败：模型会把输入里没有的动作、人物、往事写进去，
同时漏掉本回合唯一真正发生的变化。原因不是中文不通顺，而是“整段场景”这个要求本身
要求模型自己补连接动作，而连接动作就是编造。

v3 因此改成**按拍写**：`policy.mode = 'beats'`（传了 `policy.scene` 时默认就是它）。

1. `planBeats` 把已结算事实排成有序的拍：场景开场（如有场景上下文）、每个必述事实一拍、
   需要报时间时加一拍。每拍写明“这一件”是什么、能出现哪些名字。
2. 每拍只请求一到两句，提示里给视角、地点、在场人物、环境描述、上一句、这一件，
   并禁止新增人物/物品/事件/往事/承诺/数字。
3. 每拍单独校验（复用同一套 `verifyNarration`，只是把必述集合缩到这一拍）。不合格
   只重写这一拍，最多 `beatAttempts` 次；仍不合格时，**事实拍**退回该事实的普通叙述句
   （如“林川从走廊走到了门厅。”），场景拍直接跳过。整段场景因此不会因为一句坏话全废。
4. 程序把拍拼成段落（一拍一段，和训练范文的节奏一致），去掉跨拍重复句，补上漏掉的
   时间句/事实句，然后对整段再做一次完整校验。
5. 流式是真实的：每拍内部照常转发 engine 的 token 回调，拍与拍之间也推进显示文本，
   页面在第一个拍完成时就能读到第一段。

如果所有拍都退回了事实句，结果标 `all_beats_fell_back` 并 `accepted: false`——那是
事实句拼接，不是模型正文，不能当作通过。

### 0.5B 场景候选（10 线 qwen05b-scene-v1）

10 已登记 `D:/others/Jity/.local/models-narration/qwen05b-scene-v1/model-Q4_K_M.gguf`
（SHA-256 `5a9879f1…`）。它用 Qwen2.5 ChatML：**独立 system 轮** + user=xProse
（v2 或 legacy），assistant=正文。页面现有的 `WllamaInferenceEngine.complete`
只发一条 user 消息，无法表达这个 system 轮；脚本里的 `ChatEngine` 可以，页面接线
需要 08/06 增加 `completeChat(messages)` 或 `system` 选项。请求写在
`results/quality/integration-02.json` 第 6 步。

### 训练模板核对

之前的真实探针（18 次全拒）喂的是 `legacyNarrationInput`：一行扁平状态加 `【正文】`。
但浏览器里的两个权重都不是这个形状训练的：

- 无指令臂：`【状态】<x 的 JSON>
【视角】…
【叙事】`（`qwen-train/train_qwen.py` 的
  `INSTRUCTION = None` 分支）；
- 指令臂：ChatML + `instruction.md` 系统提示 + 三段式用户输入。

`trained-input.ts` 现在能从同一份只读状态重建这两种形状（`trainedSceneView` →
`renderTrainedRawPrompt` / `renderTrainedInstructUser` / `wrapChatml`），场景模式可用
`--template trained-raw|trained-instruct` 复现。这样“某个权重不行”的结论才是关于权重的结论。

`probe-template.mjs` 走 `createCompletion`（绕过页面适配器必做的 ChatML 包装），用同一组
事实喂四种形状，用来确认某个权重到底是哪种训练臂。

### v3 新增 API

```ts
policy.mode?: 'scene' | 'beats';        // 传 scene 时默认 beats
policy.scene?: BeatSceneContext | null; // 地点/环境/在场人物/可见物品，只读状态
policy.beatAttempts?: number;           // 每拍重试次数，默认 2
policy.beatMaxChars?: number;           // 单拍字数上限，默认 170

// 返回新增：
// beats: NarrationBeatEvidence[]  // 每拍的指令、文本、来源(model/fallback/skipped)、
//                                 // 尝试次数、耗时、问题、完整 prompt 与 raw
// assembly: { droppedSentences, appendedSentences }  // 程序拼装时删除/补上的句子

export const generateCandidate = generateCommittedNarration; // QUALITY-TEAMS.md 的入口名
```

## 导出 API

```ts
// frontend/src/lib/world-engine/local/narration-generation/index.ts
export async function generateCommittedNarration(input: {
  engine: InferenceEngine;
  committed: CommittedNarration;        // 只读已结算事实
  inputText: string;                    // 调用方/01 序列化串，注入
  priorText?: string | null;            // 上一段已接受叙事
  signal?: AbortSignal;
  onProgress?: (state: NarrationDisplayState) => void;
  policy?: NarrationPolicy;
}): Promise<GeneratedNarration>;

// GeneratedNarration:
// { text, rawAttempts, accepted, issues, timings, strategyVersion,
//   status, ledger, metrics, attemptIndex, display }
```

`policy` 常用字段：`viewpoint`、`roster`、`locations`、`knownPositions`、
`knownEntities`、`visibleEntities`、`licensedEvents`、`forbiddenKnowledge`、
`time`、`minChars`、`targetChars`、`maxAttempts`、`maxTokens`、
`maxTokensCeiling`、`temperature`、`retryTemperature`、`seed`、`timeoutMs`、
`deadlineMs`、`instruction`、`revisionMode`。完整定义见 `types.ts`。

## 主 game-model 接线

在 `frontend/src/lib/world-engine/local/game-model.ts` 的 `narration()` 中，把
“一次 `complete` + `validateNarration` + `pruneNarration`”替换为一次策略调用。
`alignmentPacket(...)`、`brief.prompt`、`factualNarration(...)`、`EVENT_VERBS`
都可以原样复用：

```ts
import { generateCommittedNarration } from './narration-generation';

// class 内新增：private lastAcceptedNarration: string | null = null;
const packet = alignmentPacket(data.before ?? null, data.delta ?? {}, after);
const result = await generateCommittedNarration({
  engine: this.narrationEngine,
  committed: packet,
  inputText: brief.prompt,                    // 现有 legacy/instruct 序列化器
  priorText: this.lastAcceptedNarration,
  // signal: this.narrationSignal,            // 主 agent 若已有取消信号则传入
  // 现有 onNarrationProgress 只有 {pointId, raw, elapsedMs}；先按这个形状接。
  // 若要把“未核验/已接受”显示状态带到页面，再给该选项加 status/verified 两个字段。
  onProgress: (state) => this.options.onNarrationProgress?.({
    pointId, raw: state.text, elapsedMs: state.elapsedMs,
  }),
  policy: {
    viewpoint: { id: view, name: after.initial.characters[view]?.name ?? view },
    roster: Object.values(after.initial.characters).map((entity) => entity.name),
    locations: Object.values(after.initial.locations).map((entity) => entity.name),
    knownPositions: visibleCharacters(after, view).filter((id) => id !== view).map((id) => ({
      name: after.initial.characters[id]?.name ?? id,
      location: locationName(after, roomOf(after, id)),
    })),
    knownEntities: [
      ...Object.values(after.initial.characters).map((entity) => entity.name),
      ...Object.values(after.initial.locations).map((entity) => entity.name),
      ...Object.values(after.initial.items).map((entity) => entity.name),
    ],
    visibleEntities: sameRoomItems(after, view).map((id) => after.initial.items[id]?.name ?? id),
    // 主树当前导出了 EVENT_VERBS；若该导出被撤回，先删掉这一行（更保守）。
    licensedEvents: EVENT_VERBS.filter((verb) => this.lastPlayerInput.includes(verb)),
    time: data.delta?.timeAdvance ?? null,
    minChars: 60,   // 01 的短场景 60–149 字；不要用 120 把忠实的短场景判短
    maxAttempts: 2,
    maxTokens: this.options.narrationMaxTokens ?? 380,
    maxTokensCeiling: 700,
    temperature: this.options.narrationTemperature ?? 0.7,
    retryTemperature: 0.55,
    timeoutMs: this.options.narrationTimeoutMs ?? 150_000,
    deadlineMs: 300_000,
  },
});
const accepted = result.accepted && result.text.length > 0;
if (accepted) this.lastAcceptedNarration = result.text;
const reason = accepted ? undefined : result.issues
  .filter((issue) => issue.severity === 'hard').map((issue) => issue.kind).join(',');
const text = accepted ? result.text : factualNarration(data.before ?? null, data.delta ?? {}, after, view, this.lastPlayerInput);
this.options.onNarrationComplete?.({ pointId, raw: text, completion: {
  raw: text, finishReason: accepted ? 'stop' : result.status,
  firstTokenMs: result.timings.firstTokenMs, wallMs: result.timings.totalMs,
} });
this.options.onTask?.('narration', key, {
  ms: result.timings.totalMs, fallback: !accepted, error: reason, raw: text, promptChars: brief.prompt.length,
});
return { value: text as unknown as Json, raw: text, ms: result.timings.totalMs, fallback: !accepted, error: reason };
```

注意：

1. **只有 `result.accepted === true` 才提交模型正文**；否则仍用主 agent 现有的
   `factualNarration` 兜底，并把 `status`/`issues` 记进 `onTask`，不要静默。
2. `result.issues` 里可能有 `severity: 'soft'` 的 `unverified_sentence`；判断失败看
   `accepted`/`status`，不要看 `issues.length`。
3. `priorText` 用上一段**已接受**的正文；被拒绝的稿不要喂回去，否则回声检查会污染。
4. 取消：`WorldModelPort.generate` 目前没有 signal 参数。本模块已经支持
   `signal`，主 agent 若要在页面取消，需要在自己的 port/controller 增加一个可选的
   `signal` 并传进来；不接线也能按 `deadlineMs` 超时，只是 UI 取消无法中断底层推理。
5. `instruct` 模式的 `brief.prompt` 已带任务说明；不要再把同一段说明塞进
   `policy.instruction`，否则会重复。`legacy` 模式可留空。
6. 旧 `validateNarration`/`pruneNarration`/`alignNarration` 调用可由本策略替代；
   `factualNarration` 保留作显式兜底，并继续在 `onTask` 标记 `fallback`。

## 验证

复用来源：`runtime/committed-narration.ts`、`runtime/narration-alignment.ts`、
`runtime/engine.ts`、`local/prompt.ts`、`runtime/b3-short-samples.ts` 都直接来自本工作树
基线 `865ae64e`，没有从其他分支复制实现。真实模型是用户提供的本地 GGUF，不提交；
证据只记录文件路径与 SHA-256。

### CPU（本线必跑）

```
cd frontend
npx vitest run src/lib/world-engine/local/narration-generation/narration-generation.test.ts --maxWorkers=1
npx tsc -p tsconfig.world-contract.json
npx eslint src/lib/world-engine/local/narration-generation
```

57 项测试覆盖：正确方向的移动被接受；方向反转被拒且第二稿提示带正确方向；必述遗漏；
整段拒绝返回最佳稿和全部问题；非视角心理泄露；POV 心理合法；隐藏知识；未许可实体；
句内循环；跨回合回声；提前收尾；截断后提高 token 预算；elapsed 时间必述；玩家
动作许可事件；复述指令；revise/regenerate 两种修复；外取消（无输出/带部分流式）；
预取消；端到端超时；引擎错误重试；证据链完整性；真实 projector + `legacyNarrationInput`
的接线形状；新增承诺/往事只有在输入或前文有来源时才放行。

这些只证明策略逻辑和证据链，不证明真实文风。

### 真实浏览器模型

命令、模型 SHA、逐次原始输出与问题在
`results/02-narration/real-model-legacy.json`（以及可选的 instruct 证据文件）。
使用真实 Edge headless + wllama + CPU 4 线程，通过自助资源锁运行；不重跑其他线基线。

命令：

```
cd frontend
MSYS_NO_PATHCONV=1 node scripts/parallel-narration/run-real-narration.mjs   --model /models/qwen25-0.5b-narration-Q4_K_M.gguf   --out ../../../results/02-narration/real-model-legacy.json
MSYS_NO_PATHCONV=1 node scripts/parallel-narration/run-real-narration.mjs   --model /models/qwen25-0.5b-narration-instr-Q4_K_M.gguf   --instruction "根据下面已经结算的事实写一段中文小说正文。只写事实里出现的人和事；不要新增人物、地点、物品、事件、往事或数字；不要复述事实清单；不要写标题或说明；写连贯的段落，约二百五十字。"   --max-tokens 360 --min-chars 100   --out ../../../results/02-narration/real-model-instruct.json
```

环境：headless Edge + wllama，CPU 4 线程（未用 WebGPU），contextSize 4096，
temperature 0.7 / 重试 0.55，seed 42，最多 2 次尝试。模型是用户提供的本地文件，
未提交；证据里只记路径、SHA-256 和输出。

| 模型 | 场景 | 结果 | 字数 | 2 次尝试的硬问题 | 用时 |
|---|---|---|---|---|---|
| legacy `a5fea8c3…` (v2) | root（无变化） | 拒 | 140 | 新增事件＋无事实移动；新增事件×3＋截断 | 38.9 s |
| legacy (v2) | move（林川 走廊→门厅） | 拒 | 235 | 漏述移动＋过短；新增事件＋漏述移动 | 16.4 s |
| legacy (v2) | elapsed 2 分钟（空增量） | 拒 | 97 | 新增事件＋时长错误×2＋未写时间；新增事件＋未写时间 | 31.1 s |
| instruct `41fbef75…` (v1) | root | 拒 | 343 | 新增事件×2；新增事件＋截断＋句内重复 | 45.4 s |
| instruct (v1) | move | 拒 | 344 | 时长错误＋移动声明＋新增事件×2＋漏述移动；新增事件×2＋漏述移动 | 35.5 s |
| instruct (v1) | elapsed 2 分钟 | 拒 | 510 | 新增事件＋未写时间＋句内重复；新增事件＋移动声明＋未写时间 | 49.5 s |
| 1.5B `6ed2268d…` (v2) | root | 拒 | 167 | 新增事件×2＋移动声明×2；移动声明＋新增事件＋移动声明 | 62.9 s |
| 1.5B (v2) | move | 拒 | 312 | 移动声明＋漏述移动；移动声明＋漏述移动 | 85.3 s |
| 1.5B (v2) | elapsed 2 分钟 | 拒 | 555 | 新增事件＋未写时间＋往事“曾经”＋截断；新增事件×2＋时长错误＋移动声明＋未写时间＋往事“十年前” | 134.4 s |

三次运行的模型加载分别为 14.6 s（legacy v2）/ 10.3 s（instruct v1）/ 24.4 s（1.5B v2）；单次生成平均约 29 s / 43 s / 94 s。
legacy 与 1.5B 都在 `v2`（新增承诺/往事硬检查）下跑过，三个场景仍然全拒，问题类型不变；
1.5B 的 elapsed 场景实际触发了 `past_without_fact`（“曾经”“十年前”）。instruct 的模型文件在
11:44 左右被其他线从共享模型目录替换/移除，v2 无法重跑，保留它的 v1 原始证据；v2 的承诺/
往事检查只会增加拒绝理由，不会改变已经因其他硬问题被拒的结论。

逐次完整 prompt、raw 文本、清洗文本、finishReason、问题、对齐 coverage/violations/
unverified/repetition 都在上面两个 JSON 里。原始输出确实通顺（不是乱码、不是空串），
问题在于内容不服从已结算事实：例如 root 场景编出“旧报纸/字条”，move 场景没有写
“林川从走廊走到门厅”，elapsed 场景写“1987 年的书”却没有写两分钟。策略按设计拒绝
这些稿，不把它们当成通过，也不自动换成模板冒充模型正文。

### 未做 / 限制

- 真实模型质量未达标：上面的逐条问题就是证据，不能把“策略把坏稿拒了”说成
  “策略已经写出好稿”。目标文风（接近训练范文）没有在真实模型上得到证明。
- 本线不负责页面接线、35 次终验、全流程 20 次页面输入或人工读评；这些归主集成流程。
- 视角检查基于已知人名，不解析纯代词（“他/她”）的指代；代词心理只能靠人工复核。
- 完全不在 `knownEntities` 里的**新具名人物**无法只靠确定性规则与普通词表外措辞区分：
  已知但未许可的名字会硬拒（`unlicensed_entity`），真正的新名字只能落到 `unverified_sentence`
  软提示。1.5B 的真实输出里出现过“顾明”这种新名字，这是本版没有硬门的能力。
- 上游 `alignNarration` 的否定、数字、移动动词歧义只做了上述三处局部收窄，不是全面修复。
- 真实运行的模型、权重与浏览器资产不提交到仓库；证据里只放 SHA/路径/输出。
- 时间/地点/物品的展示名来自调用方序列化；本模块不判断序列化本身是否完整或可见性正确。
