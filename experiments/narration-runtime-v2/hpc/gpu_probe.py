# -*- coding: utf-8 -*-
"""Measure what the GPU partition can actually do for inference.

Answers, on real hardware, the questions that decide whether 11/12 batches may
use an existing GPU instead of the CPU queue:
  * which GPU is allocated and what driver/CUDA it reports,
  * whether torch can run fp16 and bf16 there (the training bf16 restriction is
    a training fact, not an inference fact),
  * one loaded-instance throughput number (tokens/s) for a fixed prompt set,
  * sampled GPU utilisation and memory while generating.

It writes runs/<id>/gpu-probe.json. Nothing here is a quality claim.

    sbatch --partition=gpu --gres=gpu:v100:1 ... python hpc/gpu_probe.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

OUT = os.environ.get("GPU_PROBE_OUT", "runs/gpu-probe/gpu-probe.json")
MODEL = os.environ.get("GPU_PROBE_MODEL", os.path.expanduser("~/qwen15b"))
PROMPTS = [
    "用一句话说明潮位曲线纸为什么会被风吹得响。",
    "写一句沈砚走进值班室的动作，不要对白。",
    "写一句罗平擦掉鞋底的水的动作，不要对白。",
    "写一句陈漪放下电报底稿的动作，不要对白。",
]


def sh(cmd: str) -> str:
    result = subprocess.run(cmd, shell=True, capture_output=True)
    return result.stdout.decode("utf-8", "replace").strip()


def main() -> int:
    report = {"startedAtLocal": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "model": MODEL,
              "prompts": len(PROMPTS)}
    report["nvidiaSmi"] = sh(
        "nvidia-smi --query-gpu=index,name,memory.total,driver_version,compute_cap "
        "--format=csv,noheader")
    report["cudaVersion"] = sh("nvidia-smi | head -4 | tail -1")

    import torch
    report["torch"] = torch.__version__
    report["cudaAvailable"] = torch.cuda.is_available()
    if not torch.cuda.is_available():
        report["verdict"] = "no CUDA on this node; nothing to measure"
        write(report)
        return 0
    report["device"] = torch.cuda.get_device_name(0)
    report["bf16Supported"] = bool(torch.cuda.is_bf16_supported())
    report["capability"] = f"{torch.cuda.get_device_capability(0)}"

    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    load_started = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, local_files_only=True, torch_dtype=torch.float16).cuda()
    report["loadSeconds"] = round(time.time() - load_started, 2)

    def generate(dtype: str) -> dict:
        """One generation over the fixed prompt set; returns wall time and tokens/s."""
        prompts = [f"<|im_start|>user\n{p}<|im_end|>\n<|im_start|>assistant\n" for p in PROMPTS]
        encoded = tokenizer(prompts, return_tensors="pt", padding=True).to("cuda")
        started = time.time()
        with torch.no_grad():
            out = model.generate(**encoded, max_new_tokens=96, do_sample=False,
                                 pad_token_id=tokenizer.eos_token_id)
        seconds = time.time() - started
        new_tokens = int((out.shape[1] - encoded["input_ids"].shape[1])) * len(prompts)
        text = tokenizer.decode(out[0][encoded["input_ids"].shape[1]:], skip_special_tokens=True)
        return {"dtype": dtype, "seconds": round(seconds, 2), "newTokens": new_tokens,
                "tokensPerSecond": round(new_tokens / seconds, 1) if seconds else None,
                "sample": text.strip()[:120]}

    # First call pays kernel autotuning/CUDA-graph warmup; a warm call is the
    # number that matters for "can a batch run here", so both are recorded.
    report["fp16FirstCall"] = generate("float16")
    report["fp16Warm"] = generate("float16")
    report["fp16"] = report["fp16Warm"]
    report["memAfter"] = sh("nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader")
    report["verdict"] = "fp16 inference runs on this GPU" if report["fp16"]["tokensPerSecond"] \
        else "fp16 ran but produced no tokens"
    report["notQualityEvidence"] = ("throughput only; no narration quality is claimed, and the "
                                   "browser page remains the only acceptance surface")
    report["endedAtLocal"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    write(report)
    return 0


def write(report: dict) -> None:
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
