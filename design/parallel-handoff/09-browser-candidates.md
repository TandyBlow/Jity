# 09 交接：三条正文候选的共用真实浏览器队列

## 1. 这条线解决什么

A（03 生成 + 08 模型）、B（02 + 10）、C（04 骨架 + 07 成文）各自都要把候选放进真实浏览器、真实权重上生成中文正文。之前每条线各建一次浏览器、各自抢本机推理锁，锁频繁空转，同一条输入被重复冷启动。

本线只交付一个共用执行入口：候选模块由各线自己写，队列负责一次加载、按顺序跑真实输入、把原文与失败原样写进共享证据。它不是评测框架：机器返回的 `accepted` 只表示候选自己的校验通过，不代表产品读评通过。

## 2. 入口

- 驱动（浏览器内）：`frontend/src/lib/world-engine/local/narration-candidates/browser-driver/`
  - `scenarios.ts`：场景与真实投影；`run.ts`：引擎复用、候选导入、单场景运行、契约检查；`types.ts`：证据与调用类型。
- 命令（Node）：`frontend/scripts/quality-candidates/run-browser-candidates.mjs`
- 说明：`frontend/scripts/quality-candidates/README.md`
- 共享证据：`D:/others/Jity/.local/parallel-local-game/results/quality/browser-09.json`

最小调用（A 组当前入口，CPU）：

```bash
cd frontend
node scripts/quality-candidates/run-browser-candidates.mjs \
  --candidate 08-runtime=/abs/.../model-runtime/index.ts \
  --candidate-loader 08-runtime=/abs/.../model-runtime/index.ts::loadCandidateModel \
  --candidate-model-id 08-runtime=qwen2.5-1.5b-instruct-q4km \
  --model /models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --threads 6 --set free-day --only free-day-open \
  --purpose "A candidate free-day opening" \
  --out ../../../results/quality/browser-09.json
```

```bash
# 先做不占锁的导入检查
node scripts/quality-candidates/run-browser-candidates.mjs --inspect \
  --candidate 04-settlement=/abs/.../constrained/index.ts --set free-day --out ../../../results/quality/browser-09.json

# 等待别的线释放锁再跑（每 20 秒重试）
... --lease-wait-seconds 600
```

## 2.5 本机模型（2026-11-10 实测）

模型目录：`D:/others/Jity/.local/world-narration-worktree/frontend/public/models`（由 `--model-dir` 服务）。

| 文件 | 字节 | sha256 | 用途 |
|---|---:|---|---|
| `qwen2.5-1.5b-instruct-q4_k_m.gguf` | 1117320736 | `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e` | 03/04/08 的 A/C 模型路线 |
| `qwen25-0.5b-narration-Q4_K_M.gguf` | 397807488 | `a5fea8c3e313786bcb409804355c6f27a4e4804062683c05d996f724c25b9f81` | 02/10 的 B 训练权重 |
| `qwen25-1.5b-narr-Q4_K_M.gguf` | 986048096 | `6ed2268db2e1277933094c8b3af3348c18d6c0689244679a393c2008a1af5a0b` | 06 页面 B 对照 |
| `Qwen3-0.6B-Q4_K_M.gguf` | 396705472 | `ac2d97712095a558e31573f62f466a3f9d93990898b0ec79d7c974c1780d524a` | 08 的快速对照（本轮未跑） |

1.5B instruct 在 GPU 上加载 39–46 s；0.5B narration 20–24 s。`--gpu` 的直连引擎只记录“请求了 GPU”；08 加载器会明确写 `backend=webgpu`，本 handoff 的 WebGPU 结论只引用后者或 console 的 `ggml_webgpu` 行。

## 3. 候选契约（队列实际传给候选的东西）

```ts
generateCandidate({
  engine,                  // 已加载的真实引擎；有 chat 就用 chat，否则 complete
  committed,               // {anchor, facts} + state/beforeState/timeAdvance/entityDeltas
  state, before, delta,    // 同一份已结算读出的另一种写法（03 用）
  inputText,               // legacyNarrationInput 产品投影（B 的训练输入另由候选模板处理）
  priorText,               // 连续回合：上一场景 accepted 的正文
  signal, onProgress, policy,
}) => {
  text, accepted, rawAttempts, issues, timings, strategyVersion
}
```

