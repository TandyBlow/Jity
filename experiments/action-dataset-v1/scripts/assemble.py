"""Concatenate per-batch row files into one delivery file.

The per-batch files stay the source of truth: each one carries the rewrite that
produced it. This script only joins them in a fixed order so a consumer (the
loader, the reviewer, the trainer) can point at one path, and refuses to write
if a rowId or an X repeats across the inputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_ORDER = [
    "train13r",
    "batch1",
    "batch2",
    "batch3",
    "batch4",
    "batch5",
    "batch6",
]


def read(path: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{number}: not JSON: {exc}") from exc
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows-dir", default="rows")
    parser.add_argument("--order", nargs="*", default=DEFAULT_ORDER)
    parser.add_argument("--out", required=True)
    parser.add_argument("--provenance-out", required=True)
    parser.add_argument("--report-out", required=True)
    args = parser.parse_args(argv)

    root = Path(args.rows_dir)
    rows: list[dict] = []
    provenance: list[dict] = []
    per_file: dict[str, int] = {}
    for name in args.order:
        file_rows = read(root / f"{name}-candidates.jsonl")
        file_prov = read(root / f"{name}-provenance.jsonl")
        if len(file_rows) != len(file_prov):
            return _fail(f"{name}: {len(file_rows)} rows but {len(file_prov)} provenance entries")
        rows.extend(file_rows)
        provenance.extend(file_prov)
        per_file[name] = len(file_rows)

    problems = []
    row_ids = [row.get("rowId") for row in rows]
    if len(set(row_ids)) != len(row_ids):
        seen = set()
        for row_id in row_ids:
            if row_id in seen:
                problems.append(f"duplicate rowId: {row_id}")
            seen.add(row_id)
    x_digests: dict[str, str] = {}
    for entry in provenance:
        digest = entry.get("xSha256")
        if digest in x_digests:
            problems.append(f"duplicate X: {x_digests[digest]} and {entry.get('rowId')}")
        else:
            x_digests[digest] = entry.get("rowId")
    if problems:
        return _fail("; ".join(problems))

    counts = {"rows": len(rows), "skip": 0, "oneStep": 0, "twoStep": 0}
    classes: dict[str, int] = {}
    # rowClass lives in provenance, never in the row: the row keeps exactly the
    # nine fields the contract names, and the class is reviewer information.
    for row, entry in zip(rows, provenance):
        steps = len(row["y"]["steps"])
        if steps == 0:
            counts["skip"] += 1
        elif steps == 1:
            counts["oneStep"] += 1
        else:
            counts["twoStep"] += 1
        row_class = entry.get("rowClass", "?")
        classes[row_class] = classes.get(row_class, 0) + 1
    report = {
        "files": per_file,
        "rows": counts,
        "rowClasses": classes,
        "uniqueX": len(x_digests),
        "problems": problems,
    }
    write_json(Path(args.out), rows)
    write_json(Path(args.provenance_out), provenance)
    Path(args.report_out).write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


def write_json(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _fail(message: str) -> int:
    print(f"refused: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
