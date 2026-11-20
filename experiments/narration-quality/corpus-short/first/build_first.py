#!/usr/bin/env python3
"""Apply the first-batch handwritten targets to their frozen rows.

The 22 rows built here keep the frozen ``x`` copied into ``input`` unchanged;
only ``targetText``/``targetChars`` are rewritten from ``scenes.json``.  Every
other line in ``rows.jsonl`` is preserved byte for byte.
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE.parent
ROWS_PATH = CORPUS / "rows.jsonl"
SPEC_PATH = HERE / "scenes.json"


def canonical(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    spec = json.load(io.open(SPEC_PATH, encoding="utf-8"))
    texts = {entry["id"]: entry for entry in spec["rows"]}
    if len(texts) != len(spec["rows"]):
        raise SystemExit("duplicate id in first/scenes.json")

    lines = [line for line in io.open(ROWS_PATH, encoding="utf-8") if line.strip()]
    applied = 0
    out = []
    for line in lines:
        row = json.loads(line)
        rid = row["id"]
        if rid in texts:
            if not rid.startswith("short-") or rid.startswith("short2-") or rid.startswith("short-long-"):
                raise SystemExit(f"{rid}: first-batch id must start with short- and not short2-/short-long-")
            digest = hashlib.sha256(canonical(row["input"]).encode("utf-8")).hexdigest()
            if digest != row["sourceInputSha256"]:
                raise SystemExit(f"{rid}: frozen input hash changed")
            entry = texts[rid]
            text = entry["targetText"]
            override = entry.get("sourceRowId")
            if override:
                if not (override.startswith("row-") or override.startswith("derived:row-")):
                    raise SystemExit(f"{rid}: unexpected sourceRowId override {override!r}")
                row["sourceRowId"] = override
            if not 60 <= len(text) <= 160:
                raise SystemExit(f"{rid}: {len(text)} chars is outside 60-160")
            row["targetText"] = text
            row["targetChars"] = len(text)
            applied += 1
        out.append(json.dumps(row, ensure_ascii=False))
    missing = sorted(set(texts) - {json.loads(line)["id"] for line in lines})
    if missing:
        raise SystemExit(f"rows missing from rows.jsonl: {missing}")
    io.open(ROWS_PATH, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
    print(f"first-batch targets applied: {applied}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
