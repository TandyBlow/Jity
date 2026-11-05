#!/usr/bin/env bash
# Three-arm continuation on the HPC. Prepared, NOT executed from this worktree.
#
#   arm A  pool targets unchanged (control)
#   arm B  fact repair only, trailing clauses kept
#   arm C  fact repair plus deletion of unlicensed trailing clauses
#
# All three use the same base checkpoint, steps, batch, learning rate, seed and
# pool mix, and the pools hold the same unit ids in the same order, so the step
# sampler draws the same units; only the target strings differ. The script checks
# that from the training reports instead of assuming it.
#
# Usage:  bash hpc_three_arm.sh [--dry-run]
#   --dry-run prints the commands and the preflight checks without training.
#
# Environment:
#   N4_MODEL_DIR   checkpoint to continue from (read-only), default $PWD/.local/models
#   N4_PYTHON      python with torch+transformers, default python
#   N4_RUN_ROOT    where run directories are created, default artifacts/next-runs
set -euo pipefail

cd "$(dirname "$0")/../.."          # worktree root
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

PY="${N4_PYTHON:-python}"
MODEL="${N4_MODEL_DIR:-$PWD/.local/models}"
RUN="${N4_RUN_ROOT:-artifacts/next-runs}"
FREEZE=artifacts/three-arm-r1/three-arm-freeze.json
STEPS=240; BATCH=8; MIX=4,3,1; SEED=20261102; LR=3e-4

[[ -f "$FREEZE" ]] || { echo "missing $FREEZE"; exit 1; }
[[ -f "$MODEL/model.safetensors" ]] || { echo "missing weights under $MODEL"; exit 1; }

echo "== preflight =="
"$PY" - "$FREEZE" "$MODEL" <<'PY'
import hashlib, json, pathlib, sys
freeze = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
model = pathlib.Path(sys.argv[2]) / 'model.safetensors'
expected = freeze['base']['modelSha256']
actual = hashlib.sha256(model.read_bytes()).hexdigest()
assert actual == expected, f'base weights drifted: {actual} != {expected}'
print('base weights', actual[:16], 'ok')
for arm in 'abc':
    for name, item in freeze['files'][arm].items():
        path = pathlib.Path(item['path'])
        data = path.read_bytes()
        got = hashlib.sha256(data).hexdigest()
        assert got == item['sha256'], f'{arm}/{name} drifted: {got}'
        rows = sum(1 for line in data.decode('utf-8').splitlines() if line.strip())
        assert rows == item['rows'], f'{arm}/{name} row count {rows} != {item["rows"]}'
    print('arm', arm, 'pools ok', freeze['rows'][arm], 'rows, changed', freeze['changedRows'][arm])
ids = freeze['idOrder']
assert ids['identicalAcrossArms'], 'freeze says the id order differs'
print('shared id order', ids['count'], ids['sha256'][:16])
PY

run_arm() {
  local arm="$1" label="$2"
  local dir="$RUN/three-arm-$arm"
  local cmd=("$PY" -X utf8 -B experiments/world-components/train_revision_arm.py
    --base "$MODEL"
    --pool "artifacts/three-arm-r1/arm-$arm-verbalizer.jsonl"
    --pool "artifacts/three-arm-r1/arm-$arm-expand78.jsonl"
    --pool "artifacts/three-arm-r1/arm-$arm-object34.jsonl"
    --steps "$STEPS" --batch "$BATCH" --mix "$MIX" --lr "$LR" --seed "$SEED"
    --run-dir "$dir" --arm "$label")
  echo "+ ${cmd[*]}"
  [[ $DRY -eq 1 ]] && return 0
  "${cmd[@]}"
}

echo "== training =="
run_arm a control-original-targets
run_arm b conservative-fact-repair
run_arm c full-audit-targets

if [[ $DRY -eq 0 ]]; then
  echo "== sampling identity =="
  "$PY" - "$RUN" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
reports = {}
for arm in 'abc':
    path = root / f'three-arm-{arm}' / 'train-report.json'
    reports[arm] = json.loads(path.read_text(encoding='utf-8'))['sampling']
ids = {arm: reports[arm]['idSha256'] for arm in 'abc'}
targets = {arm: reports[arm]['targetSha256'] for arm in 'abc'}
assert len(set(ids.values())) == 1, f'unit draws differ across arms: {ids}'
assert len(set(targets.values())) == 3, f'targets are not three distinct sequences: {targets}'
print('ids identical', list(ids.values())[0][:16], '| targets distinct')
PY
fi

echo "== next =="
cat <<'TXT'
Training only. Evaluation is a separate run on the same device for all three arms:
  run_cf24_baseline.py --units world-components/n4-cf24-contract.jsonl
  run_cf24_baseline.py --units world-components/n4-final24-contract.jsonl
  run_cf24_baseline.py --units world-components/n4-moved24-contract.jsonl
then check_cf24_overlap / score_cf24_baseline / review_cf24_baseline per arm, and
report moved24 on its own (never merged with final24).
TXT
