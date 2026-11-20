# -*- coding: utf-8 -*-
"""Merge a LoRA state dict into the Qwen2.5 base and export a GGUF.

    python hpc/export_candidate.py \
        --adapter hpc/runs/251222/adapter-best.pt \
        --base D:/others/Jity/.local/qwen-train/model \
        --out D:/others/Jity/.local/models-narration/qwen05b-scene-v1 \
        --quant Q4_K_M

The merged HF directory and the quantized GGUF stay outside Git; the candidate
registry records the paths and hashes.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

CONVERT = "D:/others/Jity/.local/qwen-train/convert_hf_to_gguf.py"
QUANTIZE = "D:/others/Jity/.local/llama-cpp/llama-quantize.exe"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--quant", default="Q4_K_M")
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--alpha", type=int, default=32)
    parser.add_argument("--dropout", type=float, default=0.05)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    merged_dir = os.path.join(args.out, "hf")
    if not os.path.isdir(merged_dir):
        model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.float16)
        config = LoraConfig(r=args.rank, lora_alpha=args.alpha,
                            lora_dropout=args.dropout, bias="none",
                            task_type="CAUSAL_LM",
                            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                            "gate_proj", "up_proj", "down_proj"])
        model = get_peft_model(model, config)
        state = torch.load(args.adapter, map_location="cpu", weights_only=False)
        missing, unexpected = model.load_state_dict(state, strict=False)
        print("missing", len(missing), "unexpected", len(unexpected))
        merged = model.merge_and_unload()
        merged.save_pretrained(merged_dir, safe_serialization=True)
        tokenizer = AutoTokenizer.from_pretrained(args.base)
        tokenizer.save_pretrained(merged_dir)

    f16 = os.path.join(args.out, "model-f16.gguf")
    if not os.path.exists(f16):
        subprocess.run([sys.executable, "-X", "utf8", CONVERT, merged_dir,
                        "--outfile", f16, "--outtype", "f16"], check=True)
    quant = os.path.join(args.out, f"model-{args.quant}.gguf")
    if not os.path.exists(quant):
        subprocess.run([QUANTIZE, f16, quant, args.quant, "8"], check=True)
    info: Dict[str, Any] = {"merged": merged_dir, "f16": f16, "quant": quant}
    for name, path in list(info.items()):
        if isinstance(path, str) and os.path.exists(path):
            info[name + "Bytes"] = os.path.getsize(path)
    print(json.dumps(info, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
