"""Diagnostic (not the official model): are the frozen mean-pooled features
separable? Extract features once, then fit a small linear 13-way scorer on the
train decisions and report validation rowHit. Tells us whether the frozen probe
failed because of optimization scale or because the features carry no signal.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import torch
from transformers import BertTokenizer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pairwise_model as pm
import pairwise_serialize as ps
import pairwise_train as pt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--pairs-freeze", required=True)
    ap.add_argument("--valid-rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    groups = ps.load_predicate_groups(args.labels)
    pairs = pt.load_frozen_pairs(pathlib.Path(args.pairs), pathlib.Path(args.pairs_freeze))
    rows = json.loads(pathlib.Path(args.valid_rows).read_text(encoding="utf-8"))["rows"]
    tokenizer = BertTokenizer.from_pretrained(args.base, do_lower_case=True)
    model = pm.PairwiseModel(args.base, dropout=0.0).to(device).eval()
    for p in model.parameters():
        p.requires_grad_(False)

    def encode(texts):
        feats = []
        with torch.no_grad():
            for start in range(0, len(texts), 64):
                batch = texts[start:start + 64]
                enc = tokenizer(batch, padding=True, truncation=False, return_tensors="pt")
                enc = {k: v.to(device) for k, v in enc.items()}
                out = model.encoder(input_ids=enc["input_ids"],
                                    attention_mask=enc["attention_mask"]).last_hidden_state
                mask = enc["attention_mask"].unsqueeze(-1).to(out.dtype)
                pooled = (out * mask).sum(1) / mask.sum(1).clamp(min=1.0)
                feats.append(pooled.cpu())
        return torch.cat(feats)

    by_decision = {}
    for pair in pairs:
        by_decision.setdefault((pair["rowId"], pair["stepIndex"]), []).append(pair)
    keys = sorted(by_decision)
    train_texts = [p["text"] for key in keys for p in by_decision[key]]
    train_labels = [[p["label"] for p in by_decision[key]] for key in keys]
    X_train = encode(train_texts).view(len(keys), 13, -1)
    v_texts = []
    v_gold = []
    for row in rows:
        rendered = ps.pairs_for_row(row, groups)[:13]
        v_texts.extend(pair["text"] for pair in rendered)
        v_gold.append(next(i for i, pair in enumerate(rendered) if pair["label"] == 1))
    X_valid = encode(v_texts).view(len(rows), 13, -1)

    mean = X_train.view(-1, X_train.shape[-1]).mean(0)
    std = X_train.view(-1, X_train.shape[-1]).std(0).clamp(min=1e-6)
    Z = (X_train - mean) / std
    Zv = (X_valid - mean) / std
    Zg, Zvg = Z.to(device), Zv.to(device)

    w = torch.zeros(Z.shape[-1], requires_grad=True, device=device)
    b0 = torch.zeros(1, requires_grad=True, device=device)
    opt = torch.optim.Adam([w, b0], lr=1e-2)
    lbl = torch.tensor(train_labels, device=device, dtype=torch.float32)
    for step in range(600):
        logits = Zg @ w + b0
        loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, lbl)
        opt.zero_grad(); loss.backward(); opt.step()
    with torch.no_grad():
        v_logits = Zvg @ w + b0
        pred = v_logits.argmax(1).cpu().tolist()
        train_logits = Zg @ w + b0
        train_pred = train_logits.argmax(1).cpu().tolist()
    train_hit = sum(p == g for p, g in zip(train_pred, [l.index(1) for l in train_labels])) / len(train_labels)
    val_hit = sum(p == g for p, g in zip(pred, v_gold)) / len(v_gold)
    payload = {"kind": "feature-probe-diagnostic", "trainDecisions": len(keys), "validDecisions": len(rows),
               "trainRowHit": round(train_hit, 4), "validRowHit": round(val_hit, 4),
               "featureStdMean": float(std.mean()), "featureStdMax": float(std.max()),
               "validPred": pred, "validGold": v_gold, "device": device.type}
    pathlib.Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("trainRowHit", "validRowHit", "featureStdMean")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
