# 12 — best-of-N 探索线交接

## 1. 问题

产品每回合只写一份正文。单份可能事实错、漏必述项或复读上一回合。要判断“多生成几份再选”是否值得，必须先回答：

1. 同一冻结已结算输入下，6 个种子的正文是否真是**不同表达**（不是相同必述事实换词）？
2. 6 份里至少 2 份事实/视角合格且不同质吗？
3. 在相同输入、种子集合、模型与总时序条件下，best-of-2/4 相对 N=1 是否有可复核收益？
4. 多出的调用是否仍满足浏览器 60 秒首可读 / 300 秒整回合？

本线没有先实现 best-of-4 产品路径。先冻结预注册与采样器，再做真实生成和多样性分析。

## 2. 已交付（当前 HEAD `d7ca960ba2e6faf1e865f185698820772c67900c`（模块与预注册在 `adb54647`，可移植 pack 覆盖在 `4dcee4c5`，N-arm 门在 `d7ca960b`））

### 2.1 产品候选模块（新目录，未接页面）

`frontend/src/lib/world-engine/local/narration-candidates/best-of-n/`

| 文件 | 导出 |
|---|---|
| `types.ts` | `CandidateSample`、`CandidateAssessment`、`DiversityConfig`、`PairVerdict`、`DiversityReport`、`TextMetrics`、`SelectionDecision`、`PoolConfig`、`PoolRun` 等 |
| `diversity.ts` | `profileSample`、`comparePair`、`clusterProfiles`、`buildDiversityReport`、`effectiveRepetition`、`textMetrics`、`normalizeProse`、`jaccard`、`containment` |
| `select.ts` | `selectCandidate`、`transportFailed` |
| `pool.ts` | `runCandidatePool` |
| `index.ts` | 以上稳定导出 |

关键契约：

```ts
runCandidatePool(
  config: { seeds: number[]; concurrency: number; perCallTimeoutMs: number; totalBudgetMs: number },
  generate: (seed, signal, index) => Promise<{ text; finishReason; totalMs; firstTokenMs?; tokens? }>,
): Promise<PoolRun>
// PoolRun: every raw sample (including error/timeout/cancelled), real wallMs,
// requested/completed/failed, peakConcurrency, budgetExceeded.

buildDiversityReport({ profiles, qualifiedIds })
// effectiveRepetition = 1 - distinctRealizationClusters / sampleCount
// qualifiedClusters / qualifiedDistinctClusters are separate counts.

selectCandidate({ candidates, assessments, options })
// Order: fact-qualified > mandatory coverage > in-text repetition >
// prior echo > seed. Never length, never model self-score.
// `qualified: null` is not adopted unless options.allowProvisional === true.
```

同质判定只看正文：字符 3-gram（换词/复制）、句子节奏 2-gram（对白/叙述、句长桶、逗号桶）、licensed entity 出现顺序、逐句最佳对齐相似度、首尾句相似度；complete-linkage 聚类。阈值写在预注册里，代码里是 `DEFAULT_DIVERSITY`。

### 2.2 实验与预注册

`experiments/narration-best-of-n/`

- `preregistration.json` + `preregistration.sha256`：在任何模型输出前冻结；SHA-256 `b1079ca6ac39b68c220b2e23004131d84a90e6abc5a119518b5a7b93c56242b3`。
- 使用 01 的共享包 `narration-dev-package-v1`（manifest `20da8db9…`、cases `8dd2de92…`、rubric `020c9ca9…`），没有另建输入包。
- b01：`frozen-row-0012`，种子 `17,29,43,61,79,97`；模型 `~/qwen15b`（HPC 基座，不是浏览器产品权重）；temperature 0.45 / top-p 0.95 / top-k 40 / 240 new tokens（产品候选默认量级）。
- b02（泛化，未提交）：no_change、move_direction、item_transfer、gender_pronoun、continuity 各一例。
- `src/prepare.ts`：校验包哈希、用产品 `renderTrainedInstructUser` 渲染请求、写 `data/b01/{requests,expected,plan}`；`expected` 不含 `reference`。
- `src/verify_pack.py`：HPC 前再次校验 manifest/cases/rubric 哈希、Python 规范化 input SHA、prompt SHA、种子顺序、reference-only 子串泄漏。
- `src/generate_hpc.py`：10 专用；模型加载、chat template、逐种子真实生成、原始文本/首 token/总耗时/token 数/finishReason/GPU/模型权重哈希全部落盘；输出目录存在即拒绝。
- `src/analyze.ts`：调用 01 的 `reviewNarration` 判 fact/style/review；用本模块算重复率、合格簇、N=1/2/4 arm 对比；写 `report.json`、`report.md`、`review-request.json`。不读参考答案。

