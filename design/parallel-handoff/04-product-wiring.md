# 04 产品接入：结算六阶段、共同结果、继续判断

本文是给 06（唯一集成）和 03/05 的接入单。代码在本线工作树
`worktrees/04-settlement`，分支 `goal/local-04-settlement`。

## 现状（2026-11-10）

- 结算三件事（`results` / `updates` / `continuation`）已经是独立模块，按控制器
  `WorldModelPort` 的真实输入形状实现，并有两条真实内核路径的测试：
  `LocalWorldTransport` + `ControllerDriver` + 本线端口，冻结、六阶段、原子提交、
  提交后叙事都由产品自己的代码跑，只有语义回答是脚本夹具。
- 产品页（06 树）目前还走 `LocalGameModel` 里的旧内联实现：
  `updates` 是单次"每行一条变化"的自由文本解析，任务/个性只按模型当时看到的内容判，
  没有六阶段；`continuation` 是单布尔 + `maxAutoContinuations: 0`，并且无论
  是否被上限截断都写 `closedBy:'model'`。
- 因此本轮的产品接入点是：**06 把 `results/updates/continuation` 三个任务换成本线端口，
  删掉 0 上限**。其余（action/targets/reaction、叙事、页面）不动。

## 精确文件名单（本线拥有，06 按来源合入）

新增：

- `frontend/src/lib/world-engine/local/turn-execution/index.ts`
- `frontend/src/lib/world-engine/local/turn-execution/port.ts`
- `frontend/src/lib/world-engine/local/turn-execution/turn-execution.test.ts`

修改：

- `frontend/src/lib/world-engine/local/semantics/settlement/continuation.ts`
  （policy stop 不再产出 `handback`；新增 `policyStop()`）
- `frontend/src/lib/world-engine/local/semantics/settlement/updates.ts`
  （位置/外貌提示压缩到上下文内；阶段覆盖与顺序不变）
- `frontend/src/lib/world-engine/local/semantics/settlement/support.ts`
  （`appearanceLine` 增加按角色数预算的紧凑模式，保留记录 id 供 replace/remove）
- `frontend/src/lib/world-engine/local/semantics/settlement/settlement.test.ts`
  （policy stop 断言）

只读依赖（不在本线改）：`local/semantics/settlement/{results,index,types,support}.ts`
在 06 树里已有同源文件，合入时以本线提交为准。

提交：`7c75cb44`（端口 + policy stop + 容量修复）、`d60e09c3`（真实内核测试）。

## 06 的接入步骤（`local/game-model.ts` + `page.tsx`）

1. 引入端口：

```ts
import { createSettlementModelPort } from './turn-execution';
```

2. `LocalGameModel` 构造时建一次（同一个语义引擎）：

```ts
this.settlement = createSettlementModelPort(engine);
```

3. `run()` 里三个任务改走端口，其余不变：

```ts
if (task === 'results') {
  const value = await this.settlement.generate('results', key, input) as Record<string, string>;
  this.lastResultsText = Object.values(value).join('；');
  return { value: value as unknown as Json, raw: '', ms: 0, fallback: false };
}
if (task === 'updates' || task === 'continuation') {
  return { value: await this.settlement.generate(task, key, input), raw: '', ms: 0, fallback: false };
}
```

4. 删除 `LocalGameModel` 里旧的 `results` / `updates` / `continuation` 方法与
   `autoContinuations` 计数（`resetAutoContinuations` 一并删）。
5. `page.tsx` 去掉 `maxAutoContinuations: 0` 和 `maxAutonomousActors: 0`
   （这两个参数在新端口里不再生效；保留会误导读者以为链被产品封死）。
6. 每个玩家提交前后调用 `settlement.beginSubmission(text)` /
   `settlement.endSubmission()`，把返回的 `PortSubmission` 记进页面的回合证据
   （这是"完整玩家提交计时"的结算侧账本：results/updates 六阶段/continuation
   各自调用次数与毫秒数）。

