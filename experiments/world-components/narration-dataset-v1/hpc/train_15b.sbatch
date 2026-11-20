#!/bin/bash
#SBATCH --job-name=narr_lora15
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=01:30:00
#SBATCH --mem=48G
#SBATCH --output=narr_lora15_%j.out
#SBATCH --error=narr_lora15_%j.err
cd $SLURM_SUBMIT_DIR
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
echo "node=$(hostname) start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
BASE=${BASE:-$HOME/qwen15b}
~/miniconda3/envs/crf/bin/python -X utf8 train_instruct_lora.py --data rows-v2.jsonl --model "$BASE" --out run-lora15 --epochs ${EPOCHS:-10} --holdout ${HOLDOUT:-row-0010-hand,row-0017-teacher,row-0031-hand,row-0065-teacher,row-0102-hand,row-0148-teacher,row-0155-hand,row-0188-teacher} --lr ${LR:-1e-4} --batch ${BATCH:-4} --max-len 1152
rc=$?
echo "end=$(date) rc=$rc"
exit $rc
