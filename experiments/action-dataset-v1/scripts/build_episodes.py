"""Extract committed point states from real product evidence into snapshots.

Usage (from the worktree root):

    python -X utf8 experiments/action-dataset-v1/scripts/build_episodes.py \
        --evidence-dir ../../results/product/evidence

What it does:
  1. scans every *.json under the evidence directory;
  2. finds every transport record with pointStates/points;
  3. keeps one file per distinct world state (sha256 of a stable byte form);
  4. records provenance (evidence file + sha256, JSON pointer, point/round ids,
     the product's own stateDigest) and every duplicate location;
  5. re-projects X for all 14 characters and checks that no 8-character window
     of that run's narration text appears in the rendered input;
  6. writes snapshots/index.json with the measured counts.

The narration texts themselves are not written anywhere; only the overlap
result and the narration count are kept.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from tools import provenance, state_view  # noqa: E402
from tools.project_x import SERIALIZER_VERSION, project_x, serialize_x  # noqa: E402

DEFAULT_EVIDENCE = Path("D:/others/Jity/.local/parallel-local-game/results/product/evidence")
INDEX_SCHEMA = "action-dataset-snapshot-index-v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--out", type=Path, default=HERE / "snapshots")
    args = parser.parse_args()

    episodes = provenance.extract_episodes(args.evidence_dir)
    if not episodes:
        print(f"no transport records found under {args.evidence_dir}", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    index_entries = []
    leaks = 0
    for episode in episodes:
        state = episode["state"]
        digest = episode["provenance"]["snapshotSha256"]
        narrations = episode.pop("narrationTexts", [])
        for actor_id in sorted(state["characters"]):
            x = project_x(state, actor_id)
            check = provenance.narration_leak_check(narrations, provenance.string_values(x), state)
            if check["overlap"]:
                leaks += 1
                print(f"PROSE LEAK {digest[:12]} actor={actor_id} sample={check['sample']!r}", file=sys.stderr)
        snapshot_path = args.out / f"{digest[:16]}.json"
        provenance.write_json(snapshot_path, episode)
        goal_ids = sorted(
            {
                str(task["id"])
                for character in state["characters"].values()
                for task in character["tasks"].values()
                if task.get("status") == "pending"
            }
        )
        index_entries.append(
            {
                "snapshotSha256": digest,
                "file": f"{digest[:16]}.json",
                "worldId": episode["provenance"]["worldId"],
                "protagonistId": episode["provenance"]["protagonistId"],
                "time": episode["provenance"]["time"],
                "pointId": episode["provenance"]["pointId"],
                "pointSequence": episode["provenance"]["pointSequence"],
                "pointTrigger": episode["provenance"]["pointTrigger"],
                "roundId": episode["provenance"]["roundId"],
                "evidenceFile": episode["provenance"]["evidenceFile"],
                "pointer": episode["provenance"]["pointer"],
                "recordedStateDigest": episode["provenance"]["recordedStateDigest"],
                "duplicateLocations": len(episode["alsoIn"]),
                "characters": len(state["characters"]),
                "items": len(state["items"]),
                "locations": len(state["locations"]),
                "roomsOccupied": len({state_view.room_of(state, cid) for cid in state["characters"]}),
                "pendingGoalIds": goal_ids,
                "narrationProseOverlap": leaks,
            }
        )

    index = {
        "schema": INDEX_SCHEMA,
        "serializerVersion": SERIALIZER_VERSION,
        "evidenceDir": str(args.evidence_dir),
        "episodeCount": len(index_entries),
        "proseLeakRows": leaks,
        "episodes": sorted(index_entries, key=lambda entry: entry["snapshotSha256"]),
    }
    provenance.write_json(args.out / "index.json", index)
    print(json.dumps(
        {
            "episodes": index["episodeCount"],
            "proseLeakRows": leaks,
            "worlds": sorted({entry["worldId"] for entry in index_entries}),
            "distinctRooms": sorted(
                {
                    state_view.location_name(
                        provenance.read_json(args.out / entry["file"])["state"],
                        state_view.room_of(provenance.read_json(args.out / entry["file"])["state"], cid),
                    )
                    for entry in index_entries
                    for cid in provenance.read_json(args.out / entry["file"])["state"]["characters"]
                }
            ),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if leaks == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