- `committed.facts` 与 `state/beforeState` **同源**，都是已结算状态；队列不产生第二份世界，也不改写任何候选输出。
- 候选需要自己的加载器时用 `--candidate-loader <id>=<path>::<export>` + `--candidate-model-id <id>=<catalog id>`。同一 model+loader 只加载一次；同模型不同候选共享同一个引擎实例。
- 引擎被候选自己的超时 hard stop 后（08 的引擎会清空 `instance` 和 `info.modelId`），队列会先卸载并重载，证据里记 `engine_reload:engine_dead_after_previous_run`，不让下一个候选背前一个的错误。

## 4. 场景（真实输入，不是手写示例）

- `short-root / short-move / short-elapsed`：既有公开短场景，与旧探针可比。
- `free-day-open`：真实《自由一日》世界文件的开局点。`inputText` 就是页面会送给叙事的 `legacyNarrationInput`（1092 字）。
- `free-day-move`：路明非、诺诺在同一分钟内从西侧服务巷移到西回廊；由 `applyPoint` 实际应用，canonical digest 由内核计算。
- `free-day-task`：`task_lu_choice` 达成 + 个性变化 + 精神值 43→48 的同一因果链。

移动/任务场景的 delta 是确定性探针，不是模型结算输出；证据 `scenario.note` 与 handoff 都这样标注。

## 5. 真实运行记录

### 5.1 第一次真实运行（CPU，已发生）

三次运行都写进了 `results/quality/browser-09.json`，`notices[]` 是给各负责人的具体指认。摘要：

| 候选 | 输入 | 结果 | 时间 | 具体失败 |
|---|---|---|---|---|
| 08-runtime（A） | free-day-open | 无正文 | load 35.9s；请求 152.8s | 第一次尝试 150s 内 0 个 token，仅一个 `retry` 进度事件；重试时引擎已被 hard stop，抛 `wllama engine is not loaded` |
| 03-actions（A） | free-day-open | 未进入生成 | 3ms | 上一个候选把共享引擎打死后 `info.modelId=null` → `unknown_instruct_template:null`；队列已修，待健康引擎重跑 |
| 04-settlement（C） | free-day-open | 程序回退 5 段，`accepted=false` | 44ms | 自己的 hard `fact_actor_swap`：`root_free_day:at:lu` 被套到写诺诺的句子上；模型 beat 因死引擎全部回退 |

真实后端：`n_gpu_layers=0`，08 加载器报告 `cpu`；页面 `navigator.gpu` 存在，但本机这条运行**没有**用 WebGPU，证据不写 WebGPU。线程 6。

### 5.2 WebGPU 真机对照（06 的页面 product-turn，2026-11-10 07:08 UTC）

06 在 `scratch/shipping-06` 的页面上用同一把锁跑完一次真实回合（`results/06-recovery/product-turn.json`）：

- 浏览器 console 明确出现 `ggml_webgpu: adapter_info ... intel gen-12lp`，这是 WebGPU 真的在跑，不是把 `navigator.gpu` 当成已经生效。
- `readyMs=167917`，`turnMs=503844`；root 叙事 candidate 报 `input_unavailable:no_before_state`，round 3 报 `rejected:too_short+all_beats_fell_back`。
- 实际显示的正文是程序回退，且把玩家输入又复述了一遍：

  > 时间过去了约1分钟。路明非沿着服务巷的低墙走到器材棚门口，先看领用台上有谁。路明非：本组结算未能确认新的结果。……

  这句不能当产品正文；已写进 `notices[]` 给 02/06。

- 同一次运行里，06 的 product page 请求 `Qwen3-0.6B` 和 `qwen25-1.5b-narr` 都是 200；之前的 404 是 dev server 没放模型，不是模型缺失。

### 5.3 真机 WebGPU：C 04 与 A 03 的 free-day-open（2026-11-10 08:35 UTC）

锁释放后，共用队列用 **1.5B instruct + 08 的 `loadCandidateModel` + `--gpu`** 跑了同一条 `free-day-open`（1092 字，`root_free_day`，digest 见 `runs[].identity`）：

- 加载：45639 ms；加载器记录 `backend=webgpu`、`gpuLayers=99999`、无 fallback；模型文件
  `qwen2.5-1.5b-instruct-q4_k_m.gguf`，sha256 `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`，1117320736 B。
- **C 04-settlement**：`accepted=true`，212 字，wall 55132 ms，`firstReadableAtMs=13970`，3 个 beat（21143 / 21844 / 12115 ms）。
  前四段是程序 realizer 的地点/人物/物品清单；第五段是模型写的
  「诺诺紧握着红色识别带，右臂上红痕清晰可见，她深吸一口气，准备进入演习区。」
  事实包只给诺诺在此地（at），没有“准备进入”的下一步动作或心理；该句是否应 accepted 需 04/07 判断。
