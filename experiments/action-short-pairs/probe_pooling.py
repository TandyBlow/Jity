# -*- coding: utf-8 -*-
"""Zero-gradient pooling probe for the short-pair task (measurement, not training).

The authorised run (job 254378) trained only the linear head on a frozen
encoder with masked-mean pooling, and reached 20% rowHit on 01's 15 validation
decisions. Before calling that a property of the data, this script measures how
much of the failure is the pooling choice:

  * the 13 candidate texts of one decision differ only in the last token
    (`动作：<group>`); masked-mean pooling over ~163 tokens dilutes that;
  * this probe computes frozen-encoder features at three pooling points
    (masked mean, [CLS], last non-pad token), fits a multinomial logistic
    regression on the train rows and scores the same 13-way argmax on the
    validation rows.

It trains no network weights of the pair model; the probe classifier is a
separate diagnostic and is never reported as a candidate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModel, BertTokenizer

sys.path.insert(0, str(Path(__file__).parent))
import pairwise_serialize as ps  # noqa: E402


def load_rows(path: Path):
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
        if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
            return payload["rows"]
    except json.JSONDecodeError:
        pass
    return [json.loads(line) for line in text.splitlines() if line.strip()]


@torch.no_grad()
def features(model, tokenizer, texts, max_len, batch=16):
    mean, cls, last = [], [], []
    for start in range(0, len(texts), batch):
        chunk = texts[start:start + batch]
        encoded = tokenizer(chunk, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        out = model(input_ids=encoded["input_ids"], attention_mask=encoded["attention_mask"]).last_hidden_state
        mask = encoded["attention_mask"].unsqueeze(-1).float()
        mean.append(((out * mask).sum(1) / mask.sum(1)).numpy())
        cls.append(out[:, 0, :].numpy())
        lengths = encoded["attention_mask"].sum(1) - 1
        last.append(out[torch.arange(out.shape[0]), lengths, :].numpy())
    return {"mean": np.concatenate(mean), "cls": np.concatenate(cls), "last": np.concatenate(last)}


def decision_rows(rows, groups, tokenizer, split):
    texts, labels, row_ids, steps = [], [], [], []
    for row in rows:
        for step in range(max(1, ps.step_count(row))):
            for pair in ps.pairs_for_step(row, step, predicate_to_group=groups):
                texts.append(pair["text"])
                labels.append(pair["label"])
                row_ids.append(row["rowId"])
                steps.append(step)
    return texts, np.array(labels), row_ids, steps


def argmax_per_decision(scores, labels, row_ids, steps, decisions):
    """13 candidates per decision, in order; picks the top-scoring candidate."""
    hits, golds, preds = 0, [], []
    index = 0
    for row_id, step in decisions:
        block = np.arange(index, index + 13)
        gold = int(np.argmax(labels[block]))
        pred = int(np.argmax(scores[block]))
        hits += int(gold == pred)
        golds.append(gold)
        preds.append(pred)
        index += 13
    return {"decisions": len(decisions), "rowHit": round(hits / max(1, len(decisions)), 4),
            "confusion": list(zip(golds, preds))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", required=True)
    parser.add_argument("--val", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--max-len", type=int, default=224)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    groups = ps.load_predicate_groups(args.labels)
    train = [row for row in load_rows(Path(args.rows))]
    val = load_rows(Path(args.val))
    tokenizer = BertTokenizer.from_pretrained(args.base, do_lower_case=True)
    model = AutoModel.from_pretrained(args.base).eval()

    tr_texts, tr_labels, tr_ids, tr_steps = decision_rows(train, groups, tokenizer, "train")
    va_texts, va_labels, va_ids, va_steps = decision_rows(val, groups, tokenizer, "val")
    print(json.dumps({"trainPairs": len(tr_texts), "valPairs": len(va_texts)}), flush=True)

    tr_feat = features(model, tokenizer, tr_texts, args.max_len)
    va_feat = features(model, tokenizer, va_texts, args.max_len)
    train_decisions = [(tr_ids[i], tr_steps[i]) for i in range(0, len(tr_ids), 13)]
    val_decisions = [(va_ids[i], va_steps[i]) for i in range(0, len(va_ids), 13)]

    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    report = {"kind": "short-pair-pooling-probe", "note": "diagnostic only; not a candidate",
              "trainPairs": len(tr_texts), "valPairs": len(va_texts), "poolings": {}}
    for name in ("mean", "cls", "last"):
        # unscaled MiniRBT features saturate the solver into a constant
        # probability for every candidate (the first probe did exactly that and
        # predicted the majority group for all 325 decisions)
        clf = make_pipeline(StandardScaler(),
                            LogisticRegression(max_iter=4000, C=0.05, class_weight="balanced"))
        clf.fit(tr_feat[name], tr_labels)
        tr_score = argmax_per_decision(clf.predict_proba(tr_feat[name])[:, 1], tr_labels, tr_ids, tr_steps,
                                       train_decisions)
        va_score = argmax_per_decision(clf.predict_proba(va_feat[name])[:, 1], va_labels, va_ids, va_steps,
                                       val_decisions)
        report["poolings"][name] = {"train": tr_score, "validation": va_score}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, entry in report["poolings"].items():
        print(name, "train", entry["train"]["rowHit"], "validation", entry["validation"]["rowHit"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
