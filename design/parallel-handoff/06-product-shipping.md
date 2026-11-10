# 06 交付装配：叙述候选进入同一个产品页面

本线把已经可用的叙述候选（B=02 committed-fact beats、C=04 constrained fact-to-prose）做成薄适配：从已结算点投影出候选需要的材料、按内部配置选一个、把候选的真实增量与最终裁决映射回页面现有回调。不训练模型、不改页面文件、不造第二套状态。

**当前没有合格的模型候选，但页面不会退回成流水账。** 用户的产品口径是：模型正文优先，状态流水账/程序文本只能是明确降级的回退。B 在页面叙述模型上没有被接受；C 程序版是明确降级；C 模型版在 instruct 模型上虽有 223 字接受记录，但夹带编造动作、且部分是程序段。三者都还不满足“事实 + 文风”的合格叙事条件，所以：

- `auto` 仍然先让原来的单发写作生成；模型正文通过它自己的事实校验时，页面显示模型正文。
- 单发写作自己拒绝这一轮时，补丁用 C 的骨架 + 07 合成器写一段程序正文（约 0.1 s、不调用模型），并在页面标注“程序按已结算事实成文”。这只是可读的降级，不是合格叙事。
- 程序文本不会写入下一轮的 `priorText`，也不会被标记成高质量结果。

候选通过内部开关随时可开；等 02/10/03/04 交出真正合格的正文后，主集成者只需把该候选设为 `productDefault`。

## 1. 页面拿到一段正文的完整路径

controller 把已结算点组装成 `narration` 输入：

```
{ pointId, before: WorldState|null, delta: { timeAdvance, entityDeltas }, after: WorldState, perspective }
```

补丁让 `LocalGameModel.narration()` 在原来的单发写作之前先问选择层：

1. **投影**（`selection/projection.ts`，只读）
   - `facts`：换房间、在场、任务完成、人格变化、精神值变化，全部从 `before`/`delta`/`after` 抄出。
   - `inputText`：lane 01 的 `yuyan-prose-result-v2` 序列化（`projectNarrationInput` + `renderResultInput`）；投影失败就记缺失并跳过需要输入的候选，不拼假输入。
   - `policy`/`scene`：视角、名册、地点、同房间的人与物、时间推进、长度与温度上限。只做许可，不产生事实。
2. **选候选**（`selection/runner.ts`）：`globalThis.__jityNarrationCandidate`（内部 QA）→ `narrationCandidate` 选项 → `auto`（只跑 `productDefault` 的候选）。
3. **裁决**：候选自己 `accepted` 才可能成为本点正文；拒绝/超时/取消/抛错一律回落到原来的单发写作，原因写在内部 console。被拒绝的草稿不会提交。程序成文即使被接受，也以 `grade: 'program'` 送进 `onTask`，页面标注降级。
4. **单发写作之后的降级**：如果单发写作也没有通过事实校验，补丁调用 `runner.generateProgram()`，用同一个已结算点让 C 的骨架 + 07 合成器写程序正文；它按 `fallback:true` + “程序按已结算事实成文”提交。模型正文已经被接受时不会走这一步。

## 2. 装进来的候选

| 候选 | 来源提交（已合入本线） | 入口 | 内部开关 | 产品默认 |
|---|---|---|---|---|
| B：committed-fact beats | `211fd463` + `92c2d95e` | `generateCandidate({ committed, inputText, priorText, policy })`，`mode: beats \| scene` | `narrationCandidate: 'trained'`，可选 `trainedMode` | 否 |
| C：constrained fact-to-prose + 07 成文 | `11e7433b`（04 骨架，facts-only scene hints + 结算结果原句）+ 07 的 composer（补丁内嵌，源提交 `69915b49`） | `generateCandidate({ committed, inputText, priorText, policy: { mode, scene, resultsText, composer, … } })` | `narrationCandidate: 'constrained'`，可选 `constrainedMode: program \| model` | 否 |
| A：instruct | 只有 `goal/local-03-actions` 的 `e74ac849`，**未合入** | `generateCandidate({ state, before, delta, playerInput, … })` | 无 | 未交付 |

