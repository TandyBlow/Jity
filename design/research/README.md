# Research records (Chapter 8 material)

One file per experiment. Each record answers a research question with measured
numbers, states the conditions under which it holds, and ends with a design
principle that can be cited. Records are written when the experiment runs, not
after the fact; failures stay in.

## Format

```text
# E<nn> <short title>
Question      one sentence, the research question
Setup         code paths, page/offline, model ids and hashes, driver hash
Data          ids, counts, splits/holdouts, label provenance
Arms          what is compared and how each arm decides
Metrics       definitions and thresholds (frozen before the run)
Results       tables with real numbers; failures included
Conditions    what the numbers do and do not cover (proxy vs device, sample size)
Principle     one or two sentences a paper can quote
Artifacts     evidence files, manifests, commits
```

## Index

| id | title | status |
|---|---|---|
| E01 | Information extraction: rule distillation vs appearance-level holdout | done |
| E02 | Fact-support verification: claim vs settled record | done |
| E03 | Existence-gated decision arm for information reads | done (experimental) |
| E04 | Mobile-proxy timing composition | done (proxy only) |
| E05 | Deployment parity: PyTorch vs int8 ONNX heads | done |
| E06 | Information as events: independent annotation vs clause labels | done |
| E07 | Negation/failure probes with verified golds | done |
| E08 | Same-budget decomposition: shared vs split heads | done (criterion partly met) |
| E09 | Narration representation A/B: prose-facts vs serialized | done (prose-facts direction) |
| E10 | Outcome relation: model head vs rule on narration | done (HPC) |
| E11 | Condition relation: fact vs task goal | done (HPC, directional) |
| E12 | Decide vs shadow on read turns: where the model's turn never comes | partial (turn 4 unmeasured) |
| E13 | Cross-turn relation: prior point in the goal decision | done (HPC, directional) |
| E14 | Relation heads: int8 export and decision parity | done (deployment-ready) |
| E15 | Five-arm scoreboard: measured cells and gaps | done (2/5 fixed, 1/5 end-to-end) |
| E16 | Cross-appearance negatives fix the extraction pointer | done (holdout 8/9 when decided) |
| E17 | Decide arm increments predate the topic guard | done (3 corroborated decisions) |
| E18 | Contribution accounting for the hybrid arm | done (5131 micro vs 133 LLM) |
| E19 | Per-role guard: model channel measurable in the page | done (1 decision/turn) |
| E20 | Five-arm end to end: the LLM arm | done (26/48 state, 264 s) |
| E21 | Micro-generative arm: measured below its gate | done (0% event exact) |
| E22 | Mobile-proxy timing: current build | done (218.6/252.8 s, still 4x) |
| E23 | LLM fixed-event cell: direct four-state probe | done (7/19 vs heads 17/19) |
| E24 | 20-input acceptance on the micro default | done (20/20 gates) |
| E25 | Phone real device: single 0.6B CPU arm, two turns | done (25.2/193.3 s; WebGPU still crashes) |
| E28 | Narration reverse decomposition: six-operation taxonomy, open share | done (30-sample manual: open 3.6%) |
| E29 | Memory baseline: single-engine arm on desktop | done (page 0.72 GB attribution; Edge RSS peak 4.65 GB; JS heap 58 MB) |
| E30 | Planning dataset v0: fact-clause selection and order | done (58.8% clauses expressed) |
| E31 | Program reconstruction baseline | done (program plan 0.21 / oracle plan 0.29 char F1) |
| E32 | Clause selection model (0.1M logistic) | done (grouped CV F1 0.906; reconstruction 0.265) |
| E33 | plan-to-prose v0 (0.84M char transformer) | negative (charF1 0.332 but degenerate/garbled samples) |
| E34 | Word-level edit profile | done (delete 63.8%, replace 22.6%, keep 11.5%, insert 2.1%) |
| E35 | Edit decoder v1: char keep/delete tagger | done (charF1 0.465, zero invention, but char-scrambled output) |
| E36 | Edit decoder v2: word-level span pointers | done (charF1 0.459, wordRatio 0.312, zero invention, incoherent) |
| E37 | Replacement layer: phrase rewrite pairs + tiny seq2seq | negative (exact 1.2%, charF1 0.212; needs joint decoding) |
| E38 | Joint edit decoder v1 + phase-3 synthesis | negative (mode collapse; data volume is the bottleneck) |
| E39 | Corpus ceiling: all human-written targets sum to 362 passages | done (expansion needs new human writing) |
| E40 | Snapshot growth: 200 KB/turn, dominated by per-point full states | done (pointStates 1.77 MB over 12 turns) |
| E41 | Hand-written expansion: 62 targets, corpus 362 to 424, frozen holdout | done (410 SFT rows; curve run in E43) |
| E42 | Semantic context sizing: 64k real calls, KV budget, page memory | done (max 6,797 tokens; 8192 is safe) |
| E44 | Context-aware rewrite choice: retrieval and a 10-feature ranker | done (rank 0.116 vs freq 0.104 exact) |
| E45 | Zero-invention pointer editor (copy + learned order) | done (charF1 .431, zero invention, 13 test) |
| E46 | 1.7B LoRA data curve, same 58-prompt holdout | negative (290 rows .709 vs 339 rows .671) |
| E47 | Semantic ctx A/B, headless single turn | done (12288 2342.7MB vs 8192 2064.3MB, delta 278MB) |
| S1 | Synthesis 2026-11-28: what is publishable, what is still open | done |
| E48 | Memory levers measured: browser 731MB, Next 270MB, KV q4 −227MB, n_batch no-op, URL/OPFS no-op | done |
| E49 | Pointer v3: beam search +0.05, bigram prior hurts every metric | done (λ=0: .600/.496/.495, zero invention) |
| E50 | Sentence frames from fact clauses: generic patterns express 10/10, charF1 .899 vs human | done |
| E51 | Frame v2: 160 annotations, slots are verbatim fact spans, frozen inventory | done (160/160 render, held-out 27/30) |
| E52 | Structure model: 1.24M end-to-end pattern+span | negative (test .036 vs .107 majority; oracle 0.706) |
| E53 | Semantic LLM call audit with per-task attribution | done (344 calls/20 turns; handoff) |

> 编号前缀（2026-11-28）：叙事实验用 `N`，语义实验用 `S`，实验平台用 `P`。
> 本页 N01–N08 即 2026-11-28 之前的 E54–E61（与语义分支的 E54–E57 冲突后重编）。
| N01 | Role parse of settled facts: 36% subject-less, 4.5% recoverable from settlement | done (bundle fixed) |
| N02 | Rule composer baseline: fidelity by construction, length 0.45x, drops 36% of clauses | done (bundle fixed) |
| N03 | Rule organization: 29 merges (1.8%), event clustering is the missing step | done (bundle fixed) |
| N04 | Event clustering: discourse inheritance recovers 26% at 86% precision; 693 merges; log feel is in the facts | done |
| N05 | Per-point grounded eval: 1.7B covers 57% of facts and 0% of NPC outcome labels; rules 67%/100% | done |
| N06 | Delta narration: 82% of fact clauses repeat; delta arm covers 100%/100% in 57% of current chars | done |
| N07 | Zero-parameter candidate: action opening + delta + all results; 103 chars/point, 100%/100%, 0.069 ms | done |
| N08 | Failure taxonomy: candidate has 0 misattribution and 100% outcome labels; current arm omits 99% | done |
