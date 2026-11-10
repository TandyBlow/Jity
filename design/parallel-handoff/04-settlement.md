# 04-settlement 交接：共同结果、六阶段更新、继续判断

## 问题

主集成页的 `game-model.ts` 目前自己实现了三块任务，但它们都不是通用语义：

- `results()` 对单人组直接返回“完成了刚才的动作”，多人组才调用模型；这不区分行动被接纳、目标未达成、骰点未准入。
- `updates()` 让模型输出 `实体|字段|值` 文本行，再由 `parseLineChanges` 解析；位置、外貌、任务、个性、理智没有完整人物覆盖，也没有“位置→外貌→任务→新增小任务→个性→理智”的阶段依赖。模型失败时还会用关键词移动规则兜底。
- `continuation()` 用 `this.autoContinuations < 1` 把自动推进硬性限制为一次；模型异常时 `fallback()` 直接返回 handback，等于把失败伪装成交还。

本线把这三块改成真实语义候选，并保持共享契约不变：输出仍是 `Record<Id,string>`、`UpdatesCall[]`/`UpdatesCall`、`Conclusion`；不碰已提交世界、不掷骰、不写状态内核。

## 一次完整流程

以四人物小世界为例：甲（a，主角）、乙（b）、丁（c，无任务）、丙（off，不在场，有任务 off1）。

1. 共同组冻结了甲、乙两条行动。甲对乙有一次骰点 `result=3, eligible=true, admitted=false`。
2. `results('g1', input)` 读取 `groupId/members/workingState`，把每条冻结行动和骰点回执写进提示词。模型返回：
   - `judgments`：甲的 `effects` 必须写 `{targetId:'b', reacted:false}`，因为 admitted=false；乙的 effects 为空。
   - `facts`：一条共享事实可以同时归属 a、b；每个成员至少被一条事实归属。
   - 校验通过后得到 `{a:'甲乙都……', b:'乙没有反应……'}`；校验不通过先带错误反馈重试一次。
3. `updates('g1', input)` 没有 `stage`，按固定顺序执行六个阶段：
   1. `position`：扫描所有人物和物品的当前位置；模型只列移动的实体（如 a→远处、tool→盒子）；本地状态内核先验证最终位置图无环、槽位和相对位置合法。
   2. `appearance`：扫描地点、物品、人物的当前外貌；提示词已包含第 1 步后的位置；`add/remove/replace/keep` 必须覆盖被操作实体的全部有效记录。
   3. `tasks`：列出全人物全部任务（包括已完成和没有任务的人物）；只允许 pending→achieved，已完成任务输出 achieved 也不会产生 delta。覆盖 evidence 的 `taskCoverageIds` 是完整人物表。
   4. `subtasks`：只允许挂在已有任务下，负责人等于父任务负责人；新任务一律 pending，ID 由程序分配；超过预算（默认 8）整段失败，不截断。
   5. `personality`：只有本轮有新任务达成才执行；扫描完整人物表（包括 off 这种不在场人物）；每个角色都必须给 keep/add/remove/replace，且有效记录必须被覆盖。
   6. `sanity`：只为第 5 步实际发生个性变化的人物生成 0–100 整数；人物集合必须与个性变化集合完全一致；非法输出回退到当前理智值并记录 `fallback:true`，不会夹取或编造。
4. 合并调用返回六个 `UpdatesCall`；控制器用现有 `checkUpdatesStages`、`assembleCandidates`、`preview_point` 逐阶段应用并最终提交。拆分调用（`input.stage`）只返回当前阶段的一个 `UpdatesCall`，后续阶段的输入是控制器已经应用前序阶段后的 `workingState`。
5. `continuation('r1', input)` 先让模型提出“大概率发生且与主角相关”的候选行动，再让模型逐条判断 `likely` 和 `related`：
   - 两者都为 true 的候选才进入 `candidateCharacterIds`，返回 `kind:'continue'` 和新的 `nextRoundId`。
   - 没有候选，或全部不是 likely+related，返回普通 `kind:'handback'`。
   - 连续两轮没有任何实体变化（只有时间推进也算无进展），或同一组候选连续三轮重复，策略返回 handback，并把 `no_progress`/`repeated_candidate` 写进 evidence。
   - 模型调用失败、输出结构错误、head 对不上：返回 `value:null` 和错误，**不返回 handback**。接入方必须抛错/停止，不能把异常当交还。
   - 默认 `continuationPolicy.maxAutoContinuations = null`，不存在“默认 0 次”或“只允许 1 次”的静默关闭。

## 导出 API

文件：`frontend/src/lib/world-engine/local/semantics/settlement/`

