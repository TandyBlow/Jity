#!/bin/bash
#SBATCH --job-name=gword1
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=00:30:00
#SBATCH --mem=32G
#SBATCH --output=gword1_%j.out
#SBATCH --error=gword1_%j.err

cd $SLURM_SUBMIT_DIR
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONHASHSEED=0
echo "start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1
$HOME/miniconda3/envs/crf/bin/python -X utf8 run_group_wording_v1.py \
  --base "$HOME/sentence784_run/out/ckpt-final" \
  --freeze freeze-v1.json \
  --freeze-sha 0d8db13f0ca079174504d02fece57514b32672ee53bba3d0e3a9959a9e66f0ed \
  --out run-v1
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
