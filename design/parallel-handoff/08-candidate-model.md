# 08 candidate-model handoff（A 组：可部署模型与浏览器运行）

分支 `goal/local-08-runtime`。本线的工作树：
`D:/others/Jity/.local/parallel-local-game/worktrees/08-runtime`。
本线负责 A 组的模型与真实运行：把本机已有的原生 instruct GGUF 真正在浏览器里
加载、按模型自己的模板生成中文正文、留下可复查的原文与耗时，并把模板、加载
方式、模型路径交给 03（生成策略）和 09（页面/共享运行器）。

**状态（如实）**：真实浏览器里已经用 `qwen3-1.7b-q4km` 生成出一段 120 字的
中文正文，事实核对通过（移动与时间都写到），但长度没到 240 字目标；0.5B 和
1.5B 的第一次真实运行都失败了，原因已定位并改进了提示词。
**改进后的 3 段长度约束还没有在浏览器里复测**（本机推理锁被其他线长时间占用）。
在复测原文写进 `results/quality/team-08-runtime.json` 之前，不声明 A 组正文达标。

## 1. 本机已核对的模型

文件都在共享只读目录，没有复制到本工作树。大小和 sha256 由本机文件算出；
架构、上下文长度、`tokenizer.chat_template` 由
`frontend/scripts/candidate-model/gguf-meta.mjs` 直接读 GGUF 头得到。

| catalog id | 文件 | 大小 | sha256 | 架构 | 上下文 | 模板 | 思考 |
|---|---|---|---|---|---|---|---|
| `qwen3-4b-instruct-2507-q4km` | Qwen3-4B-Instruct-2507-Q4_K_M.gguf | 2 497 281 120 | `3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597` | qwen3 | 262144 | `qwen3-instruct-2507-chatml-v1`（模板里没有 `enable_thinking`） | 无 |
| `qwen3-1.7b-q4km` | Qwen3-1.7B-Q4_K_M.gguf | 1 107 409 472 | `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897` | qwen3 | 40960 | `qwen3-hybrid-chatml-no-thinking-v1` | 混合，加载时关 |
| `qwen2.5-1.5b-instruct-q4km` | qwen2.5-1.5b-instruct-q4_k_m.gguf | 1 117 320 736 | `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e` | qwen2 | 32768 | `qwen2.5-instruct-chatml-v1` | 无 |
| `qwen3-0.6b-q4km` | Qwen3-0.6B-Q4_K_M.gguf | 396 705 472 | `ac2d97712095a558e31573f62f466a3f9d93990898b0ec79d7c974c1780d524a` | qwen3 | 40960 | 同 Qwen3 1.7B | 混合，加载时关 |
| `qwen2.5-0.5b-instruct-q4km` | qwen2.5-0.5b-instruct-q4_k_m.gguf | 491 400 032 | `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db` | qwen2 | 32768 | 同 Qwen2.5 1.5B | 无 |

文件位置（按顺序查找，`--models-dir` 可覆盖）：

1. `D:/others/Jity/.local/world-narration-worktree/frontend/public/models`
2. `D:/others/Jity/frontend/public/models`
3. `D:/others/Jity/.local/models`

脚本对选中的文件做大小 + SHA-256 校验；不一致直接失败，不会静默换成别的权重。

## 2. 模板：按模型区分，不要手写一份通用 ChatML

wllama 3.8.1 的 `createChatCompletion` 会应用 GGUF 自带的 Jinja 模板。所以本线
不手拼 ChatML，而是把**消息列表**交给引擎：

- Qwen2.5（0.5B / 1.5B instruct）：模板没有 `enable_thinking` 分支，额外参数被
  忽略。传 `system` + `user` 两条消息，引擎按 ChatML 渲染。
- Qwen3-0.6B / Qwen3-1.7B（混合思考）：模板里
  `{%- if enable_thinking is defined and enable_thinking is false %}` 会插入一个
  空的思考块。引擎固定传 `chat_template_kwargs: { enable_thinking: false }`，
  所以输出直接是正文；候选再在流式和最终文本两层剥掉任何残余思考块。
- Qwen3-4B-Instruct-2507：模板没有 `enable_thinking` 分支，本身不思考，这个
  参数无害。

每个文件的完整模板已用 `gguf-meta.mjs --out` 存到 `.local/candidate-model/meta/`，
02/03 可以对照。

