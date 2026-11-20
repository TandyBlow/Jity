#!/bin/bash
#SBATCH --job-name=ap-evaltr
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --time=00:20:00
#SBATCH --mem=16G
#SBATCH --output=ap-evaltr_%j.out
#SBATCH --error=ap-evaltr_%j.err
cd "$SLURM_SUBMIT_DIR" || exit 1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
echo "start=$(date)"
~/miniconda3/envs/crf/bin/python -X utf8 code/eval_train.py \
  --base base --labels data/labels-v1.json \
  --checkpoint runs/pairs-x2-unfrozen2/pairwise-unfrozen.pt --freeze freeze.json \
  --pairs data/pairs.jsonl --pairs-freeze data/pairs-freeze.json \
  --out runs/train-eval-unfrozen2.json
echo "end=$(date) rc=$?"
