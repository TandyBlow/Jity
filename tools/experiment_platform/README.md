# experiment_platform

Shared read-only tooling for experiment data governance. Stdlib only.

```bash
# 1. index every file under the standard data roots
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.data_index

# 2. run the validation checks over that index
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.validate_data

# 3. check declared splits (disjoint/subset) and independence status
PYTHONUTF8=1 python -X utf8 -m tools.experiment_platform.split_sets

# tests
PYTHONUTF8=1 python -X utf8 -m pytest tools/experiment_platform/tests -q
```

Outputs (tracked evidence):

- `artifacts/goal/platform/data-index.json` — path, family, role, bytes, sha256, git blob/last commit, dirty flag, JSON/JSONL/CSV structure hints.
- `artifacts/goal/platform/data-validation.json` — malformed files, empty datasets, JSONL key drift, duplicate content, tracked large files, stale report references, sha256 sidecars, canonical manifest hashes, evidence files that are missing or untracked.
- `artifacts/goal/platform/split-check.json` — per-set usage/independence and pairwise ID overlap. `independent: false` means regression only.

Options: `--root` (repeatable) limits the scan; `--max-parse-mb` / `--max-hash-mb` bound cost; `--no-last-commit` skips the one-pass git history walk (~20 s on this repo).

Rules of the tool:

- Read-only: it never edits or deletes source data.
- Runs are reproducible: the index records `headCommit` and per-file git blob, so a later diff shows what changed.
- Large files are size-only past the hash cap; raise the cap for a targeted audit.
