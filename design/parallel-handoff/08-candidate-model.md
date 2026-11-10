# 08 candidate-model handoff（A 组：可部署模型与浏览器运行）

分支 `goal/local-08-runtime`。本线工作树：
`D:/others/Jity/.local/parallel-local-game/worktrees/08-runtime`。
本线负责 A 组的模型与真实运行：把本机已有的原生 instruct GGUF 真正在浏览器里
加载、按模型自己的模板生成中文正文、留下可复查的原文与耗时，并把模板、加载
方式、模型路径和**实测出来的限制**交给 03（生成策略）、09（页面/共享运行器）
和 06（接入）。

## 0. 状态（如实）

- **已真实跑通**：Edge + wllama 3.8.1 + WebGPU，适配器是 **NVIDIA RTX 4060
  Laptop（lovelace）**。Qwen3-1.7B 在连续三个点（起点、移动、时间流逝）全部
  通过事实核对，正文 137～145 字，每点 8～11 s，首段 1.5～2.2 s，加载 44.7 s。
- **Qwen3-4B-Instruct-2507 不能加载**：单文件 2.5 GB，超过 wllama 3.8.1 把整
  文件读进一个 ArrayBuffer 的上限；WebGPU 和 CPU 都一样。已在浏览器里单独测过
  HEAD/Range/流式读取都正常，只有 `arrayBuffer()` 失败。**03 不要再花窗口试 4B。**
- **1.5B 在 220 字目标下不稳定**：会自造对话、钥匙、开门，并出现重复段落；
  1.7B 更稳，但通常写到 140 字左右。200～300 字的稳定正文要靠训练权重或更大
  基座，这不是 A 组两个小 instruct 模型能保证的。
- **free-day 开局复跑待做**：09 的共享队列已经用 1.5B 跑通过一次（1092 字真实
  产品输入，289 字 accepted），但那次把全 roster 的站位念了一遍；模板已改成
  开局不列站位，需要再跑一次确认。当时锁被 09 占给 10 线，未抢跑。

## 1. 后端能力（先说结论，再说证据）

| 启动方式 | `requestAdapter()` 默认 | `{powerPreference:'high-performance'}` |
|---|---|---|
| `--force_high_performance_gpu` | nvidia / lovelace | nvidia / lovelace |
| `--force_low_power_gpu` | intel / gen-12lp | intel / gen-12lp |

运行日志里 ggml 也打印了同一件事：

```
ggml_webgpu: adapter_info: vendor_id: 0 | vendor: nvidia | architecture: lovelace
```

**关键点**：这台混合显卡笔记本如果不加 `--force_high_performance_gpu`，Edge
的 WebGPU 会选 Intel 核显；`n_gpu_layers=99999` 和 `backend:'webgpu'` 都不能
说明用的是独显。本线的 `probe-models.mjs` / `run-a-candidate.mjs` 现在默认带
这个开关，并把 `adapterInfo` 和 ggml 行写进证据。

`probe-adapter.mjs` 不加载模型，几秒钟就能复核；`maxBufferSize` 是
2 147 483 648（2 GB），这也是 2.5 GB 模型读不进来的直接背景。

## 2. 本机已核对的模型

文件在共享只读目录，未复制。大小/sha256 由本机文件计算；架构、上下文、
chat template 由 `scripts/candidate-model/gguf-meta.mjs` 读 GGUF 头得到。

| catalog id | 文件 | 大小 | sha256 | 模板 | 能加载 | 用途 |
|---|---|---|---|---|---|---|
| `qwen3-1.7b-q4km` | Qwen3-1.7B-Q4_K_M.gguf | 1 107 409 472 | `b139949c…181897` | `qwen3-hybrid-chatml-no-thinking-v1` | 是 | **A 组质量默认** |
| `qwen2.5-1.5b-instruct-q4km` | qwen2.5-1.5b-instruct-q4_k_m.gguf | 1 117 320 736 | `6a1a2eb6…e9407e` | `qwen2.5-instruct-chatml-v1` | 是 | 速度备选；09 共享队列默认 |
| `qwen3-4b-instruct-2507-q4km` | Qwen3-4B-Instruct-2507-Q4_K_M.gguf | 2 497 281 120 | `3605803b…67e597` | `qwen3-instruct-2507-chatml-v1` | **否（2.5 GB）** | 暂不可部署 |
| `qwen3-0.6b-q4km` | Qwen3-0.6B-Q4_K_M.gguf | 396 705 472 | `ac2d9771…d524a` | 同 Qwen3 1.7B | 是 | 冒烟测试 |
| `qwen2.5-0.5b-instruct-q4km` | qwen2.5-0.5b-instruct-q4_k_m.gguf | 491 400 032 | `74a4da8c…d7a9db` | 同 Qwen2.5 1.5B | 是 | 冒烟测试 |

