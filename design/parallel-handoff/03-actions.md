# 03-actions handoff：自主行动、目标与被迫反应

问题、实现、导出 API、调用示例、验证、限制，以及主 agent 需要在 `game-model.ts`
里改的接线。工作树 `D:/others/Jity/.local/parallel-local-game/worktrees/03-actions`，
分支 `goal/local-03-actions`，基线 `865ae64e0901a70c3db4f1d0eb2af60268943c53`。

## 1. 问题

当前 `local/game-model.ts` 对行动/牵连/反应做了两处“点名即全部语义”的门：

- `action()`：非主角且 `!lastPlayerInput.includes(角色名) || !INTERACTION.test(lastPlayerInput)`
  直接返回 `skip`。NPC 没被玩家点名、或玩家句子没命中固定动词表，就永远不动，
  人物自己的任务、精神、现场事件完全不参与。
- `targets()`：非主角的发起者同样要求玩家点名，否则空目标。

结果是同房间 NPC 只有“被点名 + 命中动词表”才进入一次判断；`指代（他/她/对方）`、
容器/槽位位置、不在场人物、NPC 自主目标都无法表达。这不是模型能力不足，是程序
在模型之前把答案定了。

## 2. 实现

独占目录 `frontend/src/lib/world-engine/local/semantics/actions/`：

| 文件 | 作用 |
|---|---|
| `types.ts` | 处理器结果与证据类型（`issues` / `calls` / `source` / `fallback`） |
| `inputs.ts` | 读取 controller 现有调用形状（action/targets/reaction），缺 state 明确报错 |
| `scene.ts` | 从 `WorldState` 推导现场：同地点人物、容器/槽位位置、持有物、不在场名单、名字表、指代检测 |
| `prompts.ts` | 三类任务提示词；行动明确“被点名不是前提、可以不行动” |
| `checks.ts` | 程序守卫：归属性、缺席、容器、目标合法化、复述/冒名、因果呼应 |
| `index.ts` | `createActionHandlers({engine, options})`、`createActionModelPort`、提示词导出 |
| `fixtures.ts` | 测试用小世界（嵌套地点、容器物品、随身物品、异地人物） |
| `actions.test.ts` | 28 个结构/规则测试，engine 为脚本化假 engine（**不是语义证据**） |

导出（`index.ts`）：

```ts
createActionHandlers({ engine, options? }): {
  action(key: string, input: Json): Promise<HandlerResult>;
  targets(key: string, input: Json): Promise<HandlerResult>;
  reaction(key: string, input: Json): Promise<HandlerResult>;
}
createActionModelPort(engine, options?): { generate(task, key, input): Promise<Json>; handlers; evidence }
buildScene / nameTable / sceneMentions / positionLabel / roomChain
actionPrompt / targetsPrompt / reactionPrompt
```

`HandlerResult`：

```ts
{
  task, key,
  value: Json,              // 已过 structured-output 的任务 codec
  source: 'model' | 'program' | 'fallback',
  fallback: boolean,        // 仅 source==='fallback'
  elapsedMs, attempts,
  raw: string,
  issues: { code, severity: 'info'|'warn'|'error', message, entityId?, detail? }[],
  calls: { attempt, promptChars, raw, elapsedMs, decoded, error?, prompt? }[]
}
```

输入就是 `schedule.ts` 现在的声明：

- action：`{ actor, advance: { inputText, intentStatus }, workingState }`
- targets：`{ sourceId, actionText, workingState }`
- reaction：`{ sourceId, memberId, sourceActionText, rollId, workingState }`

输出与 `runtime/output-schema.ts`、`runtime/structured-output.ts` 完全一致：
`{"kind":"act","text":...}` / `{"kind":"skip"}` / `{"targets":[{"targetId":...}]}` /
反应正文。没有骰点、没有 transport 调用、没有状态写入；反应准入、已行动去重、
共同组冻结仍由 controller 管。

### 各任务的判断方式

