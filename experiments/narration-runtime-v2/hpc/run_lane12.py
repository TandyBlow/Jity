# -*- coding: utf-8 -*-
"""Run lane 12's preregistered b01 batch on the cluster, from lane 10.

Lane 10 is the only HPC submit/cancel owner, so this driver uploads the exact
committed files lane 12 asked for, verifies their hashes before and after the
upload, then submits one sbatch job and records the queue facts.

It does not edit lane 12's files, prompts, seeds or sampling.

    python hpc/run_lane12.py --lane12 <worktree> --pack <01 dev package> \
        --commit 87de2f09 --gres gpu:4090:1
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

FILES = ["README.md", "preregistration.json", "preregistration.sha256",
         "configs/b01.json", "data/b01/requests.jsonl", "data/b01/expected.jsonl",
         "data/b01/plan.json", "src/prepare.ts", "src/generate_hpc.py", "src/verify_pack.py"]
PACK_FILES = ["manifest.json", "cases.jsonl", "RUBRIC.md", "README.md"]

SBATCH = """#!/bin/bash
#SBATCH --job-name=lane12_b01
#SBATCH --partition={partition}
#SBATCH --gres={gres}
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=00:30:00
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err
set -e
source ~/miniconda3/etc/profile.d/conda.sh && conda activate crf
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
cd ~/{root}/narration-best-of-n
export NARRATION_DEV_PACK_ROOT=../shared-dev-package-v1
echo "== verify $(date '+%Y-%m-%dT%H:%M:%S%z')"
python -X utf8 src/verify_pack.py --batch b01
echo "== generate $(date '+%Y-%m-%dT%H:%M:%S%z')"
python -X utf8 src/generate_hpc.py --requests data/b01/requests.jsonl \
  --config configs/b01.json --preregistration preregistration.json \
  --expected-prereg-sha256 {prereg} --out-dir results/b01 --model ~/qwen15b \
  --dtype {dtype}
echo "== done $(date '+%Y-%m-%dT%H:%M:%S%z')"
"""


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane12", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--gres", default="gpu:4090:1")
    parser.add_argument("--partition", default="gpu")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--prereg", default="b1079ca6ac39b68c220b2e23004131d84a90e6abc5a119518b5a7b93c56242b3")
    args = parser.parse_args()

    expected = {
        "preregistration.json": args.prereg,
        "configs/b01.json": "6e23223f6b5c6489c777bb517fc1e935eeac8ab14dea94c0116dbc3994736a63",
        "data/b01/requests.jsonl": "77251fb07437e02abf2a084057782b363807d4228f52aada293a583625ff6c7d",
        "data/b01/expected.jsonl": "b0c018a3a00a4e81fa32d3154b658af8d33a5e7e66b585535841c9429ecfa060",
    }
    for name, want in expected.items():
        got = sha256(os.path.join(args.lane12, "experiments", "narration-best-of-n", name))
        if got != want:
            raise SystemExit(f"{name}: local hash {got} != requested {want}")
    pack_expected = {"manifest.json": "20da8db9051740a48901bf143fdff5fde01aac2accc691409e74c9acba386dc7",
                     "cases.jsonl": "8dd2de925c7de03b0f4df43196cb684cd8022bbf198039be74c4470e63b9207b",
                     "RUBRIC.md": "020c9ca9e19ae474256404e70c985b67b8d56598ba07b65d7ed089d169b58107"}
    for name, want in pack_expected.items():
        got = sha256(os.path.join(args.pack, name))
        if got != want:
            raise SystemExit(f"pack {name}: {got} != requested {want}")

    import beats_job as B
    h = B.hpc()
    root = f"beats_v1/best-of-n/{args.commit[:8]}"
    try:
        start_queue, _, _ = h.do("squeue -u $USER -h -o '%i|%j|%T|%P|%R'", show=False)
        h.do(f"mkdir -p ~/{root}/narration-best-of-n/configs ~/{root}/narration-best-of-n/data/b01 "
             f"~/{root}/narration-best-of-n/src ~/{root}/shared-dev-package-v1", show=False)
        for name in FILES:
            h.put(os.path.join(args.lane12, "experiments", "narration-best-of-n", name),
                  f"{root}/narration-best-of-n/{name}")
        for name in PACK_FILES:
            h.put(os.path.join(args.pack, name), f"{root}/shared-dev-package-v1/{name}")
        remote_hashes, _, _ = h.do(
            f"cd ~/{root} && sha256sum narration-best-of-n/preregistration.json "
            f"narration-best-of-n/configs/b01.json narration-best-of-n/data/b01/requests.jsonl "
            f"shared-dev-package-v1/manifest.json shared-dev-package-v1/cases.jsonl "
            f"shared-dev-package-v1/RUBRIC.md", show=False)
        for line in remote_hashes.strip().splitlines():
            digest, name = line.split()
            base = os.path.basename(name)
            want = expected.get(os.path.relpath(name, "narration-best-of-n")) if name.startswith(
                "narration-best-of-n/") else pack_expected[base]
            if want and digest != want:
                raise SystemExit(f"remote {name}: {digest} != {want}")

        script = SBATCH.format(partition=args.partition, gres=args.gres, root=root,
                               prereg=args.prereg, dtype=args.dtype)
        local_script = os.path.join(V2, ".lane12-b01.sbatch")
        with io.open(local_script, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(script)
        h.put(local_script, f"{root}/run_b01.sbatch")
        os.remove(local_script)
        out, _, _ = h.do(f"cd ~/{root} && sbatch run_b01.sbatch", show=True)
        match = re.search(r"(\d+)", out)
        if not match:
            raise SystemExit(f"no job id: {out}")
        job = match.group(1)
        time.sleep(3)
        after, _, _ = h.do("squeue -u $USER -h -o '%i|%j|%T|%M|%P|%N|%R'", show=False)
        record = {"jobId": job, "root": root, "gres": args.gres, "dtype": args.dtype,
                  "queueBefore": start_queue.strip().splitlines(),
                  "queueAfter": after.strip().splitlines(),
                  "submittedAtLocal": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        path = os.path.join(V2, "hpc", "runs", f"lane12-{job}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, indent=1) + "\n")
        print(json.dumps(record, ensure_ascii=False, indent=1))
        return 0
    finally:
        h.c.close()


if __name__ == "__main__":
    raise SystemExit(main())
