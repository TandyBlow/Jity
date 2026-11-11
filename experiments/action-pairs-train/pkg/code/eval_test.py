"""Blind TEST inference for the frozen short-pair checkpoint (owner: 01/10).

Reads a rows file that contains only x (no y/yGroup), renders 13 pairs per row
with the frozen serializer, and writes one prediction per decision. No labels
are read, no metric is computed here; lane 01 joins predictions to the private
answers afterwards.
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--rows", required=True, help="blind rows: rowId + x, no y")
    parser.add_argument("--out", required=True)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    frozen = json.loads(pathlib.Path(args.freeze).read_text(encoding="utf-8"))
    groups = ps.load_predicate_groups(args.labels)
    rows = ps.load_rows(args.rows)
    for row in rows:
        if row.get("y") or row.get("yGroup"):
            raise SystemExit(f"REFUSED: {row.get('rowId')} carries labels; the blind file must not")
    checkpoint = torch.load(args.checkpoint, map_location="cpu")
    if checkpoint.get("serializerDigest") != frozen["serializer"]["digest"]:
        raise SystemExit("REFUSED: checkpoint serializer digest differs from the freeze")
    max_len = int(checkpoint.get("maxLen") or frozen.get("measurement", {}).get("maxLenCeil32"))
    device = torch.device("cuda" if (args.device in ("auto", "cuda") and torch.cuda.is_available()) else "cpu")
    torch.manual_seed(frozen["training"]["seed"])
    model = pm.PairwiseModel(args.base, dropout=frozen["training"]["dropout"])
    model.load_state_dict(checkpoint["state"])
    model.to(device).eval()
    tokenizer = BertTokenizer.from_pretrained(args.base, do_lower_case=True)
    decisions = [(row["rowId"], 0) for row in rows]
    dataset = pm.PairwiseDataset(rows, tokenizer, max_len, groups, decisions)
    out = []
    with torch.no_grad():
        for indices in dataset.decisions:
            batch = dataset.collate([dataset[i] for i in indices], tokenizer.pad_token_id)
            batch = {k: v.to(device) for k, v in batch.items()}
            logits = model(batch["input_ids"], batch["attention_mask"]).detach().cpu().tolist()
            prediction = pm.predict_decision(logits)
            first = dataset[indices[0]]
            out.append({"rowId": first["rowId"], "group": prediction["top1"],
                        "top2": prediction["top2"], "margin": round(prediction["margin"], 4),
                        "logits": [round(v, 4) for v in logits]})
    pathlib.Path(args.out).write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in out), encoding="utf-8")
    print(json.dumps({"rows": len(out), "device": device.type, "maxLen": max_len}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
