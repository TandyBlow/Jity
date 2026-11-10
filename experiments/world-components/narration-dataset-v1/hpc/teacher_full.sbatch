#!/bin/bash
#SBATCH --job-name=narr_teacher
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=03:00:00
#SBATCH --mem=32G
#SBATCH --output=teacher_full_%j.out
#SBATCH --error=teacher_full_%j.err
cd $SLURM_SUBMIT_DIR
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
echo "node=$(hostname) start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
~/miniconda3/envs/crf/bin/python -X utf8 teacher_rewrite.py --data rows-yuyan.jsonl --model ~/qwen7b --out teacher-test.jsonl --limit 0 --batch 6 --max-new 900
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
