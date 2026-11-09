#!/usr/bin/env python
"""Preflight before submitting: tokenizer loads, data parses, lengths known.

Runs in seconds on any machine with transformers + sentencepiece; it does not
touch CUDA, so it can run on the cluster login node before the job is queued.

  python preflight.py --data rows-xy.jsonl --base ~/n4v2_run/base/randeng-t5-77m
"""

import argparse
import io
import json
import os
import sys

from transformers.models.t5.tokenization_t5 import T5Tokenizer

from narration_text import decode_output, encode_target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=os.path.join(os.path.dirname(__file__), "rows-xy.jsonl"))
    parser.add_argument("--base", required=True, help="dir with config.json/model.safetensors/spiece.model")
    args = parser.parse_args()

    missing = [name for name in ("config.json", "model.safetensors", "spiece.model")
               if not os.path.exists(os.path.join(args.base, name))]
    if missing:
        print(f"FAIL base dir {args.base} is missing {missing}")
        return 1

    tokenizer = T5Tokenizer(vocab_file=os.path.join(args.base, "spiece.model"),
                            extra_ids=0, legacy=True)
    rows = [json.loads(line) for line in io.open(args.data, encoding="utf-8")]
    xs, ys = [], []
    for row in rows:
        for field in ("id", "x", "y", "xText"):
            if field not in row:
                print(f"FAIL row {row.get('id')} lacks {field}")
                return 1
        xs.append(len(tokenizer(row["xText"], truncation=False)["input_ids"]))
        ys.append(len(tokenizer(encode_target(row["y"]), truncation=False)["input_ids"]))
    print(json.dumps({"rows": len(rows),
                      "inputTokens": {"min": min(xs), "max": max(xs),
                                      "mean": round(sum(xs) / len(xs))},
                      "targetTokens": {"min": min(ys), "max": max(ys),
                                       "mean": round(sum(ys) / len(ys))}},
                     ensure_ascii=False))
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
