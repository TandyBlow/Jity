# Measure real token lengths for the frozen serializer, then register maxLen.
#
# The old N5 head used MAX_LEN=96 silently. That is not reused: a 9-slot X with
# candidates is longer, and cutting it would drop the very slots the labels
# depend on (goals, candidates). This script counts tokens for every delivered
# row with the real tokenizer and writes the registered rule's result:
#
#   maxLen = ceil(p100 / 32) * 32, capped at 384
#   if p100 > 384: truncation would be required -> refuse and report the count
#
# Usage (HPC, where the tokenizer files live):
#   python measure_tokens.py --base base/minirbt-h256 \
#       --rows data/train.jsonl data/validation.jsonl --out token-lengths.json
#
# With --stub-tokenizer it runs offline on a character-count proxy, for the CPU
# mechanism test only; the output is labelled `stub` and train.py refuses it for
# a real run.

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import List, Sequence

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dataset import read_rows  # noqa: E402
from labels import sha256_file  # noqa: E402
from serialize import render_candidate, render_x  # noqa: E402

CAP = 384
STEP = 32


def percentile(values: Sequence[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def measure(texts: Sequence[str], count_tokens) -> List[int]:
    return [count_tokens(text) for text in texts]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--rows", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--stub-tokenizer", action="store_true")
    args = parser.parse_args()

    rows: List[dict] = []
    for path in args.rows:
        rows.extend(read_rows(path))
    texts = [render_x(row) for row in rows]
    candidate_texts = [
        render_candidate(candidate)
        for row in rows for candidate in ((row.get("x") or {}).get("candidates") or [])
    ]

    if args.stub_tokenizer:
        count = lambda text: len(text) + 2  # noqa: E731  (offline proxy only)
        tokenizer_name = "stub:len(text)+2"
        tokenizer_files = {"stub": "offline-test"}
    else:
        if not args.base:
            raise SystemExit("REFUSED: --base is required for the real tokenizer")
        from transformers.models.bert.tokenization_bert import BertTokenizer

        tokenizer = BertTokenizer.from_pretrained(args.base)
        count = lambda text: len(tokenizer(text, truncation=False)["input_ids"])  # noqa: E731
        tokenizer_name = "BertTokenizer"
        base = pathlib.Path(args.base)
        tokenizer_files = {name: sha256_file(base / name) for name in ("vocab.txt", "config.json") if (base / name).exists()}

    lengths = measure(texts, count)
    candidate_lengths = measure(candidate_texts, count)
    p100 = percentile(lengths, 1.0)
    max_len = min(CAP, ((p100 + STEP - 1) // STEP) * STEP)
    over = [index for index, value in enumerate(lengths) if value > max_len]
    result = {
        "measured": True,
        "tokenizer": tokenizer_name,
        "tokenizerFiles": tokenizer_files,
        "rows": len(lengths),
        "candidateTexts": len(candidate_lengths),
        "xLength": {
            "min": min(lengths) if lengths else 0,
            "p50": percentile(lengths, 0.5),
            "p90": percentile(lengths, 0.9),
            "p100": p100,
            "mean": round(sum(lengths) / len(lengths), 2) if lengths else 0,
        },
        "candidateLength": {
            "p50": percentile(candidate_lengths, 0.5),
            "p100": percentile(candidate_lengths, 1.0),
        },
        "rule": "maxLen = ceil(p100/32)*32 capped at 384; over-cap rows are reported, never truncated",
        "maxLen": max_len,
        "truncatedRows": len(over),
        "overCapRowIds": [rows[index].get("rowId") for index in over][:20],
        "rowsSha256": {path: sha256_file(pathlib.Path(path)) for path in args.rows},
    }
    pathlib.Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("rows", "xLength", "maxLen", "truncatedRows")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