文件位置（按顺序查找，`--models-dir` 可覆盖）：

1. `D:/others/Jity/.local/world-narration-worktree/frontend/public/models`
2. `D:/others/Jity/frontend/public/models`
3. `D:/others/Jity/.local/models`

### 2.1 为什么 4B 不行（可复核）

`probe-fetch.mjs` 在真实浏览器里对同一个 URL 做了四件事：

- `HEAD` → 200，`content-length` 2 497 281 120，`accept-ranges: bytes`；
- `Range: bytes=0-1023` → 206，正好 1024 字节；
- 读 `response.body` 流 → 1 MiB 正常；
- `response.arrayBuffer()` → **Failed to fetch**（1.1 GB 的 1.7B 同样调用成功）。

wllama 3.8.1 的模型下载路径最后是 `fetch(url).arrayBuffer()`，所以 2.5 GB
在浏览器里根本到不了 ggml。要支持 4B，需要：小于 2 GB 的量化、用
`llama-gguf-split` 生成真正的分片（不是按字节切）、或者换成流式写 OPFS 的
加载器。三件都不是本线现在能顺手做的；先把 1.7B 作为上限。

## 3. 模板（按模型区分，不要手写通用 ChatML）

wllama 3.8.1 的 `createChatCompletion` 会应用 GGUF 自带的 Jinja 模板。本线把
**消息列表**交给引擎，不拼 ChatML：

- Qwen2.5（0.5B / 1.5B instruct）：模板没有 `enable_thinking` 分支，多传的
  参数被忽略；`system` + `user` 两条消息即可。
- Qwen3-0.6B / 1.7B（混合思考）：模板在 `enable_thinking=false` 时插入空思考块；
  引擎固定传 `chat_template_kwargs: { enable_thinking: false }`，候选再在流式
  和最终文本两层剥掉残余思考块。
- Qwen3-4B-Instruct-2507：模板没有 `enable_thinking` 分支，本来不思考。

### 登记的引擎改动

原 `complete(prompt)` 只发一条 user 消息，instruct 模型会用自带默认 system。
新增 `WllamaInferenceEngine.chat(messages, options)`，复用原有取消、超时、流式、
证据路径；`complete()` 与公共 `InferenceEngine` 接口不变。21 项引擎测试通过。

## 4. 导出 API

`frontend/src/lib/world-engine/local/narration-candidates/model-runtime/index.ts`

```ts
MODEL_CATALOG; modelSpec(id); modelSpecByFile(fileOrModelId)

loadCandidateModel(spec, {
  modelRoot?, preferGpu?, forceCpu?, contextSize?, numThreads?,
  abortGraceMs?, signal?, onEvidence?,
}) => { engine, backend, fallback, attempts, loadMs, evidence, webgpuAvailable }

generateCandidate({
  engine, committed, inputText, priorText?, signal?, onProgress?,
  state?, before?, delta?, policy?,
}, { spec? }) => {
  text, accepted, status, rawAttempts, issues, timings,
  strategyVersion, model, verification,
}
```

`generateCandidate` 不传 `spec` 时会按 `engine.info.modelId` 从 catalog 识别，
所以 09 自己加载 GGUF 后直接调用即可（已实测）。`rawAttempts` 带每次调用的
prompt、正文、llama.cpp 的 `prompt_n / predicted_n / predicted_ms / finishReason`。
失败不会用模板句替换正文：`accepted:false` 原样返回，`status` 是
`accepted|rejected|timeout|error`；超时和引擎死亡是终止态，不会拿死引擎重试。

`policy` 关键字段：`scene`、`viewpoint`、`roster`、`locations`、`knownPositions`、
`knownEntities`、`time`（普通时长或 09 的 `{duration:{...}}`）、`minChars`、
`targetChars`、`paragraphs`（默认 3）、`maxTokens`、`attempts`（默认 2）、
`temperature`、`seed`、`timeoutMs`、`instruction`、`priorText`、
`includeInputText`（默认关）、`includePriorText`（默认关）。

