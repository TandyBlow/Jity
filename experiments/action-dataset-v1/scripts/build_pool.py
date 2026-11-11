"""Build the X-only candidate pool from real evidence snapshots.

The pool is not training data: it has no `y`. It exists so that the supply of
real-provenance situations is measured before any label is written, and so
that 01's allowed-goal list can be applied mechanically.

Only characters whose every pending goal is in the allowed TRAIN list are
included. A held-out character may still appear inside another row's `在场`
list as scenery (their goals never appear anywhere in X), which is recorded in
the summary rather than hidden.

Usage:
    python -X utf8 experiments/action-dataset-v1/scripts/build_pool.py \
        --allowed-goals ../../results/action-dataset-20261111/01-train-goals-for-13.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from tools import cases, provenance  # noqa: E402
from tools.project_x import (  # noqa: E402
    SERIALIZER_PROFILES,
    SERIALIZER_VERSION,
    candidate_ids,
    project_x,
    serialize_report,
    serialize_x,
)
from tools.state_view import canonical_bytes, entity_name, position_label, room_of  # noqa: E402

POOL_SCHEMA = "action-dataset-pool-v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshots", type=Path, default=HERE / "snapshots")
    parser.add_argument("--out", type=Path, default=HERE / "pool")
    parser.add_argument("--allowed-goals", type=Path, required=True)
    args = parser.parse_args()

    allowed_payload = json.loads(args.allowed_goals.read_text(encoding="utf-8"))
    allowed = set(allowed_payload["goalIds"])
    index = provenance.read_json(args.snapshots / "index.json")

    rows = []
    skipped_actor = {}
    situation_keys: dict[str, str] = {}
    for entry in index["episodes"]:
        snapshot = provenance.read_json(args.snapshots / entry["file"])
        state = snapshot["state"]
        provenance_meta = snapshot["provenance"]
        events = cases.events_from_committed_deltas(state, provenance_meta.get("entityDeltas"))
        for actor_id in sorted(state["characters"]):
            pending = {
                str(task["id"])
                for task in state["characters"][actor_id]["tasks"].values()
                if task.get("status") == "pending"
            }
            outside = sorted(pending - allowed)
            if outside:
                skipped_actor[actor_id] = sorted(set(skipped_actor.get(actor_id, [])) | set(outside))
                continue
            x = project_x(state, actor_id, events=events)
            rendered = serialize_x(x)
            row = {
                "poolId": f"{entry['snapshotSha256'][:10]}-{actor_id}",
                "source": "evidence-snapshot",
                "worldId": entry["worldId"],
                "characterId": actor_id,
                "x": x,
                "xSha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
                "xChars": len(rendered),
                "goalsInX": sorted(goal["id"] for goal in x["goals"]),
                "candidates": candidate_ids(x),
                "episode": {
                    "snapshotSha256": entry["snapshotSha256"],
                    "file": entry["file"],
                    "pointId": entry["pointId"],
                    "pointSequence": entry["pointSequence"],
                    "evidenceFile": entry["evidenceFile"],
                    "pointer": entry["pointer"],
                    "time": entry["time"],
                    "duplicateLocations": entry["duplicateLocations"],
                },
                "justNowEvents": len(x["justNow"]),
            }
            situation = dict(x)
            situation["place"] = {key: value for key, value in x["place"].items() if key != "time"}
            situation_keys.setdefault(hashlib.sha256(canonical_bytes(situation)).hexdigest(), row["poolId"])
            rows.append(row)

    rows.sort(key=lambda row: (row["episode"]["time"], row["characterId"], row["poolId"]))
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "candidates.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    profiles = {}
    for profile in SERIALIZER_PROFILES:
        measured = [serialize_report(row["x"], profile=profile) for row in rows]
        sizes = sorted(item["chars"] for item in measured)
        clipped: dict[str, int] = {}
        for item in measured:
            for field, count in item["clipped"].items():
                clipped[field] = clipped.get(field, 0) + count
        profiles[profile] = {
            "charsMin": sizes[0] if sizes else 0,
            "charsP50": sizes[len(sizes) // 2] if sizes else 0,
            "charsP95": sizes[min(len(sizes) - 1, int(0.95 * len(sizes)))] if sizes else 0,
            "charsMax": sizes[-1] if sizes else 0,
            "clippedFieldCounts": dict(sorted(clipped.items())),
            "fitsFiveTwelveCharBudget": bool(sizes) and sizes[-1] <= 512,
        }

    summary = {
        "schema": POOL_SCHEMA,
        "serializerVersion": SERIALIZER_VERSION,
        "allowedGoals": {
            "file": str(args.allowed_goals),
            "count": len(allowed),
            "version": allowed_payload.get("version"),
            "splitSha256": allowed_payload.get("splitSha256"),
        },
        "poolRows": len(rows),
        "uniqueRenderedX": len({row["xSha256"] for row in rows}),
        "uniqueSituations": len(situation_keys),
        "actors": sorted({row["characterId"] for row in rows}),
        "excludedActors": {actor: goals for actor, goals in sorted(skipped_actor.items()) if actor not in {row["characterId"] for row in rows}},
        "rooms": sorted({row["x"]["place"]["name"] for row in rows}),
        "withRecentEvents": sum(1 for row in rows if row["justNowEvents"]),
        "xChars": {"min": profiles["full"]["charsMin"], "p50": profiles["full"]["charsP50"], "p95": profiles["full"]["charsP95"], "max": profiles["full"]["charsMax"]},
        "profiles": profiles,
        "goalsCovered": sorted({goal for row in rows for goal in row["goalsInX"]}),
        "episodes": [
            {
                "snapshotSha256": entry["snapshotSha256"],
                "pointId": entry["pointId"],
                "time": entry["time"],
                "evidenceFile": entry["evidenceFile"],
                "duplicateLocations": entry["duplicateLocations"],
            }
            for entry in index["episodes"]
        ],
        "notDone": [
            "no y labels yet: this file is a candidate pool, not training data",
            "token length is not measured (the MiniRBT tokenizer is not available in this lane); only character length is measured, which is an upper bound for Chinese text",
        ],
    }
    provenance.write_json(args.out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