- **action**：主角且 `intentStatus==='pending'` → 玩家原话原样作为冻结行动（0 次调用）；
  主角且 `consumed` → 只判断“同一件事是否还要继续”，不许复述原话；其他角色 →
  同房间就交给模型，按自己的待办任务、个性、精神、现场事件决定 act/skip，**不点名也问**。
  异地角色默认 `offscreenPolicy:'skip'`：0 调用、记为 `actor_out_of_scene`。这是
  **可见范围/等待预算**规则，不是点名规则——同房间角色无论是否被点名都真判断。
  `'judge'` 模式会让异地角色按自己的房间判断（提示词只给它自己房间的人/物/事件，
  隐藏主角的举动），但首次实测每次调用均值 6.3s，14 人整轮放不进等待预算，首接线
  不要默认打开。
- **targets**：始终把行动者所在房间的在场人物 + 不在场干扰名单交给模型；指代由模型
  按现场解析。程序只做事后校验：未登记 id、物品/地点当人、自己、重复、异地、超过
  `maxTargets`（默认 2）都会记录并按规则处理。没有在场候选时 0 次调用。
- **reaction**：只针对 controller 已准入的具体威胁（`sourceActionText`）生成被牵连
  角色的反应；主角作为反应成员时模型完全不写玩家角色，返回程序最小行
  “<主角名>没有作出反应。”（`protagonistReaction:'minimal'`，可改 `'model'`）。

### 语义守卫（不是词表决策）

模型输出先过 codec，再过 `checks.ts`。守卫只拒绝可证明错误的东西：

- 行动：第一人称、逐字/长片段复述玩家原话、引号里搬玩家台词、以主角为主语的
  冒名归属、把不在场的人当现场对象（直接互动动词近邻才升级为 error，普通提及只
  warn）、提到异地物品（warn）。
- 目标：未登记 id、物品/地点、自己、异地、重复、上限；行动点名了不在场人物会记
  `absent_character_named`（合法空目标）。
- 反应：复述/引用发起者原话、第一人称、以发起者或主角为主语、现场外人物、与威胁
  无呼应（只有“既没提发起者/指代也没提被牵连角色”才 error）、主角代写。

error 会带着具体理由重试一次（`attempts` 默认 2）；仍不合格才回退：
act → `skip`，targets → 空数组，reaction → “<角色名>的反应慢了半拍。”，
并保留 `repair_requested` / `repair_failed` / `decode_failure` 与原始终稿。

## 3. 调用示例（主 agent 接线）

`game-model.ts` 是主 agent 独占文件，本线不改。最小接法：

```ts
import { createActionHandlers, type HandlerResult } from './semantics/actions';

// LocalGameModel 内：
private actionHandlers = createActionHandlers({ engine: this.engine, options: {
  recentEvents: () => this.recentEvents,          // 你维护的最近结算/事件日志，最多 4 条
  onCall: (call) => this.options.onTask?.(call.task, call.key, {
    ms: call.elapsedMs, fallback: !call.decoded,
    error: call.error, raw: call.raw, promptChars: call.promptChars,
  }),
} });
private recentEvents: string[] = [];

private report(task: ModelTask, key: string, result: HandlerResult): Json {
  this.options.onTask?.(task, key, {
    ms: result.elapsedMs, fallback: result.fallback,
    error: result.issues.filter((i) => i.severity === 'error').map((i) => i.code).join(',') || undefined,
    raw: result.raw,
  });
  return result.value;
}

// generate() 的三个分支改为：
if (task === 'action') return this.report('action', key, await this.actionHandlers.action(key, input));
if (task === 'targets') return this.report('targets', key, await this.actionHandlers.targets(key, input));
if (task === 'reaction') return this.report('reaction', key, await this.actionHandlers.reaction(key, input));
```

必须删掉的旧门（否则新处理器不会被调用到这个语义）：

```ts
// action() 内，约 game-model.ts:150
const actorName = state.initial.characters[actor]?.name ?? actor;
if (!this.lastPlayerInput.includes(actorName) || !INTERACTION.test(this.lastPlayerInput)) {
  return { value: { kind: 'skip' }, raw: '', ms: 0, fallback: false };
}

// targets() 内，约 game-model.ts:196
if (source !== state.protagonistId && !this.lastPlayerInput.includes(state.initial.characters[source]?.name ?? source)) {
  return { value: { targets: [] }, raw: '', ms: 0, fallback: false };
}
```

