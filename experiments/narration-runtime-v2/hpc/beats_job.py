# -*- coding: utf-8 -*-
"""Submit beat teacher passes and Qwen training runs on the HPC GPU.

    python hpc/beats_job.py deploy
    python hpc/beats_job.py submit --beats data/beats-v1.jsonl --out out.jsonl \
        --limit 0 --batch 6 --samples 2
    python hpc/beats_job.py submit-train --config qwen05b-scene-v1.json --run qwen05b-scene-v1
    python hpc/beats_job.py poll <jobId>
    python hpc/beats_job.py fetch <jobId> --out out.jsonl
    python hpc/beats_job.py fetch-train <jobId> --run qwen05b-scene-v1

Credentials come from the existing HPC file used by the v1/v2 clients; nothing
secret is printed. Remote root: `~/beats_v1`.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
from typing import Any, Dict

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(V2, "..", ".."))
SOURCE_HPC = os.path.join(REPO, "experiments", "world-components",
                          "narration-dataset-v1", "hpc")
REMOTE = "beats_v1"
RUNS = os.path.join(HERE, "runs")

SBATCH = """#!/bin/bash
#SBATCH --job-name=narr_beats
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=02:00:00
#SBATCH --mem=48G
#SBATCH --output=teacher_%j.out
#SBATCH --error=teacher_%j.err

set -euo pipefail
cd "$HOME/beats_v1"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
PY="${PY:-$HOME/miniconda3/envs/crf/bin/python}"
echo "node=$(hostname) start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
"$PY" -X utf8 teacher_beats.py --beats "$BEATS" --out "$OUT" \
  --model "${MODEL:-$HOME/qwen7b}" --batch "${BATCH:-6}" --samples "${SAMPLES:-2}" \
  --limit "${LIMIT:-0}" --max-new "${MAXNEW:-96}" --temperature "${TEMP:-0.85}"
"""

TRAIN_SBATCH = """#!/bin/bash
#SBATCH --job-name=narr_train
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=02:00:00
#SBATCH --mem=48G
#SBATCH --output=train_%j.out
#SBATCH --error=train_%j.err

set -euo pipefail
cd "$HOME/beats_v1"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export NARR_ROOT="$HOME/beats_v1"
PY="${PY:-$HOME/miniconda3/envs/crf/bin/python}"
echo "node=$(hostname) start=$(date) config=$CONFIG out=$OUT"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
"$PY" -X utf8 train/train_beats.py --config "configs/$CONFIG" --out "runs/$OUT" \
  --resume "${RESUME:-}" --epochs "${EPOCHS:-0}" --sample-n "${SAMPLE_N:-3}"
