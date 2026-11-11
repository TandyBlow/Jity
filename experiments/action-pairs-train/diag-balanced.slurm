#!/bin/bash
#SBATCH --job-name=ap-bal
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --time=00:30:00
#SBATCH --mem=16G
#SBATCH --output=ap-bal_%j.out
#SBATCH --error=ap-bal_%j.err
cd "$SLURM_SUBMIT_DIR" || exit 1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
echo "start=$(date)"
~/miniconda3/envs/crf/bin/python -X utf8 code/diag_balanced.py \
  --base base --labels data/labels-v1.json --freeze freeze.json \
  --pairs data/pairs.jsonl --pairs-freeze data/pairs-freeze.json \
  --valid-rows data/valid-rows.json --out runs/diag-balanced.json --cap 8
echo "end=$(date) rc=$?"