`this.lastPlayerInput` 仍被 `programMovementChanges` 使用，保留；`INTERACTION` 常量
若无其他用途可留可删。`reaction()` 整个方法体可替换为处理器调用（`textTask` 可留给
其他任务）。

行为变化（预期）：自动接续回合里主角 `intentStatus==='consumed'` 时不再重复提交
玩家原话，而是让模型判断“同一件事是否继续”；不在场角色仍不产生正文可见的变化。
如果主 agent 暂时不想要自动回合的主角模型判断，可在接线时把 `consumed` 的主角
短路成 `{kind:'skip'}`——但那就保留了现有“重复执行/无行动”的二选一，不属于本线推荐。

`recentEvents` 的建议来源：`results()` 成功后把
`` `${角色名}：${结果文本}` `` 推入数组并截到最近 4 条；它只影响行动判断的现场
信息，不参与状态权威。

## 4. 验证

已跑（本树，单 worker）：

```bash
cd frontend
npx vitest run src/lib/world-engine/local/semantics/actions --no-file-parallelism
# 51 passed（含 run-1 / run-5 真实失败回放回归）
npx tsc --noEmit -p tsconfig.json
# 0 errors
node scripts/parallel-actions/run-action-eval.mjs --dry \
  --out ../artifacts/action-eval/dry-prompts.json
# DRY, 17 prompts dumped（无模型；证明接口、场景、提示词可运行）
```

测试覆盖（脚本化 engine，仅结构/规则证据）：不点名自主行动、点名但合法不行动、
复述/改写复述/任务目标照抄/第一人称/冒名归属/缺席人物/异地物品的重试与回退、
解析失败保留原始证据、异地角色 0 调用、异地 judge 隐藏主角上下文、主角待处理
命令原样冻结、consumed 继续判断、指代单选/歧义、姓名回映射、未点名目标/缺席目标/
物品目标/空目标/上限、合法空目标、容器内人物不可选、反应因果与任务目标照抄、
替发起者/主角行动、现场外人物、主角成员 0 调用、连续失败回退、model-port 适配器。

真实模型：`frontend/scripts/parallel-actions/run-action-eval.mjs`（Edge 157 +
wllama + Qwen3-0.6B Q4_K_M，17 个案例：含异地 skip 与异地 judge 两臂，COOP/COEP，
温度 0/种子 42）。资源锁由其他线占用时不抢跑；归档在 `artifacts/action-eval/`，
逐案记录 prompt、原始输出、解码值、issues、repair、耗时。

### 真实模型迭代（同一 17 案例、同设备同参数）

| 归档 | 改动 | 结果 |
|---|---|---|
| `run-1-unguarded.json` | 首版处理器 | 16 次调用，均值 6.3s。发现三类误收：A1 玩家动作去主语复述、A4b/A6/A7 照抄任务目标、T3/T4/T5 幻影目标；A2 首答复述玩家、A3 两次复述 |
| `run-2-guarded.json` | 加改写复述、任务目标、未点名目标守卫 | T3/T5 空目标、T4 选中诺诺、A3 正常出行动；A1/A6 被守卫拦下后回退；A4b 接受了一句计划式长句；R1/R3 仍让物品发烫 |
| `run-3-action-prompt.json` | 在指令里加具体反例 | 反例被逐字复制进 5 个无关案例（“伸手把电池按进卡槽”）→ 该提示方向作废，反例删除 |
| `run-4-copy-constraint.json` | 改为“不能包含玩家原话连续 8 字” | A2 首答即过；A1/A6 仍复述后回退 |
| `run-5-subject.json` | 要求行动句带主语 | A1/A6 看似通过，实为假通过：A1 把“诺诺”加在玩家句前，A6 照抄诺诺的任务目标；守卫按证据收紧（双向覆盖 + 全人物目标），主语要求回退 |
| `run-6-final.json` | 交付代码 | 17 案例 / 16 次调用，均值 6.1s，p50 6.9s，最大 10.6s。见下 |

`run-6-final` 的具体结论：

