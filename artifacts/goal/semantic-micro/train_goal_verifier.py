#!/usr/bin/env python3
"""Train a goal-level task verifier (MiniRBT + 2-class head) on real-turn pairs.

Labels follow the committed/support behavior (E55 dataset). The frozen eight
scenarios and twenty-input evidence never appear in train/val/test.

Usage:
  python artifacts/goal/semantic-micro/train_goal_verifier.py \
      --data experiments/semantic-micro/dataset \
      --snapshot D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot \
      --out artifacts/goal/semantic-micro/models
"""
import argparse
import json
import os
import random
from collections import Counter

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import classification_report, confusion_matrix
from transformers import BertModel, BertTokenizer

MAXLEN = 192


class GoalVerifier(nn.Module):
    def __init__(self, snapshot):
        super().__init__()
        self.bert = BertModel.from_pretrained(snapshot)
        self.head = nn.Linear(self.bert.config.hidden_size, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.head(cls)


def load(path):
    if not os.path.exists(path):
        return []
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def bin_label(row):
    return 1 if row.get("label") == "yes" else 0


def encode(tokenizer, rows):
    feats = []
    for row in rows:
        enc = tokenizer((row.get("goal") or "") + " \u241f " + row.get("factText", ""),
                        truncation=True, max_length=MAXLEN, padding=False)
        feats.append({"ids": enc["input_ids"], "mask": enc["attention_mask"], "label": bin_label(row)})
    return feats


def batchify(feats, batch):
    pad = max(len(row["ids"]) for row in batch)
    ids = torch.tensor([row["ids"] + [0] * (pad - len(row["ids"])) for row in batch])
    mask = torch.tensor([row["mask"] + [0] * (pad - len(row["mask"])) for row in batch])
    labels = torch.tensor([row["label"] for row in batch])
    return ids, mask, labels


def predict(model, tokenizer, rows, device):
    model.eval()
    out = []
    with torch.no_grad():
        for start in range(0, len(rows), 32):
            chunk = encode(tokenizer, rows[start:start + 32])
            ids, mask, _ = batchify(chunk, chunk)
            out.extend(model(ids.to(device), mask.to(device)).argmax(dim=1).cpu().tolist())
    return out


def report(name, y, p):
    print(f"\n== {name} n={len(y)} yes={sum(y)}")
    print(confusion_matrix(y, p, labels=[0, 1]))
    print(classification_report(y, p, labels=[0, 1], target_names=["no", "yes"], zero_division=0, digits=3))
    return {
        "n": len(y), "yes": int(sum(y)),
        "accuracy": float((np.array(y) == np.array(p)).mean()) if y else None,
        "confusion": confusion_matrix(y, p, labels=[0, 1]).tolist(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="experiments/semantic-micro/dataset")
    parser.add_argument("--snapshot", default="D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot")
    parser.add_argument("--bench", default="experiments/semantic-micro/bench-v1.jsonl")
    parser.add_argument("--out", default="artifacts/goal/semantic-micro/models")
    parser.add_argument("--epochs", type=int, default=20)
    args = parser.parse_args()
    random.seed(20261128)
    torch.manual_seed(20261128)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    os.makedirs(args.out, exist_ok=True)
    tokenizer = BertTokenizer(vocab_file=os.path.join(args.snapshot, "vocab.txt"))
    train_rows = load(os.path.join(args.data, "train.jsonl"))
    val_rows = load(os.path.join(args.data, "val.jsonl"))
    test_rows = load(os.path.join(args.data, "test.jsonl"))
    frozen_rows = load(os.path.join(args.data, "eval_frozen.jsonl"))
    bench_rows = [row for row in load(args.bench) if row.get("verdict") in ("yes", "no")]
    train_feats = encode(tokenizer, train_rows)
    model = GoalVerifier(args.snapshot).to(device)
    counts = Counter(row["label"] for row in train_feats)
    weights = torch.tensor([len(train_feats) / (2 * max(counts[cls], 1)) for cls in (0, 1)],
                           dtype=torch.float, device=device)
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    best = {"f1": -1, "epoch": -1, "state": None}
    for epoch in range(args.epochs):
        model.train()
        random.shuffle(train_feats)
        for start in range(0, len(train_feats), 16):
            chunk = train_feats[start:start + 16]
            ids, mask, labels = batchify(chunk, chunk)
            opt.zero_grad()
            loss = loss_fn(model(ids.to(device), mask.to(device)), labels.to(device))
            loss.backward()
            opt.step()
        val_p = predict(model, tokenizer, val_rows, device)
        val_y = [bin_label(row) for row in val_rows]
        tp = sum(1 for y, p in zip(val_y, val_p) if y == 1 and p == 1)
        fp = sum(1 for y, p in zip(val_y, val_p) if y == 0 and p == 1)
        fn = sum(1 for y, p in zip(val_y, val_p) if y == 1 and p == 0)
        f1 = 2 * tp / max(1, 2 * tp + fp + fn)
        if f1 > best["f1"]:
            best = {"f1": f1, "epoch": epoch, "state": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}
        print(f"epoch {epoch}: val F1={f1:.3f}")
    model.load_state_dict(best["state"])
    metrics = {"best_val_f1": best["f1"], "best_epoch": best["epoch"]}
    for name, rows in (("val", val_rows), ("test", test_rows), ("frozen", frozen_rows)):
        p = predict(model, tokenizer, rows, device)
        metrics[name] = report(name, [bin_label(row) for row in rows], p)
    if bench_rows:
        p = predict(model, tokenizer, bench_rows, device)
        metrics["bench"] = report("bench-v1", [1 if row["verdict"] == "yes" else 0 for row in bench_rows], p)

    model.cpu().eval()
    sample = encode(tokenizer, test_rows[:2])
    ids, mask, _ = batchify(sample, sample)
    path = os.path.join(args.out, "goal-verifier-v1.onnx")
    torch.onnx.export(model, (ids, mask), path, input_names=["input_ids", "attention_mask"],
                      output_names=["logits"],
                      dynamic_axes={"input_ids": {0: "batch", 1: "len"},
                                    "attention_mask": {0: "batch", 1: "len"},
                                    "logits": {0: "batch"}}, opset_version=17)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8 = os.path.join(args.out, "goal-verifier-v1-int8.onnx")
    quantize_dynamic(path, int8, weight_type=QuantType.QInt8)
    import onnxruntime as ort
    session = ort.InferenceSession(int8, providers=["CPUExecutionProvider"])
    agree = 0
    test_feats = encode(tokenizer, test_rows)
    with torch.no_grad():
        for feat in test_feats:
            ids, mask, _ = batchify([feat], [feat])
            torch_pred = int(model(ids, mask).argmax(dim=1).item())
            onnx_pred = int(np.argmax(session.run(None, {"input_ids": ids.numpy(), "attention_mask": mask.numpy()})[0][0]))
            agree += torch_pred == onnx_pred
    metrics["parity"] = {"rows": len(test_feats), "agree": agree}
    metrics["bytes"] = {"onnx": os.path.getsize(path), "int8": os.path.getsize(int8)}
    metrics["params"] = sum(p.numel() for p in model.parameters())
    with open(os.path.join(args.out, "goal-verifier-v1-report.json"), "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=1)
    print(json.dumps(metrics, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
