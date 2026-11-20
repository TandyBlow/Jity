#!/bin/bash
# Slurm submission for the v2 result-block YuYan LoRA arm.
#
# Remote layout assumed by the config:
#   ~/narr_v2/data/rows-yuyan-v2.jsonl
#   ~/narr_v2/data/manifest.json
#   ~/narr_v2/splits/v1.json
#   ~/narr_v2/source/train_yuyan.py       (frozen v1 model/LoRA code)
#   ~/narr_rows/checkpoint_best.pt        (read-only base)
#   ~/narr_rows/dict.txt                  (read-only tokenizer)
#
#   sbatch ~/narr_v2/run_yuyan.sh

#SBATCH --job-name=narr_v2_yuyan
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=02:00:00
#SBATCH --mem=32G
#SBATCH --output=narr_v2_yuyan_%j.out
#SBATCH --error=narr_v2_yuyan_%j.err

set -euo pipefail
cd "$HOME/narr_v2"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export NARR_SOURCE_TRAIN="$PWD/source/train_yuyan.py"
PY="${PY:-$HOME/miniconda3/envs/crf/bin/python}"
CONFIG="${CONFIG:-configs/yuyan-lora-v2.json}"
OUT="${OUT:-runs/yuyan-result-v2-r1}"

echo "node=$(hostname) start=$(date) config=$CONFIG out=$OUT"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
"$PY" -V
"$PY" -X utf8 train/preflight_v2.py --config "$CONFIG" --hash-base || exit 1
"$PY" -X utf8 train/train_yuyan_v2.py --config "$CONFIG" --out "$OUT" --resume auto
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