- **A 03-actions**：`accepted=false`，175 字，wall 28621 ms，`firstTokenMs=11009`，`firstReadableAtMs=18296`；hard
  `first_person_narrator`（正文 3 处“我”）、`unlicensed_entity`，另有 13 条 soft `fact_omitted`。原文开头：
  「我站在西侧服务巷，时间是2009年10月17日15:20。……我身着校服，领口松着，膝盖沾了灰。……校服的领口松着，膝盖沾了灰。护目镜挂在胸前，右手空着。」
  同一段衣着写了两遍；已写入 `notices[]` 给 03/08。
- 结论：C 的 accepted 只代表它自己的校验；A 的首段等待 18.3 s 在 60 s 内，但正文第一人称，不能当产品通过。

### 5.4 C 的程序层 6/6 accepted（无模型，`--no-engine`）

04 v1.3（`cda83753`）和 07（`69915b49`）都在同一个队列的 `--no-engine` 路径跑了 6 个场景，全部 `accepted=true`，但原文是事实清单：

- 04 free-day-open：186 字，5 段，14 ms；旧 `fact_actor_swap` 已消失。
- 04 free-day-task：139 字；「路明非完成了「向诺诺问清当前红蓝两方局势和自己是否可以保持中立」。」是任务目标原句，
  「路明非身上多了一点变化：不再等别人替他决定，愿意先迈出一步。」是告诉而不是演出。
- 07 free-day-task：63 字，直接把任务目标写进正文；07 free-day-move 同一人“诺诺”出现两次。
- 这些都写进 `notices[]`；`accepted` 不是产品读评。

### 5.5 B 02/10 的 free-day 真实模型正文（0.5B narration，WebGPU 请求）

`free-day-open` 与 `free-day-move` 都跑了；0.5B narration 加载 20.3–24.2 s，线程 6，`gpuRequested=true`（直连引擎未独立验证 backend）。

- 02 free-day-open：最终 0 字、rejected，19.0 s；两次真实模型调用都有原文，但都在 maxTokens 处 `truncated`，所有 beat 回退，最终为空。
- 02 free-day-move：最终 43 字、rejected，66.1 s，8 次调用，`firstReadable=4834ms`；真实 raw 里有多段模型正文，但最后一次两条 hard `fact_actor_swap` + `too_short` + `all_beats_fell_back`，最终只剩事实句。
- 10 free-day-open：`accepted=true`、0 字、0 attempts、1 ms。根因是 10 的 `toBeats()` 只处理 moved/task/personality/sanity/time，root 无变化 → `beats=[]`、循环不执行、`accepted` 仍为 true。09 已把这种结果改判 `accepted=false`、`contract.ok=false`，并在 `runs[].queueCorrection` 保留原始 accepted 值。
- 10 free-day-move：`accepted=true`，195 字，24.5 s，5 attempts，`firstReadable=12253ms`；正文开头是 prompt 元信息
  「【本拍事实】路明非从西侧服务巷走到西回廊」，后面编出「林亦舟站在台阶上，手里还拿着一支演习枪」和「诺诺……又走了回来」。
  事实包只有路明非/诺诺的位置变化；这是 meta leak + added_event，accepted 只代表 10 自己的 check 没覆盖到。

### 5.6 C 04 的 free-day-move/task 真实模型（1.5B instruct，WebGPU）

- free-day-move：`accepted=true`，345 字，151.9 s，`firstReadable=27143ms`，5 attempts（33.9/36.8/36.0/25.4/19.7 s）。
  前七段是程序 realizer；最后模型段把林亦舟的「蓝色识别带沾灰、左脚踝肿起、背靠第三根廊柱坐着」写到了诺诺身上，并重复枪/蓝布带事实——
  这是 hard `fact_actor_swap`，04 的 verifier 没抓到。
- free-day-task：`accepted=true`，197 字，98.6 s，`firstReadable=14373ms`，5 attempts；仍把任务目标原句
  「路明非完成了「向诺诺问清当前红蓝两方局势和自己是否可以保持中立」。」和「身上多了一点变化」写进正文。
- 已写进 `notices[]` 给 04/07；accepted 不等于产品读评。

### 5.7 当前队列入口

