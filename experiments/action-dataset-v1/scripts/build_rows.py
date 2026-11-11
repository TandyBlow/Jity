"""Turn the authored case catalog into rows plus per-row provenance.

The catalog is the only place a label is written. This script refuses to emit
a row when:

  - the actor has any pending goal outside the allowed TRAIN list;
  - the rationale references a goal the actor does not have;
  - a step's `action` is not one of the 115 fine predicates;
  - a step's `object` is not in that row's candidates (or null);
  - a skip row has no written reason, or a non-skip row carries one;
  - two rows serialize to the same X;
  - any transform fails its legality or state-invariant checks.

Usage:
    python -X utf8 experiments/action-dataset-v1/scripts/build_rows.py \
        --catalog experiments/action-dataset-v1/cases/catalog-v1.json \
        --allowed-goals ../../results/action-dataset-20261111/01-train-goals-for-13.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
WORKTREE = HERE.parents[1]
sys.path.insert(0, str(HERE))

from tools import cases, provenance, schema  # noqa: E402
from tools.project_x import serialize_report  # noqa: E402

LABELS = Path("D:/others/Jity/.local/parallel-local-game/results/action-dataset-20261111/labels-v1.json")
CRITERION = Path("D:/others/Jity/.local/parallel-local-game/results/action-dataset-20261111/criterion.txt")


def load_catalog(path: Path) -> list[dict]:
    if not path.is_file():
        raise SystemExit(f"catalog missing: {path}")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["cases"] if isinstance(payload, dict) else payload


def build_row(case: dict, built: dict, row_id: str, labels: dict) -> dict:
    x = built["x"]
    steps = case.get("steps")
    if steps is None:
        raise SystemExit(f"case {case['caseId']} has no steps field")
    group = schema.SKIP_GROUP if not steps else labels["groupOf"].get(steps[0]["action"])
    return {
        "rowId": row_id,
        "source": "constructed" if case["base"].startswith("s0") or case.get("transforms") else "evidence-snapshot",
        "worldId": built["state"]["worldId"],
        "characterId": case["actor"],
        "x": x,
        "y": {"steps": steps},
        "yGroup": group,
        "yRationale": case["rationale"],
        "labelSource": "builder-judgment",
        "skipReason": case.get("skipReason"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--allowed-goals", type=Path, required=True)
    parser.add_argument("--snapshots", type=Path, default=HERE / "snapshots")
    parser.add_argument("--out", type=Path, default=HERE / "rows" / "train-candidates-v1.jsonl")
    parser.add_argument("--provenance-out", type=Path, default=HERE / "rows" / "provenance-v1.jsonl")
    parser.add_argument("--report-out", type=Path, default=HERE / "rows" / "report-v1.json")
    parser.add_argument("--worktree", type=Path, default=WORKTREE)
    args = parser.parse_args()

    labels = schema.load_labels(LABELS)
    allowed_payload = json.loads(args.allowed_goals.read_text(encoding="utf-8"))
    allowed = set(allowed_payload["goalIds"])
    catalog = load_catalog(args.catalog)

    rows: list[dict] = []
    records: list[dict] = []
    failures: list[dict] = []
    for index, case in enumerate(catalog, start=1):
        row_id = f"train13-{index:04d}"
        try:
            built = cases.build_case(case, args.worktree, args.snapshots, allowed)
            row = build_row(case, built, row_id, labels)
        except (cases.CaseError, ValueError) as error:
            failures.append({"caseId": case.get("caseId"), "error": str(error)})
            continue
        problems = schema.validate_row(row, labels)
        if problems:
            failures.append({"caseId": case.get("caseId"), "rowId": row_id, "problems": problems})
            continue
        row["rowId"] = row_id
        rows.append(row)
        record = {"rowId": row_id, **built["provenance"], "criteria": str(CRITERION)}
        record["xSha256"] = provenance.sha256_bytes(serialize_report(row["x"], profile="full")["text"].encode("utf-8"))
        records.append(record)

    report = schema.validate_dataset(rows, labels)
    report.update(
        {
            "catalog": str(args.catalog),
            "catalogCases": len(catalog),
            "rowsWritten": len(rows),
            "failures": failures,
            "allowedGoals": {"count": len(allowed), "splitSha256": allowed_payload.get("splitSha256")},
            "labelVocabulary": {"file": str(LABELS), "sha256": provenance.sha256_file(LABELS)},
            "criterion": {"file": str(CRITERION), "sha256": provenance.sha256_file(CRITERION)},
            "byBase": {},
        }
    )
    for record in records:
        key = record["base"]["kind"]
        report["byBase"][key] = report["byBase"].get(key, 0) + 1

    if failures or report["problems"]:
        print(json.dumps({"failures": failures[:20], "problems": report["problems"][:20]}, ensure_ascii=False, indent=2))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with args.provenance_out.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    provenance.write_json(args.report_out, report)
    print(json.dumps(
        {
            "reads": report["counts"],
            "skipRatio": report["skipRatio"],
            "groups": report["groups"],
            "sources": report["sources"],
            "predicatesUsed": report["predicatesUsed"],
            "failures": len(failures),
            "problems": len(report["problems"]),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if not failures and not report["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
