#!/bin/bash
#SBATCH --job-name=fitdiag784
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --time=00:30:00
#SBATCH --mem=32G
#SBATCH --output=fitdiag_%j.out
#SBATCH --error=fitdiag_%j.err

cd $SLURM_SUBMIT_DIR
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
echo "start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1
$HOME/miniconda3/envs/crf/bin/python -X utf8 diagnose_fit_784.py \
  --ckpt out/ckpt-final \
  --material sentence-scale-v1.jsonl \
  --previous out/results.json \
  --out out/fit-diagnostic.json
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
