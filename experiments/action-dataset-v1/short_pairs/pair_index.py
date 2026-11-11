"""Build the renderer-independent pair index for the 13-way short-pair set.

The index fixes *which* decisions exist and what each one means; it does not
contain any model text. Text comes only from 04's `pairwise_serialize.py`, so
this file can be built and verified before that serializer exists.

For every frozen row and every step of that row there are 13 pairs: one per
candidate group in the frozen order, exactly one of them positive. A two-step
row therefore contributes 26 pairs (13 for step 0, 13 for step 1), which is
where the 390 second-step pairs come from.

Nothing here reads `yRationale` or `skipReason`: the label is `yGroup` and the
step's action, both already frozen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROWS_SHA256 = "cb4676b3eb74945331f73ee8855be300455c9e11db261c288d7534c7b02ef188"
GROUPS = [
    "感知",
    "移动",
    "战斗",
    "援助",
    "请求",
    "胁迫",
    "言语",
    "算计",
    "情绪",
    "物品",
    "身体",
    "立场",
]
SKIP_GROUP = "不动"
CANDIDATES = GROUPS + [SKIP_GROUP]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def candidate_name(row: dict, object_id: str | None) -> str | None:
    if not object_id:
        return None
    for entry in row["x"]["candidates"]:
        if entry["id"] == object_id:
            return entry["name"]
    return None


def conflict_key(row: dict) -> str:
    """Rows that agree on everything except the timestamp are the same decision."""
    import copy
    import re

    x = copy.deepcopy(row["x"])
    x["place"] = re.sub(r"；时间=[^；]*", "", x["place"])
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--resolution", default=None, help="JSON {excludeRowIds: [...], reason: ..., decidedBy: ...}")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)

    rows = read_jsonl(Path(args.rows))
    digest = hashlib.sha256(Path(args.rows).read_bytes()).hexdigest()
    if digest != ROWS_SHA256:
        raise SystemExit(f"rows digest {digest} is not the frozen 300-row file")

    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    group_order = [group["group"] for group in labels["groups"]]
    if group_order != GROUPS:
        raise SystemExit(f"label group order changed: {group_order}")

    # A decision is (row, step). Two steps of one row are different decisions
    # because the second one is shown the first step's 已做 line, so the conflict
    # key must include that line. Rows that are identical except for the clock
    # but still disagree on the same decision are frozen data conflicts.
    by_key: dict[str, list[tuple[str, int, str]]] = {}
    for row in rows:
        steps = row["y"]["steps"]
        if not steps:
            key = f"{conflict_key(row)}|s0|"
            by_key.setdefault(key, []).append((row["rowId"], 0, SKIP_GROUP))
            continue
        groups = [_group_of(step["action"], labels) for step in steps]
        for step_index, step in enumerate(steps):
            done = ""
            if step_index > 0:
                first = steps[0]
                done = f"{groups[0]}|{first['object']}"
            key = f"{conflict_key(row)}|s{step_index}|{done}"
            by_key.setdefault(key, []).append((row["rowId"], step_index, step["action"]))
    conflicts = {}
    for key, members in by_key.items():
        if len({action for _, _, action in members}) > 1:
            conflicts[key] = sorted(members)

    excluded: list[str] = []
    resolution = None
    if args.resolution:
        resolution = json.loads(Path(args.resolution).read_text(encoding="utf-8"))
        excluded = list(resolution.get("excludeRowIds") or [])
        for entry in resolution.get("excluded") or []:
            if isinstance(entry, dict) and entry.get("rowId"):
                excluded.append(str(entry["rowId"]))
            elif isinstance(entry, str):
                excluded.append(entry)
        unknown = sorted(set(excluded) - {row["rowId"] for row in rows})
        if unknown:
            raise SystemExit(f"resolution excludes unknown rows: {unknown}")

    open_conflict_rows = {row_id for members in conflicts.values() for row_id, _, _ in members}
    # Resolve each conflict as "the excluded side must leave every member group".
    unresolved = []
    for key, members in conflicts.items():
        kept = [member for member in members if member[0] not in excluded]
        if len({action for _, _, action in kept}) > 1:
            unresolved.append(sorted(kept))
    if unresolved:
        print(
            json.dumps(
                {
                    "status": "refused",
                    "reason": "frozen rows disagree on the same situation (identical X except time); "
                    "they must be excluded before any pair set is written",
                    "conflicts": unresolved,
                    "candidateRowsToExclude": sorted(open_conflict_rows),
                },
                ensure_ascii=False,
            )
        )
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    index: list[dict] = []
    row_meta: list[dict] = []
    per_group_positive = {group: 0 for group in CANDIDATES}
    per_group_pairs = {group: 0 for group in CANDIDATES}
    seen_rows: set[str] = set()

    for row in rows:
        row_id = row["rowId"]
        if row_id in excluded:
            continue
        if row_id in seen_rows:
            raise SystemExit(f"duplicate rowId in frozen file: {row_id}")
        seen_rows.add(row_id)
        steps = row["y"]["steps"]
        if not steps:
            if row["yGroup"] not in (SKIP_GROUP, "skip"):
                raise SystemExit(f"skip row {row_id} is not labelled 不动/skip")
            step_groups = [SKIP_GROUP]
            actions = [None]
            objects = [None]
        else:
            step_groups = [_group_of(step["action"], labels) for step in steps]
            actions = [step["action"] for step in steps]
            objects = [step["object"] for step in steps]
        for step_index in range(len(step_groups)):
            step_group = step_groups[step_index]
            first_group = step_groups[0]
            action = actions[step_index]
            object_id = objects[step_index]
            for candidate in CANDIDATES:
                positive = candidate == step_group
                pair = {
                    "pairId": f"{row_id}#s{step_index}#{CANDIDATES.index(candidate):02d}",
                    "rowId": row_id,
                    "stepIndex": step_index,
                    "stepCount": len(steps),
                    "candidateGroup": candidate,
                    "positive": positive,
                    "labelGroup": step_group,
                    "action": action,
                    "objectId": object_id,
                    "objectName": candidate_name(row, object_id),
                    "doneGroup": None if step_index == 0 else first_group,
                    "doneObjectId": None if step_index == 0 else objects[0],
                    "doneObjectName": None if step_index == 0 else candidate_name(row, steps[0]["object"]),
                    "characterId": row["characterId"],
                    "worldId": row["worldId"],
                    "rowSource": row["source"],
                }
                index.append(pair)
                per_group_pairs[candidate] += 1
                if positive:
                    per_group_positive[candidate] += 1
        row_meta.append(
            {
                "rowId": row_id,
                "characterId": row["characterId"],
                "worldId": row["worldId"],
                "source": row["source"],
                "rowClass": None,
                "stepCount": len(steps),
                "stepGroups": step_groups,
                "actions": actions,
                "objects": objects,
                "candidates": [
                    {
                        "id": entry["id"],
                        "name": entry["name"],
                        "type": entry["type"],
                        "place": entry.get("place"),
                        "source": entry.get("source"),
                    }
                    for entry in row["x"]["candidates"]
                ],
            }
        )

    # Every decision must have exactly one positive.
    decisions: dict[tuple[str, int], int] = {}
    for pair in index:
        key = (pair["rowId"], pair["stepIndex"])
        decisions[key] = decisions.get(key, 0) + (1 if pair["positive"] else 0)
    bad = [key for key, count in decisions.items() if count != 1]
    if bad:
        raise SystemExit(f"decisions without exactly one positive: {bad[:5]}")

    pair_ids = [pair["pairId"] for pair in index]
    if len(set(pair_ids)) != len(pair_ids):
        raise SystemExit("duplicate pairId")

    counts = {
        "rowsInFile": len(rows),
        "rowsUsed": len(seen_rows),
        "rowsExcluded": len(excluded),
        "decisions": len(decisions),
        "firstStepPairs": 13 * sum(1 for row in rows if row["rowId"] in seen_rows),
        "secondStepPairs": 13 * sum(1 for row in rows if row["rowId"] in seen_rows and len(row["y"]["steps"]) == 2),
        "pairs": len(index),
        "positives": sum(1 for pair in index if pair["positive"]),
        "perGroupPairs": per_group_pairs,
        "perGroupPositive": per_group_positive,
    }
    if counts["pairs"] != counts["firstStepPairs"] + counts["secondStepPairs"]:
        raise SystemExit("pair arithmetic does not add up")

    _write_jsonl(out_dir / "pairs-index.jsonl", index)
    _write_jsonl(out_dir / "rows-meta.jsonl", row_meta)
    report = {
        "kind": "pair-index (no model text)",
        "source": {"path": str(args.rows), "sha256": digest},
        "labels": {"path": str(args.labels), "sha256": hashlib.sha256(Path(args.labels).read_bytes()).hexdigest()},
        "groups": CANDIDATES,
        "conflicts": [members for _, members in sorted(conflicts.items())],
        "resolution": resolution,
        "counts": counts,
        "indexSha256": hashlib.sha256((out_dir / "pairs-index.jsonl").read_bytes()).hexdigest(),
        "notes": [
            "pairs here have no text; text is produced only by 04's pairwise serializer",
            "a decision is (rowId, stepIndex); each decision has 13 pairs and one positive",
            "the second step carries the first step's group and object as 已做, never its own label",
        ],
    }
    (out_dir / "index-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(report["counts"], ensure_ascii=False))
    return 0


def _group_of(action: str, labels: dict) -> str:
    for group in labels["groups"]:
        if action in group["predicates"]:
            return group["group"]
    raise SystemExit(f"action not in the frozen label groups: {action}")


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    raise SystemExit(main())