## 3. 验证（本提交实际结果）

```bash
npx vitest run src/lib/world-engine/local/narration-candidates/best-of-n/best-of-n.test.ts
# 22/22 pass

npx tsc --noEmit --target ES2020 --module esnext --moduleResolution bundler --strict \
  --skipLibCheck --resolveJsonModule --lib ES2020,DOM \
  ../experiments/narration-best-of-n/src/prepare.ts ../experiments/narration-best-of-n/src/analyze.ts
# exit 0

npx eslint src/lib/world-engine/local/narration-candidates/best-of-n --ext .ts
# exit 0

python -X utf8 experiments/narration-best-of-n/src/verify_pack.py --batch b01
# status pass: manifest/cases/rubric hashes, 1 case input SHA, 6 prompt SHAs, no reference-only substring
```

单元测试覆盖：6 份完全相同 → 1 簇、`1-1/6`；同义改写同骨架 → 同质；同必述事实但不同结构 → 不同质；首尾相同 → 同质；complete-link；合格簇分母独立；不采纳未判候选；长文低覆盖输给短文全覆盖；同质重复只留证据；prior echo 选择；池预算/单调用超时/失败样本/长度截断。

## 4. 未完成 / 限制（如实）

- **尚无真实模型输出**。b01 已准备并通过哈希校验，HPC 请求在 `results/product/hpc-requests/12-best-of-n-b01.json`，等 10 运行/取回。没有 6 份原文前，不写收益结论、不接产品。
- 模型是 `~/qwen15b` 基座，不是当前浏览器产品权重；任何产品结论需同条件复测。
- 01/rubric 检查器是机械判据，不是人工；`pending` 不通过。独立逐句复核请求会在有原文后写 `review-request.json` 交 01，AI 审读另标 `independent_agent`，真实人工未发生记 pending。
- HPC 时间不是浏览器时间；60/300 秒必须由 09 在同一产品页实测。
- `runCandidatePool` 只负责“N 次生成 + 记录”，不替产品做重试策略；候选内部的 retry 时间必须计入 `totalMs`。

## 5. 给 06 的接线（等真实证据后，不现在改页面）

建议把 best-of-N 做成现有 `NarrationCandidate` 的一个新候选，而不是改 `selection/`：

```ts
// 伪代码：由 06 在自己树内接线；本线不直接改 page/game-model/selection
async run({ engine, prepared, point, policy }) {
  const pool = await runCandidatePool(
    { seeds: [17, 29, 43, 61, 79, 97], concurrency: 1,
      perCallTimeoutMs: policy.timeoutMs ?? 60_000, totalBudgetMs: 120_000 },
    async (seed, signal) => {
      const result = await generateCandidate({
        engine, committed: prepared.facts, inputText: prepared.inputText ?? '',
        policy: { ...policy, seed, maxAttempts: 1 }, signal,
      });
      return { text: result.text, finishReason: result.attempts.at(-1)?.finishReason ?? null,
        totalMs: result.timings.totalMs, firstTokenMs: result.timings.firstTokenMs };
    },
  );
  const assessments = pool.samples.map((sample) => ({
    id: sample.id, qualified: /* 该样本的 verifyNarration 无 fact 硬错 */,
    mandatoryCovered, mandatoryTotal, hardIssueKinds,
  }));
  const decision = selectCandidate({ candidates: pool.samples, assessments,
    options: { priorText: point.priorText ?? null, licensedEntities: prepared.policy.visibleEntities ?? [] } });
  // 只把 decision.selectedId 对应的、已通过检查的正文作为 candidate accepted；
  // 其余候选、issues、耗时、rejected 全部放 detail 证据。
}
```

接的前提（缺一不接）：

1. b01+b02 至少 2 个 case 有 ≥2 份事实合格且不同质；
2. N=2 或 N=4 在相同条件下严格优于 N=1；
3. 09 实测 N 方案仍满足 60 秒首可读/300 秒整回合；
4. 用户可见文本只来自通过检查的候选，程序降级单独标记。

## 6. 文件位置

- 模块：`frontend/src/lib/world-engine/local/narration-candidates/best-of-n/`
- 实验：`experiments/narration-best-of-n/`
- HPC 请求：`results/product/hpc-requests/12-best-of-n-b01.json`
- 本线结果：`results/12-best-of-n/`（后续 completion）
- 预注册哈希：`experiments/narration-best-of-n/preregistration.sha256`
