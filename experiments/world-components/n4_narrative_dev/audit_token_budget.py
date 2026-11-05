"""Measure N4 corpora with the local T5 tokenizer; never truncate silently.

This is an encoding audit, not a model or fidelity evaluation. It includes
every source row, including rows excluded by the separate world-data check.
No weights are loaded and no files are written unless --output is supplied.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics


HERE = Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(values):
    return {"min": min(values), "median": statistics.median(values),
            "max": max(values)}


def audit(path, tokenizer, max_input, max_target):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8")
            .splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"Empty corpus: {path}")
    lengths = []
    overflow = []
    splits = {}
    for row in rows:
        rid = row.get("id") or row.get("rowId") or row.get("pairId")
        if not rid:
            raise ValueError(f"Row without id in {path}")
        encoded = {key: tokenizer(row[key], add_special_tokens=True,
                                  truncation=False).input_ids
                   for key in ("input", "target")}
        ni, nt = len(encoded["input"]), len(encoded["target"])
        lengths.append((ni, nt))
        bucket = splits.setdefault(row.get("split", "unspecified"), Counter())
        bucket["rows"] += 1
        bucket["inputOverflow"] += ni > max_input
        bucket["targetOverflow"] += nt > max_target
        bucket["bothFit"] += ni <= max_input and nt <= max_target
        if ni <= max_input and nt <= max_target:
            continue
        item = {"id": rid, "split": row.get("split"),
                "inputTokens": ni, "targetTokens": nt}
        for key, limit in (("input", max_input), ("target", max_target)):
            ids = encoded[key]
            if len(ids) <= limit:
                continue
            # Ask the actual tokenizer for the retained sequence: max_length
            # includes EOS, so slicing the first `limit` content ids is wrong.
            kept = tokenizer(row[key], add_special_tokens=True,
                             truncation=True, max_length=limit).input_ids
            if tokenizer.truncation_side != "right":
                raise ValueError("Tail audit expects right truncation")
            item[key + "Truncation"] = {
                "removedTokens": len(ids) - len(kept),
                "retainedTail": tokenizer.decode(kept[-33:],
                                                  skip_special_tokens=True),
                "droppedTail": tokenizer.decode(ids[limit - 1:],
                                                 skip_special_tokens=True),
            }
        overflow.append(item)
    return {
        "path": str(path.relative_to(REPO)) if path.is_relative_to(REPO)
                else str(path),
        "sha256": sha(path), "rows": len(rows),
        "inputTokens": summarize([i for i, _ in lengths]),
        "targetTokens": summarize([t for _, t in lengths]),
        "inputOverflow": sum(i > max_input for i, _ in lengths),
        "targetOverflow": sum(t > max_target for _, t in lengths),
        "bothFit": sum(i <= max_input and t <= max_target for i, t in lengths),
        "fits768Input256Target": sum(i <= 768 and t <= 256 for i, t in lengths),
        "bySplit": {key: dict(val) for key, val in splits.items()},
        "overflowRows": overflow,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", action="append", type=Path)
    ap.add_argument("--tokenizer", type=Path,
                    default=WC / "assets" / "randeng-t5-77m")
    ap.add_argument("--max-input", type=int, default=512)
    ap.add_argument("--max-target", type=int, default=128)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--fail-on-overflow", action="store_true")
    args = ap.parse_args()
    if min(args.max_input, args.max_target) < 2:
        ap.error("Token budgets must leave room for content and EOS")

    import transformers
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    tok = T5Tokenizer.from_pretrained(str(args.tokenizer), legacy=False,
                                      local_files_only=True)
    paths = args.corpus or [HERE / "training_pairs.jsonl",
                            HERE / "formal_pairs.jsonl",
                            WC / "n4_rewrite60" / "corpus140.jsonl"]
    report = {
        "purpose": "Encoding audit; no model inference or quality score",
        "scriptSha256": sha(Path(__file__).resolve()),
        "transformersVersion": transformers.__version__,
        "tokenizer": str(args.tokenizer.resolve()),
        "tokenizerFiles": {name: sha(args.tokenizer / name) for name in
                           ("spiece.model", "tokenizer_config.json",
                            "special_tokens_map.json")},
        "legacy": False, "addSpecialTokens": True,
        "truncationSide": tok.truncation_side,
        "budgets": {"input": args.max_input, "targetIncludingEOS": args.max_target},
        "corpora": [audit(p.resolve(), tok, args.max_input, args.max_target)
                    for p in paths],
    }
    for result in report["corpora"]:
        print(f"{result['path']}: {result['rows']} rows; "
              f"input overflow {result['inputOverflow']}, "
              f"target overflow {result['targetOverflow']}, "
              f"both fit {result['bothFit']}", flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)
                               + "\n", encoding="utf-8")
        print(f"Report: {args.output}")
    has_overflow = any(r["inputOverflow"] or r["targetOverflow"]
                       for r in report["corpora"])
    return 1 if args.fail_on_overflow and has_overflow else 0


if __name__ == "__main__":
    raise SystemExit(main())
