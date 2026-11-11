# -*- coding: utf-8 -*-
"""One authorised MiniRBT-H256 pairwise run: 295 rows / 325 decisions / 4225 pairs.

Why this file exists instead of running 04's `pairwise_train.py` as-is:
- that entry defaults to `--arm both` (two arms); this run is authorised for one
  configuration only, so the arm is pinned and recorded before any result exists;
- it cannot drop the five rows 01 excluded for label conflicts (its freeze check
  pins the 300-row file), so the exclusion is applied here and the counts are
  asserted against 13's freeze;
- it has no device handling, and the report has no per-group F1, no
  `no_training_rows` and no `objectHit` field.

The trainer, model and serializer are 04's modules copied byte-for-byte
(sha256 printed in the report). Nothing in 04's tree is modified.

    python run_pairwise295.py --freeze ... --rows300 ... --val ... --labels ... \
        --split ... --base ... --out <dir> [--arm frozen] [--device auto]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pairwise_freeze as pf  # noqa: E402
import pairwise_model as pm  # noqa: E402
import pairwise_serialize as ps  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file or a JSON document holding a `rows` list.

    A JSONL file also starts with `{`, so a whole-text parse is attempted first
    and a JSONDecodeError falls back to line-by-line parsing. 01 ships the
    validation rows as one JSON object.
    """
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if payload is not None:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
            return payload["rows"]
        raise SystemExit(f"REFUSED: {path} is JSON but holds no rows list")
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def goal_texts(row: Dict[str, Any]) -> List[str]:
    out = []
    for goal in ((row.get("x") or {}).get("goals") or []):
        text = str(goal).strip()
        if "：" in text:
            text = text.split("：", 1)[1]
        out.append(text.strip())
    return out


def assign_split(rows: Sequence[Dict[str, Any]], lists: Dict[str, List[str]]) -> Dict[str, List[Dict[str, Any]]]:
    sets = {name: set(lists[name]) for name in ("TRAIN", "VALIDATION", "TEST")}
    out: Dict[str, List[Dict[str, Any]]] = {name: [] for name in sets}
    for row in rows:
        goals = set(goal_texts(row))
        hits = [name for name, pool in sets.items() if goals and goals <= pool]
        if len(hits) != 1:
            raise SystemExit(f"REFUSED: row {row['rowId']} fits {len(hits)} splits {hits}")
        out[hits[0]].append(row)
    return out


def decisions_of(rows: Sequence[Dict[str, Any]]) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    for row in rows:
        for step in range(max(1, ps.step_count(row))):
            out.append((row["rowId"], step))
    return out


