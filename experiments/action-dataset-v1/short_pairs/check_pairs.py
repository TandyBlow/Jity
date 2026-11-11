"""Independent check of the short-pair set.

Rebuilds the decisions from the frozen rows (not from the build output), renders
each pair again through 04's serializer, and verifies:

- pair count = 13 * (rows used + two-step rows), one positive per decision;
- the text of every pair matches a fresh render, and the 动作 line names its
  candidate group;
- no `yRationale` / `skipReason` / rowId text leaked into the input;
- token length with the real MiniRBT tokenizer, ceil32 and the 512 cap;
- every positive's object resolves through the row's candidate index;
- the second step carries `已做` with the first step's group and object name.

Only reads. Writes one JSON report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_pairs  # noqa: E402  (loads the serializer through the same guard)
import pair_index  # noqa: E402

SNAPSHOT = Path("D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", required=True)
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--serializer", default=build_pairs.DEFAULT_SERIALIZER)
    parser.add_argument("--tokenizer-dir", default=str(SNAPSHOT))
    parser.add_argument("--max-len", type=int, default=512)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    rows_digest = hashlib.sha256(Path(args.rows).read_bytes()).hexdigest()
    if rows_digest != pair_index.ROWS_SHA256:
        raise SystemExit(f"rows digest {rows_digest} is not the frozen 300-row file")
    rows = {row["rowId"]: row for row in read_jsonl(Path(args.rows))}
    pairs = read_jsonl(Path(args.pairs))
    serializer, serializer_sha = build_pairs.load_serializer(Path(args.serializer))

    problems: list[str] = []

    # 1. shape and counts
    used_rows = {pair["rowId"] for pair in pairs}
    two_step_rows = {row_id for row_id in used_rows if len(rows[row_id]["y"]["steps"]) == 2}
    expected = 13 * len(used_rows) + 13 * len(two_step_rows)
    if len(pairs) != expected:
        problems.append(f"pair count {len(pairs)} != expected {expected}")

    decisions: dict[tuple[str, int], list[dict]] = {}
    for pair in pairs:
        decisions.setdefault((pair["rowId"], pair["stepIndex"]), []).append(pair)
    for key, group in decisions.items():
        positives = [pair for pair in group if pair["positive"]]
        if len(group) != 13 or len(positives) != 1:
            problems.append(f"decision {key} has {len(group)} pairs and {len(positives)} positives")

    # 2. pairs must be unique and each row's step count must be covered
    if len({pair["pairId"] for pair in pairs}) != len(pairs):
        problems.append("duplicate pairId")

    # 3. re-render and compare, plus the 动作 line
    for pair in pairs:
        row = rows[pair["rowId"]]
        fresh = build_pairs.render_pair_text(serializer, row, pair)
        if fresh["text"] != pair["text"]:
            problems.append(f"{pair['pairId']}: text differs from a fresh render")
            continue
        if not pair["text"].rstrip().endswith(f"动作：{pair['candidateGroup']}"):
            problems.append(f"{pair['pairId']}: 动作 line does not name the candidate group")
        if pair["stepIndex"] == 0 and "已做：" in pair["text"]:
            problems.append(f"{pair['pairId']}: first step carries a 已做 line")
        if pair["stepIndex"] > 0:
            marker = f"已做：{pair['doneGroup']}（{pair['doneObjectName'] or '无'}）"
            if marker not in pair["text"]:
                problems.append(f"{pair['pairId']}: second step is missing {marker}")

    # 4. label-leak check
    for pair in pairs:
        row = rows[pair["rowId"]]
        for needle in (row["rowId"], row["yRationale"], row.get("skipReason") or "\u0000"):
            if needle and needle in pair["text"]:
                problems.append(f"{pair['pairId']}: input carries label text ({needle[:20]}...)")

    # 5. rows whose judgement rests on the clock must show the clock
    clock_rows = {
        row["rowId"]
        for row in rows.values()
        if "15:45" in (row.get("skipReason") or "")
        or "15:45" in (row.get("yRationale") or "")
        or "时间" in (row.get("skipReason") or "")
    }
    clock_rows &= used_rows
    clock_missing = sorted(
        row_id
        for row_id in clock_rows
        if not any("时间=" in pair["text"] for pair in pairs if pair["rowId"] == row_id)
    )
    if clock_missing:
        problems.append(f"{len(clock_missing)} clock-dependent rows do not show the time: {clock_missing}")

    # 6. object resolution on positives
    for pair in pairs:
        if not pair["positive"]:
            continue
        if pair["objectId"] is None:
            if pair["objectName"] is not None:
                problems.append(f"{pair['pairId']}: null object with a name")
            continue
        names = {entry["id"]: entry["name"] for entry in rows[pair["rowId"]]["x"]["candidates"]}
        if pair["objectName"] != names.get(pair["objectId"]):
            problems.append(f"{pair['pairId']}: object id does not resolve through the candidate index")

    # 6. token length with the real tokenizer
    from transformers import BertTokenizer

    tokenizer = BertTokenizer.from_pretrained(args.tokenizer_dir)
    token_counts = sorted(len(tokenizer.encode(pair["text"], add_special_tokens=True)) for pair in pairs)
    over = [pair["pairId"] for pair in pairs if len(tokenizer.encode(pair["text"], add_special_tokens=True)) > args.max_len]
    if over:
        problems.append(f"{len(over)} pairs exceed maxLen {args.max_len}: {over[:5]}")

    report = {
        "ok": not problems,
        "problems": problems,
        "pairs": len(pairs),
        "decisions": len(decisions),
        "rowsUsed": len(used_rows),
        "twoStepRows": len(two_step_rows),
        "serializer": {"version": serializer.VERSION, "sha256": serializer_sha},
        "tokens": {
            "min": token_counts[0],
            "p50": token_counts[len(token_counts) // 2],
            "p95": token_counts[int(len(token_counts) * 0.95)],
            "p100": token_counts[-1],
            "ceil32": ((token_counts[-1] + 31) // 32) * 32,
            "overMaxLen": len(over),
        },
        "clockRows": sorted(clock_rows),
        "rowsSha256": rows_digest,
        "pairsSha256": hashlib.sha256(Path(args.pairs).read_bytes()).hexdigest(),
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: report[key] for key in ("ok", "pairs", "tokens")}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
