#!/bin/bash
# Same run on a node with a GPU but no scheduler.
#
#   BASE=~/n4v2_run/base/randeng-t5-77m PY=python3 bash run-direct.sh
#
set -euo pipefail

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${OUT:-$PKG/runs/$(date +%Y%m%d-%H%M%S)}"
BASE="${BASE:-$HOME/n4v2_run/base/randeng-t5-77m}"
PY="${PY:-python3}"
EPOCHS="${EPOCHS:-8}"
LR="${LR:-3e-4}"

mkdir -p "$OUT"
"$PY" "$PKG/preflight.py" --data "$PKG/rows-xy.jsonl" --base "$BASE"
"$PY" "$PKG/train_narration_rows.py" \
  --data "$PKG/rows-xy.jsonl" --base "$BASE" --out "$OUT" \
  --epochs "$EPOCHS" --lr "$LR" --holdout row-0010,row-0017 --save-ckpt
echo "done: $OUT/report.json"