- B 的两种模式都实测过：beats 在页面叙述模型（`qwen25-1.5b-narr`）上被逐段拒绝；scene 写出 226 字流畅正文，但因漏掉已结算移动和时间被拒；再加“必须写出移动和时间”的约束后，模型写出了移动，却又编造钥匙、钥匙环等动作、仍然漏掉时间，仍被拒（拒绝草稿都原样保存，没有当成正文提交）。
- C 的 `program` 模式把每段交给 07 的 composer（补丁内嵌，源提交 `69915b49`），不调用模型；真实点位上 125 字、28 ms 接受；`model` 模式在 `qwen2.5-1.5b-instruct` 上 223 字接受（约 121 s），但夹带模型自加动作，且部分段由程序补写，不能算合格叙事。
- A 未交付：`e74ac849` 的模块能编译，但 22 个自带测试在已整合内核下失败（`id_unresolved: entity key uses slot slot_pocket outside ally`）。这是 lane 03 的 fixture 与内核兼容问题；把失败测试带进主树不是“可用候选”。它修好后新增 `selection/instruct.ts` 并加入 `SHIPPED_CANDIDATES` 即可。

## 3. 最小接线补丁

补丁只改 `frontend/src/lib/world-engine/local/game-model.ts`，页面 `page.tsx` 不用改。

- 候选的提示词现在按页面的聊天模板包一层（`engineTemplate: 'chatml'`，页面 `narrationMode: 'instruct'` 时自动开启），与单发写作完全相同的 `<|im_start|>user…<|im_end|><|im_start|>assistant` 形状；此前候选发的是纯文本，聊天模型没有按它训练时的形状回答，这是逐段失败的一个可疑原因。真实模型验证（`--template chatml`）：第一段模型调用跑满 180 s 生成期限、没有产出，整篇回落程序——模板不是唯一原因，1.5B 在本机 CPU 上逐段写作太慢。
- 新增内部选项 `narrationCandidate?: 'auto' | 'trained' | 'instruct' | 'constrained' | 'builtin'`（默认 `auto`）。
- 构造函数按选项建 `createNarrationRunner`；`builtin` 不建。
- `narration()` 先尝试候选；只有 `adopted` 直接返回，其余继续原来的单发路径。
- 新增 `adoptNarrationCandidate()`：真实流式片段 → `onNarrationProgress`；`accepted && grade==='candidate'` → `onTask(fallback:false)` + `onNarrationComplete`；`accepted && grade==='program'` → 同样提交正文，但 `onTask(fallback:true, error:'程序按已结算事实成文')`，页面显示降级标注；拒绝 → 返回 null，原位写作接管。
- 单发写作拒绝时，`generateProgram()` 写程序正文并同样标注降级；单发写作接受时把正文写入 `lastAcceptedNarration`，下一轮作为 `priorText`。只有非程序的接受文本进入下一轮 `priorText`。

补丁文件（内容寻址，不覆盖旧文件）：

```
frontend/scripts/candidate-shipping/patches/world-narration-candidate-57e4316fd20e-dffabefe1b1a.patch
frontend/scripts/candidate-shipping/patches/manifest.json
```

补丁新增 29 个运行时文件：选择层 + 02 的 beats 模块（内嵌在 `narration-candidates/trained-generation`，主树自己的 `narration-generation` 不动）+ 04 的 constrained 骨架 + 07 的 composer。因此它不依赖主树先合入 02/04/07 的分支，直接对当前 `game-model.ts` 快照生效；这三个目录仍由各自 lane 拥有，补丁里的副本只用于装配。