### 为什么改了 `runtime/wllama-engine.ts`（登记过的问题）

原引擎的 `complete(prompt)` 固定发**一条 user 消息**，浏览器里的 instruct 模型
会用它自己的默认 system（“You are Qwen…”），候选没法给中文叙事作者 system。
公共接口 `runtime/engine.ts` 没有改；新增
`WllamaInferenceEngine.chat(messages, options)`，复用原有的取消、超时、流式、
证据路径。`complete()` 行为不变（仍是一条 user 消息），旧调用和旧测试全部通过
（21 项引擎测试）。

## 3. 导出 API

`frontend/src/lib/world-engine/local/narration-candidates/model-runtime/index.ts`

```ts
MODEL_CATALOG: readonly ModelSpec[]
modelSpec(id: string): ModelSpec
modelSpecByFile(fileOrModelId: string): ModelSpec   // 认 info.modelId 的文件名

loadCandidateModel(spec, {
  modelRoot?: string;          // 默认 '/models'
  preferGpu?: boolean;         // 默认 true
  forceCpu?: boolean;
  contextSize?: number; numThreads?: number; abortGraceMs?: number;
  signal?: AbortSignal;
  onEvidence?: (record: ModelLoadEvidence | GenerationEvidence) => void;
}): Promise<{
  spec, engine: WllamaInferenceEngine,
  backend: 'webgpu' | 'cpu',
  fallback: { from: 'webgpu'; reason: string } | null,
  attempts: { backend; gpuLayers; ok; loadMs; error? }[],
  loadMs, evidence, webgpuAvailable,
}>

generateCandidate(
  { engine, committed, inputText, priorText?, signal?, onProgress?,
    state?, before?, delta?, policy? },
  { spec?: ModelSpec } | undefined,
): Promise<{
  text, accepted, rawAttempts, issues, timings,
  strategyVersion, model?, verification,
}>
```

`generateCandidate` 的输入/输出与 QUALITY-TEAMS 的候选约定一致。不传 `spec` 时
按 `engine.info.modelId` 从 catalog 自动识别，所以 09 的 driver 自己加载 GGUF
之后直接调用即可。`rawAttempts` 里每次调用都有 prompt、正文、llama.cpp 的
`prompt_n / predicted_n / predicted_ms / finishReason`。事实判定失败不会用模板句
替换正文，`accepted:false` 原样返回。

`policy` 字段：`scene`（地点/在场人物/物品，必须是已结算投影）、`viewpoint`、
`roster`、`locations`、`knownPositions`、`knownEntities`、`time`（普通时长或
09 driver 给的 `{duration:{amount,unit}}` 都吃）、`minChars`、`targetChars`、
`paragraphs`（默认 3）、`maxTokens`、`attempts`（默认 2）、`temperature`、
`seed`、`timeoutMs`、`instruction`、`priorText`、`includeInputText`（默认关）。

`onProgress({text,status,verified,elapsedMs})`：生成中 `verified:false`，成文后
`status:'done'` 带事实判定；思考块不会闪到玩家界面。

### 事实的两种来源（这次真实运行暴露的关键）

共享 packet 里混着两类东西：

- **这一小段时间里发生的事**（谁从哪走到哪、哪个任务达成）——正文必须写到；
- **本来就成立的状态**（谁在哪、精神值多少、个性文本）——正文不该像账本一样
  逐条念出来。

第一次真实运行里，1.5B 把“周宁的精神值为10”原样写进正文，还自己加了开盒、
关盒两个没发生的事件；0.5B 更糟，直接把提示词的清单抄了一遍。这不是模型
“不会写”，是提示词把状态当成了事件。

现在 `facts.ts` 把 packet 拆开：移动/任务达成仍是要写的事实；站位变成“此刻
的站位（不必逐条复述）”；精神值和个性变化变成“只能用神态或动作暗示，不要
写出数字、不要照抄原句”。事实核对跑在同一个投影上，所以不会因为“没念出
数字”被判失败。

提示词同时明确禁止没有列出的动作（开箱、拿取、使用物品、新对话），并要求
写成 3 段、合计 180～240 字、写满再收。**这套新提示词还没有在浏览器里跑过。**

## 4. 已经真实跑出来的结果

