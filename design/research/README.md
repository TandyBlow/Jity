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