"""


def load_base():
    sys.path.insert(0, SOURCE_HPC)
    import _hpc_narr as base
    return base


def hpc():
    return load_base().Hpc()


def write_remote(h, text: str, name: str) -> None:
    local = os.path.join(HERE, "_" + name)
    with io.open(local, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    h.put(local, f"{REMOTE}/{name}")
    os.remove(local)


def deploy(h) -> None:
    h.do(f"mkdir -p ~/{REMOTE}/data ~/{REMOTE}/configs ~/{REMOTE}/train ~/{REMOTE}/runs",
         show=False)
    files = {
        os.path.join(HERE, "teacher_beats.py"): f"{REMOTE}/teacher_beats.py",
        os.path.join(V2, "train", "train_beats.py"): f"{REMOTE}/train/train_beats.py",
        os.path.join(V2, "data", "scene-v1.jsonl"): f"{REMOTE}/data/scene-v1.jsonl",
        os.path.join(REPO, "experiments", "world-components", "narration-dataset-v1",
                     "splits", "v1.json"): f"{REMOTE}/data/splits-v1.json",
        os.path.join(V2, "configs", "qwen05b-scene-v1.json"):
            f"{REMOTE}/configs/qwen05b-scene-v1.json",
        os.path.join(V2, "configs", "qwen15b-scene-v1.json"):
            f"{REMOTE}/configs/qwen15b-scene-v1.json",
        os.path.join(V2, "configs", "qwen05b-mix-v1.json"):
            f"{REMOTE}/configs/qwen05b-mix-v1.json",
        os.path.join(V2, "data", "train-v2.jsonl"): f"{REMOTE}/data/train-v2.jsonl",
    }
    for local, remote in files.items():
        h.put(local, remote)
    write_remote(h, SBATCH, "run_teacher.sh")
    write_remote(h, TRAIN_SBATCH, "run_train.sh")
    h.do(f"chmod +x ~/{REMOTE}/run_teacher.sh ~/{REMOTE}/run_train.sh", show=False)


def submit(h, args) -> str:
    local = os.path.abspath(args.beats)
    if not os.path.exists(local):
        raise SystemExit(f"missing {local}")
    h.put(local, f"{REMOTE}/{os.path.basename(local)}")
    env = (f"BEATS={os.path.basename(local)} OUT={args.out} LIMIT={args.limit} "
           f"BATCH={args.batch} SAMPLES={args.samples} MAXNEW={args.max_new} "
           f"TEMP={args.temperature}")
    out, err, rc = h.do(f"cd ~/{REMOTE} && {env} sbatch run_teacher.sh", show=True)
    match = re.search(r"(\d+)", out)
    if not match:
        raise SystemExit(f"sbatch did not return a job id: {out} {err}")
    print("job", match.group(1))
    return match.group(1)


def submit_train(h, args) -> str:
    env = (f"CONFIG={args.config} OUT={args.run} RESUME={args.resume} "
           f"EPOCHS={args.epochs} SAMPLE_N={args.sample_n}")
    out, err, rc = h.do(f"cd ~/{REMOTE} && {env} sbatch run_train.sh", show=True)
    match = re.search(r"(\d+)", out)
    if not match:
        raise SystemExit(f"sbatch did not return a job id: {out} {err}")
    print("job", match.group(1))
    return match.group(1)


def poll(h, job: str) -> Dict[str, Any]:
    out, _, _ = h.do(f"squeue -j {job} -h -o '%T %M'", show=False)
    state = out.strip()
    print("queue:", state or "not queued")
    h.do(f"tail -8 ~/{REMOTE}/teacher_{job}.out 2>/dev/null || "
         f"tail -8 ~/{REMOTE}/train_{job}.out 2>/dev/null || true", show=True)
    return {"job": job, "queue": state}


def fetch_dir(h, job: str, pairs) -> None:
    local_dir = os.path.join(RUNS, job)
    os.makedirs(local_dir, exist_ok=True)
    sftp = h._sftp()
    try:
        for name, target in pairs:
            try:
                sftp.get(f"/home/student/{h.user}/{REMOTE}/{name}",
                         os.path.join(local_dir, target))
                print("fetched", target)
            except Exception as error:  # noqa: BLE001
                print("skip", name, error)
    finally:
        sftp.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("deploy", "submit", "poll", "fetch",
                                           "submit-train", "fetch-train"))
    parser.add_argument("job", nargs="?", default="")
    parser.add_argument("--beats", default="data/beats-v1.jsonl")
    parser.add_argument("--out", default="out.jsonl")
    parser.add_argument("--limit", default="0")
    parser.add_argument("--batch", default="6")
    parser.add_argument("--samples", default="2")
    parser.add_argument("--max-new", default="96")
    parser.add_argument("--temperature", default="0.85")
    parser.add_argument("--config", default="qwen05b-scene-v1.json")
    parser.add_argument("--run", default="qwen05b-scene-v1")
    parser.add_argument("--resume", default="")
    parser.add_argument("--epochs", default="0")
    parser.add_argument("--sample-n", default="3")
    args = parser.parse_args()
    h = hpc()
    try:
        if args.action == "deploy":
            deploy(h)
        elif args.action == "submit":
            deploy(h)
            submit(h, args)
        elif args.action == "submit-train":
            deploy(h)
            submit_train(h, args)
        elif args.action == "poll":
            poll(h, args.job)
        elif args.action == "fetch":
            if not args.job:
                raise SystemExit("fetch needs a job id")
            fetch_dir(h, args.job, ((args.out, "output.jsonl"),
                                    (f"teacher_{args.job}.out", "job.out"),
                                    (f"teacher_{args.job}.err", "job.err")))
        elif args.action == "fetch-train":
            if not args.job:
                raise SystemExit("fetch-train needs a job id")
            fetch_dir(h, args.job, (
                (f"runs/{args.run}/report.json", "report.json"),
                (f"runs/{args.run}/adapter-best.pt", "adapter-best.pt"),
                (f"train_{args.job}.out", "job.out"),
                (f"train_{args.job}.err", "job.err")))
        return 0
    finally:
        h.c.close()


if __name__ == "__main__":
    raise SystemExit(main())
