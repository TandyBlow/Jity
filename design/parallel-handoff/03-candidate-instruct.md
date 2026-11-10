# A 组：本地 instruct 模型完整正文候选（03-candidate-instruct）

## 1. 这解决什么

页面当前的正文来自 `LocalGameModel.narration()`：把 `legacyNarrationInput` 塞给模型，用 `validateNarration` 按名字/数字放行或回退。它没有“先看清场面，再写一段小说”的投影，也没有对“漏写已结算变化”和“写出资料外事件”的区分。

本线（A 组生成侧）新增一个独立候选模块：从已结算的 `WorldState` 取出视角真正能看见的房间、人、物品和本点变化，组一次完整的 instruct 对话，把模型输出的正文用页面同一套事实对齐器核对，最多重写一次，然后如实返回 `accepted` 与所有草稿。它不改 `game-model`/页面，只导出可接线入口。

## 2. 入口与调用

```ts
import { generateCandidate } from
  '@/lib/world-engine/local/narration-candidates/instruct';

const result = await generateCandidate({
  engine,                              // 现有 InferenceEngine；08 的 chat() 可用时会自动用系统消息
  pointId,                             // 可选，进度/证据用；也可从 inputText 解析
  committed,                           // 已提交事实（projectCommittedNarration / 页面 alignmentPacket 形状）
  inputText,                           // 调用方已有序列化输入（可选；没有 state 时用来还原场景）
  priorText: lastAcceptedNarration,     // 上一段已接受正文（连续性与重复检测）
  state: after,                        // 本点 after 的 WorldState（推荐，真实可见投影）
  before, delta,                       // 本点 before / {timeAdvance, entityDeltas}
  playerInput: lastPlayerInput,         // 玩家本点已冻结的行动句
  settledResults: resultLines,          // 可选：本点 results 任务的结果行（许可动词/前文）
  recentEvents: lastEvents,             // 可选：最近 4 条已提交事件
  signal,                              // 取消
  onProgress: (state) => { /* {text,status,verified,elapsedMs,attempt} */ },
  policy: {
    viewpointId,                       // 默认 state.protagonistId
    template: 'auto',                  // qwen2.5-instruct | qwen3-instruct | auto（按 engine.info.modelId）
    promptMode: 'auto',                // chat（默认 wllama）| raw（自渲染 ChatML）
    targetChars: 220, minChars: 90,
    maxAttempts: 2, maxTokens: 520,
    temperature: 0.6, retryTemperature: 0.35,
    seed: 42, timeoutMs: 180_000, deadlineMs: 240_000,
    requireTime: true,
    styleSample: null,                 // 可选风格示例（见 §5，默认关闭）
  },
});
// result: { text, accepted, rawAttempts, issues, timings, strategyVersion,
//           status, prompt, projection, attemptIndex, template }
```

`createInstructCandidate(engine, defaults)` 返回同形状的 `(args) => Promise<...>`，方便 06/09 固定模型与参数。

**模板**：Qwen2.5-Instruct / Qwen3 都是 ChatML。08 的 `WllamaInferenceEngine.chat()` 可用时，候选走真实 system + user 两轮（`enable_thinking=false` 由适配器传入）；当前基线树的 `complete()` 只接受一个 prompt，候选自动退化为“system 文本 + user 文本”的单轮，仍由 GGUF 模板包成 user turn。Qwen3 的 ` thinking` 块（含只输出一半的）在交给页面前剥离；原始输出全部留在 `rawAttempts`。

**返回语义**：`accepted` 只在这份草稿通过事实/场景检查时为 true；被拒的稿子以 `accepted:false` 返回并带每次尝试的 `issues`，绝不把退回稿标成正文。`onProgress` 的 streaming 文本 `verified:false`；最后一帧 `accepted` 才 `verified:true`。一次调用只生成一次；重写是第二次真实调用，计入 `timings`。

## 3. 生成与核对做了什么

1. **投影**（`projection.ts`）：视角房间名 + 地点描述；同房间人物（外貌剪到两条短句、只给主角一句行为个性、随身物只列主角的）；房间内物品最多 5 件；本点变化（移动/任务/精神/个性/物品换手/外貌）按“必须写到”排序；玩家行动转第三人称（引号内保留原话）；上一段结尾 200 字内。
2. **轻量内容计划**（`prompt.ts`）：程序按“地点时间 → 接住玩家动作 → 移动 → 物品去向 → 任务结果 → 其他变化 → 时间流逝 → 停在此刻”排好，不额外调用模型。
3. **核对**（`verify.ts`）：复用 `runtime/narration-alignment` 的同一事实对齐器（演员错位、方向反转、错误数字、无依据完成/移动/站位、错误时长都是硬错误）。另加：资料外人物名、禁止知识、第一人称旁白、与上一段过度重复、小模型复读、长度、截断、贴标签/JSON/思考残留。
4. **文档化的放宽**（与页面严格器不同，必须让集成者知道）：
   - 移动、时间、物品换手、以及“完成任务”必须有正文表达；站位（`at`）、精神值、个性变化只记 soft omission——页面严格器要求逐字引用任务目标和具体精神数值，那与小说正文不能共存；
   - 任务的“说了”按角色名 + 目标里至少两个内容二字词同句出现判断（“短讯机重新连上凯撒”算说到，“她看起来很高兴”不算）；
   - 玩家本点行动里出现的移动地点/动词可豁免“无依据移动/事件”的硬判（代词句“他朝器材棚走去”在页面名字对齐器里无法绑定）。
   所有**矛盾**仍为硬错误；没有 committed 包时直接拒绝（`facts_unverified`），不冒充已核对。

