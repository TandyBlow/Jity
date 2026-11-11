# Metrics for the next-action classifier.
#
# The frozen primitives are reported separately so nobody can point at one and
# call it the goal:
#   primaryGroupHit        coarse group of step 1 vs the frozen acceptable set
#   fullHit                exact steps list (count, order, fine predicate, object)
#   skipRecall             predicted skips / frozen skips
#   wrongActionRate        non-skip rows whose step-1 group is unacceptable
#   nonSkipGroupAccuracy   group accuracy over non-skip rows
#   groupMacro             12-group macro over non-skip rows
#   perGoal                one row per withheld goal, with scenario counts
#
# `--self-test` runs the metric code on hand-written predictions so a bug in the
# scorer cannot masquerade as a model result.

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Dict, List, Sequence

import torch

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dataset import Example, build_example, collate, make_tokenizer_fn, read_rows  # noqa: E402
from labels import MAX_STEPS, STEP_NONE, load_labels, sha256_file  # noqa: E402
from model import NextStepModel, build_encoder  # noqa: E402


def acceptable_groups(row: dict, labels) -> set[int]:
    """The frozen acceptable step-1 groups. A row may register several; they are
    fixed in the data file before any model output exists."""
    value = row.get("acceptableGroups") or row.get("acceptableGroupsStep1")
    if not value:
        steps = ((row.get("y") or {}).get("steps") or [])
        if not steps:
            return set()
        return {labels.group_of_label(steps[0]["action"])}
    out = set()
    for entry in value:
        if isinstance(entry, int):
            out.add(entry)
            continue
        if str(entry) in labels.groups:
            out.add(labels.groups.index(str(entry)))
            continue
        out.add(labels.group_of_label(str(entry)))
    return out


