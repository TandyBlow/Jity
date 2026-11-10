# 08 candidate-model handoff（A 组：可部署模型与浏览器运行）

分支 `goal/local-08-runtime`，基线 `865ae64e0901a70c3db4f1d0eb2af60268943c53`。
本线负责 A 组（本地指令模型完整正文）的模型与真实运行：03 写生成，08 把能
胜任的模型真正跑起来并把模板/加载/路径交给 03、09、06。旧 `runtime/` 实现
保留，本线没有扩充无关诊断。

## 0. 当前状态（如实）

- 模块与真实运行脚本已提交；模板、哈希、加载路径均已从本机文件核对。
- **真实浏览器正文运行尚在进行中**：第一次 `probe-models` 运行需要本机推理锁，
  启动时被 02 的 1.5B v3 运行占用；代码就绪后按顺序执行，结果会追加到
  `results/quality/team-08-runtime.json` 的 `realRuns`。在真实原文出现前，
  本文件与 team JSON 都不声明 A 组正文质量。

## 1. 本机已核对的模型（可直接加载）

文件都在共享只读目录，未复制到本工作树。哈希/大小由本机文件计算；架构、
上下文、`tokenizer.chat_template` 由 `scripts/candidate-model/gguf-meta.mjs`
读取 GGUF 元数据得到。

| catalog id | 文件 | 大小 | sha256 | 架构 | 上下文 | 模板 | 思考 |
|---|---|---|---|---|---|---|---|
| `qwen3-4b-instruct-2507-q4km` | Qwen3-4B-Instruct-2507-Q4_K_M.gguf | 2 497 281 120 | `3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597` | qwen3 | 262144 | `qwen3-instruct-2507-chatml-v1`（模板无 `enable_thinking`） | 无 |
| `qwen3-1.7b-q4km` | Qwen3-1.7B-Q4_K_M.gguf | 1 107 409 472 | `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897` | qwen3 | 40960 | `qwen3-hybrid-chatml-no-thinking-v1` | 混合，加载时关 |
| `qwen2.5-1.5b-instruct-q4km` | qwen2.5-1.5b-instruct-q4_k_m.gguf | 1 117 320 736 | `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e` | qwen2 | 32768 | `qwen2.5-instruct-chatml-v1` | 无 |
| `qwen3-0.6b-q4km` | Qwen3-0.6B-Q4_K_M.gguf | 396 705 472 | `ac2d97712095a558e31573f62f466a3f9d93990898b0ec79d7c974c1780d524a` | qwen3 | 40960 | 同 Qwen3 1.7B | 混合，加载时关 |
| `qwen2.5-0.5b-instruct-q4km` | qwen2.5-0.5b-instruct-q4_k_m.gguf | 491 400 032 | `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db` | qwen2 | 32768 | 同 Qwen2.5 1.5B | 无 |

文件位置（按顺序查找，`--models-dir` 可覆盖）：

1. `D:/others/Jity/.local/world-narration-worktree/frontend/public/models`（1.5B instruct、Qwen3-1.7B、Qwen3-0.6B 等）
2. `D:/others/Jity/frontend/public/models`（0.5B instruct、Qwen3-0.6B）
3. `D:/others/Jity/.local/models`（Qwen3-4B-Instruct-2507）

脚本对选中的文件做大小 + SHA-256 校验；不一致直接失败，不会静默换成别的权重。

## 2. 模板（03 必须按模型区分，不能一份通用 ChatML 硬套）

wllama 3.8.1 的 `createChatCompletion` 会应用 GGUF 自带的 Jinja 模板。因此本线
不让候选手写 ChatML，而是把**消息列表**交给引擎：

- Qwen2.5（0.5B/1.5B instruct）：模板无 `enable_thinking`，额外 kwarg 被忽略。
  传 `[{role:'system'},{role:'user'}]` 即按 ChatML 渲染。
- Qwen3-0.6B / Qwen3-1.7B（混合思考）：模板里 `{%- if enable_thinking is defined
  and enable_thinking is false %}` 会插入空 `thinking` 块。引擎固定传
  `chat_template_kwargs: { enable_thinking: false }`，所以输出直接是正文；候选
  仍会在流式与最终文本两层剥掉任何 `...` 残块。
- Qwen3-4B-Instruct-2507：模板没有 `enable_thinking` 分支，本身不思考，kwarg 无害。

`gguf-meta.mjs` 保存了每个文件的完整模板（`--out` 的 JSON），供 02/03 对照。

### 为什么改了一处 `runtime/wllama-engine.ts`

登记问题：原引擎的 `complete(prompt)` 固定发**一条 user 消息**，浏览器里的
instruct 模型会使用 checkpoint 自带的默认 system（“You are Qwen…”），候选无法
给中文叙事作者 system。原公共接口 `runtime/engine.ts` 未改；新增
`WllamaInferenceEngine.chat(messages, options)`，复用原有取消、超时、流式与证据
路径，`complete()` 行为不变（仍是一条 user 消息）。这是唯一改动原 runtime 的
原因，旧调用与旧测试全部保持通过（21 项引擎测试）。

## 3. 导出 API（可直接接线）

`frontend/src/lib/world-engine/local/narration-candidates/model-runtime/index.ts`

```ts
MODEL_CATALOG: readonly ModelSpec[]
modelSpec(id: string): ModelSpec
modelSpecByFile(fileOrModelId: string): ModelSpec   // 支持 info.modelId 的文件名
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
  { engine, committed, inputText, priorText?, signal?, onProgress?, policy? },
  { spec?: ModelSpec } | undefined,
): Promise<{
  text, accepted, rawAttempts, issues, timings,
  strategyVersion, model?: { id, templateId } | null, verification,
}>
```

