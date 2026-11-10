# 06 交付装配：叙述候选进入同一个产品页面

本线把已经可用的叙述候选（B=02 的 committed-fact beats、C=04 的 constrained fact-to-prose）做成薄适配：从已结算的点投影出候选需要的材料、按内部配置选一个、把候选的真实增量与最终裁决映射回页面现有回调。不训练模型、不改页面文件、不造第二套状态。

## 1. 页面拿到的一段正文是怎么来的

`LocalGameModel.narration()` 收到 controller 组装好的一个点：

```
{ pointId, before: WorldState|null, delta: { timeAdvance, entityDeltas }, after: WorldState, perspective }
```

补丁让它在原来的单发写作之前先问选择层：

1. **投影**（`selection/projection.ts`，只读）
   - `facts`：本点已结算的事实（换房间、在场、任务完成、人格变化、精神值变化），全部从 `before`/`delta`/`after` 抄出，不从正文猜。
   - `inputText`：lane 01 的 `yuyan-prose-result-v2` 序列化（`projectNarrationInput` + `renderResultInput`）。投影失败就记为缺失，需要输入的候选被跳过，不拼假输入。
   - `policy`/`scene`：视角、名册、地点、同房间的人与物、时间推进、长度与温度上限。只做许可，不产生事实。
2. **选候选**（`selection/runner.ts`）：`globalThis.__jityNarrationCandidate`（内部 QA）→ 调用方 `narrationCandidate` 选项 → `auto`（只跑 `productDefault: true` 的候选）。
3. **裁决**：候选自己 `accepted` 才可能是本点正文；拒绝/超时/取消/抛错一律回落到原来的单发写作，并把原因记在内部日志里。被拒绝的草稿不会提交。

## 2. 现在装进来的候选

| 候选 | 来源提交 | 入口 | 产品默认 |
|---|---|---|---|
| B：committed-fact beats | `92c2d95e`（含 `211fd463` 的 beats 与训练形状输入） | `generateCandidate({ committed, inputText, policy.scene, … })` | 否 |
| C：constrained fact-to-prose | `b18d36d7`（`constrained/` 全目录） | `generateCandidate({ committed, policy: { mode, scene, resultsText, … } })` | **是**（`mode: 'program'`） |
| A：instruct | 只有 `goal/local-03-actions` 的 `e74ac849`，未合入 | `generateCandidate({ state, before, delta, playerAction, … })` | 未交付 |

**B 为什么不是默认**：在本机真实模型上，B 的 beats 路径没有在页面所用叙述模型（`qwen25-1.5b-narr-Q4_K_M`）上通过自己的逐段校验；把默认切过去就是每轮先花几十秒再回退。用 `qwen2.5-1.5b-instruct-q4_k_m` 时 B 曾接受过一段（434.6 s），但其中有一句是模型自己加的道具动作，只能算证据，不能当产品默认。

**C 为什么是默认**：程序按已结算事实逐句成文，不调用模型，本轮实测 22–89 ms；它的每一句都受事实投影和校验约束（细节见第 6 节限制）。它是**明确的降级**：页面会把这段标成“正文已按已结算事实修正：程序按已结算事实成文”，不会说成模型正文。

**A 为什么没有交付**：`e74ac849` 的模块本身能编译，但它的测试 fixture 在已整合的状态内核（`f9af7ea9` 起）下会抛 `id_unresolved: entity key uses slot slot_pocket outside ally`（22 个测试失败）。这是 lane 03 需要修的 fixture/内核兼容问题；把失败测试带进主树不是“可用候选”。等它修好，新增一个 `selection/instruct.ts` 并加入 `SHIPPED_CANDIDATES` 即可。

## 3. 接线补丁（主集成树最小改动）

补丁只改 `frontend/src/lib/world-engine/local/game-model.ts`，页面 `page.tsx` 不需要改。

补丁做四件事：

1. 引入 `createNarrationRunner`，新增内部选项 `narrationCandidate?: 'auto' | 'trained' | 'instruct' | 'constrained' | 'builtin'`（默认 `auto`）。
2. 构造函数按选项建 runner；`builtin` 不建。
3. `narration()` 先尝试候选；只有 `adopted` 直接返回，其余继续原来的单发写作。
4. 新增 `adoptNarrationCandidate()`：把候选的真实流式片段映射到 `onNarrationProgress`，把裁决映射到 `onTask`/`onNarrationComplete`；`grade: 'program'` 时 `fallback: true` 并给出降级原因，只有 `grade: 'candidate'` 才 `fallback: false`。接受过的正文作为下一轮的 `priorText`。

补丁文件（内容寻址，不覆盖旧文件）：

```
frontend/scripts/candidate-shipping/patches/world-narration-candidate-ff1574dd9ccb-632f408ed1bc.patch
frontend/scripts/candidate-shipping/patches/manifest.json
```