def score_rows(rows: Sequence[dict], predictions: Sequence[dict], labels) -> dict:
    """`predictions[i] = {"step": 0|1|2, "actions": [..], "objects": [..]}` with
    the same length as rows[i].y.steps (objects as candidate index, 0 = null)."""
    if len(rows) != len(predictions):
        raise ValueError("rows and predictions differ in length")
    totals = {"rows": 0, "skipRows": 0, "nonSkipRows": 0, "skipCorrect": 0, "stepCountCorrect": 0}
    group_hits = 0
    group_total = 0
    wrong = 0
    full_hits = 0
    per_group = {name: {"hits": 0, "rows": 0} for name in labels.groups}
    skips_predicted = 0
    detail = []
    for row, prediction in zip(rows, predictions):
        steps = ((row.get("y") or {}).get("steps") or [])
        truth_step = len(steps)
        predicted_step = int(prediction.get("step") or 0)
        totals["rows"] += 1
        if predicted_step == 0:
            skips_predicted += 1
        if truth_step == 0:
            totals["skipRows"] += 1
            if predicted_step == 0:
                totals["skipCorrect"] += 1
        else:
            totals["nonSkipRows"] += 1
        if predicted_step == truth_step:
            totals["stepCountCorrect"] += 1
        entry = {"rowId": row.get("rowId"), "truth": truth_step, "predicted": predicted_step}
        if truth_step == 0:
            # An exact empty steps list is a full hit: fullHit compares the
            # steps list, and [] == [] is exact. Skip recall is still reported
            # on its own so a model that says nothing everywhere cannot hide.
            entry["skip"] = predicted_step == 0
            entry["fullHit"] = predicted_step == 0
            if predicted_step == 0:
                full_hits += 1
            detail.append(entry)
            continue
        allowed = acceptable_groups(row, labels)
        group_total += 1
        if predicted_step == 0:
            wrong += 1
            per_group[labels.groups[next(iter(allowed))]]["rows"] += 1 if len(allowed) == 1 else 0
            entry.update({"groupHit": False, "why": "predicted skip"})
            detail.append(entry)
            continue
        true_action = labels.action_id(steps[0]["action"])
        true_group = labels.group_of_action(true_action)
        predicted_action = prediction["actions"][0] if prediction.get("actions") else -1
        if isinstance(predicted_action, str):
            predicted_action = labels.fine_index.get(predicted_action, -1)
        predicted_group = labels.group_of_action(predicted_action) if predicted_action >= 0 else -1
        hit = predicted_group in allowed
        if hit:
            group_hits += 1
        else:
            wrong += 1
        if len(allowed) == 1:
            name = labels.groups[true_group]
            per_group[name]["rows"] += 1
            if hit:
                per_group[name]["hits"] += 1
        full = predicted_step == truth_step and all(
            labels.action_id(steps[index]["action"]) == as_fine_id(prediction, index, labels)
            for index in range(truth_step)
        )
        if full:
            # objects compared as candidate ids, so a reordered candidate list in
            # a future run cannot silently score as a hit
            full = all(
                (steps[index].get("object") or None) == (prediction.get("objects") or [None] * truth_step)[index]
                for index in range(truth_step)
            )
        if full:
            full_hits += 1
        entry.update({"groupHit": hit, "fullHit": bool(full),
                      "trueGroup": labels.groups[true_group],
                      "predictedGroup": labels.groups[predicted_group] if predicted_group >= 0 else None})
        detail.append(entry)
    macro_rows = [value for value in per_group.values() if value["rows"] > 0]
    return {
        "rows": totals["rows"],
        "skipRows": totals["skipRows"],
        "nonSkipRows": totals["nonSkipRows"],
        "skipRecall": round(totals["skipCorrect"] / totals["skipRows"], 4) if totals["skipRows"] else None,
        "skipPrecision": round(totals["skipCorrect"] / skips_predicted, 4) if skips_predicted else None,
        "skipsPredicted": skips_predicted,
        "stepCountAccuracy": round(totals["stepCountCorrect"] / max(totals["rows"], 1), 4),
        "primaryGroupHit": round(group_hits / group_total, 4) if group_total else None,
        "wrongActionRate": round(wrong / group_total, 4) if group_total else None,
        "nonSkipGroupAccuracy": round(group_hits / group_total, 4) if group_total else None,
        "groupMacro": round(sum(v["hits"] / v["rows"] for v in macro_rows) / len(macro_rows), 4) if macro_rows else None,
        "fullHit": round(full_hits / max(totals["rows"], 1), 4),
        "perGroup": {name: {"hits": value["hits"], "rows": value["rows"]} for name, value in per_group.items()},
        "detail": detail,
    }


def as_fine_id(prediction: dict, index: int, labels) -> int:
    actions = prediction.get("actions") or []
    if index >= len(actions):
        return -1
    value = actions[index]
    if isinstance(value, str):
        return labels.fine_index.get(value, -1)
    return int(value)


def per_goal(rows: Sequence[dict], scored: dict) -> List[dict]:
    buckets: Dict[str, dict] = {}
    detail_by_row = {entry["rowId"]: entry for entry in scored["detail"]}
    for row in rows:
        goal = str(row.get("goalId") or row.get("goalFamily") or (row.get("x") or {}).get("goals") or row.get("rowId"))
        bucket = buckets.setdefault(goal, {"goal": goal, "scenarios": 0, "groupHits": 0, "fullHits": 0, "skips": 0})
        entry = detail_by_row.get(row.get("rowId")) or {}
        bucket["scenarios"] += 1
        bucket["groupHits"] += 1 if entry.get("groupHit") else 0
        bucket["fullHits"] += 1 if entry.get("fullHit") else 0
        bucket["skips"] += 1 if entry.get("skip") else 0
    return sorted(buckets.values(), key=lambda item: item["goal"])


