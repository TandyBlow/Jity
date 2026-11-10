# -*- coding: utf-8 -*-
"""One table over several eval_draft.py runs.

Inputs are the JSON files eval_draft writes (per-row prose, draft, issues).
Nothing is recomputed differently here: it counts the issues eval_draft
recorded, so a reader can compare arms without opening five files.

    python src/compare_arms.py --arm v3@scene=hpc/runs/251547/eval-dev-chat.json \
        --arm v3@repair=hpc/runs/251547/eval-dev-repair.json --out hpc/runs/arm-table.md
"""

from __future__ import annotations

import argparse
import io
import json
from typing import Any, Dict, List


def load(path: str) -> Dict[str, Any]:
    with io.open(path, encoding="utf-8") as handle:
        return json.load(handle)


def summarize(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = data.get("rowsDetail") or []
    counts: Dict[str, int] = {}
    for row in rows:
        for issue in row.get("issues", []):
            key = issue.split(":")[0]
            counts[key] = counts.get(key, 0) + 1
    lengths = [len(row.get("prose") or "") for row in rows]
    return {
        "rows": len(rows),
        "clean": sum(1 for row in rows if row.get("ok")),
        "meanChars": round(sum(lengths) / len(lengths)) if lengths else 0,
        "minChars": min(lengths) if lengths else 0,
        "maxChars": max(lengths) if lengths else 0,
        "missingDraftRows": counts.get("missing_draft", 0),
        "inventedNumberRows": counts.get("invented_number", 0),
        "fillerRows": counts.get("filler", 0),
        "tooLongRows": counts.get("too_long", 0),
        "dialogueRows": counts.get("dialogue_added", 0),
        "file": data.get("gguf") or "",
        "split": data.get("split"),
        "temperature": data.get("temperature"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", action="append", default=[], help="label=path")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    table: List[Dict[str, Any]] = []
    for item in args.arm:
        label, _, path = item.partition("=")
        table.append({"arm": label, **summarize(load(path)), "path": path})
    header = ("| arm | rows | clean | chars mean/min/max | missing draft | invented number "
              "| filler | dialogue | too long |")
    lines = [header, "|---|---|---|---|---|---|---|---|---|"]
    for row in table:
        lines.append("| {arm} | {rows} | {clean} | {meanChars}/{minChars}/{maxChars} | {missingDraftRows} "
                     "| {inventedNumberRows} | {fillerRows} | {dialogueRows} | {tooLongRows} |".format(**row))
    text = "\n".join(lines)
    print(text)
    if args.out:
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text + "\n\n" + json.dumps(table, ensure_ascii=False, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
