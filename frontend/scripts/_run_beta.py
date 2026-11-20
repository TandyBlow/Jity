import sys, os
sys.path.insert(0, r'D:/others/Jity/frontend/scripts')
from _hpc_crf import Hpc
WT = r'D:/others/Jity/.local/world-components-next-worktree'
REMOTE = 'n4fix'
h = Hpc(connect_attempts=3, backoff_seconds=60)
if sys.argv[1] == 'stage':
    h.do("mkdir -p ~/%s/artifacts/margin-r1 ~/%s/artifacts/next-runs/marginbeta-r1" % (REMOTE, REMOTE), show=False)
    h.put(os.path.join(WT, 'experiments/world-components/measure_margin_beta.py'),
          '%s/experiments/world-components/measure_margin_beta.py' % REMOTE)
    h.put(os.path.join(WT, 'artifacts/margin-r1/train.jsonl'), '%s/artifacts/margin-r1/train.jsonl' % REMOTE)
    script = """#!/bin/bash
#SBATCH --job-name=n4beta
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --time=00:20:00
#SBATCH --mem=16G
#SBATCH --output=n4beta_%j.out
cd $SLURM_SUBMIT_DIR
set -e
~/miniconda3/envs/crf/bin/python -X utf8 experiments/world-components/measure_margin_beta.py \
  --model ~/n4arm3/artifacts/next-runs/three-arm-c/ckpt \
  --rows artifacts/margin-r1/train.jsonl \
  --out artifacts/next-runs/marginbeta-r1/report.json
"""
    h.do("cat > ~/%s/beta.sh <<'SEOF'\n" % REMOTE + script + "SEOF", show=False)
    out, _, _ = h.do("cd ~/%s && sbatch beta.sh" % REMOTE, timeout=120, show=False)
    print(out.strip())
else:
    raise SystemExit('stage only')
