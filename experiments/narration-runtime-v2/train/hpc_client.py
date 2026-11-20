# -*- coding: utf-8 -*-
"""Deploy, submit, poll and fetch the v2 narration training arm.

Credentials stay in the existing local file (`D:/others/yuginu/run_hpc_now.py`)
and are read at runtime; this script prints neither the password nor the host
credentials.  The remote directory is `~/narr_v2`, separate from the legacy
`~/narr_rows` used by the v1 arm.

  python train/hpc_client.py deploy
  python train/hpc_client.py submit
  python train/hpc_client.py poll <jobId>
  python train/hpc_client.py fetch <jobId>
  python train/hpc_client.py go
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import sys
import time
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(V2, "..", ".."))
SOURCE_HPC = os.path.join(REPO, "experiments", "world-components", "narration-dataset-v1", "hpc")
SOURCE_TRAIN = os.path.join(REPO, "experiments", "world-components", "narration-dataset-v1",
                            "yuyan", "train_yuyan.py")
REMOTE = "narr_v2"
RUN_DIR = "runs/yuyan-result-v2-r1"
LAST_JOB = os.path.join(V2, "hpc", "last_job.txt")
RUNS = os.path.join(V2, "hpc", "runs")


def load_base():
    sys.path.insert(0, SOURCE_HPC)
    import _hpc_narr as base
    return base


def upload_files(h) -> None:
    h.do(f"mkdir -p ~/{REMOTE}/data ~/{REMOTE}/splits ~/{REMOTE}/configs "
         f"~/{REMOTE}/train ~/{REMOTE}/src ~/{REMOTE}/source ~/{REMOTE}/runs", show=False)
    files = {
        os.path.join(V2, "data", "rows-yuyan-v2.jsonl"): f"{REMOTE}/data/rows-yuyan-v2.jsonl",
        os.path.join(V2, "data", "rows-v2.jsonl"): f"{REMOTE}/data/rows-v2.jsonl",
        os.path.join(V2, "data", "manifest.json"): f"{REMOTE}/data/manifest.json",
        os.path.join(REPO, "experiments", "world-components", "narration-dataset-v1",
                     "splits", "v1.json"): f"{REMOTE}/splits/v1.json",
        os.path.join(V2, "configs", "yuyan-lora-v2.json"): f"{REMOTE}/configs/yuyan-lora-v2.json",
        os.path.join(V2, "configs", "hf-instruct.template.json"):
            f"{REMOTE}/configs/hf-instruct.template.json",
        os.path.join(V2, "train", "train_yuyan_v2.py"): f"{REMOTE}/train/train_yuyan_v2.py",
        os.path.join(V2, "train", "train_hf_instruct.py"): f"{REMOTE}/train/train_hf_instruct.py",
        os.path.join(V2, "train", "preflight_v2.py"): f"{REMOTE}/train/preflight_v2.py",
        os.path.join(V2, "train", "submit_yuyan.sbatch"): f"{REMOTE}/run_yuyan.sh",
        os.path.join(V2, "train", "submit_instruct.sbatch"): f"{REMOTE}/run_instruct.sh",
        SOURCE_TRAIN: f"{REMOTE}/source/train_yuyan.py",
    }
    for name in ("v2_render.py", "projection_v2.py", "legacy_compat.py",
                 "tokenizer_profile.py"):
        files[os.path.join(V2, "src", name)] = f"{REMOTE}/src/{name}"
    for local, remote in files.items():
        if not os.path.exists(local):
            raise SystemExit(f"missing local file: {local}")
        h.put(local, remote)
    h.do(f"chmod +x ~/{REMOTE}/run_yuyan.sh ~/{REMOTE}/run_instruct.sh", show=False)


def submit(h) -> str:
    out, err, rc = h.do(f"cd ~/{REMOTE} && sbatch run_yuyan.sh", show=True)
    match = re.search(r"(\d+)", out)
    if not match:
        raise SystemExit(f"sbatch did not return a job id: {out} {err}")
    job = match.group(1)
    os.makedirs(os.path.dirname(LAST_JOB), exist_ok=True)
    with io.open(LAST_JOB, "w", encoding="utf-8") as handle:
        handle.write(job + "\n")
    print(f"job {job}")
    return job


def poll(h, job: str) -> Dict[str, Any]:
    out, _, _ = h.do(f"squeue -j {job} -h -o '%T %M'", show=False)
    state = out.strip()
    print(f"queue: {state or 'not queued (finished or unknown)'}")
    h.do(f"tail -25 ~/{REMOTE}/narr_v2_yuyan_{job}.out 2>/dev/null || true", show=True)
    if not state:
        h.do(f"sacct -j {job} --format=JobID,State,Elapsed,ExitCode -n 2>/dev/null | head -5",
             show=True)
    return {"job": job, "queue": state}


def get_raw(h, remote: str, local: str) -> None:
    """Fetch one file without the legacy host/user scrub, which would reject the
    report's own absolute paths."""
    os.makedirs(os.path.dirname(local), exist_ok=True)
    tmp = local + ".part"
    sftp = h._sftp()
    try:
        sftp.get(f"/home/student/{h.user}/{remote}", tmp)
    finally:
        sftp.close()
    os.replace(tmp, local)
    print(f"fetched {local} ({os.path.getsize(local)} bytes)")