def predict(rows: Sequence[dict], *, base: str, head: str, max_len: int, labels, tokenizer, tiny: bool = False) -> List[dict]:
    encoder, hidden = build_encoder(base, unfreeze=False)
    model = NextStepModel(encoder, hidden=hidden, n_fine=len(labels), freeze_encoder=True)
    checkpoint = torch.load(head, map_location="cpu")
    model.load_state_dict({**{f"encoder.{k}": v for k, v in encoder.state_dict().items()}, **checkpoint["model"]}, strict=False)
    model.eval()
    examples = [build_example(row, labels) for row in rows]
    tokenize = make_tokenizer_fn(tokenizer)
    predictions: List[dict] = []
    with torch.no_grad():
        for start in range(0, len(examples), 16):
            chunk = examples[start:start + 16]
            batch = collate(chunk, tokenize, max_len)
            outputs = model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"],
                            cand_ids=batch["cand_ids"], cand_mask=batch["cand_mask"])
            steps = outputs["step_logits"].argmax(-1).tolist()
            actions = outputs["action_logits"].argmax(-1).tolist()
            objects = outputs["object_logits"].argmax(-1).tolist()
            for index, step in enumerate(steps):
                row = rows[start + index]
                ids = [candidate.get("id") if isinstance(candidate, dict) else candidate
                       for candidate in (row.get("x") or {}).get("candidates") or []]
                chosen = []
                for slot in range(step):
                    pointer = int(objects[index][slot])
                    chosen.append(None if pointer == 0 else ids[pointer - 1])
                predictions.append({
                    "step": int(step),
                    "actions": [labels.fine[int(a)] for a in actions[index][:step]],
                    "objects": chosen,
                })
    return predictions


def self_test() -> int:
    labels = load_labels()
    rows = [
        {"rowId": "r1", "y": {"steps": [{"action": "观察", "object": "nono"}]},
         "x": {"candidates": [{"id": "nono", "name": "诺诺"}], "character": {"id": "lu", "name": "路明非"}}},
        {"rowId": "r2", "y": {"steps": []},
         "x": {"candidates": [], "character": {"id": "lu", "name": "路明非"}}},
        {"rowId": "r3", "y": {"steps": [{"action": "移动", "object": "hall"}, {"action": "查看", "object": None}]},
         "x": {"candidates": [{"id": "hall", "name": "门厅"}], "character": {"id": "lu", "name": "路明非"}}},
    ]
    scored = score_rows(rows, [
        {"step": 1, "actions": ["观察"], "objects": ["nono"]},
        {"step": 0, "actions": [], "objects": []},
        {"step": 2, "actions": ["移动", "检查"], "objects": ["hall", None]},
    ], labels)
    assert scored["rows"] == 3, scored
    assert scored["skipRows"] == 1 and scored["skipRecall"] == 1.0, scored
    assert scored["primaryGroupHit"] == 1.0, scored
    assert scored["fullHit"] == round(1 / 3, 4), scored  # r3's second predicate differs
    assert scored["perGroup"]["感知"]["rows"] == 1 and scored["perGroup"]["感知"]["hits"] == 1, scored["perGroup"]
    # a skip-prediction on a non-skip row is a wrong action, not a free pass
    scored2 = score_rows([rows[0]], [{"step": 0, "actions": [], "objects": []}], labels)
    assert scored2["wrongActionRate"] == 1.0 and scored2["fullHit"] == 0.0, scored2
    print(json.dumps({"selfTest": "ok", "checks": 5, "primaryGroupHit": scored["primaryGroupHit"]}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--rows")
    parser.add_argument("--predictions")
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--max-len", type=int)
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.predictions:
        rows = read_rows(args.rows)
        predictions = [json.loads(line) for line in pathlib.Path(args.predictions).read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        from transformers.models.bert.tokenization_bert import BertTokenizer
        labels = load_labels()
        rows = read_rows(args.rows)
        predictions = predict(rows, base=args.base, head=args.head, max_len=int(args.max_len),
                              labels=labels, tokenizer=BertTokenizer.from_pretrained(args.base))
    labels = load_labels()
    scored = score_rows(rows, predictions, labels)
    result = {**scored, "perGoal": per_goal(rows, scored), "scoredAt": dt.datetime.now(dt.timezone.utc).isoformat(),
              "rowsSha256": sha256_file(pathlib.Path(args.rows))}
    text = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
        print(f"scored -> {args.out} primaryGroupHit={result['primaryGroupHit']} fullHit={result['fullHit']}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
