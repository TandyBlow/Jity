"""Mixed blind pack for the T1 diagnostic: r1 greedy + T1 greedy, 170 items.

Hides scheme, score, seconds, stop reason, unitId and all earlier verdicts; the map
is the only file that reveals which scheme produced a row.
"""

import hashlib, json, random
from pathlib import Path

HERE = Path(__file__).resolve()
EXPERIMENT = HERE.parents[1]
TREE = HERE.parents[5]
UNIT_FILE = TREE / "artifacts/world-components/n4-cf24-contract.jsonl"
SEED, BATCH = 20261109, 10


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_raw(pattern):
    runs = sorted((EXPERIMENT / "artifacts/fact-wording").glob(pattern))
    if not runs:
        raise SystemExit(f"missing run: {pattern}")
    d = Path(runs[-1])
    return d.parent, [json.loads(l) for l in d.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    r1_path, r1_rows = load_raw("diagnostic-r1/*/raw.jsonl")
    r2_path, r2_rows = load_raw("diagnostic-r2-cand-t1/*/raw.jsonl")
    r1 = {(r["unitId"], r["arm"]): r for r in r1_rows if r["arm"] == "greedy"}
    r2 = {r["unitId"]: r for r in r2_rows}
    units = {json.loads(l)["unitId"]: json.loads(l) for l in UNIT_FILE.read_text(encoding="utf-8").splitlines() if l.strip()}
    if set(r1) != {(u, "greedy") for u in units} or set(r2) != set(units):
        raise SystemExit("unit mismatch between r1 greedy / T1 / contract")

    old_req = json.loads((EXPERIMENT / "freeze/candidate-t1-v2.json").read_text(encoding="utf-8"))["change"]["oldRequirement"]
    new_req = json.loads((EXPERIMENT / "freeze/candidate-t1-v2.json").read_text(encoding="utf-8"))["change"]["newRequirement"]

    rows = []
    for uid in sorted(units):
        rows.append(dict(scheme="r1-greedy", unitId=uid, input=units[uid]["input"], output=r1[(uid, "greedy")]["text"],
                         score=r1[(uid, "greedy")]["score"], seconds=r1[(uid, "greedy")]["seconds"],
                         stopReason=r1[(uid, "greedy")]["stopReason"], inputSha256=r1[(uid, "greedy")]["inputSha256"]))
        t1_input = units[uid]["input"].replace(old_req, new_req)
        rows.append(dict(scheme="T1-greedy", unitId=uid, input=t1_input, output=r2[uid]["text"],
                         score=r2[uid]["score"], seconds=r2[uid]["seconds"],
                         stopReason=r2[uid]["stopReason"], inputSha256=r2[uid]["inputSha256"]))

    codes = [f"c{i:04d}" for i in range(1, len(rows) + 1)]
    random.Random(SEED).shuffle(codes)
    blind = r2_path / "blind"
    blind.mkdir(exist_ok=True)
    for old in blind.glob("batch-*.json"):
        old.unlink()

    mapping, items = {}, []
    for code, row in zip(codes, rows):
        items.append(dict(code=code, fact=units[row["unitId"]]["fact"], input=row["input"], output=row["output"]))
        mapping[code] = dict(scheme=row["scheme"], unitId=row["unitId"], score=row["score"],
                             seconds=row["seconds"], stopReason=row["stopReason"],
                             inputSha256=row["inputSha256"])
    batches = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]
    for idx, batch in enumerate(batches, start=1):
        (blind / f"batch-{idx:02d}.json").write_text(json.dumps(dict(
            pack=f"cf24-t1-batch-{idx:02d}",
            instruction="judge each output against its fact and input only; no earlier reviews",
            items=batch), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (blind / "map.json").write_text(json.dumps(dict(seed=SEED, batches=len(batches), mapping=mapping),
                                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (blind / "index.json").write_text(json.dumps(dict(
        rows=len(items), batches=len(batches), batchSize=BATCH, seed=SEED,
        sources={"r1-greedy": str(r1_path.relative_to(EXPERIMENT)), "T1-greedy": str(r2_path.relative_to(EXPERIMENT))},
        hides=["scheme", "score", "seconds", "stopReason", "unitId", "earlier verdicts"],
        batchHashes={p.name: sha(p) for p in sorted(blind.glob("batch-*.json"))},
        mapSha256=sha(blind / "map.json")), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dict(rows=len(items), batches=len(batches), seed=SEED, blind=str(blind)), ensure_ascii=False))


if __name__ == "__main__":
    main()
