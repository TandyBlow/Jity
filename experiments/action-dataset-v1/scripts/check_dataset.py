"""Independent re-verification of a generated row file.

This script trusts nothing that `build_rows.py` wrote. It:

  1. reloads the frozen criterion, label vocabulary and allowed-goal list and
     re-checks their hashes;
  2. re-runs the row schema and dataset checks;
  3. re-resolves every row's base state from its recorded provenance, re-checks
     the base file's sha256, and **replays** the recorded transform list to
     re-project X (a row whose state cannot be rebuilt fails);
  4. renders every row through 04's frozen loader serializer (imported from
     its own file, digest recorded) and re-checks that each step's object
     resolves to a candidate index — the training-time pointer path;
  5. re-checks that each row's goals are inside the allowed TRAIN list;
  6. reports the measured class mix (skip ratio overall and per class), group
     and predicate coverage and the loader-rendered input length.

Usage:
    python -X utf8 experiments/action-dataset-v1/scripts/check_dataset.py \
        --rows .../rows/train-candidates-v1.jsonl \
        --provenance .../rows/provenance-v1.jsonl \
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
from tools.project_x import goal_ids, project_x  # noqa: E402

LABELS = Path("D:/others/Jity/.local/parallel-local-game/results/action-dataset-20261111/labels-v1.json")
CRITERION = Path("D:/others/Jity/.local/parallel-local-game/results/action-dataset-20261111/criterion.txt")
EXPECTED_CRITERION = "56092d0c6e5ba0a03e8dc4096e3edb1bb2e4123b351b9f14d6884afdea11d21c"
EXPECTED_LABELS = "41372ab43bc16ed90dd488bf334a562f6cec44e5633f07ba01d2833f85bb1829"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def replay(record: dict, snapshots: Path) -> dict:
    """Rebuild the row's X from its recorded base and transforms."""
    base = record["base"]
    if base["kind"] == "world-s0":
        path = WORKTREE / base["file"]
        state = json.loads(path.read_text(encoding="utf-8"))
        meta = {"kind": "world-s0", "file": base["file"], "sha256": provenance.sha256_file(path)}
    elif base["kind"] == "snapshot":
        path = snapshots / Path(base["file"]).name
        payload = provenance.read_json(path)
        state = payload["state"]
        meta = {
            "kind": "snapshot",
            "file": base["file"],
            "sha256": provenance.sha256_file(path),
            "episode": payload.get("provenance"),
        }
    else:
        raise ValueError(f"unknown base kind {base['kind']!r}")
    built_state, _, events = cases.project_case_state(state, meta, record["characterId"], record["transformsInput"])
    return project_x(built_state, record["characterId"], events=events)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--allowed-goals", type=Path, required=True)
    parser.add_argument("--snapshots", type=Path, default=HERE / "snapshots")
    parser.add_argument("--loader-serializer", type=Path, default=loader.DEFAULT_SERIALIZER)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    failures: list[dict] = []
    criterion_hash = provenance.sha256_file(CRITERION)
    labels_hash = provenance.sha256_file(LABELS)
    if criterion_hash != EXPECTED_CRITERION:
        failures.append({"check": "criterion hash", "expected": EXPECTED_CRITERION, "actual": criterion_hash})
    if labels_hash != EXPECTED_LABELS:
        failures.append({"check": "labels hash", "expected": EXPECTED_LABELS, "actual": labels_hash})
    labels = schema.load_labels(LABELS)
    allowed_payload = json.loads(args.allowed_goals.read_text(encoding="utf-8"))
    allowed = set(allowed_payload["goalIds"])
    serializer = loader.load_serializer(args.loader_serializer)

    rows = read_jsonl(args.rows)
    records = read_jsonl(args.provenance)
    by_id = {record["rowId"]: record for record in records}
    if len(by_id) != len(records):
        failures.append({"check": "provenance duplicate rowId", "count": len(records)})
    if sorted(by_id) != sorted(row["rowId"] for row in rows):
        failures.append({"check": "row/provenance id sets differ"})

    dataset_report = schema.validate_dataset(rows, labels)
    for problem in dataset_report["problems"]:
        failures.append({"check": "schema", **problem})

    replayed = 0
    rendered_chars: list[int] = []
    for row in rows:
        record = by_id.get(row["rowId"])
        if record is None:
            failures.append({"check": "missing provenance", "rowId": row["rowId"]})
            continue
        try:
            rebuilt = replay(record, args.snapshots)
        except Exception as error:  # noqa: BLE001 - report every failure
            failures.append({"check": "replay", "rowId": row["rowId"], "error": str(error)})
            continue
        if rebuilt != row["x"]:
            failures.append({"check": "replay mismatch", "rowId": row["rowId"]})
            continue
        replayed += 1
        recorded_sha = record.get("xSha256")
        actual_sha = provenance.sha256_bytes(json.dumps(row["x"], ensure_ascii=False, sort_keys=True).encode("utf-8"))
        if recorded_sha != actual_sha:
            failures.append({"check": "x sha", "rowId": row["rowId"], "recorded": recorded_sha, "actual": actual_sha})
        outside = sorted(set(goal_ids(row["x"])) - allowed)
        if outside:
            failures.append({"check": "held-out goal in X", "rowId": row["rowId"], "goals": outside})
        if not row["x"]["goals"]:
            failures.append({"check": "no pending goal", "rowId": row["rowId"]})
        try:
            rendered = loader.render_row(serializer, row)
        except loader.LoaderError as error:
            failures.append({"check": "loader render", "rowId": row["rowId"], "error": str(error)})
            continue
        rendered_chars.append(rendered["chars"])
        if rendered["serializerSha256"] != record["loaderSerializer"]["sha256"]:
            failures.append(
                {
                    "check": "loader serializer drift",
                    "rowId": row["rowId"],
                    "recorded": record["loaderSerializer"]["sha256"],
                    "actual": rendered["serializerSha256"],
                }
            )
        for step in row["y"]["steps"]:
            try:
                loader.object_index(serializer, row, step)
            except Exception as error:  # noqa: BLE001
                failures.append({"check": "object pointer", "rowId": row["rowId"], "error": str(error)})

    def ratio(subset: list[dict]) -> float:
        if not subset:
            return 0.0
        return round(sum(1 for row in subset if not row["y"]["steps"]) / len(subset), 4)

    classes: dict[str, int] = {}
    for record in records:
        classes[record["rowClass"]] = classes.get(record["rowClass"], 0) + 1
    sizes = sorted(rendered_chars)
    report = {
        "rows": dataset_report["counts"],
        "uniqueX": len({provenance.sha256_bytes(json.dumps(row["x"], ensure_ascii=False, sort_keys=True).encode("utf-8")) for row in rows}),
        "skipRatio": dataset_report["skipRatio"],
        "skipRatioBySource": {
            source: ratio([row for row in rows if row["source"] == source]) for source in sorted({row["source"] for row in rows})
        },
        "rowClasses": classes,
        "groups": dataset_report["groups"],
        "predicatesUsed": dataset_report["predicatesUsed"],
        "predicatesUnused": dataset_report["predicatesUnused"],
        "actors": dataset_report["actors"],
        "sources": dataset_report["sources"],
        "baseKinds": {kind: sum(1 for record in records if record["base"]["kind"] == kind) for kind in ("world-s0", "snapshot")},
        "replayedRows": replayed,
        "loader": {
            "version": serializer.SERIALIZER_VERSION,
            "sha256": serializer.serializer_digest(),
            "chars": {
                "min": sizes[0] if sizes else 0,
                "p50": sizes[len(sizes) // 2] if sizes else 0,
                "p95": sizes[min(len(sizes) - 1, int(0.95 * len(sizes)))] if sizes else 0,
                "max": sizes[-1] if sizes else 0,
            },
        },
        "frozen": {
            "criterionSha256": criterion_hash,
            "labelsSha256": labels_hash,
            "allowedGoalCount": len(allowed),
            "splitSha256": allowed_payload.get("splitSha256"),
        },
        "failures": failures,
    }
    if args.out:
        provenance.write_json(args.out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
