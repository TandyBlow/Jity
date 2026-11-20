#!/bin/bash
#SBATCH --job-name=ap-fro2
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=02:00:00
#SBATCH --mem=32G
#SBATCH --output=ap-fro2_%j.out
#SBATCH --error=ap-fro2_%j.err

cd "$SLURM_SUBMIT_DIR" || exit 1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=8
echo "start=$(date) host=$(hostname)"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || echo "nvidia-smi unavailable"
~/miniconda3/envs/crf/bin/python -X utf8 code/pairwise_train.py \
  --freeze freeze.json \
  --rows data/rows300.jsonl \
  --labels data/labels-v1.json \
  --split data/split-lists.json \
  --base base \
  --out runs/pairs-x2-frozen2 \
  --pairs data/pairs.jsonl \
  --pairs-freeze data/pairs-freeze.json \
  --valid-rows data/valid-rows.json \
  --device cuda \
  --arm frozen
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