### 事实的两种来源

`facts.ts` 把提交包拆开：

- **这一小段时间里发生的事**（移动、任务达成）——正文必须写到；
- **本来就成立的状态**（站位、精神值、个性）——站位只作为场景/谁没动的依据，
  精神值与个性只作为“用神态动作暗示”的提示，不写数字、不照抄原句。

事实核对跑在同一个投影上，所以不会因为“没念出精神值”被判失败。

## 5. 真实运行结果（原文在 `.local/candidate-model/`）

设备：i7-13700H / 16 GB / RTX 4060 Laptop 8 GB；Edge 157.0.4341.42，
`crossOriginIsolated=true`。除特别注明外都是 **WebGPU / nvidia lovelace**。

| 模型 | 场景 | 加载 | 首段 | 每点耗时 | 结果 |
|---|---|---|---|---|---|
| Qwen3-1.7B | dev 起点/移动/时间流逝 | 44.7 s | 2.2 / 1.6 / 1.5 s | 11.2 / 8.4 / 9.5 s | **3/3 accepted**，137～145 字 |
| Qwen3-1.7B | unseen 世界（余晚/罗青） | 43.0 s | 2.2 s | 27.4 s | rejected：把“库房→平台”写成“从楼梯间走来”，漏事实 |
| Qwen2.5-1.5B | dev 同三点，220 字目标 | 39.9 s | 1.4～1.9 s | 34～60 s | 0/3：自造对话/钥匙/开门，重复段落 |
| Qwen2.5-1.5B | 09 共享队列 free-day 开局（1092 字输入） | 28.9 s | 21.5 s | 48.3 s | accepted，289 字；但把全 roster 站位念了一遍（模板已修，待复跑） |

1.7B 的最佳原文（移动点，事实全部对上）：

> 周宁站在走廊尽头，望着门厅方向，盒子依旧紧闭在盒盖下。两分钟过去了，林川从
> 走廊走到门厅，脚步声在走廊里回响。周宁没有动，只是盯着盒子，听着走廊里偶尔
> 传来的脚步声和门厅的寂静。空气中弥漫着一股淡淡的木香，混合着潮湿的空气，
> 让人感到些许不安。盒子的阴影在墙上缓缓移动，像是在等待什么。

这段正文 145 字，读得通、事实对得上、时间写到，但**没到 200 字**。把目标拉高
到 220～240 时，1.5B 开始编事件，1.7B 也更容易编出额外移动。

## 6. 提示词上踩过的坑（都是真实运行暴露的）

1. 把原始序列化串（`【状态】/【变化】`）给 0.5B，它会直接抄字段清单 → 默认关。
2. 把精神值列成“必须写到的事实”，1.5B 会写“精神值为10”并围着它编动作 →
   精神值/个性改成行为提示，不写数字。
3. 把上一段正文（哪怕只给 90 字尾巴）放进提示，1.7B 会大段照抄（63% bigram
   重叠）并复述过期站位 → 默认不给模型，只用于重复检测。
4. 把全 roster 的站位列出来，1.5B 会念一遍“芬格尔在器材棚、楚子航在钟楼……” →
   开局不列站位，有移动时只列本场景的人。
5. 列禁用动作（“不开箱、不拿取……”）会让模型写“她没有打开它”，而共享对齐器
   不读否定，把“打开”判成新增事件 → 改成一句正向的“人物位置和物品都保持原样”。
6. 时间只写在提示中段，1.7B 会漏；放到最后一句要求里才稳定写出来。
7. 移动事实要模型“用人名和两个地点写一句”，否则它会用“他走过来”代替，
   对齐器判 `omitted_fact`。

## 7. 命令