def pairs_of(rows: Sequence[Dict[str, Any]], groups: Dict[str, str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        out.extend(ps.pairs_for_row(row, groups))
    return out


def measure_max_len(rows: Sequence[Dict[str, Any]], tokenizer: Any, groups: Dict[str, str], cap: int) -> Dict[str, Any]:
    lengths = []
    for row in rows:
        for pair in ps.pairs_for_row(row, groups):
            lengths.append(len(tokenizer(pair["text"], add_special_tokens=True)["input_ids"]))
    lengths.sort()
    longest = lengths[-1] if lengths else 0
    return {"count": len(lengths), "min": lengths[0] if lengths else 0,
            "p50": lengths[len(lengths) // 2] if lengths else 0,
            "p100": longest, "ceil32": min(cap, int(math.ceil(longest / 32.0) * 32))}


def collate_to(device: torch.device, batch: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
    return {key: value.to(device) for key, value in batch.items()}


def train_arm(model: pm.PairwiseModel, dataset: pm.PairwiseDataset, valid: pm.PairwiseDataset,
              tokenizer: Any, training: Dict[str, Any], arm: str, device: torch.device,
              seed: int, epochs: int) -> Dict[str, Any]:
    if arm == "frozen":
        for parameter in model.encoder.parameters():
            parameter.requires_grad = False
        params = list(model.head.parameters())
        optimizer = torch.optim.AdamW(params, lr=training["lrHead"], weight_decay=training["weightDecay"])
    else:
        optimizer = torch.optim.AdamW(model.parameters(), lr=training["lrEncoder"],
                                      weight_decay=training["weightDecay"])
    best = {"epoch": 0, "score": -1.0, "state": None, "metrics": None, "loss": None}
    history: List[Dict[str, Any]] = []
    stale = 0
    for epoch in range(1, epochs + 1):
        order = list(range(len(dataset.decisions)))
        random.Random(seed + epoch).shuffle(order)
        model.train()
        total, batches = 0.0, 0
        for start in range(0, len(order), training["batchDecisions"]):
            chunk = order[start:start + training["batchDecisions"]]
            indices = [index for decision in chunk for index in dataset.decisions[decision]]
            batch = collate_to(device, dataset.collate([dataset[index] for index in indices], tokenizer.pad_token_id))
            logits = model(batch["input_ids"], batch["attention_mask"])
            loss = pm.decision_loss(logits, batch["labels"], 13, pos_weight=training["posWeight"])
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total += float(loss.detach())
            batches += 1
        metrics = evaluate(model, valid, tokenizer, device)
        score = metrics["step1"]["rowHit"]
        history.append({"epoch": epoch, "trainLoss": round(total / max(1, batches), 5),
                        "validRowHit": score, "validDecisions": metrics["step1"]["decisions"]})
        print(json.dumps(history[-1], ensure_ascii=False), flush=True)
        if score > best["score"]:
            best = {"epoch": epoch, "score": score, "metrics": metrics, "loss": round(total / max(1, batches), 5),
                    "state": {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}}
            stale = 0
        else:
            stale += 1
            if stale >= training["earlyStopPatience"]:
                break
    return {"best": best, "history": history}


@torch.no_grad()
def evaluate(model: pm.PairwiseModel, dataset: pm.PairwiseDataset, tokenizer: Any, device: torch.device) -> Dict[str, Any]:
    model.eval()
    decisions = []
    for indices in dataset.decisions:
        batch = collate_to(device, dataset.collate([dataset[index] for index in indices], tokenizer.pad_token_id))
        logits = model(batch["input_ids"], batch["attention_mask"]).tolist()
        prediction = pm.predict_decision(logits)
        first = dataset[indices[0]]
        gold = next(dataset[index]["group"] for index in indices if dataset[index]["label"] == 1)
        decisions.append({"rowId": first["rowId"], "stepIndex": first["stepIndex"], "gold": gold,
                          "pred": prediction["top1"], "top2": prediction["top2"],
                          "margin": round(prediction["margin"], 4),
                          "logits": [round(value, 4) for value in logits]})
    step1 = [row for row in decisions if row["stepIndex"] == 0]
    step2 = [row for row in decisions if row["stepIndex"] == 1]
    return {"all": pm.metrics(decisions), "step1": pm.metrics(step1),
            "step2": pm.metrics(step2) if step2 else {"decisions": 0},
            "rows": decisions}


@torch.no_grad()
def measure_performance(model: pm.PairwiseModel, dataset: pm.PairwiseDataset, tokenizer: Any,
                        device: torch.device, threads: int) -> Dict[str, Any]:
    """Single pair, serial 13, batch 13 on the run device; wall ms only."""
    torch.set_num_threads(threads)
    sample = [dataset[index] for index in dataset.decisions[0]]
    batch1 = collate_to(device, dataset.collate([sample[0]], tokenizer.pad_token_id))
    batch13 = collate_to(device, dataset.collate(sample, tokenizer.pad_token_id))
    for _ in range(3):  # warmup
        model(batch1["input_ids"], batch1["attention_mask"])
    if device.type == "cuda":
        torch.cuda.synchronize()

    def timeit(call, repeats: int) -> float:
        started = time.perf_counter()
        for _ in range(repeats):
            call()
        if device.type == "cuda":
            torch.cuda.synchronize()
        return (time.perf_counter() - started) * 1000.0 / repeats

    single_ms = timeit(lambda: model(batch1["input_ids"], batch1["attention_mask"]), 20)
    batch_ms = timeit(lambda: model(batch13["input_ids"], batch13["attention_mask"]), 20)
    return {
        "device": str(device), "torch": torch.__version__, "threads": threads,
        "singlePairMs": round(single_ms, 3),
        "serial13Ms": round(single_ms * 13, 3),
        "batch13Ms": round(batch_ms, 3),
        "tokensPerPair": {"min": min(len(item["input_ids"]) for item in sample),
                          "max": max(len(item["input_ids"]) for item in sample)},
        "note": "native PyTorch on the training device; not browser latency",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--freeze13", required=True, help="13's short-pair freeze, source of the five exclusions")
    parser.add_argument("--rows300", required=True)
    parser.add_argument("--val", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--measurement", default="", help="the frozen measurement file, hash-checked")
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--arm", default="frozen", choices=("frozen", "unfrozen"))
    parser.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda"))
    parser.add_argument("--epochs", type=int, default=0, help="override for a smoke test only")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--limit-train-rows", type=int, default=0, help="smoke test only")
    args = parser.parse_args()

    frozen = json.loads(Path(args.freeze).read_text(encoding="utf-8"))
    # 04's verify() resolves the freeze's absolute Windows paths, which do not
    # exist on the cluster. The same guarantee is kept by comparing content
    # hashes of the uploaded copies against the freeze, and by recording the
    # frozen-path -> runtime-path mapping in the report.
    frozen_split = json.loads(Path(args.split).read_text(encoding="utf-8"))
    mapping = {
        "rows": (args.rows300, frozen["data"]["rows"]["sha256"]),
        "labels": (args.labels, frozen["data"]["labels"]["sha256"]),
        "baseModel": (str(Path(args.base) / "pytorch_model.bin"), frozen["base"]["files"]["pytorch_model.bin"]),
        "baseConfig": (str(Path(args.base) / "config.json"), frozen["base"]["files"]["config.json"]),
        "baseVocab": (str(Path(args.base) / "vocab.txt"), frozen["base"]["files"]["vocab.txt"]),
    }
    problems = []
    if sha256_file(Path(__file__).parent / "pairwise_serialize.py") != frozen["serializer"]["sha256"]:
        problems.append("serializer source changed")
    if ps.serializer_digest() != frozen["serializer"]["digest"]:
        problems.append("serializer digest changed")
    for label, (path, expect) in mapping.items():
        actual = sha256_file(Path(path))
        if actual != expect:
            problems.append(f"{label} hash {actual[:16]} != frozen {expect[:16]}")
    derived_from = (frozen_split.get("source") or {}).get("sha256")
    if derived_from and derived_from != frozen["data"]["split"]["sha256"]:
        problems.append("split lists were derived from a different split file")
    if args.measurement:
        expect = (frozen.get("measurement") or {}).get("sha256")
        actual = sha256_file(Path(args.measurement))
        if expect and actual != expect:
            problems.append(f"measurement hash {actual[:16]} != frozen {expect[:16]}")
    if problems:
        print("REFUSED: frozen sources changed:", *problems, sep=chr(10) + " - ")
        return 2
    training = frozen["training"]
    freeze13 = json.loads(Path(args.freeze13).read_text(encoding="utf-8"))
    excluded = [entry["rowId"] for entry in freeze13["labelConflictExclusions"]["excluded"]]
    expect = {"rows": freeze13["labelConflictExclusions"]["effect"]["rows"] - len(excluded),
              "decisions": freeze13["decisions"], "pairs": freeze13["pairs"]}

    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    groups = ps.load_predicate_groups(args.labels)
    rows = [row for row in load_jsonl(Path(args.rows300)) if row["rowId"] not in excluded]
    val_rows = load_jsonl(Path(args.val))
    overlap = set(row["rowId"] for row in rows) & set(row["rowId"] for row in val_rows)
    if overlap:
        raise SystemExit(f"REFUSED: rows in both train and validation: {sorted(overlap)[:3]}")

    train_pairs = pairs_of(rows, groups)
    val_pairs = pairs_of(val_rows, groups)
    counts = {"rows": len(rows), "decisions": len(decisions_of(rows)), "pairs": len(train_pairs)}
    if not args.limit_train_rows:
        if counts != expect:
            raise SystemExit(f"REFUSED: input counts {counts} != {expect}")
    print(json.dumps({"trainCounts": counts, "validation": {"rows": len(val_rows), "pairs": len(val_pairs)}},
                     ensure_ascii=False), flush=True)

    from transformers import BertTokenizer
    tokenizer = BertTokenizer.from_pretrained(args.base, do_lower_case=True)
    length_info = measure_max_len(rows + val_rows, tokenizer, groups, training["maxLenHardCap"])
    max_len = length_info["ceil32"]
    frozen_len = (frozen.get("measurement") or {}).get("maxLenCeil32")
    if frozen_len and max_len != frozen_len:
        print(f"NOTE: measured maxLen {max_len} differs from frozen {frozen_len}; rule still applied", flush=True)

    if args.limit_train_rows:
        rows = rows[: args.limit_train_rows]
    split_lists = json.loads(Path(args.split).read_text(encoding="utf-8"))
    parts = assign_split(rows, split_lists)
    if val_rows:
        parts["VALIDATION"] = parts["VALIDATION"] + val_rows
    if not parts["TRAIN"] or not parts["VALIDATION"]:
        raise SystemExit(f"REFUSED: empty split { {k: len(v) for k, v in parts.items()} }")

    train_set = pm.PairwiseDataset(parts["TRAIN"], tokenizer, max_len, groups, decisions_of(parts["TRAIN"]))
    valid_set = pm.PairwiseDataset(parts["VALIDATION"], tokenizer, max_len, groups, decisions_of(parts["VALIDATION"]))

    device = torch.device("cpu") if args.device == "cpu" else (
        torch.device("cuda") if args.device == "cuda" or torch.cuda.is_available() else torch.device("cpu"))
    torch.set_num_threads(args.threads)
    torch.manual_seed(training["seed"])
    random.seed(training["seed"])
    model = pm.PairwiseModel(args.base, dropout=training["dropout"]).to(device)

    epochs = args.epochs or training["epochsMax"]
    started = time.time()
    assert len(valid_set.decisions) == len(parts["VALIDATION"]), "validation decisions must equal validation rows"
    result = train_arm(model, train_set, valid_set, tokenizer, training, args.arm, device, training["seed"], epochs)
    wall = round(time.time() - started, 1)

    if result["best"]["state"] is not None:
        model.load_state_dict(result["best"]["state"])
    final = result["best"]["metrics"] or evaluate(model, valid_set, tokenizer, device)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = out_dir / f"pairwise-{args.arm}.pt"
    torch.save({"state": model.state_dict(), "maxLen": max_len, "arm": args.arm,
                "freeze": str(Path(args.freeze)), "freezeSha256": sha256_file(Path(args.freeze)),
                "serializerDigest": frozen["serializer"]["digest"], "groups": ps.ALL_GROUPS,
                "valRowHit": result["best"]["score"]}, checkpoint)

    train_positive_groups = {group: 0 for group in ps.ALL_GROUPS}
    for pair in train_set.pairs:
        if pair["label"] == 1:
            train_positive_groups[pair["group"]] += 1
    no_training_rows = [group for group, count in train_positive_groups.items() if count == 0]

    steps = {0: 0, 1: 0}
    for row in parts["TRAIN"]:
        for step in range(max(1, ps.step_count(row))):
            steps[step] = steps.get(step, 0) + 1

    perf = measure_performance(model, valid_set, tokenizer, device, args.threads)
    report = {
        "kind": "short-pair-295-run",
        "authorisedBy": "tasks/product-10-short-pair-training.md",
        "inputs": {
            "freeze": {"path": str(Path(args.freeze)), "sha256": sha256_file(Path(args.freeze))},
            "rows300": {"path": str(Path(args.rows300)), "sha256": sha256_file(Path(args.rows300))},
            "val": {"path": str(Path(args.val)), "sha256": sha256_file(Path(args.val))},
            "labels": {"path": str(Path(args.labels)), "sha256": sha256_file(Path(args.labels))},
            "split": {"path": str(Path(args.split)), "sha256": sha256_file(Path(args.split))},
            "base": {"path": str(Path(args.base)), "weightsSha256": sha256_file(Path(args.base) / "pytorch_model.bin")},
            "excludedRowIds": excluded,
            "pathMapping": {label: {"runtimePath": path, "sha256": sha256_file(Path(path)),
                                    "frozenPath": ((frozen.get("data") or {}).get(label) or {}).get("path")
                                    or ((frozen.get("base") or {}).get("dir", "") + "/" + label)}
                            for label, (path, _expect) in mapping.items()},
            "freeze13": {"path": str(Path(args.freeze13)), "sha256": sha256_file(Path(args.freeze13))},
        },
        "code": {name: sha256_file(Path(os.path.dirname(os.path.abspath(__file__))) / name)
                 for name in ("pairwise_serialize.py", "pairwise_model.py", "pairwise_freeze.py",
                              "run_pairwise295.py")},
        "config": {
            "arm": args.arm, "epochsMax": epochs, "epochsRun": len(result["history"]),
            "earlyStopPatience": training["earlyStopPatience"], "batchDecisions": training["batchDecisions"],
            "lrHead": training["lrHead"], "lrEncoder": training["lrEncoder"],
            "weightDecay": training["weightDecay"], "dropout": training["dropout"],
            "seed": training["seed"], "posWeight": training["posWeight"],
            "normalisation": training["normalisation"], "maxLen": max_len,
            "pooling": training["pooling"], "optimizer": training["optimizer"],
        },
        "counts": {"train": {"rows": len(parts["TRAIN"]), "decisions": steps, "pairs": len(train_set.pairs)},
                   "validation": {"rows": len(parts["VALIDATION"]), "pairs": len(valid_set.pairs)},
                   "test": "not run: 01's blind file is only read after this checkpoint and config are hashed"},
        "length": {**length_info, "frozenMaxLen": frozen_len, "truncation": "never"},
        "device": {"requested": args.device, "used": str(device), "torch": torch.__version__,
                   "cudaAvailable": torch.cuda.is_available(),
                   "cudaName": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},
        "training": {"history": result["history"], "bestEpoch": result["best"]["epoch"],
                     "bestValidRowHit": result["best"]["score"], "bestTrainLoss": result["best"]["loss"],
                     "wallSeconds": wall},
        "validation": {"step1": final["step1"], "step2": final["step2"], "all": final["all"],
                       "rows": final["rows"]},
        "groups": {"trainPositivePerGroup": train_positive_groups,
                   "noTrainingRows": no_training_rows,
                   "objectHit": "untested: no object input/model is implemented"},
        "performance": perf,
        "checkpoint": {"path": str(checkpoint), "sha256": sha256_file(checkpoint)},
        "limitations": [
            "step2 is teacher-forced: the second step keeps the original X and only adds 已做",
            "four groups have no positive training rows; their errors are a data gap, not a capacity claim",
            "validation is 01's 15 rows; TEST is held by 01 and is not used here",
            "no cross-world generalisation is measured",
        ],
    }
    (out_dir / "pairwise-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                                  encoding="utf-8")
    print(json.dumps({"report": str(out_dir / "pairwise-report.json"),
                      "rowHit": final["step1"]["rowHit"],
                      "skipPrecision": final["step1"]["skipPrecision"],
                      "skipRecall": final["step1"]["skipRecall"],
                      "checkpoint": report["checkpoint"]["sha256"][:16]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