`manifest.json` 记录输入 `game-model.ts` 的 sha256（当前主树 `2c25891317b8…`；主树正在被持续编辑，应用前必须按 manifest 核对哈希，变了就用 `node scripts/candidate-shipping/build-patch.mjs --prune` 重新生成。旧输入快照的补丁都标记为过期并移入 history）、补丁 sha256/字节数、转换步骤、新增文件与各自 sha256、内嵌来源提交、`git apply --check` 结果、是否过期，以及被取代补丁的历史（`--prune` 只把旧文件移入 `history`）。

应用（仓库根）：

```bash
git apply -p1 frontend/scripts/candidate-shipping/patches/world-narration-candidate-57e4316fd20e-dffabefe1b1a.patch
```

页面侧完整调用示例（`page.tsx` 的模型构造；除第一行外都是现状）：

```ts
const model = new LocalGameModel(semantic, {
  narrationEngine: narration,
  narrationMode: 'instruct',
  narrationMaxTokens: 240,
  narrationTemperature: 0.45,
  narrationCandidate: 'constrained',   // 内部评估；默认 auto = 不启用候选
  maxAutoContinuations: 0,
  onTask: (task, key, detail) => {
    // 现有代码：detail.fallback 时把 detail.error 显示成降级说明
  },
  onNarrationProgress: (progress) => { /* 现有流式显示 */ },
  onNarrationComplete: (progress) => { /* 现有落定显示 */ },
});
```

候选自己的调用（选择层内部）：

```ts
const runner = createNarrationRunner({ engine: narration, candidate: 'constrained', constrainedMode: 'program' });
const result = await runner.generate(point, (state) => {/* 真实增量 */});
// result.kind === 'adopted' ? result.text : 交给原位写作
```

### 取消 / 刷新 / 继续回合

- **取消**：补丁不新增取消路径。页面取消仍走 session 的 `round_conclusion_cancel`；程序候选瞬时完成，没有取消窗口。B 的多段生成要等当前引擎调用返回，引擎级中断属 runtime 线。
- **刷新**：本补丁不改页面存储。要在“写正文中途刷新”后保住候选进度，按 `design/parallel-handoff/06-recovery.md` §6 把 `LocalGameSession.open(openLocalProgressStore(), …)` 接进页面；候选选择与该改动互不影响（选择层只读状态）。
- **继续回合**：只有被接受的正文进入 `priorText`（wiring check 已覆盖“被取消/拒绝的草稿不会成为下一轮 priorText”）。

## 4. 真实页面跑出来的结果

页面 `/world-local`，Edge 157 + WebGPU（Intel gen-12lp），补丁后的 `game-model.ts`：

| 轮次 | 候选 | 候选结果 | 页面正文 | 用时 |
|---|---|---|---|---|
| 开局 + 第一轮 | B（内部 `trained`） | 开局段落拒绝：`too_short+all_beats_fell_back` | 原位模型正文（标注 `movement_without_fact,low_support`） | 整轮 503.8 s |
| 开局 + 第一轮 | C v1.1 程序（内部 `constrained`） | 开局点 `root_point` 让位；回合点接受 | 0.1 s 程序正文 + 降级标注 | 整轮 110.9 s |
| 开局 + 第一轮 | C v1.3 + 04 realizer（旧补丁） | 开局点让位；回合点接受，含结算结果原句 | 0.1 s 程序正文，标注降级 | 整轮 118.0 s |
| 开局 + 第一轮 | 补丁 `dffabef`，默认 `auto`（真实主树快照） | 开局与回合的单发写作都被自己的校验拒绝，补丁各写一次程序正文 | 两段都显示 04+07 程序正文，带结算结果句 `路明非：无判定。`，标注“程序按已结算事实成文” | 就绪 137.3 s；整轮 163.0 s（其中回合写作 113.6 s） |

C v1.3 页面正文（`results/06-recovery/product-turn-constrained-v13.json`）：

