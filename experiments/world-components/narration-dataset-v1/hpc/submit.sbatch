#!/bin/bash
# Slurm submission for the narration-row training run.
#
# Edit the three lines marked CHANGE if the cluster's names differ. The job
# writes everything into $OUT: report.json plus (optional) ckpt/.
#
#   sbatch submit.sbatch
#
# If the cluster has no slurm and you get a GPU node directly, use run-direct.sh.

#SBATCH --job-name=narr-train
#SBATCH --partition=gpu             # CHANGE if needed
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=narr-train-%j.log

set -euo pipefail

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${OUT:-$PKG/runs/$(date +%Y%m%d-%H%M%S)}"
BASE="${BASE:-$HOME/n4v2_run/base/randeng-t5-77m}"   # CHANGE if the base lives elsewhere
PY="${PY:-python}"
EPOCHS="${EPOCHS:-8}"
LR="${LR:-3e-4}"

mkdir -p "$OUT"

echo "package : $PKG"
echo "output  : $OUT"
echo "base    : $BASE"
echo "python  : $($PY -V 2>&1)"
echo "data sha: $(sha256sum "$PKG/rows-xy.jsonl" | cut -d' ' -f1)"

# The compute nodes have no internet: if a dependency is missing, install it on
# the login node once (this is what the previous rounds recorded).
$PY - <<'EOF' || echo "WARN: dependency check failed; see the error above"
import sentencepiece, torch, transformers  # noqa: F401
EOF

$PY "$PKG/preflight.py" --data "$PKG/rows-xy.jsonl" --base "$BASE"

$PY "$PKG/train_narration_rows.py" \
  --data "$PKG/rows-xy.jsonl" \
  --base "$BASE" \
  --out "$OUT" \
  --epochs "$EPOCHS" \
  --lr "$LR" \
  --holdout row-0010,row-0017 \
  --save-ckpt

echo "done: $OUT/report.json"
