"""Build pair-safe blind packs (v2) for r1 and T1. No inference, no re-judging.

Fixes the v1 defects found in review:
  * v1 shuffled the *codes* but kept the row order, so the two outputs of the same
    fact stayed adjacent; v2 shuffles the whole item list and rejects any layout
    that still has two neighbours sharing a fact.
  * v1 T1 items showed the full input, whose requirement clause differed between
    the baseline and the candidate, so the scheme was visible; v2 shows only the
    part before the requirement line (place / visible / scene / viewer / fact).

Output goes to `<run>/blind-v2/`, leaving the judged `blind/` packs untouched.
Nothing here is judged; this only prepares a cleaner pack for a future review.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

HERE = Path(__file__).resolve()
EXP = HERE.parents[1]
TREE = EXP.parents[3]
UNIT_FILE = TREE / "artifacts/world-components/n4-cf24-contract.jsonl"

BATCH = 10
BASE_SEED = 20261109
MAX_TRIES = 50


def latest(pattern: str) -> Path:
    runs = sorted((EXP / "artifacts/fact-wording").glob(pattern + "/*/raw.jsonl"))
    if not runs:
        raise SystemExit(f"no run for {pattern}")
    return runs[-1].parent


def strip_requirement(text: str) -> str:
    cut = text.find("要求：")
    return text[:cut].rstrip() if cut >= 0 else text.rstrip()


def facts_and_scenes() -> dict[str, dict]:
    units = {}
    for line in UNIT_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            u = json.loads(line)
            units[u["unitId"]] = u
    return units


def shuffle_no_adjacent(items: list[dict]) -> tuple[list[dict], int]:
    for seed in range(BASE_SEED, BASE_SEED + MAX_TRIES):
        order = list(items)
        random.Random(seed).shuffle(order)
        if all(order[i]["factId"] != order[i + 1]["factId"] for i in range(len(order) - 1)):
            return order, seed
    raise SystemExit("could not avoid adjacent same-fact items")


def write_pack(out: Path, name: str, rows: list[dict], seed: int) -> dict:
    items = []
    for i, row in enumerate(rows, start=1):
        items.append(dict(code=f"c{i:04d}", fact=row["fact"], scene=row["scene"], output=row["output"]))
    mapping = {it["code"]: row["meta"] for it, row in zip(items, rows)}
    batches = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]

    out.mkdir(exist_ok=True)
    for old in out.glob("batch-*.json"):
        old.unlink()
    for idx, batch in enumerate(batches, start=1):
        payload = dict(
            pack=f"{name}-batch-{idx:02d}",
            instruction="judge each output against its fact and scene only; "
                        "the requirement clause is withheld on purpose",
            items=batch,
        )
        (out / f"batch-{idx:02d}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "map.json").write_text(json.dumps(dict(seed=seed, batches=len(batches), mapping=mapping),
                                             ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    adjacency = sum(1 for i in range(len(rows) - 1) if rows[i]["factId"] == rows[i + 1]["factId"])
    (out / "index.json").write_text(json.dumps(dict(
        rows=len(items), batches=len(batches), batchSize=BATCH, seed=seed,
        requirementHidden=True, adjacentSameFact=adjacency,
    ), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return dict(rows=len(items), batches=len(batches), seed=seed, adjacentSameFact=adjacency)


def main() -> int:
    units = facts_and_scenes()

    r1_dir = latest("diagnostic-r1")
    r1_rows = [json.loads(line) for line in (r1_dir / "raw.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    r2_dir = latest("diagnostic-r2-cand-t1")
    r2_rows = [json.loads(line) for line in (r2_dir / "raw.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

    # r1: 170 rows, two arms per unit
    r1_items = []
    for row in r1_rows:
        unit = units[row["unitId"]]
        r1_items.append(dict(
            factId=row["unitId"], fact=unit["fact"], scene=strip_requirement(unit["input"]),
            output=row["text"],
            meta=dict(unitId=row["unitId"], arm=row["arm"], score=row["score"],
                      seconds=row["seconds"], stopReason=row["stopReason"]),
        ))
    r1_items, r1_seed = shuffle_no_adjacent(r1_items)
    r1_out = write_pack(r1_dir / "blind-v2", "cf24-r1-v2", r1_items, r1_seed)

    # T1: baseline greedy + candidate greedy, one row each; scene is identical after stripping
    r1_greedy = {(r["unitId"]): r for r in r1_rows if r["arm"] == "greedy"}
    r2_items = []
    for row in r2_rows:
        unit = units[row["unitId"]]
        scene = strip_requirement(unit["input"])
        r2_items.append(dict(
            factId=row["unitId"], fact=unit["fact"], scene=scene, output=r1_greedy[row["unitId"]]["text"],
            meta=dict(scheme="r1-greedy", unitId=row["unitId"], score=r1_greedy[row["unitId"]]["score"]),
        ))
        r2_items.append(dict(
            factId=row["unitId"], fact=unit["fact"], scene=scene, output=row["text"],
            meta=dict(scheme="T1-greedy", unitId=row["unitId"], score=row["score"]),
        ))
    r2_items, r2_seed = shuffle_no_adjacent(r2_items)
    r2_out = write_pack(r2_dir / "blind-v2", "cf24-t1-v2", r2_items, r2_seed)

    print("r1", r1_out)
    print("r2", r2_out)
    # self-check: the two rows of the same T1 unit must show the same scene
    scenes = {}
    for row in r2_items:
        scenes.setdefault(row["factId"], set()).add(row["scene"])
    print("T1 units with differing scenes:", sum(1 for v in scenes.values() if len(v) > 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
