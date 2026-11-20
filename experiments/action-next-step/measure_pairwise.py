"""Measure the short pair texts: real tokenizer lengths, repeats, conflicts.

Run (no training, CPU only):

    python measure_pairwise.py --rows <train13-full-candidates.jsonl> \\
        --labels <labels-v1.json> --tokenizer <minirbt snapshot> \\
        --out <measurement.json>

Reports:
- character and token length distribution over all pairs (both steps),
- the ceil-32 padding length and the 512 cap check (over-cap rows are listed,
  never truncated),
- goal counts (all 6-goal rows kept),
- identical short contexts across rows: same-label duplicates and, separately,
  different-label conflicts,
- what each conflicting pair still differs in (so a fix can be chosen from known
  row information instead of inventing a nonce).
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

import pairwise_serialize as ps


def _p(value: List[int], q: float) -> int:
    if not value:
        return 0
    ordered = sorted(value)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def distribution(values: List[int]) -> Dict[str, Any]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": min(values),
        "p50": _p(values, 0.50),
        "p95": _p(values, 0.95),
        "p100": max(values),
        "mean": round(statistics.fmean(values), 1),
    }


def context_of(text: str) -> str:
    """Everything the model sees except the candidate line."""
    kept = [line for line in text.split(chr(10)) if not line.startswith("动作：")]
    return chr(10).join(kept)



def differences(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Known, already-present row information that differs between two rows."""
    lx = left.get("x") or {}
    rx = right.get("x") or {}
    out: Dict[str, Any] = {}
    lc = lx.get("character") or {}
    rc = rx.get("character") or {}
    if lc.get("name") != rc.get("name"):
        out["characterName"] = [lc.get("name"), rc.get("name")]
    holds_l = [entry.get("name") for entry in lc.get("holds") or [] if isinstance(entry, dict)]
    holds_r = [entry.get("name") for entry in rc.get("holds") or [] if isinstance(entry, dict)]
    if holds_l != holds_r:
        out["holds"] = [holds_l, holds_r]
    if lc.get("place") != rc.get("place"):
        out["place"] = [lc.get("place"), rc.get("place")]
    # The clock lives on the row-level place, not the character's: the four
    # "conflicting" pairs in the first measurement differed only by minute.
    if lx.get("place") != rx.get("place"):
        out["rowPlace"] = [lx.get("place"), rx.get("place")]
    recent_l = lx.get("recent") or []
    recent_r = rx.get("recent") or []
    if recent_l != recent_r:
        out["recent"] = [recent_l, recent_r]
    present_l = [entry.get("name") for entry in lx.get("present") or [] if isinstance(entry, dict)]
    present_r = [entry.get("name") for entry in rx.get("present") or [] if isinstance(entry, dict)]
    if present_l != present_r:
        out["present"] = [present_l, present_r]
    items_l = [entry.get("name") for entry in lx.get("items") or [] if isinstance(entry, dict)]
    items_r = [entry.get("name") for entry in rx.get("items") or [] if isinstance(entry, dict)]
    if items_l != items_r:
        out["items"] = [items_l, items_r]
    if lx.get("personality") != rx.get("personality"):
        out["personality"] = "differs"
    if lx.get("sanity") != rx.get("sanity"):
        out["sanity"] = [lx.get("sanity"), rx.get("sanity")]
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--tokenizer", required=True, help="MiniRBT snapshot directory")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    from transformers import BertTokenizer  # local only, no download

    tokenizer = BertTokenizer.from_pretrained(args.tokenizer, do_lower_case=True)
    vocab = Path(args.tokenizer) / "vocab.txt"

    rows = ps.load_rows(args.rows)
    groups = ps.load_predicate_groups(args.labels)
    pairs = ps.pairs_for_rows(rows, groups)
    assert len(pairs) == 13 * sum(max(1, ps.step_count(row)) for row in rows)

    texts = [pair["text"] for pair in pairs]
    chars = [len(text) for text in texts]
    tokens = [len(tokenizer.encode(text, add_special_tokens=True)) for text in texts]
    max_len = min(512, -(-max(tokens) // 32) * 32)

    over_cap = [
        {"rowId": pair["rowId"], "stepIndex": pair["stepIndex"], "group": pair["group"], "tokens": count}
        for pair, count in zip(pairs, tokens) if count > 512
    ]

    by_context: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_row: Dict[str, Dict[str, Any]] = {row["rowId"]: row for row in rows}
    for pair in pairs:
        if pair["label"] != 1:
            continue
        by_context[context_of(pair["text"])].append(pair)

    repeated_same = 0
    conflicts: List[Dict[str, Any]] = []
    seen_contexts = 0
    for context, entries in by_context.items():
        rows_here = {entry["rowId"] for entry in entries}
        if len(rows_here) > 1:
            seen_contexts += 1
            labels = {entry["group"] for entry in entries}
            if len(labels) == 1:
                repeated_same += 1
                continue
            ordered = sorted(rows_here)
            detail = differences(by_row[ordered[0]], by_row[ordered[1]]) if len(ordered) == 2 else {
                "note": "more than two rows share this context"
            }
            conflicts.append({
                "rowIds": ordered,
                "labels": [by_row[row_id].get("yGroup") for row_id in ordered],
                "ySteps": [((by_row[row_id].get("y") or {}).get("steps") or []) for row_id in ordered],
                "rationale": [by_row[row_id].get("yRationale") for row_id in ordered],
                "source": [by_row[row_id].get("source") for row_id in ordered],
                "labelSource": [by_row[row_id].get("labelSource") for row_id in ordered],
                "steps": [entry["stepIndex"] for entry in entries],
                "contextSha256": ps.hashlib.sha256(context.encode("utf-8")).hexdigest(),
                "stillDiffersInRow": detail,
            })

    goal_counts = Counter(len((row.get("x") or {}).get("goals") or []) for row in rows)
    measurement = {
        "kind": "official-short-pair-serializer-measurement",
        "serializer": ps.VERSION,
        "serializerSha256": ps.serializer_digest(),
        "rowsFile": str(Path(args.rows).resolve()),
        "rowsSha256": ps.hashlib.sha256(Path(args.rows).read_bytes()).hexdigest(),
        "labelsFile": str(Path(args.labels).resolve()),
        "labelsSha256": ps.hashlib.sha256(Path(args.labels).read_bytes()).hexdigest(),
        "tokenizer": {
            "class": type(tokenizer).__name__,
            "vocabSha256": ps.hashlib.sha256(vocab.read_bytes()).hexdigest(),
            "specialTokensIncluded": True,
        },
        "rows": len(rows),
        "pairs": len(pairs),
        "step2Pairs": sum(1 for pair in pairs if pair["stepIndex"] == 1),
        "positives": sum(pair["label"] for pair in pairs),
        "characters": distribution(chars),
        "tokens": distribution(tokens),
        "maxLenCeil32": max_len,
        "over512Pairs": len(over_cap),
        "over512": over_cap[:50],
        "goalCounts": dict(sorted(goal_counts.items())),
        "goalEntriesClippedAt18": sum(pair["omitted"]["goalsClipped"] for pair in pairs if pair["label"] == 1),
        "rowsWithSixGoals": [row["rowId"] for row in rows if len((row.get("x") or {}).get("goals") or []) == 6],
        "repeatedContextRows": seen_contexts,
        "repeatedContextSameLabel": repeated_same,
        "conflictingLabelContexts": conflicts,
        "labelsUsed": dict(Counter(pair["group"] for pair in pairs if pair["label"] == 1)),
    }
    Path(args.out).write_text(json.dumps(measurement, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({
        key: measurement[key]
        for key in ("pairs", "positives", "characters", "tokens", "maxLenCeil32",
                    "over512Pairs", "repeatedContextRows", "repeatedContextSameLabel")
    }, ensure_ascii=False))
    print("conflicts", len(conflicts))
    for conflict in conflicts:
        print(" ", conflict["rowIds"], conflict["labels"])


if __name__ == "__main__":
    main()
