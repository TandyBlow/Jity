# experiment_platform

Shared read-only tooling for experiment data governance. Stdlib only.

```bash
# 1. index every file under the standard data roots
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.data_index

# 2. run the validation checks over that index
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.validate_data

# 3. check declared splits (disjoint/subset) and independence status
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.split_sets

# 4. validate / freeze an independent evaluation set
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.eval_set validate --path path/to/set.jsonl
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.eval_set freeze --path path/to/set.jsonl
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.eval_set check --path path/to/set.jsonl --manifest path/to/set.jsonl.manifest.json

# 5. build / score the independent sets
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.build_narration_holdout
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.narration_metrics --set artifacts/goal/platform/eval/narration-holdout-v1.jsonl --group-model
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.build_semantic_probes
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.head_predict --set artifacts/goal/platform/eval/semantic-probes-v1.test.jsonl --out artifacts/goal/platform/eval/semantic-probes-v1.test.pred.jsonl
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.semantic_score --set artifacts/goal/platform/eval/semantic-probes-v1.test.jsonl --predictions artifacts/goal/platform/eval/semantic-probes-v1.test.pred.jsonl --status-only

# 6. run, measure, verify
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.run_experiment --name smoke --command "python -c \"print(1)\""
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.resource_monitor --pid 1234 --duration 60
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.verify_run --evidence results/product/evidence/x.json --require-engine narration,semantic
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.perf_report

# 7. blind comparison for human review
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.anonymize --input outputs.jsonl --blind blind.jsonl --key key.json --sheet review.md

# 8. task-achievement gold (P05)
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.build_task_gold
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.task_gold_eval --cases artifacts/goal/platform/task-gold/task-gold-v1.cases.jsonl --predictions preds.jsonl

# tests
PYTHONUTF8=1 python -X utf8 -m pytest tools/experiment_platform/tests -q
```

Outputs (tracked evidence):

- `artifacts/goal/platform/data-index.json` — path, family, role, bytes, sha256, git blob/last commit, dirty flag, JSON/JSONL/CSV structure hints.
- `artifacts/goal/platform/data-validation.json` — malformed files, empty datasets, JSONL key drift, duplicate content, tracked large files, stale report references, sha256 sidecars, canonical manifest hashes, evidence files that are missing or untracked.
- `artifacts/goal/platform/split-check.json` — per-set usage/independence and pairwise ID overlap. `independent: false` means regression only.
- `eval_set.py` prints validation JSON; `freeze` writes a manifest with a canonical-JSON sha256, `check` verifies it. Record contract is in the module docstring.

Options: `--root` (repeatable) limits the scan; `--max-parse-mb` / `--max-hash-mb` bound cost; `--no-last-commit` skips the one-pass git history walk (~20 s on this repo).

Rules of the tool:

- Read-only: it never edits or deletes source data.
- Runs are reproducible: the index records `headCommit` and per-file git blob, so a later diff shows what changed.
- Large files are size-only past the hash cap; raise the cap for a targeted audit.