def fetch(h, job: str) -> Dict[str, Any]:
    local_dir = os.path.join(RUNS, job)
    os.makedirs(local_dir, exist_ok=True)
    wanted = [
        (f"{REMOTE}/{RUN_DIR}/report.json", os.path.join(local_dir, "report.json")),
        (f"{REMOTE}/{RUN_DIR}/samples.txt", os.path.join(local_dir, "samples.txt")),
        (f"{REMOTE}/narr_v2_yuyan_{job}.out", os.path.join(local_dir, "job.out")),
        (f"{REMOTE}/narr_v2_yuyan_{job}.err", os.path.join(local_dir, "job.err")),
    ]
    fetched: List[str] = []
    for remote, local in wanted:
        try:
            get_raw(h, remote, local)
            fetched.append(local)
        except Exception as error:  # noqa: BLE001
            print(f"skip {remote}: {error}")
    summary = {"job": job, "dir": local_dir, "fetched": fetched}
    if os.path.exists(os.path.join(local_dir, "report.json")):
        with io.open(os.path.join(local_dir, "report.json"), encoding="utf-8") as handle:
            report = json.load(handle)
        summary["best"] = report.get("best")
        summary["final"] = {key: report.get("final", {}).get(key)
                            for key in ("trainLoss", "devLoss", "testLoss")}
        summary["seconds"] = report.get("seconds")
        summary["identity"] = report.get("identity")
    with io.open(os.path.join(local_dir, "fetch.json"), "w", encoding="utf-8",
                 newline="\n") as handle:
        handle.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("deploy", "submit", "poll", "fetch", "go"))
    parser.add_argument("job", nargs="?", default="")
    args = parser.parse_args()
    base = load_base()
    h = base.Hpc()
    try:
        if args.action in ("deploy", "go"):
            upload_files(h)
        if args.action in ("submit", "go"):
            job = submit(h)
            if args.action == "submit":
                return 0
            # go: poll at a conservative interval, then fetch
            for _ in range(60):
                info = poll(h, job)
                if not info["queue"]:
                    break
                time.sleep(60)
            fetch(h, job)
        elif args.action == "poll":
            if not args.job:
                raise SystemExit("poll needs a job id")
            poll(h, args.job)
        elif args.action == "fetch":
            if not args.job:
                raise SystemExit("fetch needs a job id")
            fetch(h, args.job)
        return 0
    finally:
        h.c.close()


if __name__ == "__main__":
    raise SystemExit(main())