```bash
cd frontend
# 本机推理是独占资源：先取锁，finally 释放
python ../../.local/parallel-local-game/resource_lease.py acquire --lane 08-runtime --purpose "A candidate run"

# 0) 几秒钟确认这次真的用独显（不加载模型）
node scripts/candidate-model/probe-adapter.mjs --out ../.local/candidate-model/adapter.json

# 1) 验证一个 GGUF 能不能被浏览器读进来（不推理）
node scripts/candidate-model/probe-fetch.mjs --file Qwen3-1.7B-Q4_K_M.gguf

# 2) 一个模型跑多个点（默认带 --force_high_performance_gpu）
node scripts/candidate-model/run-a-candidate.mjs \
  --model qwen3-1.7b-q4km --set dev --target-chars 200 --max-tokens 360 \
  --out ../../results/quality/a-run-qwen3-1.7b.json

# 3) 用 09 的共享队列跑真实 free-day 输入（--gpu 会走 WebGPU；
#    09 的浏览器启动没有 high-performance 开关，所以会落在 Intel 核显）
cd ../09-ui/frontend
node scripts/quality-candidates/run-browser-candidates.mjs \
  --candidate 08-runtime=D:/others/Jity/.local/parallel-local-game/worktrees/08-runtime/frontend/src/lib/world-engine/local/narration-candidates/model-runtime/index.ts \
  --candidate-model 08-runtime=/models/qwen3-1.7b... \
  --candidate-model-id 08-runtime=qwen3-1.7b-q4km \
  --set free-day --only free-day-open --gpu --out <evidence.json>

python ../../.local/parallel-local-game/resource_lease.py release --lane 08-runtime
```

`--set`：`dev`（起点/移动/连续）、`unseen`（另一套世界）、`all`。
`--low-power-gpu` 强制核显，`--force-cpu` 关 WebGPU。`--entry` 可直接跑 03 的
模块（`/@fs/...` 或 `/src/...`）。

**模型服务必须支持 Range**：本线的两个脚本用 `gguf-server.mjs` 返回
`Accept-Ranges: bytes` 和 206。即使当前 wllama 仍走整文件 `arrayBuffer()`，
生产模型服务器也应该这样做（1.1 GB 能过，2.5 GB 过不了；换加载器时 Range 是
前提）。

## 8. 已验证（mock + 真实）

```bash
cd frontend
npx vitest run src/lib/world-engine/local/narration-candidates   # 26 passed
npx vitest run src/lib/world-engine/runtime/wllama-engine.test.ts \
  src/lib/world-engine/runtime/inference-queue.test.ts \
  src/lib/world-engine/local/runtime-diagnostics                  # 66 passed with the candidate suite
npx tsc --noEmit -p tsconfig.json
npx eslint src/lib/world-engine/local/narration-candidates scripts/candidate-model
```

真实运行证据：`.local/candidate-model/{adapter.json, probe-fetch-*.json,
run-qwen3-1.7b-dev-r5.json, run-qwen3-1.7b-unseen-r8.json,
run-qwen25-1.5b-all.json, run-qwen25-1.5b-dev-r3.json, via09-free-day.json}`；
共享摘要：`results/quality/team-08-runtime.json`。

## 9. 限制

- free-day 开局在“不列全 roster”模板下还没有复跑；当前共享证据里的 289 字是
  旧模板。
- 1.7B 平均 ~140 字，200～300 字目标没有稳定达到。
- 4B 单文件不可加载；没有做分片或换加载器。
- WebGPU 只证明了适配器和上下文；wllama 不暴露每层落在哪个后端。
- 共享 `narration-alignment.ts` 不读否定（“她没有打开它”），也会漏
  “走向/从楼梯间走来”这类改写。该文件不归本线，未改；出现时会多一次修复或
  误拒，主 agent 可让拥有者收紧/放宽词表。
- 训练过的叙事权重（qwen25-0.5b/1.5b narration）属于 B 组，模板由 02/10 提供，
  不能套本文件的 instruct 模板。

## 10. 主 agent / 06 需要改的几行

1. 页面加载：
   `loadCandidateModel(modelSpec('qwen3-1.7b-q4km'), { onEvidence })`，用返回的
   `engine`；把 `backend/fallback/adapterInfo` 和 ggml adapter 行写进调试日志。
   浏览器启动参数加 `--force_high_performance_gpu`，否则会落在核显。
2. `game-model.ts` 的 narration 分支：调用 `generateCandidate`（或 03 的模块），
   传 `committed/inputText/policy`（`scene` 从已结算状态取），上报
   `accepted/status/verification/timings.firstReadableMs`；`status==='timeout'`
   后先 `await engine.load()` 再继续下一个点。
3. 停止按钮：`engine.cancelActive()`。
4. 页面加载态：1.7B 冷加载约 40～45 s，首段约 1.5～2.2 s；不要用“首段慢”做
   取消的理由，慢的是加载。
5. 若采用 03 的生成模块，先用 `run-a-candidate.mjs --entry ...` 复跑同一场景，
   确认模板与模型对应，再接线。
