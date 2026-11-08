"""Build the blind judging pack from a diagnostic run (protocol v3 §3).

Input : artifacts/fact-wording/diagnostic-r1/<runId>/raw.jsonl
Output: artifacts/fact-wording/diagnostic-r1/<runId>/blind/
          batch-01.json ...   (<=10 items each, shuffled with a fixed seed)
          map.json            (code -> unitId, arm, score, seconds, stopReason)
          index.json          (counts, seed, hashes)

The batch files deliberately omit arm names, scores, timings, stop reasons, unitId
and any archived verdict. The mapping must not be opened while judging.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EXPERIMENT = HERE.parents[1]
TREE = HERE.parents[5]
UNIT_FILE = TREE / "artifacts/world-components/n4-cf24-contract.jsonl"
SEED = 20261108
BATCH = 10


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    runs = sorted((EXPERIMENT / "artifacts/fact-wording/diagnostic-r1").glob("*/raw.jsonl"))
    if not runs:
        raise SystemExit("no diagnostic run found")
    run_dir = runs[-1].parent
    rows = [json.loads(line) for line in runs[-1].read_text(encoding="utf-8").splitlines() if line.strip()]

    units = {json.loads(line)["unitId"]: json.loads(line)
             for line in UNIT_FILE.read_text(encoding="utf-8").splitlines() if line.strip()}

    codes = [f"c{i:04d}" for i in range(1, len(rows) + 1)]
    rng = random.Random(SEED)
    rng.shuffle(codes)

    items, mapping = [], {}
    for code, row in zip(codes, rows):
        unit = units[row["unitId"]]
        items.append(dict(
            code=code,
            fact=unit["fact"],
            input=unit["input"],
            output=row["text"],
        ))
        mapping[code] = dict(
            unitId=row["unitId"], sourceId=row["sourceId"], kind=row["kind"], arm=row["arm"],
            score=row["score"], seconds=row["seconds"], stopReason=row["stopReason"],
            limitHit=row["limitHit"], newTokens=row["newTokens"],
            inputSha256=row["inputSha256"], order=row["order"],
        )

    blind = run_dir / "blind"
    blind.mkdir(exist_ok=True)
    for old in blind.glob("batch-*.json"):
        old.unlink()

    batches = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]
    for idx, batch in enumerate(batches, start=1):
        payload = dict(
            pack=f"cf24-r1-batch-{idx:02d}",
            instruction="judge each output against its fact and input only; "
                        "do not use any memory of earlier reviews",
            items=batch,
        )
        (blind / f"batch-{idx:02d}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    (blind / "map.json").write_text(
        json.dumps(dict(seed=SEED, batches=len(batches), mapping=mapping),
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    index = dict(
        source=str(runs[-1].relative_to(EXPERIMENT)).replace(chr(92), "/"),
        sourceSha256=sha256(runs[-1]),
        rows=len(rows), batches=len(batches), batchSize=BATCH, seed=SEED,
        unitFile=str(UNIT_FILE.relative_to(TREE)).replace(chr(92), "/"),
        unitFileSha256=sha256(UNIT_FILE),
        hides=["arm", "score", "seconds", "stopReason", "unitId", "archived labels"],
        batchHashes={p.name: sha256(p) for p in sorted(blind.glob("batch-*.json"))},
        mapSha256=sha256(blind / "map.json"),
        note="map.json is the only file that reveals the arm; do not open it while judging",
    )
    (blind / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n",
                                      encoding="utf-8")
    print(json.dumps({k: index[k] for k in ("rows", "batches", "batchSize", "seed")}, ensure_ascii=False))
    print("blind dir:", blind)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