```ts
import {
  createSettlementHandlers,
  requireSettlementValue,
  continuationPolicy,
  createContinuationPolicy,
} from '@/lib/world-engine/local/semantics/settlement';

const settlement = createSettlementHandlers({
  engine,                       // InferenceEngine（语义模型）
  options: {                    // 全部可选
    onTask,
    maxTokens: { results, updates, continuation },
    temperature,
    timeoutMs,
    maxPromptChars,             // 默认 8000；超出返回失败，不截断
    maxNewTasks,                // 默认 8
    nextRoundId,                // 可选；默认 round_auto_<timestamp>
    continuation: continuationPolicy,
  },
});

const results = await settlement.results(key, input);       // Record<Id,string> | null
const updates = await settlement.updates(key, input);       // UpdatesCall[] | UpdatesCall | null
const conclusion = await settlement.continuation(key, input); // Conclusion | null
```

每个返回值都是：

```ts
{
  value: T | null,
  raw: string,          // 实际模型原文（多次调用用 --- 连接）
  ms: number,
  fallback: boolean,    // results/updates 的保守无变化候选
  error?: string,
  evidence: {
    task, key, raw, ms, fallback, error,
    calls: [{ prompt, raw, ms, attempt, error? }],
    detail: { ...覆盖、骰点、策略、阶段错误... },
  },
}
```

`value === null` 表示没有可提交候选：输入不合法、状态缺失、head 不一致，或 continuation 真实失败。`results`/`updates` 在模型失败时会返回 `fallback:true` 的保守无变化候选（仍带错误证据）；`continuation` 绝不这样做。

## 接入 `game-model.ts`

当前文件：`frontend/src/lib/world-engine/local/game-model.ts`。

1. 在类里创建一次 settlement（构造器内）：

```ts
import {
  createSettlementHandlers,
  requireSettlementValue,
  continuationPolicy,
} from './semantics/settlement';

private readonly settlement = createSettlementHandlers({
  engine: this.engine,
  options: {
    onTask: (task, key, detail) => this.options.onTask?.(task, key, detail),
    maxTokens: {
      results: this.options.maxTokensByTask?.results,
      updates: this.options.maxTokensByTask?.updates,
      continuation: this.options.maxTokensByTask?.continuation,
    },
    temperature: this.options.temperature,
    nextRoundId: () => `round_auto_${Date.now().toString(36)}_${++this.roundCounter}`,
    continuation: continuationPolicy,
  },
});
```

如果 TypeScript 对 `onTask` 的可选字段严格，改成显式包装函数即可。

2. 替换 `run()` 的三个分支（当前约 104–106 行）：

```ts
if (task === 'results') {
  const outcome = await this.settlement.results(key, input);
  return {
    value: requireSettlementValue(outcome) as unknown as Json,
    raw: outcome.raw, ms: outcome.ms, fallback: outcome.fallback, error: outcome.error,
  };
}
if (task === 'updates') {
  const outcome = await this.settlement.updates(key, input);
  return {
    value: requireSettlementValue(outcome) as unknown as Json,
    raw: outcome.raw, ms: outcome.ms, fallback: outcome.fallback, error: outcome.error,
  };
}
if (task === 'continuation') {
  const outcome = await this.settlement.continuation(key, input);
  return {
    value: requireSettlementValue(outcome) as unknown as Json,
    raw: outcome.raw, ms: outcome.ms, fallback: outcome.fallback, error: outcome.error,
  };
}
```

`requireSettlementValue` 在 `value:null` 时抛错；`run()` 现有的 catch 会记录失败并继续抛出，控制器会停止，不会把 continuation 失败写成 handback。

3. 删除或停止调用旧实现（保留会造成两套语义）：

- `private async results(...)`：包括 `program_single_member` 单人捷径；单人也应走模型共同结算。
- `private async updates(...)`：`parseLineChanges` 文本行解析、`programMovementChanges` 关键词移动兜底。
- `private async continuation(...)`：`this.autoContinuations < 1` 上限、本地 `nextRoundId`、模型失败后的 handback。
- `normalizeChanges()`、`parseLineChanges()`、`programMovementChanges()`、`programResult()`、`mentionedLocation()`（如果只被上述逻辑使用）。
- `fallback()` 里的 `results`/`updates`/`continuation` 分支；尤其不能保留 `continuation → {kind:'handback'}`。`action`/`targets`/`reaction`/`narration` 的 fallback 可保留。
- `autoContinuations` 字段可删除；`roundCounter` 如果只用于 `nextRoundId` 则移到 settlement 的 `nextRoundId` 回调里。

4. 页面续推选项：

- `frontend/src/app/world-local/page.tsx` 现在在每次提交后调用 `modelRef.current?.resetAutoContinuations()`。保留这个调用，并让 `LocalGameModel.resetAutoContinuations()` 改为：

