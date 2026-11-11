"""Train / evaluate the single-logit pairwise model.

Refuses to run unless the freeze verifies (serializer, rows, labels, split, base,
measurement all unchanged) and unless the length rule from the frozen
measurement is respected (no truncation).

    python pairwise_train.py --freeze freeze_pairwise.json --rows <jsonl> \\
        --labels <labels-v1.json> --split <01-goal-split-v1.json> \\
        --base <minirbt snapshot> --out <run dir> [--eval-only <ckpt>] [--arm both]

Splits come from the frozen split file: 73 goals = TRAIN48 / VALIDATION10 /
TEST15, owner-complete. TEST is only read with --use-test (once, after the
configuration is frozen).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import torch

import pairwise_freeze
import pairwise_model as pm
import pairwise_serialize as ps


def load_split(path: Path) -> Dict[str, List[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: Dict[str, List[str]] = {}
    for key in ("TRAIN", "VALIDATION", "TEST", "train", "validation", "test"):
        if key in data and isinstance(data[key], list):
            out[key.upper()] = data[key]
    if not {"TRAIN", "VALIDATION"} <= set(out):
        raise SystemExit(f"REFUSED: split file {path} has no TRAIN/VALIDATION lists")
    return out


def goals_of(row: Dict[str, Any]) -> List[str]:
    goals = (row.get("x") or {}).get("goals") or []
    out = []
    for goal in goals:
        text = str(goal).strip()
        if "：" in text:
            text = text.split("：", 1)[1]
        out.append(text)
    return out


def split_rows(rows: Sequence[Dict[str, Any]], split: Dict[str, List[str]]) -> Dict[str, List[Dict[str, Any]]]:
    """Owner-complete by goal text: a row belongs to a split when its goals are
    inside that split's goal set. A row matching two splits is an error."""
    sets = {name: set(values) for name, values in split.items()}
    out: Dict[str, List[Dict[str, Any]]] = {name: [] for name in sets}
    for row in rows:
        goals = set(goals_of(row))
        hits = [name for name, values in sets.items() if goals and goals <= values]
        if len(hits) != 1:
            raise SystemExit(f"REFUSED: row {row['rowId']} belongs to {len(hits)} splits: {hits}")
        out[hits[0]].append(row)
    return out


def decisions_of(rows: Sequence[Dict[str, Any]]) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    for row in rows:
        for step in range(max(1, ps.step_count(row))):
            out.append((row["rowId"], step))
    return out


def measure_max_len(rows: Sequence[Dict[str, Any]], tokenizer: Any, groups: Dict[str, str],
                    cap: int = 512) -> int:
    longest = 0
    for row in rows:
        for pair in ps.pairs_for_row(row, groups):
            longest = max(longest, len(tokenizer(pair["text"], add_special_tokens=True)["input_ids"]))
    return min(cap, int(math.ceil(longest / 32) * 32))


def run_epoch(model: pm.PairwiseModel, dataset: pm.PairwiseDataset, tokenizer: Any,
              optimizer: torch.optim.Optimizer | None, batch_decisions: int,
              seed: int) -> Dict[str, float]:
    order = list(range(len(dataset.decisions)))
    generator = random.Random(seed)
    generator.shuffle(order)
    total_loss = 0.0
    batches = 0
    model.train(optimizer is not None)
    for start in range(0, len(order), batch_decisions):
        chunk = order[start:start + batch_decisions]
        indices = [index for decision in chunk for index in dataset.decisions[decision]]
        batch = dataset.collate([dataset[index] for index in indices], tokenizer.pad_token_id)
        logits = model(batch["input_ids"], batch["attention_mask"])
        loss = pm.decision_loss(logits, batch["labels"], 13)
        if optimizer is not None:
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        total_loss += float(loss.detach())
        batches += 1
    return {"loss": total_loss / max(1, batches), "batches": batches}