`generateCandidate` 的输入/输出与 QUALITY-TEAMS 的候选约定一致；未传 `spec` 时按
`engine.info.modelId` 从 catalog 自动识别，09 的 driver 直接加载 GGUF 后调用即可。
返回真实 `attempts`：每次调用的 prompt、正文、llama.cpp timings、事实判定；失败
不会用模板句替换正文，`accepted:false` 原样返回。

`policy` 关键字段：`scene`（地点/在场人物/物品，来源必须是已结算投影）、
`viewpoint`、`roster`、`locations`、`knownPositions`、`knownEntities`、`time`、
`minChars`、`targetChars`、`maxTokens`、`attempts`（默认 2）、`temperature`、
`seed`、`timeoutMs`、`instruction`、`priorText`。流式回调
`onProgress({text,status,verified,elapsedMs})`：生成中 `verified:false`，成文后
`status:'done'` 带事实判定；思考块不会闪现在玩家界面。

事实判定复用既有 `alignNarration`（提交事实、方向、人物、数字、时间、新增
事件），不新造真值库。风格与措辞不是它的判据，终验仍由人读。

## 4. 真实运行命令（09 可直接用）

脚本：`frontend/scripts/candidate-model/probe-models.mjs`（每模型一个共享输入）
和 `run-a-candidate.mjs`（一次加载跑多个点，含连续回合）。

```bash
# from frontend/，先取本机推理锁，finally 释放
python ../../.local/parallel-local-game/resource_lease.py acquire --lane 08-runtime --purpose "candidate model probe"

# 1) 每模型：加载 + 一个冻结提交点（林川 走廊→门厅，2 分钟，周宁视角）
node scripts/candidate-model/probe-models.mjs \
  --model qwen2.5-0.5b-instruct-q4km --model qwen2.5-1.5b-instruct-q4km \
  --model qwen3-1.7b-q4km \
  --out ../.local/candidate-model/probe.json

# 2) 选一个模型跑 dev 连续回合（起点/移动/时间流逝/连续）
node scripts/candidate-model/run-a-candidate.mjs \
  --model qwen2.5-1.5b-instruct-q4km --set dev \
  --out ../../results/quality/a-run-1.5b.json
```

`probe-models` 记录：host 侧哈希校验、加载尝试（WebGPU→CPU 回退及原因）、加载
耗时、首可读字符、每调用 `prompt_n/predicted_n/predicted_ms`（吞吐可由模型自己
的计数器算出）、完整原文、事实判定、host 侧 nvidia-smi 显存峰值、页面 console
里与 backend 相关的行。`backend:'webgpu'` 只表示 WebGPU 路径加载成功，不表示
每层都落在 GPU；显存峰值与 CPU 对照是补充证据。**不要把 n_gpu_layers 当 GPU
生效的证明。**

`run-a-candidate` 可加 `--entry /src/lib/.../instruct/index.ts`（03 的模块）与
`--export generateCandidate`，即用同一加载、同一场景跑 03 的候选，避免 09/03
各自重建运行器。

## 5. 已验证（mock，不代表 GPU/速度）

```bash
cd frontend
npx vitest run src/lib/world-engine/runtime/wllama-engine.test.ts   # 21 passed
npx vitest run src/lib/world-engine/local/narration-candidates/model-runtime  # 14 passed
npx tsc --noEmit -p tsconfig.json
npx eslint src/lib/world-engine/local/narration-candidates src/lib/world-engine/runtime/wllama-engine.ts
```

覆盖：catalog 身份/哈希格式、模板消息与 fallback prompt、思考块完整/流式剥离
（含跨块分割）、事实通过时 accepted、方向写反自动带修复提示重试、两次失败保留
草稿并 `accepted:false`、空增量点编造移动被拒、abort 不被吞、`chat()` 真实
system 转发。

## 6. 限制与后续

- 真实浏览器正文尚未产出（推理锁被 02 占用）。解锁后按第 4 节顺序跑，
  先把原文追加到 `results/quality/team-08-runtime.json`，再据真实失败改 prompt。
- 目标设备是 RTX 4060 Laptop 8GB / 16GB / i7-13700H。4B 模型仅 2.5GB 权重，
  但 WebGPU + KV cache 是否放得下、首段等待是否可接受，必须由 probe 实测；
  未测前不把 4B 当默认。
- 本线不拥有主页面与 `game-model.ts`。接线由主集成者完成（见下）。
- 03 的 `instruct/template.ts` 目前把 system 拼进 user 首行（chat 模式），可用
  但弱于真实 system 消息；建议改用 `engine.chat()`（本线已支持）或直接调用
  `generateCandidate`。
- 训练权重（qwen25-0.5b/1.5b narration）不在本线候选内；它们属于 B 组，模板由
  02/10 提供，不能拿本文件的 instruct 模板套用。

## 7. 主 agent 需要改的几行

1. 页面加载：把 `loadEngine(url)` 换成
   `loadCandidateModel(modelSpec('qwen2.5-1.5b-instruct-q4km'))`（或页面配置的
   model id），用返回的 `engine`；`backend/fallback` 写进调试日志。页面现有
   WebGPU→CPU 回退逻辑可删除，避免两套回退互相覆盖。
2. `game-model.ts` 的 narration 分支：调用本线 `generateCandidate`
   （或 03 的模块），传入 `committed/inputText/policy`（scene 从已结算状态取），
   把 `accepted`、`verification`、`timings.firstReadableMs` 上报；不要再用
   模板句覆盖已接受的正文。
3. 停止按钮：`engine.cancelActive()`（08-runtime 前一任务已交付）。
4. 若 03 的生成模块被采用，用本线 `run-a-candidate.mjs --entry ...` 复跑同一
   场景，确认模板与模型对应，再接线。