## 4. 真实运行（本机 Edge + wllama，CPU 6 线程）

运行器：`frontend/scripts/candidate-instruct/run-instruct-candidate.mjs`（自己取资源锁）。它用真实内核 `applyPoint` 构造自由一日世界的已结算点，用页面同一 `projectFacts` 投影，记录每案 prompt、全部原始输出、清洗稿、判定、逐次耗时和模型 completion 证据。

```bash
python D:/others/Jity/.local/parallel-local-game/resource_lease.py acquire --lane 03-actions --purpose "instruct candidate"
cd frontend
MSYS_NO_PATHCONV=1 node scripts/candidate-instruct/run-instruct-candidate.mjs \
  --assets D:/others/Jity/.local/world-narration-worktree/frontend/public \
  --model /models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --out ../artifacts/candidate-instruct/run.json
python D:/others/Jity/.local/parallel-local-game/resource_lease.py release --lane 03-actions
```

已跑（`artifacts/candidate-instruct/`）：

| 归档 | 结果 |
|---|---|
| `dry-prompts.json` | 6 个自由一日点的真实投影/prompt（无模型），证明入口与场景数据可运行 |
| `probe-qwen25-s1.json` | Qwen2.5-1.5B 第一次真实生成：把玩家“我”续写进正文，50 字，两次都被拒；暴露提示词第三人称问题 |
| `run-qwen25-r2.json` | 已改第三人称/自然时间/放宽数值后：S1 生成 167 字但重复移动句并撞 340 token 上限；S2/S4 第二轮为空（适配器在 token 上限时抛 `IncompleteGenerationError`，旧代码丢了已付费文本）；S4 出现“诺诺的手…”复读 |

r2 直接导致三项修复（已提交在后续提交里）：接收 `IncompleteGenerationError.completion.raw` 并按 `truncated` 处理；maxTokens 340→520、温度 0.6、近重复句去重与复读硬检查；投影剪短外貌/随身物、物品 5 件、地点 160 字（减少模型逐字照抄）。

**首次加载 42–52 s（冷启动，不计入单点等待）；首 token 3–25 s；单次 520 token 生成在 1.5B/6 线程约 60–90 s。** 60 s 首段、300 s 整段的验收线要用最终组合在页面实测，这里只给单次生成证据。

## 5. 风格示例（可选）

`policy.styleSample` 可放一小段优质范文，prompt 明确标注“只学语气和句子节奏，人名、地点、事件一律不得写进正文”。默认关闭：0.5B 曾把提示里的反例逐字复制，1.5B 是否也这样要靠真实运行判定。05 的 `tide-watch` 场景正文（如 `experiments/narration-quality/corpus-scenes/generated/rows.jsonl` 的 `tide-duty-t1`）是可用的候选风格锚点，来源与许可在 05 的交接里。

## 6. 主 agent 需要改的几行

在 `local/game-model.ts` 的 `narration()` 里替换单次 `complete()` 路径：

```ts
import { generateCandidate } from './narration-candidates/instruct';

const candidate = await generateCandidate({
  engine: this.narrationEngine,
  pointId,
  committed: alignmentPacket(data.before ?? null, data.delta ?? {}, after),
  inputText: facts,                       // 现有 legacyNarrationInput，保留
  priorText: this.lastAcceptedNarration,
  state: after, before: data.before ?? null, delta: data.delta ?? null,
  playerInput: this.lastPlayerInput,
  onProgress: (state) => this.options.onNarrationProgress?.({
    pointId, raw: state.text, elapsedMs: state.elapsedMs,
  }),
  policy: { targetChars: 220, maxAttempts: 2, maxTokens: 520,
            template: 'auto', promptMode: 'auto',
            temperature: this.options.narrationTemperature ?? 0.6 },
});
if (candidate.accepted) this.lastAcceptedNarration = candidate.text;
return { value: candidate.text as unknown as Json, raw: candidate.text,
         ms: candidate.timings.totalMs, fallback: !candidate.accepted,
         error: candidate.accepted ? undefined : candidate.issues.filter(i => i.severity === 'hard').map(i => i.kind).join(',') };
```

- 若页面暂时保留 `alignNarration` 二次判定：它会把本候选“任务按结果词表达”“精神变化按情绪表达”判成遗漏，从而回退；要么以候选 `accepted` 为准，要么只把对齐器的 `violations`（矛盾）接为硬错误，把 `omissions` 交给候选。
- 页面 stop 按钮：传 `signal` 给候选；候选在 AbortError 时返回 `status:'cancelled'`，不显示半段为已接受。
- `onProgress` 的 `text` 已经去掉思考块和标签，可直接显示；`verified:false` 时页面应保留“未核对”状态。

## 7. 限制与未覆盖

- 1.5B 仍会：照抄外貌短句、复读同一动作、把“时间过去”写死；这些已被 prompt/清洗/复读检查压住一部分，但真实质量要等本轮修复后的原文。
- 任务结果用“结果词”判是否说到，是程序近似，不证明语义等价；最终读评仍看正文。
- 未登记的新专名无法识别（没有词表），只拦已登记但不在场的人物。
- 没有接页面/E2E；没有在真实产品流程里测 60 s/300 s；模型加载与整链等待由 08/主集成负责。
- 风格示例、连续回合的跨点记忆（目前只传 `priorText` 一段）尚未真实验证。
- 资源锁与 02/08/09 共用；本线只在取得锁时跑真实模型。