```
整整一分钟过去。

器材棚里，推拉门可回服务巷。

路明非没有停，从西侧服务巷进入器材棚。

秦越也在器材棚，灰色器材背心套在校服外，胸前挂着领用牌。

器材棚里，路明非的护目镜还在原处；镜片无裂纹，镜带松着，现挂在胸前而非戴在眼前。

路明非的演习背心在器材棚，背心前襟完好，没有演习弹痕；胸袋能放一只弹匣，肩上没有阵营识别带。

路明非：无判定。

秦越也没有动。
正文已按已结算事实修正：程序按已结算事实成文
```

它仍是降级文本：最后两句“没有停/也没有动”是程序补的动作，不是事实；页面已明确标注，不冒充模型正文。

## 5. 验证

```bash
cd frontend
npx tsc -p tsconfig.world-contract.json
npx tsc --noEmit -p tsconfig.json
npx vitest run src/lib/world-engine/local/narration-candidates --maxWorkers=1
node scripts/candidate-shipping/build-patch.mjs --prune
node scripts/candidate-shipping/run-wiring-check.mjs --out ../../../results/06-recovery/wiring-check.json
node scripts/candidate-shipping/run-real-candidate.mjs --tree <打过补丁的树> --candidate constrained --mode program
node scripts/candidate-shipping/run-product-turn.mjs --base http://127.0.0.1:<port> --candidate constrained
```

`run-wiring-check.mjs` 用补丁后的真实 `game-model.ts` 驱动 `generate('narration')`，20 项全过：接受候选时正文与真实增量直达页面；拒绝时回落到原位路径；`auto` 先让原位模型写，模型自己拒绝时用 04+07 程序正文降级并标注；`builtin` 完全不建 runner；被取消的草稿不会成为下一轮 `priorText`。

证据文件：

- `results/06-recovery/real-candidate-composer-program.json`：04 骨架 + 07 composer，真实点位 125 字、28 ms、未调用模型。
- `results/06-recovery/real-candidate-composer-program-v2.json`：同一真实点位带结算结果句，132 字；07 composer 写场景/移动/收束，04 realizer 写 `路明非：无判定。`，结果事实覆盖率 100%。
- 降级时会向内部 console 打一行 `[narration] in-model rejected <原因> -> program fallback`，便于主集成者看到模型为什么没被接受，不影响页面文字。
- 默认 `auto` 的降级路径也接上了这套合成器：模型正文被自己的校验拒绝时，补丁调用 `runner.generateProgram()` 用已结算事实写一段程序正文并标注降级；模型正文被接受时不会替换。接线检查里这条路径输出 60+ 字、`fallback: true`、`error: 程序按已结算事实成文`、无引擎调用。
- `results/06-recovery/real-candidate-constrained-program-v13.json`：C v1.3（04 realizer）真实点位，171 字、23 ms。
- `results/06-recovery/real-candidate-trained-scene.json`：B scene 模式，226 字但 `fact_omitted+time_missing` 拒绝。
- `results/06-recovery/real-candidate-trained-scene-instructed.json`：B scene + 移动/时间约束，233 字但 `fact_movement_claimed+time_missing` 拒绝，并含编造动作。
- `results/06-recovery/real-candidate-15bnarr-v3.json`：B beats，拒绝。
- `results/06-recovery/real-candidate-instruct15.json`：B + instruct 1.5B，104 字接受，434.6 s，含模型自加道具动作。
- `results/06-recovery/real-candidate-constrained-model-instruct.json`：C model + instruct 1.5B（160 token/段），223 字，模型段与程序段混合，含编造动作。
- `results/06-recovery/real-candidate-constrained-model-narr-short.json`、`…-instruct-short.json`：把每段压到 60–80 token 后，模型段全部被 C 的逐段校验打回，整篇变成程序文本（composers 全为 `program+model-failed`）。
- `results/06-recovery/product-turn-auto-main.json`：**默认 `auto` 的真实页面整轮**（补丁打在带主树未提交结算改动的快照上）：开局 70.4 s 被拒后显示程序正文，回合 113.6 s 被拒后显示含 `路明非：无判定。` 的程序正文，页面标注“程序按已结算事实成文”；就绪 137.3 s、整轮 163.0 s。
- `results/06-recovery/product-turn*.json`：其余真实页面整轮（B 选择、C v1.1、C v1.2、C v1.3），含内部日志、页面正文、降级标注、快照字节数。
- `results/06-recovery/wiring-check.json`：20 项接线检查（本线合并树）。
- `results/06-recovery/wiring-check-main.json`：把补丁应用到干净的主树快照 `77be4c0a` 后，`tsc` 通过、20 项接线检查全过；证明补丁不依赖 02/04/07 的合入。