设备：ASUS TUF F15，i7-13700H，20 逻辑核，16 GB，Windows；Edge
157.0.4341.42，`crossOriginIsolated=true`。

| 运行 | 后端 | 加载 | 首可读 | 生成 | 结果 |
|---|---|---|---|---|---|
| qwen2.5-0.5b-instruct（旧提示词） | WebGPU | 19.1 s | 2.1 s | 43.4 s | 失败：正文抄了提示词清单（125 字），人物写反 |
| qwen2.5-1.5b-instruct（旧提示词） | WebGPU | 39.9 s | 7.4 s | 79.7 s | 失败：加了开盒/关盒事件、念了精神值、没写时间（175 字） |
| qwen3-1.7b（旧提示词） | WebGPU | 64.0 s | 10.7 s | 53.5 s | 第一次调用加了开盒事件被拒；第二次 120 字、移动与“两分钟”都写到，事实核对通过，但长度没到目标 |

三段的完整原文、prompt、每次调用的 token 计数都在
`.local/candidate-model/probe-run1.json` 和 `probe-qwen3-1.7b.json`。

**后端必须如实写**：这三次的 `backend` 都是 `webgpu`，但页面 console 里
ggml 打印的适配器是

```
vendor: intel | architecture: gen-12lp | device_id: 0
```

也就是 **Intel 核显**，不是 RTX 4060。`n_gpu_layers=99999` 只代表“请求把层放到
GPU”，不代表放到了独显。WebGPU 确实生效（不是 CPU），但独显是否更快、能不能
装下 4B，必须用 `--force_high_performance_gpu`（新脚本已默认带上）重测并看
adapter 名字。

脚本每次运行都会记录：`webgpuAvailable`、加载尝试列表（WebGPU→CPU 回退及
原因）、`adapterInfo`（页面自己 `requestAdapter()` 拿到的 vendor/architecture）、
console 里与 backend 相关的行、host 侧 nvidia-smi 采样。**不要用
`n_gpu_layers` 或 `backend:'webgpu'` 单独当 GPU 生效的证明。**

## 5. 命令（09/03 可直接用）

脚本：`frontend/scripts/candidate-model/probe-models.mjs`（每个模型一个共享输入）
和 `run-a-candidate.mjs`（一次加载跑多个点，含连续回合）。

**和 09 共用一个已加载模型**：09 的共享队列已经登记了 `08-runtime` 候选，命令是

```bash
cd D:/others/Jity/.local/parallel-local-game/worktrees/09-ui/frontend
node scripts/quality-candidates/run-browser-candidates.mjs   --lane 08-runtime --purpose "A candidate free-day text"   --candidate 08-runtime=D:/others/Jity/.local/parallel-local-game/worktrees/08-runtime/frontend/src/lib/world-engine/local/narration-candidates/model-runtime/index.ts   --owner 08-runtime=08-runtime   --candidate-model 08-runtime=/models/Qwen3-1.7B-Q4_K_M.gguf   --candidate-model-id 08-runtime=qwen3-1.7b-q4km   --set free-day --only free-day-open,free-day-move --gpu   --out D:/others/Jity/.local/parallel-local-game/results/quality/browser-09.json
```

`--gpu` 必须显式给，09 默认是 CPU；CPU 上 1.5B 跑 1400 字输入会在 150 s 超时。
`--candidate-model-id` 让本线按 catalog 识别模板，否则只有模型文件名可用于猜。
同一次运行里同模型只加载一次；09 记录 `inputText/committed/scene/policy` 和我的
`rawAttempts`，可直接对照。

本线自己的脚本：

```bash
cd frontend
# 本机推理是独占资源：先取锁，finally 释放
python ../../.local/parallel-local-game/resource_lease.py acquire --lane 08-runtime --purpose "candidate model run"

# 1) 每模型：加载 + 一个冻结提交点（林川 走廊→门厅，2 分钟，周宁视角）
node scripts/candidate-model/probe-models.mjs \
  --model qwen2.5-1.5b-instruct-q4km --model qwen3-1.7b-q4km \
  --max-tokens 320 --out ../.local/candidate-model/probe.json

# 2) 一个模型跑 dev 连续回合（起点 / 移动 / 时间流逝 / 连续）
node scripts/candidate-model/run-a-candidate.mjs \
  --model qwen3-1.7b-q4km --set all --target-chars 240 --max-tokens 420 \
  --out ../../results/quality/a-run-qwen3-1.7b.json

# 3) 用同一加载器跑 03 的模块（把 --entry 指向他们的 index.ts）
node scripts/candidate-model/run-a-candidate.mjs \
  --model qwen2.5-1.5b-instruct-q4km --set dev \
  --entry /@fs/D:/others/Jity/.local/parallel-local-game/worktrees/03-actions/frontend/src/lib/world-engine/local/narration-candidates/instruct/index.ts \
  --export generateCandidate --out ../../results/quality/a-run-03.json

python ../../.local/parallel-local-game/resource_lease.py release --lane 08-runtime
```

