# -*- coding: utf-8 -*-
"""Generate a few dev prompts from a LoRA adapter on the GPU, as raw text.

The exported GGUF is the product artefact, but waiting for a full merge +
quantise to see whether an adapter writes prose at all wastes a cycle. This runs
the adapter in transformers on the same frozen prompts and prints what it says,
so overfitting or a broken prompt shows up in minutes.

    python hpc/probe_adapter.py --adapter runs/<run>/adapter-best.pt \
        --config configs/<cfg>.json --data data/train-page-v1.jsonl \
        --split dev --limit 5 --out runs/<run>/probe-dev.json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import time

import torch


def read_jsonl(path: str):
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default="", help="empty with --base-only measures the unadapted baseline")
    parser.add_argument("--config", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--split", default="dev")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--max-new", type=int, default=220)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=20261110)
    parser.add_argument("--base-only", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with io.open(args.config, encoding="utf-8") as handle:
        config = json.load(handle)
    base = os.path.expanduser(config["base"]["file"])
    system = config.get("systemPrompt") or "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."

    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(base, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        base, local_files_only=True, torch_dtype=torch.float16).cuda()
    lora = config["training"]["lora"]
    if not args.base_only:
        model = get_peft_model(model, LoraConfig(
            r=int(lora["r"]), lora_alpha=int(lora["alpha"]),
            lora_dropout=float(lora.get("dropout", 0.05)),
            target_modules=list(lora["targetModules"]), bias="none", task_type="CAUSAL_LM"))
        state = torch.load(args.adapter, map_location="cpu")
        missing = model.load_state_dict(state, strict=False)
    else:
        missing = type("M", (), {"missing_keys": []})()
    model.eval()

    rows = [row for row in read_jsonl(args.data) if row["split"] == args.split][:args.limit]
    torch.manual_seed(args.seed)
    results = []
    for row in rows:
        prompt = (f"<|im_start|>system\n{system}<|im_end|>\n"
                  f"<|im_start|>user\n{row['user']}<|im_end|>\n<|im_start|>assistant\n")
        encoded = tokenizer(prompt, return_tensors="pt").to("cuda")
        started = time.time()
        with torch.no_grad():
            out = model.generate(**encoded, max_new_tokens=args.max_new, do_sample=True,
                                 temperature=args.temperature, top_p=0.9,
                                 pad_token_id=tokenizer.eos_token_id)
        text = tokenizer.decode(out[0][encoded["input_ids"].shape[1]:], skip_special_tokens=True)
        results.append({"id": row["id"], "draft": row.get("draft"), "target": row["target"],
                        "prose": text.strip(), "seconds": round(time.time() - started, 2),
                        "newTokens": int(out.shape[1] - encoded["input_ids"].shape[1])})
        print(f"{row['id']} {results[-1]['newTokens']}tok {len(results[-1]['prose'])}ch", flush=True)

    report = {"adapter": args.adapter or None, "baseOnly": args.base_only, "loadedMissing": [k for k in missing.missing_keys][:5],
              "base": base, "split": args.split, "temperature": args.temperature,
              "seed": args.seed, "rows": results,
              "note": "raw adapter output on dev prompts; no grading and no quality claim"}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    for row in results:
        print("-" * 60)
        print(row["id"], "| draft:", (row["draft"] or "")[:80])
        print("PROSE:", row["prose"][:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
