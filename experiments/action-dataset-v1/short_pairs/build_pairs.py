"""Render the 13-way short-pair set with 04's only official serializer.

This module contains no text template of its own. It imports
`experiments/action-next-step/pairwise_serialize.py` from 04's worktree, checks
its version and group order, and refuses to write anything if the serializer is
missing or changed. That keeps a single serializer in the project: lane 13 owns
the decision index and the reports, lane 04 owns the text.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

DEFAULT_SERIALIZER = (
    "D:/others/Jity/.local/parallel-local-game/worktrees/04-settlement/"
    "experiments/action-next-step/pairwise_serialize.py"
)
GROUPS = ["感知", "移动", "战斗", "援助", "请求", "胁迫", "言语", "算计", "情绪", "物品", "身体", "立场"]
CANDIDATES = GROUPS + ["不动"]
ROWS_SHA256 = "cb4676b3eb74945331f73ee8855be300455c9e11db261c288d7534c7b02ef188"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_serializer(path: Path):
    if not path.exists():
        raise SystemExit(
            f"the official pairwise serializer is missing: {path}\n"
            "lane 04 owns it; 13 does not ship a second renderer. "
            "Ask 04 for experiments/action-next-step/pairwise_serialize.py first."
        )
    spec = importlib.util.spec_from_file_location("pairwise_serialize", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import serializer from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["pairwise_serialize"] = module
    spec.loader.exec_module(module)
    for name in ("VERSION", "short_context", "render_pair"):
        if not hasattr(module, name):
            raise SystemExit(f"serializer {path} does not expose {name}")
    groups = getattr(module, "ALL_GROUPS", None) or getattr(module, "GROUPS", None)
    if list(groups) != CANDIDATES:
        raise SystemExit(f"serializer group order changed: {list(groups)}")
    return module, hashlib.sha256(path.read_bytes()).hexdigest()


def render_pair_text(serializer, row: dict, entry: dict) -> dict:
    """Call 04's serializer. It owns the text; this only passes the decision."""
    context, omitted = serializer.short_context(row)
    prior = None
    if entry["stepIndex"] > 0:
        prior = {"group": entry["doneGroup"], "object": entry["doneObjectName"] or ""}
    text = serializer.render_pair(context, entry["candidateGroup"], prior=prior)
    return {"text": text, "chars": len(text), "omitted": omitted}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--serializer", default=DEFAULT_SERIALIZER)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--allow-same-label-duplicates",
        action="store_true",
        help="keep short texts shared by two decisions that carry the same label; they are listed in the report",
    )
    args = parser.parse_args(argv)

    rows_digest = hashlib.sha256(Path(args.rows).read_bytes()).hexdigest()
    if rows_digest != ROWS_SHA256:
        raise SystemExit(f"rows digest {rows_digest} is not the frozen 300-row file")
    rows = {row["rowId"]: row for row in read_jsonl(Path(args.rows))}
    index = read_jsonl(Path(args.index))
    serializer, serializer_sha = load_serializer(Path(args.serializer))

    pairs = []
    omitted_totals = {"goalsClipped": 0, "presentClipped": 0, "itemsClipped": 0, "recentClipped": 0}
    for entry in index:
        row = rows[entry["rowId"]]
        result = render_pair_text(serializer, row, entry)
        text = result["text"]
        omitted = result["omitted"] or {}
        omitted_totals["goalsClipped"] += int(omitted.get("goalsClipped") or 0)
        omitted_totals["presentClipped"] += len(omitted.get("presentOmitted") or [])
        omitted_totals["itemsClipped"] += len(omitted.get("itemsOmitted") or [])
        omitted_totals["recentClipped"] += max(0, int(omitted.get("recentTotal") or 0) - 1)
        pairs.append(
            {
                **entry,
                "text": text,
                "chars": len(text),
                "omitted": omitted,
                "serializerVersion": serializer.VERSION,
            }
        )

    texts: dict[str, list[dict]] = {}
    for pair in pairs:
        texts.setdefault(pair["text"], []).append(pair)
    shared = {text: group for text, group in texts.items() if len(group) > 1}
    conflicting = [group for group in shared.values() if len({pair["positive"] for pair in group}) > 1]
    if conflicting:
        raise SystemExit(
            f"refused: {len(conflicting)} short X strings carry opposite labels for the same decision; "
            "no amount of extra fields fixes a label conflict, exclude one side first. "
            f"example: {[pair['pairId'] for pair in conflicting[0]]}"
        )
    if shared and not args.allow_same_label_duplicates:
        raise SystemExit(
            f"refused: {len(shared)} short X strings are shared by decisions with the same label "
            "(indistinguishable inputs). Pass --allow-same-label-duplicates to keep them and record "
            "them in the report, or fix the serializer fields. "
            f"example: {[pair['pairId'] for pair in next(iter(shared.values()))]}"
        )
    indistinguishable = [
        {
            "textSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "pairIds": [pair["pairId"] for pair in group],
            "label": next(pair["positive"] for pair in group),
        }
        for text, group in shared.items()
    ]

    decisions: dict[tuple[str, int], int] = {}
    for pair in pairs:
        key = (pair["rowId"], pair["stepIndex"])
        decisions[key] = decisions.get(key, 0) + (1 if pair["positive"] else 0)
    if any(count != 1 for count in decisions.values()):
        raise SystemExit("a decision does not have exactly one positive")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "pairs.jsonl", pairs)
    report = {
        "kind": "short-pair dataset",
        "serializer": {"version": serializer.VERSION, "sha256": serializer_sha, "path": str(Path(args.serializer).resolve())},
        "rows": {"path": str(Path(args.rows)), "sha256": rows_digest},
        "indexSha256": hashlib.sha256(Path(args.index).read_bytes()).hexdigest(),
        "pairs": len(pairs),
        "decisions": len(decisions),
        "positives": sum(1 for pair in pairs if pair["positive"]),
        "perGroupPositive": _count([pair for pair in pairs if pair["positive"]], "labelGroup"),
        "perCandidate": _count(pairs, "candidateGroup"),
        "omittedTotals": omitted_totals,
        "indistinguishable": indistinguishable,
        "indistinguishableTexts": len(indistinguishable),
        "pairsSha256": hashlib.sha256(_jsonl_bytes(pairs)).hexdigest(),
    }
    (out_dir / "build-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({k: report[k] for k in ("pairs", "decisions", "positives", "omittedTotals")}, ensure_ascii=False))
    return 0


def _count(pairs: list[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pair in pairs:
        counts[pair[field]] = counts.get(pair[field], 0) + 1
    return counts


def _jsonl_bytes(records: list[dict]) -> bytes:
    return ("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n").encode("utf-8")


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_bytes(_jsonl_bytes(records))


if __name__ == "__main__":
    raise SystemExit(main())
