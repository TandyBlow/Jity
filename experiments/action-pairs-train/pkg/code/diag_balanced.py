"""Diagnostic: fine-tune the same model on a class-balanced slice of TRAIN
decisions (max 8 per group) to see whether the collapse to 感知 is an imbalance
artifact. Not the official run; reported separately."""
from __future__ import annotations
import argparse, json, pathlib, sys, random, time
import torch
from transformers import BertTokenizer
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pairwise_model as pm, pairwise_serialize as ps, pairwise_train as pt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--labels", required=True)
    ap.add_argument("--freeze", required=True); ap.add_argument("--pairs", required=True)
    ap.add_argument("--pairs-freeze", required=True); ap.add_argument("--valid-rows", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--cap", type=int, default=8)
    args = ap.parse_args()
    frozen = json.loads(pathlib.Path(args.freeze).read_text(encoding="utf-8"))
    training = frozen["training"]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    groups = ps.load_predicate_groups(args.labels)
    pairs = pt.load_frozen_pairs(pathlib.Path(args.pairs), pathlib.Path(args.pairs_freeze))
    by_decision = {}
    for p in pairs:
        by_decision.setdefault((p["rowId"], p["stepIndex"]), []).append(p)
    by_group = {}
    for key, group in sorted(by_decision.items()):
        gold = next(p["group"] for p in group if p["label"] == 1)
        by_group.setdefault(gold, []).append(key)
    rng = random.Random(training["seed"])
    chosen = []
    for gold, keys in by_group.items():
        rng.shuffle(keys)
        chosen.extend(keys[:args.cap])
    sub = [p for key in chosen for p in by_decision[key]]
    tok = BertTokenizer.from_pretrained(args.base, do_lower_case=True)
    torch.manual_seed(training["seed"]); random.seed(training["seed"])
    model = pm.PairwiseModel(args.base, dropout=training["dropout"]).to(device)
    opt = torch.optim.AdamW([
        {"params": model.encoder.parameters(), "lr": training["lrEncoder"]},
        {"params": model.head.parameters(), "lr": training["lrHead"]},
    ], weight_decay=training["weightDecay"])
    ds = pm.PairsDataset(sub, tok, 224)
    for epoch in range(1, 13):
        stats = pt.run_epoch(model, ds, tok, opt, training["batchDecisions"], training["seed"] + epoch, device)
        res = pt.evaluate(model, ds, tok, device)
        print(json.dumps({"epoch": epoch, "loss": round(stats["loss"], 4),
                          "trainRowHit": res["step1"]["rowHit"]}, ensure_ascii=False), flush=True)
    rows = json.loads(pathlib.Path(args.valid_rows).read_text(encoding="utf-8"))["rows"]
    vds = pm.PairwiseDataset(rows, tok, 224, groups, pt.decisions_of(rows))
    res = pt.evaluate(model, vds, tok, device)
    payload = {"kind": "balanced-slice-diagnostic", "capPerGroup": args.cap,
               "decisions": len(chosen), "perGroup": {g: len(v) for g, v in sorted(by_group.items())},
               "trainRowHit": pt.evaluate(model, ds, tok, device)["step1"]["rowHit"],
               "validRowHit": res["step1"]["rowHit"],
               "validPred": [r["pred"] for r in res["rows"]], "validGold": [r["gold"] for r in res["rows"]]}
    pathlib.Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("trainRowHit", "validRowHit", "decisions")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
