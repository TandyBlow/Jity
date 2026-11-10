# 06 交付装配：把叙述候选接进同一个产品页面

本线只做三件事：把一个已经结算的点投影成候选需要的材料、按内部配置选一个候选、把候选的**真实**增量与最终裁决映射回页面现有的回调。它不训练模型、不重写页面、不造第二套状态。

## 1. 一条回合的完整路径

输入来自 controller 已有的 `narration` 模型调用（`assembleNarrationInput`）：

```
{ pointId, before: WorldState|null, delta: { timeAdvance, entityDeltas }, after: WorldState }
```

页面上的模型对象（`LocalGameModel`）在 `narration()` 里先问选择层，选择层做三件事：

1. **投影**（`selection/projection.ts`）：从 `before`、本点的 `delta`、`after` 三个已结算记录里抄出
   - `facts`：本点必须/可以写入正文的事实（`moved` 换房间、`at` 在场、`sanity`/`sanity_changed`、`task_achieved`、`personality_changed`）；
   - `inputText`：lane 01 的 `yuyan-prose-result-v2` 序列化结果（`projectNarrationInput` + `renderResultInput`），不是本地手写状态串；
   - `policy`/`scene`：视角、全名册、地点名、同房间的在场者与物品、时间推进、长度与温度上限。

   投影只读：不改状态、不推测变化。投影失败（例如没有 before）时 `inputText` 记为缺失，需要输入的候选会被跳过，而不是拼一个假输入。

2. **选候选**（`selection/runner.ts`）：顺序是
   - `globalThis.__jityNarrationCandidate`（内部 QA 覆盖，页面不展示）；
   - 调用方传入的 `candidate`；
   - `auto`：只考虑 `productDefault === true` 的候选。

3. **裁决**：
   - 候选 `accepted === true` → 返回 `adopted`，这段正文就是本点的正文；`onNarrationProgress` 收到的是候选自己的真实流式片段，`onTask('narration')` 标记 `fallback: false`。
   - 其余情况（拒绝、取消、超时、抛错、没有可用候选）→ 返回 `fallback`，并让原位模型路径继续写正文。页面已有的降级提示保持不变；被拒绝的候选草稿**不会**被当成正文提交。

## 2. 当前唯一可交付的候选

| 路由 | 来源 | 入口 | 状态 |
|---|---|---|---|
| B（训练/committed-fact beats） | lane 02 提交 `211fd463` | `generateCommittedNarration({ committed, inputText, policy })`，`policy.mode='beats'` + `scene` | 已适配（`selection/trained.ts`） |
| A（instruct） | lane 03 | 仅有未提交的 `narration-candidates/instruct/types.ts` | 未提交，没有可导入的入口 |
| C（fact-control） | lane 04/07 | 仅有未提交的 `types.ts` | 未提交，没有可导入的入口 |

B 的适配只做四件事：把 `facts` 当事实许可、把 lane 01 的序列化结果当许可证据、把 `policy`/`scene` 传进去、把 `GeneratedNarration` 的 `accepted/issues/timings/beats` 原样映射出来。它不重写候选的提示词、不用别的序列化格式、不把拒绝改成接受。

B 的 `productDefault: false`：真实模型证据目前没有一条被接受的正文（见 `results/02-narration/real-model-*.json`，0/3、0/3、0/3）。选择层不会拿“单测通过”冒充“正文可用”。要让产品默认走 B，必须先在真实模型上拿到 accepted 记录，再把 `trained.ts` 里的 `productDefault` 改成 `true`（一行），`auto` 就会自动选中它。

## 3. 接线补丁（主集成树可直接应用）

补丁只改一个文件：`frontend/src/lib/world-engine/local/game-model.ts`；页面 `page.tsx` **不需要改**。

- 新增内部选项 `narrationCandidate?: 'auto' | 'trained' | 'instruct' | 'constrained' | 'builtin'`（默认 `auto`）。
- 构造函数按选项创建 `createNarrationRunner`；`builtin` 时不创建。
- `narration()` 先尝试候选；只有 `adopted` 才直接返回，其余继续走原来的单发提示词 + 校验 + 裁剪路径。
- 新增 `adoptNarrationCandidate()`：映射流式增量、`onNarrationComplete`、`onTask`，并只在接受时更新 `lastAcceptedNarration`（下一轮作为 `priorText` 传给候选，避免重复上一段）。

补丁文件（内容寻址，不覆盖旧文件）：

