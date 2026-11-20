#!/bin/bash
#SBATCH --job-name=shortpair295
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=03:00:00
#SBATCH --output=%x_%j.out
#
# One authorised MiniRBT-H256 pairwise run: 295 rows / 325 decisions / 4225 pairs.
# Submitted by lane 10; inputs and code are hashed in the run report.
set -x
source ~/miniconda3/etc/profile.d/conda.sh && conda activate crf
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
cd ~/beats_v1/short-pairs
python -c "import torch, transformers; print('torch', torch.__version__, 'transformers', transformers.__version__, 'cuda', torch.cuda.is_available())"
nproc
python -X utf8 run_pairwise295.py \
  --freeze inputs/04-pairwise-freeze.json \
  --freeze13 inputs/13-freeze.json \
  --rows300 inputs/train13-full-candidates.jsonl \
  --val inputs/val-01-rows.json \
  --labels inputs/labels-v1.json \
  --split inputs/01-goal-split-lists-v1.json \
  --base base \
  --out runs/295-frozen \
  --measurement inputs/04-pairwise-measurement-v2.json --arm frozen --device cuda --threads 4
echo RUN_DONE
