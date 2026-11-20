"""CPU forward-cost record for the pairwise model.

The architecture measured by the coordinator (MiniRBT-H256 encoder + one logit
head, sequence 224, batch 13, 4 threads, PyTorch CPU) is the same architecture
this experiment trains, so the recorded numbers are reused instead of re-run:

    results/action-short-pairs-20261111/cpu-forward-measurement.json
    single p50 114.9 ms, serial 13 p50 1520.2 ms, batch 13 p50 984.5 ms

`--reuse` (default) copies those numbers into the experiment record bound to the
file's sha256 and the current serializer/model shape. `--run` performs a real
measurement with a fresh random head (latency only, never accuracy) and writes a
new record.

    python pairwise_cpu_measure.py --measurement <json> --out <json> [--run]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List

import pairwise_serialize as ps

EXPECTED = {
    "architecture": "MiniRBT-H256 encoder + single logit head",
    "sequenceLength": 224,
    "batch": 13,
    "threads": 4,
    "head": "single logit",
    "dtype": "float32",
}


def signature_ok(record: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    if record.get("sequenceLength") != EXPECTED["sequenceLength"]:
        problems.append(f"sequenceLength {record.get('sequenceLength')} != {EXPECTED['sequenceLength']}")
    if record.get("threads") != EXPECTED["threads"]:
        problems.append(f"threads {record.get('threads')} != {EXPECTED['threads']}")
    head = str(record.get("head", ""))
    if "single logit" not in head:
        problems.append(f"head '{head}' is not the single-logit head")
    if record.get("device") != "CPU":
        problems.append(f"device {record.get('device')} is not CPU")
    if record.get("tokenizationIncluded") not in (False, None):
        problems.append("recorded timing includes tokenization; not comparable")
    if record.get("loadIncluded") not in (False, None):
        problems.append("recorded timing includes model load; not comparable")
    return problems


def run_measurement(args: argparse.Namespace) -> Dict[str, Any]:
    import statistics
    import torch

    import pairwise_model as pm

    torch.set_num_threads(args.threads)
    model = pm.PairwiseModel(args.base, dropout=0.0)
    model.eval()
    width = EXPECTED["sequenceLength"]
    ids = torch.randint(0, 20000, (EXPECTED["batch"], width), dtype=torch.long)
    mask = torch.ones_like(ids)
    single_ids, single_mask = ids[:1], mask[:1]

    def timed(call, warmup: int, repeats: int) -> List[float]:
        with torch.no_grad():
            for _ in range(warmup):
                call()
            samples = []
            for _ in range(repeats):
                started = time.perf_counter()
                call()
                samples.append((time.perf_counter() - started) * 1000.0)
        return samples

    def stats(samples: List[float]) -> Dict[str, float]:
        ordered = sorted(samples)
        pick = lambda q: ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]
        return {"min": round(ordered[0], 3), "p50": round(statistics.median(ordered), 3),
                "p95": round(pick(0.95), 3), "p100": round(ordered[-1], 3)}

    serial = timed(lambda: [model(single_ids, single_mask) for _ in range(13)],
                   args.warmup, args.repeats)
    batch = timed(lambda: model(ids, mask), args.warmup, args.repeats)
    single = timed(lambda: model(single_ids, single_mask), args.warmup, args.repeats)
    return {
        "device": "CPU",
        "torch": torch.__version__,
        "threads": args.threads,
        "sequenceLength": width,
        "warmupEach": args.warmup,
        "repetitions": args.repeats,
        "head": "fresh random single logit; measures latency only",
        "tokenizationIncluded": False,
        "loadIncluded": False,
        "singleMs": stats(single),
        "serial13Ms": stats(serial),
        "batch13Ms": stats(batch),
        "browserMeasured": False,
        "notes": "CPU native PyTorch; not ONNX/WebGPU performance or quality evidence",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measurement", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--base", default="D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot")
    parser.add_argument("--threads", type=int, default=EXPECTED["threads"])
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()

    record: Dict[str, Any] = {
        "kind": "pairwise-cpu-forward-record",
        "serializerDigest": ps.serializer_digest(),
        "groupCount": len(ps.ALL_GROUPS),
        "architecture": EXPECTED["architecture"],
    }
    if args.run:
        measured = run_measurement(args)
        record.update({"source": "measured-now", "measurement": measured})
    else:
        source = Path(args.measurement)
        payload = json.loads(source.read_text(encoding="utf-8"))
        problems = signature_ok(payload)
        if problems:
            raise SystemExit("REFUSED: recorded measurement does not match this architecture:\n - "
                             + "\n - ".join(problems))
        record.update({
            "source": "reused",
            "sourcePath": str(source.resolve()),
            "sourceSha256": __import__("hashlib").sha256(source.read_bytes()).hexdigest(),
            "measurement": payload,
            "reuseReason": "same architecture (MiniRBT-H256 + single logit), same sequence length "
                           "(224), same batch (13), same thread count (4); coordinator ran it on this host",
        })
    Path(args.out).write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"out": args.out, "source": record["source"],
                      "singleP50": record["measurement"]["singleMs"]["p50"],
                      "batchP50": record["measurement"]["batch13Ms"]["p50"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