`manifest.json` 记录输入 `game-model.ts` 的 sha256（本轮 `ff1574dd9ccb…`）、补丁 sha256、转换步骤、新增文件及其 sha256、`git apply --check` 结果、前提条件、是否过期，以及被取代补丁的历史。主树该文件一变，重跑生成器就会产出新文件名并把旧补丁标成 `stale`；`--prune` 只把旧文件移入 `history`，不静默覆盖。

应用（仓库根）：

```bash
git apply -p1 frontend/scripts/candidate-shipping/patches/world-narration-candidate-ff1574dd9ccb-632f408ed1bc.patch
```

启用其它候选（内部配置，不进玩家界面）：

```ts
// page.tsx 里创建 LocalGameModel 的 options
narrationCandidate: 'trained',   // 评估 B
// narrationCandidate: 'constrained' 是默认值，不需要写
```

## 4. 页面实际跑出来的结果

真实页面（Edge + WebGPU，`/world-local`，补丁后的 `game-model.ts`）：

| 轮次 | 候选 | 候选结果 | 页面正文 | 用时 |
|---|---|---|---|---|
| 世界开局 | B（内部覆盖 `trained`） | 拒绝：`too_short+all_beats_fell_back` | 原位模型正文，标注 `movement_without_fact,low_support` | 整轮 503.8 s，正文 63.3 s |
| 第一轮（C 默认，修复前） | C | 开局点拒绝（`too_short`），回合点接受 | 回合正文 0.1 s，降级标注 | 整轮 110.9 s |
| 第一轮（C 默认，修复后） | C | 开局点不可用（`root_point`），回合点接受 | `一分钟之后。路明非没有停，从西侧服务巷进入器材棚。秦越也在器材棚。秦越也没有动。` 标注“程序按已结算事实成文” | 整轮 109.4 s，正文 0.089 s |

开局那一次仍由原模型写（65.9 s），因为程序候选在开局点没有 before 可对照，主动让位。

## 5. 验证命令与证据

```bash
cd frontend
npx tsc -p tsconfig.world-contract.json                 # 通过
npx vitest run src/lib/world-engine/local/narration-candidates --maxWorkers=1   # 15 + 20 个测试
node scripts/candidate-shipping/build-patch.mjs --prune # 生成 + apply --check
node scripts/candidate-shipping/run-wiring-check.mjs --out ../../../results/06-recovery/wiring-check.json
```

`run-wiring-check.mjs` 用补丁后的真实 `game-model.ts` 驱动 `generate('narration')`，16 项全过：候选接受时正文与真实增量直达页面、拒绝时回落到原位路径、`auto` 不调模型只出程序正文并标降级、`builtin` 完全不碰候选、被取消的草稿不会成为下一轮 `priorText`。

真实模型/程序证据：

- `results/06-recovery/real-candidate-constrained-program.json`：C 程序模式接受 48 字，22 ms，未调用模型。
- `results/06-recovery/real-candidate-instruct15.json`：B + instruct 1.5B 接受 104 字，434.6 s，首 token 8.2 s，两条 soft `unverified_sentence`（其中有模型自加的道具动作，只作证据）。
- `results/06-recovery/real-candidate-15bnarr-v3.json`：B + 页面叙述模型，拒绝（`too_short+all_beats_fell_back`）。
- `results/06-recovery/product-turn.json`、`product-turn-constrained-2.json`：真实页面整轮，含候选内部日志、页面正文、降级标注、快照字节数。
- `results/06-recovery/wiring-check.json`：补丁后游戏模型的 16 项接线检查。

## 6. 已知限制

- C 程序正文是**降级**：事实覆盖正确，但句子平、缺少场景质感；本轮真实输出里还有一句“秦越也没有动”属于程序自己补的动作（lane 04 的 realizer/verifier 需要处理）。页面已明确标注，不冒充模型正文。
- C 的程序模式不调用模型；`mode: 'model'` 可用同一骨架逐段生成并校验，但在页面叙述模型上的接受率尚未验证。
- B 在页面叙述模型上不稳定：同一模型在 GPU 上 60 token 约 10.7 s，但逐段校验经常以 `too_long`/`fact_event_added`/`time_missing` 拒绝，随后整段回退。
- A 未交付：fixture 与已整合内核不兼容（见第 2 节），不是本线可以修改的文件。
- 开局点仍走原单发模型（约 66 s），候选明确让位；这一轮没有候选加速。
- 取消：session 的取消路径没有改；程序候选瞬时完成，不存在取消窗口；B 的多段生成在取消后要等当前引擎调用返回（引擎中断由 runtime 线负责）。
- 刷新/继续：沿用 lane 06 的 IndexedDB checkpoint 与 `priorText`（只有接受过的正文进入下一轮）；页面本身仍用 localStorage 单槽（主树页面未接线），本补丁不改变这一点。
- 只在 Chromium/Edge（Windows）上验证。
