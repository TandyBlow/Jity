#!/bin/bash
# Slurm submission for the v2 result-block instruct arm.
#
# The default config is a template with status=pending.  Fill base/tokenizer
# identities and hashes, then set CONFIG to the completed file.  The trainer
# refuses a pending config; this is intentional.
#
#   CONFIG=configs/hf-instruct.json sbatch ~/narr_v2/run_instruct.sh

#SBATCH --job-name=narr_v2_instruct
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=03:00:00
#SBATCH --mem=48G
#SBATCH --output=narr_v2_instruct_%j.out
#SBATCH --error=narr_v2_instruct_%j.err

set -euo pipefail
cd "$HOME/narr_v2"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
PY="${PY:-$HOME/miniconda3/envs/crf/bin/python}"
CONFIG="${CONFIG:-configs/hf-instruct.json}"
OUT="${OUT:-runs/instruct-result-v2-r1}"

echo "node=$(hostname) start=$(date) config=$CONFIG out=$OUT"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
"$PY" -V
"$PY" -X utf8 train/preflight_v2.py --config "$CONFIG" || exit 1
"$PY" -X utf8 train/train_hf_instruct.py --config "$CONFIG" --out "$OUT" --resume auto
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
