#!/usr/bin/env python3
"""Render the three art-room points into C6's extended N4 input."""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from adapter import VERSION, build_fixture  # noqa: E402


def main() -> int:
    fixture_path = pathlib.Path(
        sys.argv[1] if len(sys.argv) > 1
        else HERE / "fixtures" / "art-room-three-points.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    results = build_fixture(fixture)

    out_dir = HERE / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "version": VERSION,
        "fixture": fixture_path.name,
        "points": [],
    }
    for result in results:
        path = out_dir / f"{result['pointId']}.txt"
        path.write_text(result["input"], encoding="utf-8")
        report["points"].append({
            "pointId": result["pointId"],
            "file": path.name,
            "sha256": result["sha256"],
            "diagnostics": result["diagnostics"],
        })
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for row in report["points"]:
        print(f"{row['pointId']}  {row['sha256'][:12]}  {row['file']}"
              f"  diagnostics={len(row['diagnostics'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