## 6. 已知限制

- **没有合格叙事候选**：B 在页面模型上不被接受；C 程序版是流水账降级；C 模型版夹带编造动作。默认路径现在是“模型先写、失败则程序降级”，因此真实页面上看到的仍是程序文本加降级标注；等 02/10/03/04 交出让候选自己接受、且事实与文风都合格的正文。
- 模型优先的代价：回合要先等被拒绝的模型尝试（本次 113.6 s），之后程序正文瞬时出现。若把程序降级提前会更快，但会放弃模型正文被接受的机会。
- 07 的 composer 仍会补“没有停/盒子也没有动”这类动作/状态句；它是程序文本，只是比 04 的 realizer 更像段落。
- B 的 scene 模式能写长文但漏掉已结算移动与时间；加上约束后移动写了、时间仍漏，并开始编造动作。beats 模式在页面模型上逐段超长/加事件。
- C model 模式在 instruct 1.5B 上 121 s，且部分段回退程序；页面当前加载的是叙述 LoRA，不是 instruct 模型。
- 07 的 composer 是内嵌进补丁的运行时文件（8 个，源提交 `69915b49`），主树不需要合入 07 的大分支；07 仍拥有这份代码。
- A 未交付（fixture 与整合内核不兼容）。
- 开局叙述仍由原位模型写（约 66–73 s）；候选主动让位。
- 取消：选择层把 `point.signal` 传给候选；页面取消仍是 controller 的回合结论命令，未完成的候选结果不会提交。程序候选瞬时完成，没有取消窗口；B 的多段生成在取消后要等当前引擎调用返回（引擎中断属 runtime 线）。刷新：叙述发生在 transport 检查点内；刷新按既有恢复模块从最近检查点继续。继续回合：只有非程序的接受正文进入 `priorText`。
- 只在 Chromium/Edge（Windows）验证。
- C 的 `model` 模式在本机 1.5B + CPU 上单段就可能跑满 180 s，产品回合预算内写不完 5 段；这不是提示词能修的，短期只能靠单发写作或程序降级。
- `run-product-turn.mjs --turns "a||b"` 可在同一页面连续跑多轮并逐轮记录耗时/正文/标注/快照，用于后续连续回合验收（本轮没有抢到推理锁，未实跑）。

## 7. 用户试玩（同一页面）

1. 主集成者按上面的 `git apply` 应用补丁，`npx tsc --noEmit -p tsconfig.json` 通过后启动现有 `/world-local` 页面；不需要开任何实验站点。
2. 打开 `/world-local`，等“本地世界已就绪”。开局叙述由原模型写；若它被自己的事实校验拒绝，页面会显示 04 骨架 + 07 合成器写出的程序正文，并标注“程序按已结算事实成文”。
3. 输入行动，等回合结束。模型正文被接受时显示模型正文；被拒绝时显示同一标注的程序降级正文，不会退回成字段流水账。
4. 候选的开关是内部配置（`narrationCandidate` 或 QA 的 `__jityNarrationCandidate`），页面不显示训练/测试细节；试玩时保持默认 `auto` 即可。
