#!/bin/bash
#SBATCH --job-name=gword2
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=00:30:00
#SBATCH --mem=32G
#SBATCH --output=gword2_%j.out
#SBATCH --error=gword2_%j.err

cd $SLURM_SUBMIT_DIR
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONHASHSEED=0
echo "start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1
$HOME/miniconda3/envs/crf/bin/python -X utf8 run_group_wording_v1.py \
  --base "$HOME/sentence784_run/out/ckpt-final" \
  --freeze freeze-b2-v1.json \
  --freeze-sha 34d7be711105a660aa2d4eab29e233f6efd143fe256dd2a6e64f13f74de50f02 \
  --out run-b2-v1
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