```
frontend/scripts/candidate-shipping/patches/world-narration-candidate-<输入哈希>-<补丁哈希>.patch
frontend/scripts/candidate-shipping/patches/manifest.json
```

`manifest.json` 记录：输入文件路径 + sha256、补丁 sha256/字节数、转换步骤 id、新增文件与各自 sha256、`git apply --check` 结果、前提条件、是否过期（`stale`）。输入变化后重新运行生成器会产出新文件名，并把旧补丁标成 `superseded`/`stale`，不会静默覆盖。

前提：目标树必须已包含 lane 02 的 `211fd463`（beats + trained-input），否则 `selection/trained.ts` 引用的 `policy.mode/scene`、`result.beats` 不存在。

应用方式（在主集成树的仓库根）：

```bash
git apply -p1 <补丁文件>
```

启用 B 做评估（主集成者只改这一处，仍是内部配置）：

```ts
// page.tsx 里创建 LocalGameModel 的 options 增加一行
narrationCandidate: 'trained',
```

不想改页面时，用内部覆盖（脚本注入 `window.__jityNarrationCandidate = 'trained'`）也能让同一页面走 B；玩家界面不出现候选名、模型名或测试细节。

## 4. 页面拿到的结果

| 情况 | 页面看到的正文 | `onTask('narration').fallback` | 说明 |
|---|---|---|---|
| 候选接受 | 候选正文 | `false` | 流式片段是候选真实输出 |
| 候选拒绝/超时/取消/抛错 | 原位模型路径的正文（原有行为） | 由原位路径决定 | 控制台只有一行内部 `[narration] candidate fallback <reason>` |
| `auto` 且没有产品默认候选 | 原位模型路径的正文 | 由原位路径决定 | 不会多花一次模型调用 |

取消、刷新、继续回合不新增机制：取消仍走 session 的 `round_conclusion_cancel` 与引擎级中断；刷新仍由 lane 06 的 IndexedDB checkpoint 恢复；继续回合把上一段**已接受**的正文作为 `priorText` 交给候选（未被接受的不进历史）。

## 5. 验证

在本线工作树：

```bash
cd frontend
npx tsc -p tsconfig.world-contract.json
npx vitest run src/lib/world-engine/local/narration-candidates --maxWorkers=1
node scripts/candidate-shipping/build-patch.mjs            # 生成补丁 + apply --check
node scripts/candidate-shipping/run-wiring-check.mjs       # 在打好补丁的树上驱动真实 game-model
```

`run-wiring-check.mjs` 默认读取 `D:/others/Jity/.local/parallel-local-game/scratch/shipping-06`（主树 HEAD + live 文件 + 本补丁）。它验证：候选接受时正文与流式增量直达页面、拒绝时回落到原位路径、`auto` 不触发候选、第二轮拿到上一段已接受正文。

真实模型（需先申请资源锁）：

```bash
python D:/others/Jity/.local/parallel-local-game/resource_lease.py acquire --lane 06-recovery --purpose "..."
node scripts/candidate-shipping/run-real-candidate.mjs --tree <打过补丁的树>
python D:/others/Jity/.local/parallel-local-game/resource_lease.py release --lane 06-recovery
```

证据写到 `results/06-recovery/real-candidate.json`：模型 sha256、加载耗时、投影（事实/输入长度/场景）、流式事件数、候选裁决、被拒绝时的逐 beats 来源与文本。`--projection-only` 不加载模型，只验证真实世界上的投影。

## 6. 已知限制

- 目前没有一条被真实模型接受的候选正文；B 的 beats 路径在真实世界上能跑通（投影、输入、逐 beat 生成、裁决），但接受与否以证据为准，不在此处宣称质量。
- A/C 的入口尚未提交，本线只留了适配位与统一契约；它们落地后需要新增一个 `selection/<route>.ts` 并在 `SHIPPED_CANDIDATES` 里加一行。
- 取消不会中止候选正在进行的单次生成（引擎中断由 runtime 线负责，页面取消后由 session 丢弃输出）；候选的多 beat 生成可能在取消后继续占用设备直到当前调用返回。
- 候选的流式片段在页面上的显示与原来一致：未验证的片段不会被标成已验证，但页面也没有第二次校验。
- 补丁绑定主集成树当前 `game-model.ts` 的字节；主树该文件再改动后必须重新生成（`manifest.json` 会标 `stale`）。
- 只在 Chromium/Edge 上验证；Firefox/Safari 未测。