03/04 用 1.5B instruct + 08 的 `loadCandidateModel`，02/10 用 0.5B narration；`--gpu`。命令与候选路径由 `--status` 可查；证据会写 `backend=webgpu`（08 加载器）或 `gpuRequested=true, backendNote=...`（直连引擎，未独立验证）。
`--no-engine` 只给程序成文候选（04 program / 07），不加载权重、不占锁；模型候选在 `--no-engine` 下会得到抛错的 stub engine，不会被误当成跑过。

## 5.8 给 06 的接线入口（不需要你重建浏览器）

06 只需两步，不需要审批、不需要等 09 的人在线：

1. **在自己的候选选择层加一个可导入的实现**：`generateCandidate(args)` 或你现有的 `generateCommittedNarration(args)`（09 两种都接受，非标准导出名会记进 `evidence.exportName`）。参数就 `engine / committed / inputText / priorText / onProgress / policy`；`committed` 额外带 `state / beforeState / timeAdvance / entityDeltas`，都是同一份已结算读出的同源数据。
2. **自己跑一次真实页面验证**（持有锁时）：
   ```bash
   cd frontend
   node scripts/quality-candidates/run-browser-candidates.mjs      --candidate selection=D:/others/Jity/.local/parallel-local-game/worktrees/06-recovery/frontend/src/lib/world-engine/local/narration-candidates/selection/trained.ts      --candidate-model selection=/models/qwen25-0.5b-narration-Q4_K_M.gguf      --model-dir D:/others/Jity/.local/world-narration-worktree/frontend/public/models      --gpu --set free-day --only free-day-move      --lease-wait-seconds 600 --purpose "06 selection on free-day move"      --out D:/others/Jity/.local/parallel-local-game/results/quality/browser-09.json
   ```
   或看已有结果不占锁：`--status`。

可加载路径（本机现成、已用真实浏览器加载过）：

- 02 策略：`worktrees/02-narration/frontend/src/lib/world-engine/local/narration-generation/index.ts`（导出 `generateCommittedNarration` 与 `generateCandidate`）
- 04 骨架：`worktrees/04-settlement/frontend/src/lib/world-engine/local/narration-candidates/constrained/index.ts`
- 07 成文：`worktrees/07-sync/frontend/src/lib/world-engine/local/narration-candidates/prose-composer/index.ts`（程序，无模型）
- 10 分拍：`worktrees/10-training/experiments/narration-runtime-v2/browser/candidate.ts`
- 03 instruct：`worktrees/03-actions/frontend/src/lib/world-engine/local/narration-candidates/instruct/index.ts`

注意：`accepted` 是候选自己的校验结果；09 只把 `accepted=true` 且正文为空的结果强制改判 `accepted=false` + `contract.ok=false`（`runs[].queueCorrection` 保留原值）。不要用 `accepted` 当页面“高质量”标志。

## 6. 待办与判断

- A：03 的 1.5B 真机首段 18.3 s，但第一人称 3 处、重复衣着段；需要候选侧改成第三人称并补必写事实。08 自己的 1.5B dev 3 点也全 rejected（root 幻觉、move 截断/新增事件、continuation 无事实移动）。A 仍无 accepted 正文。
- B：02 的真实 raw 有内容但 beat 截断/actor swap；10 的 move 有 195 字 but meta/added_event。B 仍未达到产品正文；02/10 已收到具体坏句。
- C：04 的 move 已被真实模型写出 345 字，但 verifier 漏掉跨人物换位；task 仍是任务目标原句 + 告诉。C 的可读性比程序层好，但需要修 verifier 和 task 写法。
- 本线不判断正文质量；谁先有可读正文由各负责人读 `runs[].result.paragraphs`。
- 公开短场景补跑（真机 WebGPU）：02 short-root 33 字/1 次、short-move 11 字/4 次都因 `too_short` 被自己的下限打回；10 short-move accepted 60 字但编出「楼梯口」「盒子打开/旧日记」；10 short-root 又是 `beats=[]` 空正文；03 short-root 编出「门厅现代房间/巨幅画作」并漏 fact。已逐条写进 `notices[]`。
- 锁：06 自 05:59 手工 acquire 后一直持到 08:35 才释放（product-turn 07:08 已写完）；08 在 08:37 接过锁跑 4B 失败、1.5B dev 3 点全 rejected；10 在 09:20 跑过一轮。09 的队列只在启动浏览器前 acquire、finally release；等待期间不启动第二个浏览器，并把占用原样写进 `notices[]`/`failures[]`。