`--set`：`dev`（起点/移动/连续）、`unseen`（另一套世界：余晚/罗青/账本）、
`all`。`--low-power-gpu` 可强制核显，`--force-cpu` 可关掉 WebGPU 做对照。
`--entry` 也接受 `/src/...` 形式的本树路径。

## 6. 已通过的检查（mock，不代表 GPU/速度）

```bash
cd frontend
npx vitest run src/lib/world-engine/runtime/wllama-engine.test.ts   # 21 passed
npx vitest run src/lib/world-engine/local/narration-candidates      # 19 passed
npx tsc --noEmit -p tsconfig.json
npx eslint src/lib/world-engine/local/narration-candidates scripts/candidate-model
```

覆盖：catalog 身份/哈希、模板消息与 fallback prompt、思考块完整/流式剥离、
事实通过时 accepted、方向写反带修复提示重试、两次失败保留草稿并
`accepted:false`、长度截断保留草稿并重试、空变化点编造移动被拒、abort 不被吞、
`chat()` 真实 system 转发、事件/站位/暗示拆分、站位去重。

## 7. 限制

- 改过提示词之后的真实浏览器原文还没产出（推理锁被别的线占用）。解锁后按第 5
  节跑，先把原文追加到 `results/quality/team-08-runtime.json`，再据真实失败改。
- Qwen3-4B-Instruct-2507 权重 2.50 GB，未测。核显上多半太慢；独显 8 GB 是否
  装得下 KV cache、首段等待多久，都要实测。
- 03 的 `instruct/template.ts` 目前把 system 拼进 user 首行（`chat` 模式），能
  用但弱于真实 system 消息；建议改用 `engine.chat()`（本线已支持）或直接调用
  `generateCandidate`。
- 训练过的叙事权重（qwen25-0.5b/1.5b narration）不在 A 组候选内，模板由 02/10
  提供，不能套本文件的 instruct 模板。
- 事实核对用既有 `alignNarration`；文风和可读性仍是人读项，不是机器分数。
- 实测到 `alignNarration` 的一个误报：把「把盒子换到另一只手上」判成
  `movement_without_fact`（句子里出现地点名「走廊」+ 动词「换到」）。这个文件
  不归本线管，未改；出现这类句子时会多一次修复调用，主 agent 可让拥有者收紧
  移动动词表。
- 超时后引擎可能已经硬停 worker（09 的一次 CPU 运行就是这样）。候选现在把超时
  当终止态返回 `status:'timeout'`，不再拿死引擎重试；**下一个点之前要重新
  `await engine.load()`**（带模型 URL 的加载是 memoized，未停时是空操作）。页面
  若要自动恢复，可在 `status==='timeout'` 后调一次 `load()`。

## 8. 主 agent 需要改的几行

1. 页面加载：把 `loadEngine(url)` 换成
   `loadCandidateModel(modelSpec('<id>'))`，用返回的 `engine`；把
   `backend/fallback/adapterInfo` 写进调试日志。页面现有的 WebGPU→CPU 回退可以
   删掉，避免两套回退互相覆盖。
2. `game-model.ts` 的 narration 分支：调用本线 `generateCandidate`（或 03 的
   模块），传入 `committed/inputText/policy`（`scene` 从已结算状态取），上报
   `accepted`、`verification`、`timings.firstReadableMs`；不要再用模板句覆盖
   已接受的正文。
3. 停止按钮：`engine.cancelActive()`（08-runtime 前一任务已交付）。
4. 若采用 03 的生成模块，先用本线 `run-a-candidate.mjs --entry ...` 复跑同一
   场景，确认模板与模型对应，再接线。
