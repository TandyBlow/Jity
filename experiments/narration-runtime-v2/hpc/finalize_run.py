# -*- coding: utf-8 -*-
"""One command from a finished training run to a registered candidate.

Steps: fetch report.json + adapter-best.pt -> merge LoRA into fp16 -> quantise to
Q4_K_M -> screen the dev split -> print a candidate record.

It does not decide quality and does not run a browser: 09 runs the real page and
01 reviews the text. This only removes the hand work between "job ended" and
"06 can load a file".

    python hpc/finalize_run.py --run qwen15b-page-v1 --model-id qwen25-1.5b-page-draft-v1 \
        --dev-limit 14
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(V2, "..", ".."))
MODELS = "D:/others/Jity/.local/models-narration"
CONVERT = "D:/others/Jity/.local/qwen-train/convert_hf_to_gguf.py"
QUANTIZE = "D:/others/Jity/.local/llama-cpp/llama-quantize.exe"

sys.path.insert(0, HERE)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="remote run dir name, e.g. qwen15b-page-v1-gpu")
    parser.add_argument("--job", required=True, help="slurm job id that produced the run")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--base", default="D:/others/Jity/.local/qwen-train/model15")
    parser.add_argument("--dev-limit", type=int, default=14)
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--keep-fp16", action="store_true")
    args = parser.parse_args()

    import beats_job as B
    run_dir = os.path.join(V2, "hpc", "runs", args.job)
    report_path = os.path.join(run_dir, "report.json")
    if not os.path.exists(report_path):
        B.fetch_dir(B.hpc(), args.job, (
            (f"runs/{args.run}/report.json", "report.json"),
            (f"runs/{args.run}/adapter-best.pt", "adapter-best.pt"),
            (f"train_{args.job}.out", "job.out"),
            (f"train_{args.job}.err", "job.err")))
    report = json.load(io.open(report_path, encoding="utf-8"))

    adapter = os.path.join(run_dir, "adapter-best.pt")
    if not os.path.exists(adapter):
        raise SystemExit(f"missing adapter {adapter}")
    out_dir = os.path.join(MODELS, args.run)
    os.makedirs(out_dir, exist_ok=True)
    gguf = os.path.join(out_dir, "model-Q4_K_M.gguf")
    if not os.path.exists(gguf):
        subprocess.run([sys.executable, os.path.join(HERE, "export_candidate.py"),
                        "--adapter", adapter, "--base", args.base, "--out", out_dir,
                        "--quant", "Q4_K_M"], check=True)
    if not args.keep_fp16:
        for leftover in ("hf", "model-f16.gguf"):
            path = os.path.join(out_dir, leftover)
            if os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.exists(path):
                os.remove(path)

    record = {
        "id": args.model_id,
        "runId": args.run,
        "status": "exported; not quality-checked",
        "weights": {"gguf": gguf.replace("/", "\\"), "ggufSha256": sha256(gguf),
                    "ggufBytes": os.path.getsize(gguf)},
        "training": {"report": os.path.relpath(report_path, REPO).replace("\\", "/"),
                     "best": report.get("best"), "testLoss": report.get("testLoss"),
                     "data": report.get("data"), "precision": report.get("precision")},
        "honesty": ["loss is not prose quality", "no browser run has been made with this file",
                    "no independent review has read its output"],
    }
    if not args.skip_eval:
        eval_out = os.path.join(run_dir, "eval-dev.json")
        subprocess.run([sys.executable, os.path.join(V2, "src", "eval_draft.py"),
                        "--gguf", gguf, "--split", "dev", "--limit", str(args.dev_limit),
                        "--out", eval_out], check=True)
        summary = json.load(io.open(eval_out, encoding="utf-8"))
        record["offlineScreen"] = {"rows": summary["rows"], "passed": summary["passed"],
                                   "passRate": summary["passRate"],
                                   "detail": os.path.relpath(eval_out, REPO).replace("\\", "/"),
                                   "note": "cheap checks only; not product acceptance"}
    print(json.dumps(record, ensure_ascii=False, indent=1))
    with io.open(os.path.join(run_dir, "candidate.json"), "w",
                 encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