@torch.no_grad()
def evaluate(model: pm.PairwiseModel, dataset: pm.PairwiseDataset, tokenizer: Any) -> Dict[str, Any]:
    model.eval()
    decisions: List[Dict[str, Any]] = []
    for indices in dataset.decisions:
        batch = dataset.collate([dataset[index] for index in indices], tokenizer.pad_token_id)
        logits = model(batch["input_ids"], batch["attention_mask"]).tolist()
        prediction = pm.predict_decision(logits)
        first = dataset[indices[0]]
        gold = next(dataset[index]["group"] for index in indices if dataset[index]["label"] == 1)
        decisions.append({
            "rowId": first["rowId"], "stepIndex": first["stepIndex"], "gold": gold,
            "pred": prediction["top1"], "top2": prediction["top2"],
            "margin": round(prediction["margin"], 4), "logits": [round(value, 4) for value in logits],
        })
    step1 = [row for row in decisions if row["stepIndex"] == 0]
    step2 = [row for row in decisions if row["stepIndex"] == 1]
    return {
        "all": pm.metrics(decisions),
        "step1": pm.metrics(step1),
        "step2": pm.metrics(step2) if step2 else {"decisions": 0},
        "rows": decisions,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--rows", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--arm", default="both", choices=["frozen", "unfrozen", "both"])
    parser.add_argument("--eval-only")
    parser.add_argument("--use-test", action="store_true")
    args = parser.parse_args(argv)

    problems = pairwise_freeze.verify(Path(args.freeze))
    if problems:
        print("REFUSED: registered source changed after the freeze:")
        for problem in problems:
            print(" -", problem)
        return 2
    frozen = json.loads(Path(args.freeze).read_text(encoding="utf-8"))
    training = frozen["training"]

    from transformers import BertTokenizer
    tokenizer = BertTokenizer.from_pretrained(args.base, do_lower_case=True)
    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    if labels != json.loads(Path(frozen["data"]["labels"]["path"]).read_text(encoding="utf-8")):
        print("REFUSED: labels argument differs from the frozen labels file")
        return 2
    groups = ps.load_predicate_groups(args.labels)
    rows = ps.load_rows(args.rows)
    split = load_split(Path(args.split))
    parts = split_rows(rows, split)
    if args.use_test != bool(parts.get("TEST")):
        pass  # TEST is only read when it exists; using it is a separate decision.

    max_len = measure_max_len(parts["TRAIN"] + parts["VALIDATION"], tokenizer, groups,
                              cap=training["maxLenHardCap"])
    frozen_len = (frozen.get("measurement") or {}).get("maxLenCeil32")
    if frozen_len and max_len > frozen_len:
        print(f"REFUSED: registered maxLen {frozen_len} violates the frozen rule; measured {max_len}")
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    report: Dict[str, Any] = {
        "kind": "pairwise-run",
        "freeze": str(Path(args.freeze).resolve()),
        "freezeSha256": pairwise_freeze.sha256_file(Path(args.freeze)),
        "serializerDigest": frozen["serializer"]["digest"],
        "rows": len(rows),
        "splitCounts": {name: len(values) for name, values in parts.items()},
        "maxLen": max_len,
        "arms": {},
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    train_set = pm.PairwiseDataset(parts["TRAIN"], tokenizer, max_len, groups, decisions_of(parts["TRAIN"]))
    valid_set = pm.PairwiseDataset(parts["VALIDATION"], tokenizer, max_len, groups, decisions_of(parts["VALIDATION"]))

    if args.eval_only:
        # One checkpoint, one split. TEST is only used when --use-test is passed,
        # and only after the configuration is frozen.
        checkpoint = torch.load(args.eval_only, map_location="cpu")
        if checkpoint.get("serializerDigest") != frozen["serializer"]["digest"]:
            print("REFUSED: checkpoint was trained with a different serializer digest")
            return 2
        torch.manual_seed(training["seed"])
        model = pm.PairwiseModel(args.base, dropout=training["dropout"])
        model.load_state_dict(checkpoint["state"])
        target = valid_set
        target_name = "validation"
        if args.use_test and parts.get("TEST"):
            target = pm.PairwiseDataset(parts["TEST"], tokenizer, max_len, groups, decisions_of(parts["TEST"]))
            target_name = "test"
        result = evaluate(model, target, tokenizer)
        payload = {"kind": "pairwise-eval", "split": target_name, "checkpoint": args.eval_only,
                   "measurement": result}
        (out_dir / f"pairwise-eval-{target_name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + chr(10) + "",
            encoding="utf-8")
        print(json.dumps({"split": target_name, "rowHit": result["step1"]["rowHit"]}, ensure_ascii=False))
        return 0
    report["pairs"] = {"train": len(train_set.pairs), "validation": len(valid_set.pairs)}

    arms = ["frozen", "unfrozen"] if args.arm == "both" else [args.arm]
    for arm in arms:
        # Seed BEFORE the encoder is loaded and the head created.
        torch.manual_seed(training["seed"])
        random.seed(training["seed"])
        model = pm.PairwiseModel(args.base, dropout=training["dropout"])
        if arm == "frozen":
            for parameter in model.encoder.parameters():
                parameter.requires_grad = False
            head_params = list(model.head.parameters())
            optimizer = torch.optim.AdamW(head_params, lr=training["lrHead"],
                                          weight_decay=training["weightDecay"])
        else:
            optimizer = torch.optim.AdamW(model.parameters(), lr=training["lrEncoder"],
                                          weight_decay=training["weightDecay"])
        best = {"loss": float("inf"), "state": None, "epoch": 0, "metrics": None}
        best_score = -1.0
        history: List[Dict[str, Any]] = []
        stale = 0
        for epoch in range(1, training["epochsMax"] + 1):
            train_stats = run_epoch(model, train_set, tokenizer, optimizer,
                                    training["batchDecisions"], training["seed"] + epoch)
            valid_metrics = evaluate(model, valid_set, tokenizer)
            score = valid_metrics["step1"]["rowHit"]
            history.append({"epoch": epoch, "train": train_stats, "validRowHit": score})
            if score > best_score:
                best_score = score
                best = {"loss": train_stats["loss"], "epoch": epoch, "metrics": valid_metrics,
                        "state": {key: value.detach().clone() for key, value in model.state_dict().items()}}
                stale = 0
            else:
                stale += 1
                if stale >= training["earlyStopPatience"]:
                    break
        if best["state"] is not None:
            model.load_state_dict(best["state"])
        final = best["metrics"] or evaluate(model, valid_set, tokenizer)
        checkpoint = out_dir / f"pairwise-{arm}.pt"
        torch.save({
            "state": model.state_dict(),
            "maxLen": max_len,
            "arm": arm,
            "freeze": str(Path(args.freeze).resolve()),
            "serializerDigest": frozen["serializer"]["digest"],
            "groups": ps.ALL_GROUPS,
        }, checkpoint)
        report["arms"][arm] = {
            "bestEpoch": best["epoch"],
            "history": history,
            "validation": {"step1": final["step1"], "step2": final["step2"], "all": final["all"]},
            "checkpoint": str(checkpoint),
        }
        print(json.dumps({arm: {"bestEpoch": best["epoch"], "rowHit": final["step1"]["rowHit"],
                                 "skipPrecision": final["step1"]["skipPrecision"],
                                 "skipRecall": final["step1"]["skipRecall"]}}, ensure_ascii=False))

    report["wallSeconds"] = round(time.time() - started, 1)
    report["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out_dir / "pairwise-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                                  encoding="utf-8")
    print(json.dumps({"report": str(out_dir / "pairwise-report.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
