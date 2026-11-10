# -*- coding: utf-8 -*-
"""Aggregate raw screening runs without pretending to judge quality.

Reads the per-case JSON written by `screen.py` and reports only mechanical
facts: character count, sentence/paragraph counts, repeated sentences and
clauses inside one draft, finish reason, wall time, token/s. Fact accuracy,
style and the pass/fail decision belong to lane 01's rubric/reviewer; this
script never emits a "pass".

Usage:
    python -X utf8 src/collect.py --run evidence/runs/batch-1/qwen25-1.5b-instruct \
        --run evidence/runs/batch-1/internlm2_5-1.8b-chat --out-dir evidence/summary
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
import sys

SENTENCE_SPLIT = re.compile(r"[。！？!?…]+|\n+")
CLAUSE_SPLIT = re.compile(r"[。！？!?…；;，,、\n]+")
NORMALIZE = re.compile(r"[\s\u3000\"'“”‘’「」『』（）()《》<>…—\-·]+")


def sentences_of(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT.split(text) if part.strip()]


def clauses_of(text: str) -> list[str]:
    return [part.strip() for part in CLAUSE_SPLIT.split(text) if len(part.strip()) >= 2]


def key(text: str) -> str:
    return NORMALIZE.sub("", text)


def repeated(candidates: list[str]) -> dict:
    seen: dict[str, int] = {}
    for item in candidates:
        normalized = key(item)
        if not normalized:
            continue
        seen[normalized] = seen.get(normalized, 0) + 1
    total = sum(seen.values())
    duplicate = sum(count - 1 for count in seen.values() if count > 1)
    return {
        "total": total,
        "duplicateOccurrences": duplicate,
        "duplicateRatio": round(duplicate / total, 3) if total else 0.0,
        "mostRepeated": sorted(
            ({"text": text, "count": count} for text, count in seen.items() if count > 1),
            key=lambda item: -item["count"],
        )[:3],
    }


def case_stats(record: dict) -> dict:
    text = record.get("text") or ""
    sentence_list = sentences_of(text)
    clause_list = clauses_of(text)
    timings = record.get("timings") or {}
    return {
        "caseId": record["caseId"],
        "chars": len(text),
        "sentences": len(sentence_list),
        "clauses": len(clause_list),
        "paragraphs": len([p for p in text.split("\n") if p.strip()]),
        "sentenceRepeat": repeated(sentence_list),
        "clauseRepeat": repeated(clause_list),
        "finishReason": record.get("finishReason"),
        "httpStatus": record.get("httpStatus"),
        "wallMs": record.get("wallMs"),
        "promptTokens": timings.get("prompt_n"),
        "predictedTokens": timings.get("predicted_n"),
        "promptPerSecond": timings.get("prompt_per_second"),
        "predictedPerSecond": timings.get("predicted_per_second"),
        "empty": not text.strip(),
        "error": record.get("error"),
    }


def summarize_run(run_dir: pathlib.Path) -> dict:
    manifest = {}
    manifest_path = run_dir / "run-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = []
    for path in sorted(run_dir.glob("*.json")):
        if path.name == "run-manifest.json":
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if "caseId" in record:
            cases.append(case_stats(record))
    walls = [case["wallMs"] for case in cases if isinstance(case["wallMs"], (int, float))]
    decodes = [case["predictedPerSecond"] for case in cases
               if isinstance(case["predictedPerSecond"], (int, float))]
    return {
        "modelId": manifest.get("modelId") or run_dir.name,
        "modelSha256": manifest.get("modelSha256"),
        "loadSeconds": manifest.get("loadSeconds"),
        "cases": len(cases),
        "emptyCases": [case["caseId"] for case in cases if case["empty"]],
        "wallMs": {
            "mean": round(statistics.mean(walls), 1) if walls else None,
            "p50": round(statistics.median(walls), 1) if walls else None,
            "max": max(walls) if walls else None,
        },
        "predictedPerSecond": {
            "mean": round(statistics.mean(decodes), 2) if decodes else None,
            "p50": round(statistics.median(decodes), 2) if decodes else None,
        },
        "chars": {
            "mean": round(statistics.mean([case["chars"] for case in cases]), 1) if cases else None,
            "min": min((case["chars"] for case in cases), default=None),
            "max": max((case["chars"] for case in cases), default=None),
        },
        "caseStats": cases,
        "quality": "not judged here: fact/style decisions use 01's rubric and reviewer",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="append", required=True, help="run directory (repeatable)")
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    summary = {
        "note": "mechanical aggregation only; no pass/fail is produced by lane 11",
        "runs": [summarize_run(pathlib.Path(run)) for run in args.run],
    }
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = [
        "# Screening mechanical summary",
        "",
        "No quality pass/fail here. Fact/style decisions use 01's rubric.",
        "",
        "| model | cases | empty | chars mean | wall p50 ms | decode tok/s p50 | load s |",
        "|---|---|---|---|---|---|---|",
    ]
    for run in summary["runs"]:
        lines.append(
            f"| {run['modelId']} | {run['cases']} | {len(run['emptyCases'])} | "
            f"{run['chars']['mean']} | {run['wallMs']['p50']} | "
            f"{run['predictedPerSecond']['p50']} | {run['loadSeconds']} |"
        )
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
