# -*- coding: utf-8 -*-
"""Import lane 01's hand-written short-scene corpus into the v2 training data.

Lane 01 owns the prose; this module only (a) re-serializes the structured input
with the v2 reference serializer so the training text is the same format the
browser will feed, (b) checks that the serialized input equals the frozen row's
v2 xProse byte for byte, and (c) cuts per-fact beat targets out of the human
target when a sentence actually binds the fact.

No prose is generated here and no source file is modified.
"""

from __future__ import annotations

import io
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(V2, "..", ".."))
CORPUS = os.path.abspath(os.path.join(
    REPO, "..", "01-input", "experiments", "narration-quality", "corpus-short",
    "rows.jsonl"))
ROWS = os.path.join(V2, "data", "rows-v2.jsonl")
OUT_ROWS = os.path.join(V2, "data", "rows-short-v1.jsonl")
OUT_BEATS = os.path.join(V2, "data", "beats-short-v1.jsonl")

sys.path.insert(0, HERE)
import narration_rules as R  # noqa: E402
import projection_v2  # noqa: E402
import v2_render  # noqa: E402


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path: str) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build_sentence_beats(row: Dict[str, Any], facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cut a 1-2 sentence beat out of the human target for each fact it binds."""
    text = row["targetText"]
    parts = R.sentences(text)
    beats: List[Dict[str, Any]] = []
    for fact in facts:
        hit: Optional[str] = None
        for index, sentence in enumerate(parts):
            joined = sentence
            if R.binds(fact, joined, [fact["name"]]):
                hit = joined
                break
            if index + 1 < len(parts):
                joined = sentence + parts[index + 1]
                if R.binds(fact, joined, [fact["name"]]):
                    hit = joined
                    break
        if not hit:
            continue
        beats.append({"id": f"{row['id']}-{fact['kind']}-{len(beats)}",
                      "source": "short", "sourceId": row["id"],
                      "split": row["sourceSplit"], "fact": fact,
                      "target": hit, "fullTarget": text})
    return beats


def main() -> int:
    corpus_sha = sha256(CORPUS)
    corpus = read_jsonl(CORPUS)
    rows_v2 = {row["id"]: row for row in read_jsonl(ROWS)}
    out_rows: List[Dict[str, Any]] = []
    out_beats: List[Dict[str, Any]] = []
    problems: List[str] = []
    for row in corpus:
        source = rows_v2.get(row["sourceRowId"])
        normalized, ledger = projection_v2.normalize_projection(row["input"])
        serialized = v2_render.serialize(normalized)
        if source is not None and serialized.text != source["xProse"]:
            problems.append(f"{row['id']}: serialized input differs from frozen v2 xProse")
        unexpected = [entry for entry in ledger
                      if entry.get("path") != "本回合变化/时间推进"]
        if unexpected:
            problems.append(f"{row['id']}: whitespace removal outside 时间推进: {unexpected[:2]}")
        facts = R.build_facts(row["input"])
        mandatory = [fact for fact in facts if fact["kind"] in R.MANDATORY]
        for fact in mandatory:
            fact.setdefault("phrase", "")
        beats = build_sentence_beats(row, mandatory)
        out_beats.extend(beats)
        out_rows.append({
            "id": row["id"],
            "sourceRowId": row["sourceRowId"],
            "split": row["sourceSplit"],
            "xProse": serialized.text,
            "target": row["targetText"],
            "requiredFacts": row["requiredFacts"],
            "categories": row["categories"],
            "beatCount": len(beats),
            "whitespaceLedger": ledger,
            "factCount": len(mandatory),
            "corpusSha256": corpus_sha,
            "reviewState": row.get("reviewState"),
        })
    with io.open(OUT_ROWS, "w", encoding="utf-8", newline="\n") as handle:
        for row in out_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with io.open(OUT_BEATS, "w", encoding="utf-8", newline="\n") as handle:
        for beat in out_beats:
            handle.write(json.dumps(beat, ensure_ascii=False) + "\n")
    summary = {
        "corpus": CORPUS,
        "corpusSha256": corpus_sha,
        "rows": len(out_rows),
        "beats": len(out_beats),
        "facts": sum(row["factCount"] for row in out_rows),
        "rowsWithAllFacts": sum(1 for row in out_rows
                                if row["beatCount"] == row["factCount"] and row["factCount"]),
        "rowsFile": OUT_ROWS,
        "beatsFile": OUT_BEATS,
        "problems": problems,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
