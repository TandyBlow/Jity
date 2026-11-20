# -*- coding: utf-8 -*-
"""Build and freeze final-batch-v1.

The batch is authored by 01 and frozen before any candidate output exists, so
01 recuses from reviewing it; 05 reviews it first, 03 only if 05 is conflicted.
Build steps:

  1. build one settled-input case per authored scene from the static world;
  2. leak check: no 12-character run may be shared with the dev package, the
     71-row corpus, the old 199 rows or the 05 tide scenes;
  3. write cases.jsonl and a manifest with hashes of the world, the sources
     used for the leak check and this script.
"""
import datetime as dt
import hashlib
import io
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WT = HERE.parents[2]
sys.path.insert(0, str(WT / "experiments/narration-quality/corpus-short/authored"))
from build_authored import build_row  # noqa: E402

SHORT_ROWS = WT / "experiments/narration-quality/corpus-short/rows.jsonl"
DEV_CASES = WT / "experiments/narration-quality/dev-package-v1/cases.jsonl"
FROZEN = pathlib.Path(
    "D:/others/Jity/.local/world-components-worktree/experiments/world-components/narration-dataset-v1/rows-xy.jsonl"
)
TIDE = pathlib.Path(
    "D:/others/Jity/.local/parallel-local-game/worktrees/05-kernel/experiments/narration-quality/corpus-scenes/generated/rows.jsonl"
)
WORLD = WT / "frontend/public/worlds/dragon-raja-free-day.world.json"

WINDOW = 12


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runs(text, size=WINDOW):
    clean = "".join(ch for ch in text if ch.strip())
    return {clean[index:index + size] for index in range(0, max(0, len(clean) - size + 1))}


def main():
    scenes_doc = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))
    world = json.loads(WORLD.read_text(encoding="utf-8"))
    if sha(WORLD) != scenes_doc["world"]["worldSha256"]:
        raise SystemExit("world SHA mismatch")

    cases = []
    for scene in scenes_doc["scenes"]:
        row = build_row(world, scene, scenes_doc["world"])
        cases.append({
            "caseId": row["id"],
            "category": scene["categories"][0],
            "worldFamily": row["worldFamily"],
            "source": {
                "kind": "final-batch-authored",
                "file": "worktrees/01-input/experiments/narration-quality/final-batch-v1/scenes.json",
                "worldSha256": scenes_doc["world"]["worldSha256"],
                "author": "01-input",
                "independence": "final_batch_authored_by_01",
            },
            "viewpoint": row["input"]["视角"],
            "input": row["input"],
            "requiredFacts": scene["requiredFacts"],
            "licensedEntities": sorted(
                list(row["input"]["上回合状态"].get("人物", {})) +
                list(row["input"]["上回合状态"].get("地点", {})) +
                list(row["input"]["上回合状态"].get("物品", {}))
            ),
            "priorTexts": [],
            "reference": {
                "text": row["targetText"],
                "author": "01-input",
                "status": "final_batch_reference",
                "reviewerRecusal": "01 authored this reference and must not be its independent reviewer",
            },
            "notes": scene["notes"],
        })

    # Leak check against every public source a candidate may have seen.
    known = []
    for line in SHORT_ROWS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            known.append(("corpus-short:" + record["id"], record["targetText"]))
    for line in DEV_CASES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            known.append(("dev-package:" + record["caseId"], record["reference"]["text"]))
    for path, label in ((FROZEN, "frozen-199"), (TIDE, "tide-05")):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                text = record.get("y") or record.get("targetText") or ""
                known.append((label + ":" + record["id"], text))

    leaks = []
    for case in cases:
        fresh = runs(case["reference"]["text"])
        for label, text in known:
            overlap = fresh & runs(text)
            if overlap:
                leaks.append({"caseId": case["caseId"], "against": label, "sample": sorted(overlap)[0]})

    manifest = {
        "batch": "narration-final-batch-v1",
        "frozenAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "owner": "01-input",
        "status": "frozen_before_candidate_output",
        "purpose": "Independent final batch for model comparison. Authored and frozen before lanes 11/12 produced any output; no candidate has seen it.",
        "caseCount": len(cases),
        "categories": sorted({case["category"] for case in cases}),
        "independence": {
            "author": "01-input",
            "reviewers": {"first": "05-kernel", "second": "03-actions"},
            "recusal": "01 authored every input and reference here, so 01 does not review this batch. 05 must state it did not write, tune for or train on these cases; 03 only if 05 is conflicted. row-0188 stays excluded everywhere.",
            "notUsableAs": "not a development package; must not be published to lanes that are still training or tuning",
        },
        "inputs": {
            "world": {"path": str(WORLD), "sha256": sha(WORLD)},
            "scenes": {"path": str(HERE / "scenes.json"), "sha256": sha(HERE / "scenes.json")},
            "leakCheckSources": [
                {"path": str(SHORT_ROWS), "sha256": sha(SHORT_ROWS)},
                {"path": str(DEV_CASES), "sha256": sha(DEV_CASES)},
                *([{"path": str(FROZEN), "sha256": sha(FROZEN)}] if FROZEN.exists() else []),
                *([{"path": str(TIDE), "sha256": sha(TIDE)}] if TIDE.exists() else []),
            ],
        },
        "leakCheck": {"window": WINDOW, "leaks": leaks, "clean": not leaks},
        "cases": [
            {
                "caseId": case["caseId"],
                "inputSha256": hashlib.sha256(json.dumps(case["input"], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
                "referenceSha256": hashlib.sha256(case["reference"]["text"].encode("utf-8")).hexdigest(),
            }
            for case in cases
        ],
    }

    with io.open(HERE / "cases.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")
    manifest["files"] = {"cases.jsonl": sha(HERE / "cases.jsonl")}
    with io.open(HERE / "manifest.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print("cases", len(cases), "clean", manifest["leakCheck"]["clean"], "leaks", len(leaks))
    for leak in leaks[:10]:
        print("  LEAK", leak["caseId"], "vs", leak["against"], leak["sample"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
