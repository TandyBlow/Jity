# N5 relation-head eval (commit 3). Pre-registered HERE before any training:
#
#   G1 wrong-pass (hard): ZERO contradiction pairs may be judged support on
#      the test split (an error negative must never pass).
#   G2 wrong-reject cap (hard): ZERO support pairs may be judged
#      contradiction on the test split.
#   G3 support floor (hard): support pairs judged support >= 0.60 (the
#      minimum pass rate registered before training).
#   G4 contradiction floor (hard): contradiction pairs judged contradiction
#      >= 0.60.
#   unknown pairs are the PENDING class by construction: they gate nothing
#   and their rate is REPORTED per class (a pair judged unknown is 待核).
#
# Threshold rule (fixed on the DEV split before the test split is loaded):
#   T_SUPPORT / T_CONTRADICT range over a fixed grid; pick the SMALLEST
#   pair (T_S, T_C) on the grid such that on dev
#     dev contradiction->support == 0 and dev support->contradiction == 0
#   and both dev floors (>= 0.60) hold; if no grid point satisfies all
#   four, the eval FAILS with the dev table attached (no test numbers are
#   consulted — the thresholds never see the test split).

import argparse
import hashlib
import importlib.machinery
import json
import pathlib
import sys
import types

# F6 process stubs (same as eval_n4_finetune.py / export_n5_onnx.py): the
# base env's pyarrow wheel is ABI-broken against numpy 2.x and sklearn
# transitively imports it through transformers.generation; stubbing it
# before torch/transformers keeps the local CPU eval alive.
try:
    import pyarrow  # noqa: F401
except Exception:
    _stub = types.ModuleType("pyarrow")
    _stub.__version__ = "16.1.0"
    _stub.__path__ = []
    sys.modules["pyarrow"] = _stub
_tf = types.ModuleType("tensorflow")
_tf.__spec__ = importlib.machinery.ModuleSpec("tensorflow", None)
_tf.__path__ = []
sys.modules.setdefault("tensorflow", _tf)

import torch
from torch import nn

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "n4_corpus"))
PAIRS = HERE / "corpus_v2" / "n5"
LABELS = {"support": 0, "contradiction": 1, "unknown": 2}
NAMES = {v: k for k, v in LABELS.items()}
GRID = [round(0.40 + 0.05 * i, 2) for i in range(10)]  # 0.40..0.85
FLOOR = 0.60


def pair_text(pair: dict) -> str:
    from build_n5_pairs import fact_desc
    return f"句子：{pair['sentence']}事实：{fact_desc(pair['fact'])}关系："


def predict(model, tok, pairs, batch=64):
    model.eval()
    out = []
    with torch.no_grad():
        for s in range(0, len(pairs), batch):
            chunk = pairs[s:s + batch]
            enc = tok([pair_text(p) for p in chunk], padding=True,
                      truncation=True, max_length=96, return_tensors="pt")
            logits = model(**enc)
            probs = torch.softmax(logits, dim=-1)
            out.extend(probs.tolist())
    return out


def judge(probs, t_s, t_c):
    labels = []
    for p in probs:
        if p[LABELS["support"]] >= t_s:
            labels.append("support")
        elif p[LABELS["contradiction"]] >= t_c:
            labels.append("contradiction")
        else:
            labels.append("unknown")
    return labels


