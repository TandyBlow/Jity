# 02-narration 交接：已结算事实约束下的叙事生成策略

分支 `goal/local-02-narration`，工作树
`D:/others/Jity/.local/parallel-local-game/worktrees/02-narration`，基线
`865ae64e0901a70c3db4f1d0eb2af60268943c53`。本文件随本线提交一起交付；实际提交哈希见
`results/02-narration/completion.json`。

## 结论

- 已实现可执行策略 `generateCommittedNarration(...)`，接入现有
  `InferenceEngine` 与 `CommittedNarration`，不写世界状态、不重建事实序列化。
- CPU 小测试 29 项通过（`npx vitest run src/lib/world-engine/local/narration-generation/narration-generation.test.ts --maxWorkers=1`），
  `npx tsc -p tsconfig.world-contract.json` 通过，ESLint 本目录无告警。
- 真实浏览器模型（Edge headless + wllama）：两个叙事检查点各 3 个代表性点，共 12 次真实生成全部被拒（legacy 0/3，instruct 0/3）。模型能写出通顺中文，但仍在编造动作和往事、漏掉已结算移动、不写时间。这是真实模型限制的证据，不是本策略的通过证明；正文质量未达到训练范文水平。
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
    minChars: 120,
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

### CPU（本线必跑）

```
cd frontend
npx vitest run src/lib/world-engine/local/narration-generation/narration-generation.test.ts --maxWorkers=1
npx tsc -p tsconfig.world-contract.json
npx eslint src/lib/world-engine/local/narration-generation
```

29 项测试覆盖：正确方向的移动被接受；方向反转被拒且第二稿提示带正确方向；必述遗漏；
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

两次运行的模型加载分别为 14.6 s（legacy v2）/ 10.3 s（instruct v1）；legacy 单次生成平均约 29 s，instruct 约 43 s。
legacy 在 `v2`（新增承诺/往事硬检查）下重跑过，三个场景仍然全拒，问题类型不变。instruct
的模型文件在 11:44 左右被其他线从共享模型目录替换/移除，v2 无法重跑，保留它的 v1 原始证据；
v2 的承诺/往事检查只会增加拒绝理由，不会改变已经因其他硬问题被拒的结论。

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
- 上游 `alignNarration` 的否定、数字、移动动词歧义只做了上述三处局部收窄，不是全面修复。
- 真实运行的模型、权重与浏览器资产不提交到仓库；证据里只放 SHA/路径/输出。
- 时间/地点/物品的展示名来自调用方序列化；本模块不判断序列化本身是否完整或可见性正确。