接入后 `updates` 是一次任务、内部按固定顺序走六个阶段（位置→外貌→任务→
小任务→个性→理智），后面阶段读到前面阶段已应用后的工作态；任务与个性阶段
扫描全部登记人物，不按在场裁剪。控制器仍然只收一个 `UpdatesCall[]`。

## 已测到的真实问题与共享修复（需要 05/06 改共享文件，本线不改）

### 1. 同一地点第二次外貌变化会被判成悬挂引用（阻断）

证据：本线 `turn-execution.test.ts` 里的
`KNOWN SHARED BUG ... second room appearance change`。真实控制器 + 真实传输，
第一回合给走廊加一条外貌变化，第二回合 `replace` 它时：

```
{"kind":"stop","reason":"dangling_updates_refs:[{\"stage\":\"appearance\",
 \"entity\":\"corridor\",\"kind\":\"change\",\"id\":\"change_7\"}]"}
```

原因：`schedule.ts` 的 `inputIds(memory)` 只收集 `state.items` 和
`state.characters` 的 `appearanceChanges` / `personalityChanges`，漏了
`state.locations`。修复（3 行，加在 item 循环旁）：

```ts
for (const location of Object.values(state.locations)) {
  for (const change of location.appearanceChanges) { changeIds.add(change.id); for (const id of change.supersedes) changeIds.add(id); }
}
```

本线测试现在标记为 expected-fail；共享修复落地后它会报“expected to fail but
passed”，那时把 `.fails` 去掉即可。

### 2. policy stop 的 `closedBy` 只能是 `model`（阻断正确记账）

`local/transport.ts` 的 `handleConclude` 对任何 `kind:'handback'` 都写
`closedBy:'model'`；`world-engine/types.ts` 的 `Conclusion` 也只允许
`model`/`cancel`。所以：

- 本线的策略停止（无进展/候选重复/显式调用上限）现在返回**没有结论值** +
  `continuation_policy_*`，页面应把它当"自动链按规则停止"，不能当模型交还；
- 若希望它作为正常交还显示，必须扩 `Conclusion`：
  `{ kind:'handback'; closedBy:'policy'; cancelReason:null; policyReason:string }`
  并让 `handleConclude` 原样保存 `closedBy`/`policyReason`。这是共享协议改动，
  由 05/06 决定；本线不擅自改。

### 3. 产品页仍把自动链封死

`page.tsx` 的 `maxAutoContinuations: 0` / `maxAutonomousActors: 0` 让"自动推进"
永远不发生，同时旧 continuation 仍写 `closedBy:'model'`。这与
`tasks/product-04-turns.md` 的"不得因 0 固定 handback 却写 closedBy:model"
正对。按上面第 5 步删除。

## 真实世界的上下文容量（本线已修）

`scripts/parallel-settlement/prompt-size.mjs` 用真实
`public/worlds/dragon-raja-free-day.world.json`（14 人物 / 26 地点 / 74 物品 /
73 任务）逐阶段构造提示词，不装模型、不产生质量证据：

| 阶段 | 修复前 | 修复后 |
|---|---|---|
| 外貌 | 11220（超过 8000，整段直接 `context_capacity_exceeded`，变化永远丢失） | 7876（覆盖 114 个实体一行不少） |
| 位置 | ~11000 | 6671 |
| 任务 | 6015 | 6015 |
| 小任务 | 5899 | 5899 |
| 继续判断 | 1047 | 1047 |

修复只压缩每行的描写长度（按实体数算预算）和把位置/容器改成 id，**没有删实体、
没有跳过阶段**；被替换的记录 id 仍然打印，replace/remove 仍可判。

## 已跑通的真实内核链路（本线测试）

`LocalWorldTransport` + `ControllerDriver` + 本线端口，语义用脚本夹具：

