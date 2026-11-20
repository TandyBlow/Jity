# -*- coding: utf-8 -*-
"""Teacher pass over beat prompts on the HPC GPU.

Reads a beat JSONL (each record has `prompt`), asks the teacher for 1-2
sentences, and writes `{id, text}` records. The teacher is a local instruct
model loaded with its own chat template; the beat prompt is the user turn and
the short style instruction is the system turn. No reference target is sent.

    python teacher_beats.py --beats beats-pilot.jsonl --out out-pilot.jsonl \
        --model ~/qwen7b --batch 8 --limit 8 --temperature 0.8
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from typing import Any, Dict, List

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

SYSTEM = ("你是中文小说作者，为一个文字冒险游戏写正文。文字要具体、克制，"
          "靠动作、环境和物件细节推进，不写标题，不复述设定。")


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    tmp = path + ".part"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--beats", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default="~/qwen7b")
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--samples", type=int, default=2,
                        help="how many candidate sentences per beat to keep")
    parser.add_argument("--max-new", type=int, default=96)
    parser.add_argument("--temperature", type=float, default=0.85)
    parser.add_argument("--top-p", type=float, default=0.92)
    parser.add_argument("--seed", type=int, default=20261110)
    parser.add_argument("--no-system", action="store_true",
                        help="send the prompt as a single user turn, exactly like the product page")
    parser.add_argument("--system", default=SYSTEM)
    args = parser.parse_args()

    beats = read_jsonl(args.beats)
    if args.limit:
        beats = beats[:args.limit]
    torch.manual_seed(args.seed)
    model_path = os.path.expanduser(args.model)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_path, local_files_only=True, torch_dtype=torch.bfloat16,
        device_map={"": 0})
    model.eval()
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    started = time.time()
    done: List[Dict[str, Any]] = []
    for start in range(0, len(beats), args.batch):
        chunk = beats[start:start + args.batch]
        prompts = []
        for beat in chunk:
            messages = ([] if args.no_system else [{"role": "system", "content": args.system}])
            messages.append({"role": "user", "content": beat["prompt"]})
            prompts.append(tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True))
        encoded = tokenizer(prompts, return_tensors="pt", padding=True,
                            add_special_tokens=False).to(model.device)
        with torch.no_grad():
            output = model.generate(
                **encoded, max_new_tokens=args.max_new,
                do_sample=args.temperature > 0,
                temperature=max(args.temperature, 1e-5),
                top_p=args.top_p,
                num_return_sequences=args.samples,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id)
        width = encoded["input_ids"].shape[1]
        for index, beat in enumerate(chunk):
            texts = []
            for sample in range(args.samples):
                row = index * args.samples + sample
                text = tokenizer.decode(output[row, width:],
                                        skip_special_tokens=True).strip()
                texts.append(text)
            done.append({"id": beat["id"], "source": beat.get("source", "pilot"),
                         "kind": beat["fact"]["kind"], "candidates": texts})
        elapsed = time.time() - started
        print(f"{min(start + args.batch, len(beats))}/{len(beats)} "
              f"{elapsed:.0f}s", flush=True)
        write_jsonl(args.out, done)
    print(json.dumps({"beats": len(done), "seconds": round(time.time() - started, 1)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
