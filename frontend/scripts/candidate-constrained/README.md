# C 路线运行入口

## 1. 不起模型的完整自检（本线）

```bash
cd frontend
node scripts/candidate-constrained/run-program.mjs --out ../.local/candidate-constrained/run.json
```

- 用页面同一个状态内核（`buildInitialState` + `applyPoint` + `stateDigest`）构造真实点位：公开短场景 3 个点、自由一日 2 个点（其中 1 个是 6 类事实同时发生、另有 2 条视角外改动的复杂点）。
- `mode:'program'`，零模型调用；输出每个场景的正文、每段的来源与问题、必写事实覆盖、隐藏事实、耗时。
- 有任何场景 `accepted:false` 时脚本以非零码退出。

把 07 的语言层接进来（仍是程序，无模型）：

```bash
node scripts/candidate-constrained/run-program.mjs \
  --composer D:/others/Jity/.local/parallel-local-game/worktrees/07-sync/frontend/src/lib/world-engine/local/narration-candidates/prose-composer/index.ts
```

`--composer` 在运行时用 vite 加载对方模块并取 `createBeatComposer()`，通过 `policy.composer` 注入；本线 `src` 里没有任何跨线 import。

## 2. 真实浏览器 + 真实模型（09 的共用入口）

09 的 runner 不在本线，直接调用它的脚本，把候选指到本模块：

```bash
cd D:/others/Jity/.local/parallel-local-game/worktrees/09-ui/frontend
node scripts/quality-candidates/run-browser-candidates.mjs \
  --lane 04-settlement \
  --purpose "C route constrained candidate" \
  --candidate 04-settlement=D:/others/Jity/.local/parallel-local-game/worktrees/04-settlement/frontend/src/lib/world-engine/local/narration-candidates/constrained/index.ts \
  --candidate-export 04-settlement=generateCandidate \
  --candidate-policy 04-settlement='{"mode":"model","turnTimeoutMs":180000}' \
  --allow-dir D:/others/Jity/.local/parallel-local-game/worktrees/04-settlement/frontend/src \
  --model /models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --model-dir D:/software/Git/models \
  --set short --threads 6 --max-tokens 220 --hard-timeout-ms 240000 \
  --lease-wait-seconds 1800 \
  --out D:/others/Jity/.local/parallel-local-game/worktrees/04-settlement/.local/candidate-constrained/browser-short.json
```

要点：

- `--set short` 先跑公开短场景三个点；`--set free-day` 是自由一日真实点位。`--only` 可只跑单个场景。
- `mode:"program"` 时同一命令不需要模型：把 `--candidate-policy` 换成 `{"mode":"program"}` 即可（仍然会加载引擎，除非用 `--dry`/`--inspect`）。
- 模型每回合最多 6 次顺序调用，`turnTimeoutMs` 用完后剩余段由程序写，不会把整回合拖过等待上限；`--hard-timeout-ms` 是 runner 自己的兜底。
- 返回的 `rawAttempts` 里有每段的提示词、模型原始输出、这一段的全部问题；`composers` 标明每段谁写的（`model`/`program`/`program+model-failed`/`*:external`）。

## 3. 单元与类型检查（本线）

```bash
cd frontend
npx vitest run src/lib/world-engine/local/narration-candidates/constrained --maxWorkers=1
npx tsc -p tsconfig.world-contract.json --noEmit
npx eslint src/lib/world-engine/local/narration-candidates/constrained scripts/candidate-constrained
```