1. **六阶段全人物**：主角在走廊、任务负责人在门厅（视角外）。任务阶段仍判定
   该人物任务达成，个性阶段改其个性，理智阶段按新个性重算，同一点位原子提交；
   叙事在提交之后才被调用，且叙事拿到的 `after` 已含达成状态。
2. **自动轮**：继续判断给出"主角下一步"，第二回合以 `trigger:'automatic'` 提交，
   第二个点的行动判断拿到 `intentStatus:'consumed'`（玩家输入只消费一次），
   然后模型交还。
3. **策略停止**：`maxAutoContinuations: 0` 时抛
   `settlement_failed:continuation:continuation_policy_safety_cap`，不写交还、
   不改已提交点。

命令：

```bash
cd frontend
npx vitest run src/lib/world-engine/local/turn-execution --maxWorkers=1
npx vitest run src/lib/world-engine/local/semantics/settlement --maxWorkers=1
node scripts/parallel-settlement/prompt-size.mjs
```

## 还没验证（不冒充）

- **真实模型 + 真实 `/world-local` 页面**：未跑。需要 06 先按上文接入，09 用
  统一队列在 Edge+wllama 上跑 10/20 回合；本线只声明"模块在真实内核上通过"，
  不声明产品通过。
- 六阶段在 0.6B 上的实际耗时：每组 4–6 次阶段调用 + 1 次 results + 1–2 次
  continuation；必须由 09 按完整玩家提交计时，不能用本文的毫秒数代替。
- 自动轮的候选行动由 03 的行动端口执行；本线只负责"判定是否继续"。

## 状态更新（2026-11-10 20:25Z 左右，UTC）

06 已合入并发布产品入口：`results/product/integration.json` 记录 `/world-local`、`http://127.0.0.1:3221`、工作树 `worktrees/06-recovery`。本线三个提交已进入产品树：

- `8449df1e`：settlement 目录取 04 `ac1e1c0a`，删掉 `sceneScope`/`mergedStages`/`maxPromptChars`，并修了 `schedule.ts inputIds` 的位置外貌变更登记（本线原先的 `it.fails` 复现测试因此可升级为正常通过）。
- `07f75c9d`：合入 04 的 constrained 叙事（3da0831b）：叙事化事实句、按失败项的具体重试指令、被拒草稿审计、开头避让、`segments/beatCounts/mixed` 逐段来源。
- `ab7c3fd9`：合入 04 `3fc9419f`，`window.__worldSubmission` 的每条 updates 记录带 `coverage:{tasks,personality}`，可直接证明任务/个性阶段覆盖全人物而不是只覆盖当前房间。

09 取证据时注意：`window.__worldSubmission` 只保留最近一次提交，必须在每回合结束后立刻取出（脚本可每回合 `page.evaluate` 一次）。`window.__worldTurns` 是每回合计时/来源的累计数组，两者互补。

本线提供只读账本检查（不判文风、不替代 01/09 验收）：

```bash
node frontend/scripts/parallel-settlement/check-run.mjs <09 的证据文件> --cast 14
```

硬失败（缺六阶段、阶段乱序/重复、覆盖少于全人物、策略停止被记成模型交还、缺整次计时）退出码 1；回退、策略停止等作为软问题列出。

### 仍存在的标注限制（交 06/05 决定，不阻塞本线）

继续判断里“模型给了候选，但候选全是主角或不在场人物，被程序过滤后交还”目前仍写成 `closedBy:'model'`。模型确实做了判断（提出了候选），但结束自动链是程序的过滤规则，不是模型说“不要继续”。证据里 `rejectedCandidates` 和 `reason:'no_eligible_candidate'` 是真实的；只有回合结论字段的 `closedBy` 不够准确。若协议增加 `closedBy:'program'`（或 `closedBy:'policy'`），本线会把这两种情况改过去。`maxAutoContinuations:0` 造成的那种固定交还已经改成显式策略失败，不再写入 `closedBy:'model'`。