```ts
resetAutoContinuations(): void { this.settlement.resetContinuation(); }
```

- 页面如果有 `maxAutoContinuations: 0` 或任何固定次数默认值（当前基线没有该选项，但主树可能已加），删掉它。正常交还不能由次数决定；需要安全上限时用 `continuationPolicy.maxAutoContinuations`（默认 `null` = 不按次数交还），把 `noProgressRounds`/`repeatRounds` 作为可解释的防循环规则。
- 策略交还目前仍使用现有 `Conclusion` 的 `kind:'handback'`（共享类型只允许 `closedBy:'model'` 或 `cancel`）；具体原因是 evidence 里的 `reason: 'no_progress' | 'repeated_candidate'`。如果页面要显示“推进已暂停”而不是“世界没有后续”，需要读取该 evidence 并显示不同提示；本线不改页面。

## 验证

已跑（本线只跑必要的小范围）：

```bash
node frontend/scripts/parallel-settlement/run-focused.mjs
# 2 files, 17 tests passed

cd frontend && npx tsc -p tsconfig.world-contract.json --noEmit
# pass

cd frontend && npx eslint src/lib/world-engine/local/semantics/settlement scripts/parallel-settlement
# pass, no warnings
```

测试覆盖：

- 共同结果共享事实、逐成员归属、未准入骰点不得写成目标反应、连续无效输出回退无变化。
- 六阶段顺序、物品移动、全人物任务/个性覆盖、跨人物任务达成、已完成任务不重做、个性与理智配对、理智非法回退当前值。
- 时间扫描跳过位置/外貌，仍扫描全部任务；没有个性变化不写理智。
- 拆分阶段返回单个 `UpdatesCall`；后续阶段读取已应用工作态；同批任务达成触发个性阶段。
- 继续：likely+related 才继续；无候选交还；连续无进展/重复候选策略交还；模型失败返回 null；默认无次数上限。
- `settlement-integration.test.ts` 用真实 `ControllerDriver` + `LocalWorldTransport` + 脚本化 engine 跑通一个回合：results → 六阶段 updates → continuation → 状态提交。

## 限制和未验证

- **真实模型/浏览器推理未运行。** 全部测试是脚本化 engine；真实小模型是否按格式输出、真实耗时和页面等待未验证。需由主集成方预约资源后在真实页面复测。
- 合并 updates 会串行调用六次模型（时间扫描跳过位置/外貌，通常 3–4 次）。真实首字/整段等待未测；如果超过产品等待要求，可改用 scenario 的拆分阶段、换更小/更快的模型或优化提示词，但不能删掉阶段依赖。
- 提示词默认上限 8000 字符。大世界超出时返回 `context_capacity_exceeded` 失败，不静默截断；需要主集成方决定分批或提高上限。
- `results` 只接受完整骰点回执（`targetId/rollId/result/eligible/admitted`），与 controller 的 `groupActions.rolls` 一致；不读取、不重掷骰点。
- 共同结果对“目标是否真的达成”依赖模型语义；没有用关键词把任务判完成。任务达成只由第 3 阶段模型逐任务判断。
- 个性阶段要求每个角色都有操作（keep 也算）；弱模型可能因覆盖不完整被拒绝，回退为空个性（任务达成仍保留，理智不写），evidence 会记录。
- 拆分阶段恢复到 `sanity` 时如果本进程没有批次缓存，会用工作态里最新 `sourceSequence` 的个性变化作为理智重算对象，并在 detail 标 `sanityBasis:'latest_personality_sequence'`；这是恢复边界，正常同进程拆分不会走到。
- `results`/`updates` 的 `fallback:true` 无变化候选允许流程继续；如果产品希望模型失败时直接停，接入方应检查 `fallback` 并抛错，而不是提交无变化。continuation 没有这个选择：失败必须停。
- 本线不改 `game-model.ts`、页面、公共 controller/schedule/types、状态内核；接线由主集成方完成。

## 来源

- 语义参考：`origin/codex/d-training-source-20261110` 提交 `51bd76e97a8892a6ff012a2ebea57476deb22d4b`，`experiments/world-components-logic/short_settlement.py`（D05/D06 六阶段、共同结果）、`short_lifecycle.py`（D07 继续判断）、`tests/test_short_settlement.py`。本线按浏览器契约重写为 TypeScript，没有引入 Python 运行时依赖。
- 设计：`design/browser-world-state-workflow.md` §6.1–6.3（共同组、结果、六阶段）、§8.1（自动推进）；`design/world-engine-reports/full-design-implementation-direction.md` R09/R10。