- **行动（8）**：A1 不点名自主行动两次都复述玩家 → 守卫拒绝并回退 `skip`（不冒名，
  但这个 0.6B 模型确实写不出独立的诺诺行动）；A2/A3/A7 正常出行动（A2 首答即过）；
  A4a 范围跳过 0 调用；A4b 异地判断接受了一句计划式长句（质量缺口，不是守卫漏放）；
  A5 玩家待处理命令原样冻结 0 调用；A6 consumed 首答复述玩家被拒，第二答
  “把胸前护目镜推上去”被接受（部分复述，仍是限制）。
- **目标（6）**：T1 指代→诺诺、T2 歧义指代→芬格尔（按现场论证）、T3 找楚子航→空目标
  并记 `absent_character_named`、T4 容器场景→诺诺（笼内秦越不可选）、T5 移动→空目标；
  T6 同时点名两人只回诺诺（少选，提示词已要求“点名要回应的人通常都列入”但模型未做到）。
- **反应（3）**：R1/R3 通过归属/复述/因果守卫，但仍写出“识别带微微发烫”这类未登记的
  物品状态，且没有真正回应递地图这条威胁；R2 主角成员 0 调用，程序返回
  “路明非没有作出反应。”。

结论：点名门已移除（A1/A2/A3/A7 都真实调用模型），目标因果由 T3/T4/T5 的修复验证，
反应归属/复述由守卫保证；剩余失败集中在 **0.6B 语义模型自身的行动/反应写作能力**
（A1、A6、A4b、R1/R3）。主 agent 接入时若要这两类也达标，需要换更强的语义模型或
接受“写不出就回退不行动/最小反应”的保守行为，不能把回退冒充成模型通过。

运行方式（资源锁被占时不抢跑）：

```bash
python D:/others/Jity/.local/parallel-local-game/resource_lease.py acquire --lane 03-actions --purpose "action/targets/reaction real-model probe"
cd frontend
node scripts/parallel-actions/run-action-eval.mjs   --assets D:/others/Jity/.local/world-narration-worktree/frontend/public   --out ../artifacts/action-eval/run.json
python D:/others/Jity/.local/parallel-local-game/resource_lease.py release --lane 03-actions
```

## 5. 限制与未覆盖

- 未登记且从未出现在世界里的**新专名**无法靠程序识别（没有词表就不知道它是专名）；
  本线只处理“已登记但不在场”的实体，以及物品/地点被误当人物。模型凭空造的新名字
  仍要靠后续结果/叙事事实门。
- 指代解析交给模型；程序只记录 `anaphora_present`，无法独立核对“他”指谁。
- 异地角色默认范围跳过（0 调用），异地任务不会在主角场景里产生可见变化；
  `offscreenPolicy:'judge'` 可让它们在自己的房间判断并推进全局状态，但实测均值
  6.3s/次，14 人整轮约 88s，超出当前等待预算。两种模式都记录原因，同房间角色
  不受影响，不是全人物固定 skip。
- 反应与威胁的“因果”程序只能做到拒绝明显错误（复述、主语错位、现场外人物、完全
  无呼应），不能证明语义因果；最终仍由读评/叙事事实门确认。
- 主角作为反应成员时返回“没有作出反应。”是保守程序下限，保留玩家决定权；是否要在
  页面层改成“给玩家一个反应机会”的交互，不在本线范围。
- 0.6B 语义模型在 A1（不点名自主行动）和 A6（主角续写）上写不出合格行动，守卫会
  回退为不行动；A4b 接受计划式长句；R1/R3 仍会写未登记的物品状态。这些是模型能力
  限制，不是守卫漏放（回放测试证明同类错误会被拒绝），换模型或接受保守回退由主
  agent 决定。
- 行动的部分复述（A6 第二答“把胸前护目镜推上去”）在现有阈值下会通过；再收紧会
  误伤 A2 这类“按玩家请求行动”的合法回复，故保留并如实记录。
- 本线没有接入页面/E2E，也没有改 `game-model.ts`、`prompt.ts`、controller/schedule/types；
  真实模型结果已跑，但不等于整链验收通过。
