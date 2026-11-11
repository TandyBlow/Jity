"""Turn the authored case catalog into rows plus per-row provenance.

The catalog is the only place a label is written. This script refuses to emit
a row when:

  - the actor has any pending goal outside the allowed TRAIN list;
  - the actor has no pending goal at all (the frozen criterion is "given what
    this character knows, what does he most likely do"; with no goal the row is
    not evidence for that question, and 01 rejected the earlier
    "finish every task, then call it skip" recipe);
  - the rationale references a goal the actor does not have;
  - a step's `action` is not one of the 115 fine predicates;
  - a step's `object` is not in that row's candidates (or null);
  - a skip row has no written reason, or a non-skip row carries one;
  - `刚才` reads like an engine log instead of something the actor perceives;
  - two rows carry the same X;
  - any transform fails its legality or state-invariant checks.

`rowClass` (A = the condition for the goal step is present, B = the label first
creates the condition, skip = no new action this beat) is authored per case and
recorded in provenance; it is not a row field and not a label rule.

Usage:
    python -X utf8 experiments/action-dataset-v1/scripts/build_rows.py \
        --catalog experiments/action-dataset-v1/cases \
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

from tools import cases, loader, provenance, schema  # noqa: E402
from tools.project_x import goal_ids  # noqa: E402

LABELS = Path("D:/others/Jity/.local/parallel-local-game/results/action-dataset-20261111/labels-v1.json")
CRITERION = Path("D:/others/Jity/.local/parallel-local-game/results/action-dataset-20261111/criterion.txt")
ROW_CLASSES = ("A", "B", "skip")


def load_catalog(paths: list[Path]) -> list[dict]:
    """Concatenate catalog files in the given order (directories expand sorted)."""
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("*.jsonl")))
        elif path.is_file():
            files.append(path)
        else:
            raise SystemExit(f"catalog missing: {path}")
    entries: list[dict] = []
    for path in files:
        if path.suffix == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entries.append(json.loads(line))
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entries.extend(payload["cases"] if isinstance(payload, dict) else payload)
    return entries


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
    parser.add_argument("--catalog", type=Path, nargs="+", required=True)
    parser.add_argument("--allowed-goals", type=Path, required=True)
    parser.add_argument("--snapshots", type=Path, default=HERE / "snapshots")
    parser.add_argument("--out", type=Path, default=HERE / "rows" / "train-candidates-v1.jsonl")
    parser.add_argument("--provenance-out", type=Path, default=HERE / "rows" / "provenance-v1.jsonl")
    parser.add_argument("--report-out", type=Path, default=HERE / "rows" / "report-v1.json")
    parser.add_argument("--worktree", type=Path, default=WORKTREE)
    parser.add_argument("--loader-serializer", type=Path, default=loader.DEFAULT_SERIALIZER)
    args = parser.parse_args()

    labels = schema.load_labels(LABELS)
    allowed_payload = json.loads(args.allowed_goals.read_text(encoding="utf-8"))
    allowed = set(allowed_payload["goalIds"])
    catalog = load_catalog(args.catalog)
    serializer = loader.load_serializer(args.loader_serializer)

    rows: list[dict] = []
    records: list[dict] = []
    failures: list[dict] = []
    seen_x: dict[str, str] = {}
    for index, case in enumerate(catalog, start=1):
        row_id = f"train13-{index:04d}"
        row_class = case.get("rowClass")
        try:
            if row_class not in ROW_CLASSES:
                raise cases.CaseError(f"rowClass must be one of {ROW_CLASSES}, got {row_class!r}")
            built = cases.build_case(case, args.worktree, args.snapshots, allowed)
            if not built["x"]["goals"]:
                raise cases.CaseError(
                    "actor has no pending goal; the earlier 'finish every task then skip' recipe is not accepted"
                )
            row = build_row(case, built, row_id, labels)
        except (cases.CaseError, ValueError) as error:
            failures.append({"caseId": case.get("caseId"), "error": str(error)})
            continue
        problems = schema.validate_row(row, labels)
        if problems:
            failures.append({"caseId": case.get("caseId"), "rowId": row_id, "problems": problems})
            continue
        try:
            rendered = loader.render_row(serializer, row)
        except loader.LoaderError as error:
            failures.append({"caseId": case.get("caseId"), "rowId": row_id, "error": str(error)})
            continue
        key = provenance.sha256_bytes(json.dumps(row["x"], ensure_ascii=False, sort_keys=True).encode("utf-8"))
        if key in seen_x:
            failures.append(
                {"caseId": case.get("caseId"), "rowId": row_id, "problems": [f"identical X to {seen_x[key]}"]}
            )
            continue
        seen_x[key] = row_id
        rows.append(row)
        record = {
            "rowId": row_id,
            "rowClass": row_class,
            "characterId": case["actor"],
            "goalsReferenced": case.get("goalsReferenced") or [],
            "judgmentBasis": case.get("judgmentBasis") or ["goal"],
            "xSha256": key,
            "loaderXSha256": provenance.sha256_bytes(rendered["text"].encode("utf-8")),
            "loaderXChars": rendered["chars"],
            "loaderSerializer": {
                "version": rendered["serializerVersion"],
                "sha256": rendered["serializerSha256"],
                "file": str(args.loader_serializer),
            },
            **built["provenance"],
        }
        records.append(record)

    report = schema.validate_dataset(rows, labels)
    classes = {"A": 0, "B": 0, "skip": 0}
    goal_class: dict[str, set[str]] = {}
    for record in records:
        classes[record["rowClass"]] = classes.get(record["rowClass"], 0) + 1
        for goal in record.get("goalsReferenced") or []:
            goal_class.setdefault(goal, set()).add(record["rowClass"])
    report.update(
        {
            "catalog": [str(path) for path in args.catalog],
            "catalogCases": len(catalog),
            "rowsWritten": len(rows),
            "failures": failures,
            "allowedGoals": {"count": len(allowed), "splitSha256": allowed_payload.get("splitSha256")},
            "labelVocabulary": {"file": str(LABELS), "sha256": provenance.sha256_file(LABELS)},
            "criterion": {"file": str(CRITERION), "sha256": provenance.sha256_file(CRITERION)},
            "rowClasses": classes,
            "goalCoverage": {
                "referenced": len(goal_class),
                "withoutA": sorted(allowed - {goal for goal, kinds in goal_class.items() if "A" in kinds}),
                "withoutB": sorted(allowed - {goal for goal, kinds in goal_class.items() if "B" in kinds}),
                "byGoal": {goal: sorted(kinds) for goal, kinds in sorted(goal_class.items())},
            },
            "byBase": {},
        }
    )
    for record in records:
        key = record["base"]["kind"]
        report["byBase"][key] = report["byBase"].get(key, 0) + 1

    if failures or report["problems"]:
        print(json.dumps({"failures": failures[:20], "problems": report["problems"][:20]}, ensure_ascii=False, indent=2))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline=chr(10)) as handle:
        for row in rows:
            handle.write(json.dumps({key: row[key] for key in schema.ROW_KEYS}, ensure_ascii=False) + "\n")
    with args.provenance_out.open("w", encoding="utf-8", newline=chr(10)) as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    provenance.write_json(args.report_out, report)
    print(json.dumps(
        {
            "rows": report["counts"],
            "skipRatio": report["skipRatio"],
            "rowClasses": classes,
            "groups": report["groups"],
            "sources": report["sources"],
            "predicatesUsed": report["predicatesUsed"],
            "goalsReferenced": report["goalCoverage"]["referenced"],
            "failures": len(failures),
            "problems": len(report["problems"]),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if not failures and not report["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
