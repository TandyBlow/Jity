# Lane 12 — realization diversity and best-of-N (experiments)

Owned by `12-best-of-n`. This directory holds the preregistration, the six-seed
sampler, the HPC generation entry, the offline analysis and the raw outputs. It
does not touch the product page, runtime, existing generation/checker modules or
another lane's worktree.

## Current status (2026-11-10)

b01 completed on HPC job 251512 (V100, fp16, 6 real outputs). It is a **negative
pilot**: 4 realization clusters (`1 - 4/6 = 0.333`) but **0/6 fact-qualified**.
All six omit the settled 4-minute advance and 黎知微's personality change; one
also uses first person and omits the move. The four clusters are four different
error shapes, not four valid realizations. Per the frozen rules there is no
benefit and N is not expanded. See `cause-analysis-b01.md`.

`preregistration.v2.json` (SHA-256 `ea077908…`) freezes the minimal follow-up:
the same case, model, seeds, sampling, cap and rubric, with one fixed writing
instruction in the user turn. It has no outputs yet. The HPC request is
`results/product/hpc-requests/12-best-of-n-b01-v2.json`.

## What is studied first

Not "more N is better". The first question is whether six independent samples of
ONE frozen settled input are actually different realizations: different
narrative structure, rhythm and detail organisation. Two samples that state the
same mandatory facts are not duplicates; two samples that arrange the same
skeleton with synonyms are.

Only when at least two fact/perspective-qualified samples are non-homogeneous,
and a best-of-N arm shows a reproducible improvement over N=1 on the same
inputs, seeds, model and timing accounting, does this lane test best-of-2 and
best-of-4. Effective repetition is reported as
`1 - distinctRealizationClusters / 6`; qualified distinct clusters are reported
as a separate count and never replace that denominator.

## Shared input package (not owned here)

01-input owns `narration-dev-package-v1`
(`worktrees/01-input/experiments/narration-quality/dev-package-v1/`). This lane
pins the manifest and `cases.jsonl` hashes and uses only its case IDs, `input`,
`requiredFacts`, `licensedEntities` and `priorTexts`. The model sees only
`input`. `reference`, `requiredFacts` and `notes` never enter the prompt, and
the analyzer never reads `reference`.

The package is public development regression material, never a final holdout.

## Files

| Path | Role |
|---|---|
| `preregistration.json` | frozen before any output; duplicate/qualification/benefit/stop rules |
| `preregistration.sha256` | hash of the exact preregistration bytes |
| `preregistration.v2.json` / `.sha256` | v2 template-test preregistration, frozen before any v2 output |
| `cause-analysis-b01.md` | b01 evidence, hypotheses and next step |
| `v2-analysis-plan.md` | how v2 will be interpreted, written before any v2 output |
| `analysis-addendum-arms.md` / `.sha256` | all-subset N-arm definition, frozen before any arm result |
| `configs/b01.json` | first batch: one long dialogue case, 6 seeds |
| `configs/b01-template-v2.json` | same batch with the fixed writing instruction only |
| `configs/b02-generalization.json` | same-condition coverage batch (blocked on b01 analysis) |
| `src/prepare.ts` | validates the shared pack, renders the exact prompt, writes requests |
| `src/verify_pack.py` | Python-side pack/hash verification before HPC |
| `src/generate_hpc.py` | dumb HPC runner: prompt in, raw text + timings + env out |
| `src/analyze.ts` | 01 checker + diversity + arm comparison + evidence report |
| `src/compare-b01-v2.ts` | side-by-side v1/v2 report; never pools the two prompts |
| `src/arms.ts` / `src/arms.test.ts` | all size-N subsets; C(6,1)=6, C(6,2)=15, C(6,4)=15 |
| `data/<batch>/` | generated request/expected files (committed) |
| `results/<batch>/` | raw outputs, env, report (committed) |

## Commands

```bash
# local preparation (no model)
cd frontend && node_modules/.bin/jiti ../experiments/narration-best-of-n/src/prepare.ts --batch b01

# pack verification (Python, no model)
python -X utf8 experiments/narration-best-of-n/src/verify_pack.py --batch b01

# HPC: executed only by lane 10, never by this lane
python -X utf8 generate_hpc.py --requests data/b01/requests.jsonl \
  --expected-prereg <sha256> --out-dir results/b01 --model ~/qwen15b

# offline analysis (01 checker + this lane's module)
cd frontend && node_modules/.bin/jiti ../experiments/narration-best-of-n/src/analyze.ts --batch b01
cd frontend && node_modules/.bin/jiti ../experiments/narration-best-of-n/src/analyze.ts --batch b01-template-v2

# side-by-side after v2 exists
cd frontend && node_modules/.bin/jiti ../experiments/narration-best-of-n/src/compare-b01-v2.ts   --left ../experiments/narration-best-of-n/results/b01/report.json   --right ../experiments/narration-best-of-n/results/b01-template-v2/report.json   --out ../experiments/narration-best-of-n/results/b01-vs-v2
```

No local 4060 run and no SSH from this lane. Batch runs go through
`results/product/hpc-requests/12-best-of-n-<id>.json` to lane 10; local heavy
inference only through lane 09 and only after the preregistered offline gate.

## Honesty rules

- Raw text is stored unedited except special-token removal; both token count and
  finish reason are kept.
- Fact qualification uses 01's frozen rubric and its `reviewNarration` as one
  mechanical checker; it is not a human review. `pending` is not a pass.
- Model-segment output and any program fallback are recorded separately; a
  fallback never counts as model prose.
- HPC measurements are not browser evidence. The browser 60 s first-readable /
  300 s full-turn accounting is a separate lane-09 run.
