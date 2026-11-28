#!/usr/bin/env python3
"""Check declared experiment splits against the data on disk.

The registry (default tools/experiment_platform/splits.json) names each
dataset, its key field, its usage and whether it is still an independent
evaluation set. Pairs declare `disjoint`, `subset` or `report`; a violated
hard relation exits 1.

This is how a set that drove iterative fixes gets demoted to regression
instead of being re-labelled as generalization later.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_keys(path: Path, key: str) -> set[str]:
    if key == "list":
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(item) for item in data}
    if path.suffix == ".jsonl":
        rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8-sig").splitlines() if ln.strip()]
    else:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = data if isinstance(data, list) else data.get("rows", [])
    return {str(row[key]) for row in rows if isinstance(row, dict) and key in row}


def check(repo: Path, registry: dict) -> dict:
    sets = {}
    findings = []
    for spec in registry["sets"]:
        path = repo / spec["path"]
        if not path.exists():
            findings.append({"set": spec["name"], "error": "file missing"})
            continue
        keys = load_keys(path, spec.get("key", "id"))
        sets[spec["name"]] = {"keys": keys, "usage": spec.get("usage"),
                              "independent": spec.get("independent", False),
                              "uniqueKeys": len(keys), "path": spec["path"]}
    pairs = []
    for pair in registry.get("pairs", []):
        left, right = sets.get(pair["left"]), sets.get(pair["right"])
        if left is None or right is None:
            findings.append({"pair": [pair["left"], pair["right"]], "error": "set unavailable"})
            continue
        overlap = left["keys"] & right["keys"]
        expect = pair.get("expect", "report")
        ok = True
        if expect == "disjoint":
            ok = not overlap
        elif expect == "subset":
            ok = left["keys"] <= right["keys"]
        pairs.append({"pair": [pair["left"], pair["right"]], "expect": expect,
                      "overlap": len(overlap), "ok": ok, "note": pair.get("note", "")})
        if not ok:
            findings.append({"pair": [pair["left"], pair["right"]], "expect": expect,
                             "overlap": sorted(overlap)[:20]})
    return {"sets": {name: {k: v for k, v in s.items() if k != "keys"} for name, s in sets.items()},
            "pairs": pairs, "findings": findings, "failed": bool(findings)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--registry", default="tools/experiment_platform/splits.json")
    parser.add_argument("--out", default="artifacts/goal/platform/split-check.json")
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    registry = json.loads((repo / args.registry).read_text(encoding="utf-8"))
    report = check(repo, registry)
    out = repo / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{'pair':48} {'expect':8} {'overlap':>7} ok")
    for pair in report["pairs"]:
        print(f"{pair['pair'][0] + ' / ' + pair['pair'][1]:48} {pair['expect']:8} {pair['overlap']:7} {pair['ok']}")
    for finding in report["findings"]:
        print(f"FAIL {finding}")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
