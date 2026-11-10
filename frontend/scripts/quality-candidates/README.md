# quality-candidates：共用真实浏览器执行队列

一个入口跑多条候选路线，避免每条线各建浏览器、各自抢锁。它不是评测平台：记录真实输入、真实原文、真实时间与真实失败，正文是否合格由对应路线负责人读后判断。

## 1. 候选要准备什么

在自己的独占目录实现一个浏览器可导入的模块，导出：

```ts
export async function generateCandidate(args: {
  engine: InferenceEngine;          // 已加载的真实引擎，直接 engine.complete(...)
  committed: CommittedNarration;    // 已结算事实包（只读）
  inputText: string;                // 产品串行化的完整事实输入（只读）
  priorText: string | null;         // 连续回合时上一轮已接受正文
  onProgress?: (s: { text: string; status: string; verified: boolean; elapsedMs: number }) => void;
  policy: Record<string, unknown>;  // 视角、场景、时间、上限等，只读
}): Promise<{
  text: string;
  accepted: boolean;
  rawAttempts: unknown[];           // 每次真实调用的 prompt/raw/finish/耗时
  issues: unknown[];
  timings: { totalMs?: number; attemptMs?: number[]; firstTokenMs?: number | null };
  strategyVersion: string;
}>;
```

- 不要改写 `committed`/`inputText`/`policy`，不要自己读世界文件或另建状态。
- 模板由候选自己决定；已有训练权重必须用训练时的模板。
- 程序一次生成就一次返回（不能把整段预生成伪装成流式）；流式时通过 `onProgress` 给真实增量。
- 兼容旧导出名 `generateCommittedNarration`，但会记录 `export=generateCommittedNarration`（非标准契约）。

## 2. 一条命令

```bash
cd frontend
# 不要手动先拿锁：脚本会在启动浏览器前 acquire，结束（含失败）在 finally release。
# 等待别的线时只轮询锁文件，不启动第二个浏览器。

node scripts/quality-candidates/run-browser-candidates.mjs \
  --candidate 03-actions=/abs/path/to/instruct/index.ts \
  --candidate 04-settlement=/abs/path/to/constrained/index.ts \
  --owner 03-actions=03-actions \
  --set free-day \
  --only free-day-open,free-day-move \
  --model /models/qwen25-0.5b-narration-Q4_K_M.gguf \
  --out ../../../results/quality/browser-09.json
```

- `--candidate <id>=<模块路径>`：绝对路径可直接指向别的工作树，运行器用 Vite `/@fs` 读入，**不复制**候选代码。
- `--candidate-model <id>=/models/x.gguf`：同一队列里不同候选可用不同模型；同模型只加载一次，后续候选复用。
- `--set short|free-day|all`、`--only`、`--exclude`：先跑少量，看到可用改善再展开。
- `--repeat 2`：同一输入重复跑（记录波动，不用于刷分）。
- `--inspect`：只导入模块、解析导出，不加载模型、不占锁；候选作者可先自查。
- `--dry`：只打印场景身份，不加载模型。
- `--status`：不启动浏览器，只打印证据文件里每个候选最近一次运行、失败与通知。
- `--no-engine`：程序成文/规则候选专用；不加载模型、不占锁，给候选一个调用即抛 `engine_unavailable:stub_engine` 的 stub。模型候选用了它会被记成失败，而不是假装跑过。
- `--probe`：不导入候选，用纯文本 prompt 测浏览器/wllama 栈；用于区分“栈坏了”和“候选 prompt 不好”。
- `--lease-wait-seconds 1200`：锁被其他线持有时轮询等待；超时记 `lease_busy`，不假装跑过。
- `--gpu`：请求 WebGPU 层；证据同时记录 `webgpuAvailable`、`gpuRequested`、候选加载器报告的 `backend`（08 加载器）和 `backendNote`。请求不等于生效；只有 `backend=webgpu` 才写 WebGPU。
- 默认 CPU（`nGpuLayers=0`），证据明确写 CPU-only。
- `--model-dir <dir>`：模型实际服务目录；证据里的 `modelFile.servedPath/sha256/bytes` 是浏览器真正加载的那份字节，`requested` 是命令行请求，不混为一谈。
- `--candidate-loader <id>=<path>::loadCandidateModel` + `--candidate-model-id <id>=<catalog id>`：候选自带加载器时使用；同 model+loader 只冷启动一次。

## 3. 场景

`browser-driver/scenarios.ts` 只提供两类输入：

- `short-*`：既有的公开短场景（走廊/门厅、一人移动、两分钟流逝），与旧探针可比。
- `free-day-*`：真实《龙族·自由一日》世界。开局点直接取发布的世界文件；移动/任务场景由浏览器状态内核 `applyPoint` 实际应用作者给定的 delta，前后的状态摘要与 canonical digest 都是内核算的。**这些确认是确定性探针，不是模型结算输出**，证据里写明了。

每个场景都带：真实产品输入 `inputText`（`legacyNarrationInput`）、适配事实包 `committed`（同事实种类，但允许 slot 位置）、场景 grounding（地点/在场人物/物品/随身物/出口）、policy。

## 4. 证据

`results/quality/browser-09.json` 每次运行后原子写入，包含：

- `runner`：脚本路径、驱动路径、实际命令行、lane、alias 根；
- `device`：CPU、浏览器、`crossOriginIsolated`、`webgpuAvailable`；
- `candidates[id]`：owner、模块绝对路径与 sha256、实际导出名、模型、最近一次每场景摘要（`firstParagraph`、`chars`、`wallMs`、`runId`、`textLocation`）；
- `runs[]`：每次运行的完整输入（`input.text`）、场景身份（world/point/version/digest/viewpoint/changeKinds）、候选 prompt 与 raw attempts、段落、接受状态、`timings`、`progress.firstReadableAtMs`、错误、契约缺口；
- `failures[]`：加载失败、契约缺口、lease 占用、runner 超时。

`wallMs` 是请求起点到返回；`progress.firstReadableAtMs` 是真实流式文本第一次形成可读段（段落分隔或 ≥80 可见字符）的时间，候选不流式时为 null。

## 5. 首次运行结果

见 `design/parallel-handoff/09-browser-candidates.md` 与 `results/quality/browser-09.json` 的 `candidates[*].latest`。本文件不预设任何候选已经合格。
