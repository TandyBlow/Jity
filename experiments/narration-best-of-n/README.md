# Lane 12 — realization diversity and best-of-N (experiments)

Owned by `12-best-of-n`. This directory holds the preregistration, the six-seed
sampler, the HPC generation entry, the offline analysis and the raw outputs. It
does not touch the product page, runtime, existing generation/checker modules or
another lane's worktree.

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
| `configs/b01.json` | first batch: one long dialogue case, 6 seeds |
| `configs/b02-generalization.json` | same-condition coverage batch (blocked on b01 analysis) |
| `src/prepare.ts` | validates the shared pack, renders the exact prompt, writes requests |
| `src/verify_pack.py` | Python-side pack/hash verification before HPC |
| `src/generate_hpc.py` | dumb HPC runner: prompt in, raw text + timings + env out |
| `src/analyze.ts` | 01 checker + diversity + arm comparison + evidence report |
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