def rates(pairs, labels):
    from collections import Counter
    cm = Counter((p["label"], l) for p, l in zip(pairs, labels))
    n = {k: sum(1 for p in pairs if p["label"] == k) for k in LABELS}
    return {
        "confusion": {f"{g}->{j}": cm.get((g, j), 0)
                      for g in LABELS for j in NAMES.values()},
        "supportRate": cm.get(("support", "support"), 0) / n["support"],
        "contradictionRate": cm.get(("contradiction", "contradiction"), 0)
        / n["contradiction"],
        "wrongPass": cm.get(("contradiction", "support"), 0),
        "wrongReject": cm.get(("support", "contradiction"), 0),
        "pendingRate": {k: cm.get((k, "unknown"), 0) / n[k]
                        for k in LABELS},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=str(HERE / "ckpt-n5"))
    parser.add_argument("--out", default=str(HERE.parents[2] / "artifacts" /
                                             "world-components" /
                                             "n5-relation-eval.json"))
    args = parser.parse_args()
    from transformers.models.bert.tokenization_bert import BertTokenizer
    from train_n5_head import RelationHead
    tok = BertTokenizer.from_pretrained(args.model)
    model = RelationHead(args.model)
    sd = torch.load(pathlib.Path(args.model).parent / "head-n5.pt",
                    map_location="cpu", weights_only=True)
    model.classifier.load_state_dict(sd["classifier"])
    model.eval()

    rows = [json.loads(l) for l in
            (PAIRS / "train.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    dev = [r for r in rows if r["split"] == "dev"]
    dev_probs = predict(model, tok, dev)
    # threshold fixing on dev ONLY
    chosen = None
    table = []
    for t_s in GRID:
        for t_c in GRID:
            labels = judge(dev_probs, t_s, t_c)
            r = rates(dev, labels)
            ok = (r["wrongPass"] == 0 and r["wrongReject"] == 0
                  and r["supportRate"] >= FLOOR
                  and r["contradictionRate"] >= FLOOR)
            table.append({"t_s": t_s, "t_c": t_c, "ok": ok,
                          "supportRate": round(r["supportRate"], 3),
                          "contradictionRate": round(r["contradictionRate"], 3),
                          "wrongPass": r["wrongPass"],
                          "wrongReject": r["wrongReject"]})
            if ok and chosen is None:
                chosen = (t_s, t_c)
    if chosen is None:
        archive = {"pass": False,
                   "reason": "no dev threshold pair satisfies the "
                             "pre-registered gates",
                   "devTable": table}
        pathlib.Path(args.out).write_text(
            json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        print("FAIL: no dev thresholds; see", args.out)
        return 1
    t_s, t_c = chosen
    test = [json.loads(l) for l in
            (PAIRS / "test.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    freeze = json.loads((PAIRS / "test-freeze.json").read_text(
        encoding="utf-8"))
    got = hashlib.sha256((PAIRS / "test.jsonl").read_bytes()).hexdigest()
    if got != freeze["sha256"]:
        print("REFUSED: test set moved after the freeze")
        return 2
    test_probs = predict(model, tok, test)
    labels = judge(test_probs, t_s, t_c)
    r = rates(test, labels)
    gates = {
        "G1_no_wrong_pass": r["wrongPass"] == 0,
        "G2_no_wrong_reject": r["wrongReject"] == 0,
        "G3_support_floor": r["supportRate"] >= FLOOR,
        "G4_contradiction_floor": r["contradictionRate"] >= FLOOR,
    }
    predictions = [
        {"pairId": p["pairId"], "label": p["label"], "pred": l,
         "probs": [round(float(x), 6) for x in probs]}
        for p, l, probs in zip(test, labels, test_probs)]
    wrong_reject_ids = [p["pairId"] for p, l in zip(test, labels)
                        if p["label"] == "support" and l == "contradiction"]
    archive = {
        "purpose": "N5 relation-head frozen-test eval (commit 3)",
        "model": {"dir": str(pathlib.Path(args.model).resolve()
                             .relative_to(HERE.parents[2]).as_posix()),
                  "encoderSha256": hashlib.sha256(
                      (pathlib.Path(args.model) / "model.safetensors")
                      .read_bytes()).hexdigest()},
        "thresholds": {"t_support": t_s, "t_contradict": t_c,
                       "rule": "smallest dev-grid pair with zero wrong-pass/"
                               "wrong-reject and both floors; test untouched "
                               "during fixing"},
        "devSummary": {"pairs": len(dev), "table": table},
        "test": {"pairs": len(test), **r},
        "wrongRejectPairIds": wrong_reject_ids,
        "testPredictions": predictions,
        "gates": gates, "pass": all(gates.values()),
    }
    pathlib.Path(args.out).write_text(
        json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(json.dumps({"thresholds": archive["thresholds"],
                      "test": {k: v for k, v in r.items()},
                      "gates": gates, "pass": archive["pass"]},
                     ensure_ascii=False, indent=1)[:900])
    return 0 if archive["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
