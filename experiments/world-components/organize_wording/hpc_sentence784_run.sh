#!/bin/bash
#SBATCH --job-name=sentence784
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=01:30:00
#SBATCH --mem=32G
#SBATCH --output=sentence784_%j.out
#SBATCH --error=sentence784_%j.err

cd $SLURM_SUBMIT_DIR
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
echo "start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1
$HOME/miniconda3/envs/crf/bin/python -X utf8 train_sentence_scale_784.py \
  --base base/randeng-t5-784m \
  --material sentence-scale-v1.jsonl \
  --replay sampled_calls-B-large.jsonl \
  --freeze sentence-base-784m-freeze-v1.json \
  --out out
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
