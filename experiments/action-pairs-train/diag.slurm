#!/bin/bash
#SBATCH --job-name=ap-diag
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --time=00:30:00
#SBATCH --mem=16G
#SBATCH --output=ap-diag_%j.out
#SBATCH --error=ap-diag_%j.err
cd "$SLURM_SUBMIT_DIR" || exit 1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
echo "start=$(date) host=$(hostname)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
~/miniconda3/envs/crf/bin/python -X utf8 code/diag_features.py \
  --base base --labels data/labels-v1.json --pairs data/pairs.jsonl \
  --pairs-freeze data/pairs-freeze.json --valid-rows data/valid-rows.json \
  --out runs/diag-features.json --device cuda
echo "end=$(date) rc=$?"
