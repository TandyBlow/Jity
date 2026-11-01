# N2 encoder-head candidate arm (batch 2): MiniRBT-H256 pooled 3-class head
# (must / may / omit) over (viewpoint rule + fact line), trained on the
# frozen 16-item dev set under item-level 2-fold cross-validation, scored
# with the SAME frozen v3 metric machinery as every other arm
# (recompute_must_v3.score_row / full_metrics), against the program rule
# arm (run_n2.arm_rule) on the identical folds.
#
# Scope honesty, recorded in the output:
#   - the 16-item set is C's development set; folds never train on their
#     eval items, but results are development-grade, NOT generalization
#     claims (formal held-out sets are still to be established);
#   - the program arm and this head see the same inputs; must-P/R is the
#     selection criterion (must-miss stays a hard failure per the frozen
#     N2 protocol), may-selection rate is reported but not gated;
#   - the 0.6B instruct arm is NOT run (coordinator pause); this head is
#     the only trainable N2 candidate this batch.

import argparse
import hashlib
import importlib.machinery
import json
import pathlib
import platform
import sys
import time
import types

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

import torch  # noqa: E402
from torch.utils.data import DataLoader, Dataset  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_n2  # noqa: E402
import recompute_must_v3 as rmv  # noqa: E402

LABELS = {"must": 0, "may": 1, "omit": 2}
INV = {v: k for k, v in LABELS.items()}


def sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_items_and_labels(items_path, labels_path):
    items = [json.loads(l) for l in
             pathlib.Path(items_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    labels = {}
    for l in pathlib.Path(labels_path).read_text(encoding="utf-8").splitlines():
        if l.strip():
            row = json.loads(l)
            labels[(row["itemId"], row["factId"])] = row["label"]
    v3 = []
    for item in items:
        v3.append(rmv.v3_item(item, labels))
    return v3


def encode_samples(item):
    """(text, label, factId) per fact: viewpoint rule + numbered fact line,
    the same fact vocabulary the existing N2 arms consume."""
    v = item["viewpoint"]
    out = []
    for i, f in enumerate(item["facts"]):
        label = ("must" if f["factId"] in item["must"]
                 else "may" if f["factId"] in item["omittable"]
                 else "omit")
        text = f"视角规则：{v['rule']}。事实：{run_n2.fact_line(i + 1, f)}"
        out.append((text, LABELS[label], f["factId"]))
    return out


class PairDataset(Dataset):
    def __init__(self, samples, tokenizer, max_len=160):
        self.samples = samples
        self.tok = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        text, label, _ = self.samples[i]
        enc = self.tok(text, truncation=True, max_length=self.max_len,
                       padding="max_length", return_tensors="pt")
        return {k: v[0] for k, v in enc.items()}, label


def train_fold(model_dir, train_samples, device, epochs=20, seed=20261101):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    torch.manual_seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_dir, num_labels=3).to(device)
    counts = [0, 0, 0]
    for _, y, _ in train_samples:
        counts[y] += 1
    weights = torch.tensor([sum(counts) / (3 * c) if c else 1.0 for c in counts],
                           device=device)
    ds = PairDataset(train_samples, tok)
    loader = DataLoader(ds, batch_size=8, shuffle=True,
                        generator=torch.Generator().manual_seed(seed))
    opt = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=0.01)
    model.train()
    t0 = time.perf_counter()
    for epoch in range(epochs):
        for batch, y in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            y = y.to(device)
            loss = torch.nn.functional.cross_entropy(
                model(**batch).logits, y, weight=weights)
            opt.zero_grad()
            loss.backward()
            opt.step()
    train_seconds = time.perf_counter() - t0
    return model, tok, {"trainSeconds": round(train_seconds, 1),
                        "classCounts": dict(zip(LABELS, counts)),
                        "classWeights": [round(w, 3) for w in weights.tolist()]}


def predict(model, tok, samples, device):
    model.eval()
    out = []
    with torch.no_grad():
        for text, _, fact_id in samples:
            enc = tok(text, truncation=True, max_length=160,
                      return_tensors="pt").to(device)
            pred = int(model(**enc).logits[0].argmax())
            out.append((fact_id, INV[pred]))
    return out


def arm_rows(items, selections_by_item):
    rows = []
    for item in items:
        sel = selections_by_item[item["itemId"]]
        rows.append(rmv.score_row(item, {"selected": sel}))
    return rows


def program_selections(items):
    out = {}
    for item in items:
        # arm_rule selects 1-based positions; the frozen v3 machinery scores
        # factId lists — convert per the item's own fact order
        selected, _ = run_n2.arm_rule(item)
        out[item["itemId"]] = [item["facts"][i - 1]["factId"] for i in sorted(selected)]
    return out


def pooled(rows):
    return rmv.full_metrics(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", default=str(HERE / "items.jsonl"))
    parser.add_argument("--labels", default=str(HERE / "annotation" / "labels-v3.jsonl"))
    parser.add_argument("--model-dir", default=str(HERE.parent / "assets" / "minirbt-h256-snapshot"))
    parser.add_argument("--device", default="auto")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import transformers
    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    v3 = load_items_and_labels(args.items, args.labels)
    item_ids = sorted(i["itemId"] for i in v3)
    halves = [item_ids[:len(item_ids) // 2], item_ids[len(item_ids) // 2:]]

    folds = []
    for fi, eval_ids in enumerate(halves):
        eval_items = [i for i in v3 if i["itemId"] in eval_ids]
        train_items = [i for i in v3 if i["itemId"] not in eval_ids]
        train_samples = [s for i in train_items for s in encode_samples(i)]
        eval_samples_by_item = {i["itemId"]: encode_samples(i) for i in eval_items}
        model, tok, train_info = train_fold(args.model_dir, train_samples,
                                            device, epochs=args.epochs)
        sel = {}
        for iid, samples in eval_samples_by_item.items():
            preds = predict(model, tok, samples, device)
            sel[iid] = [fid for fid, p in preds if p == "must"]
        head_rows = arm_rows(eval_items, sel)
        prog_rows = arm_rows(eval_items, program_selections(eval_items))
        folds.append({
            "fold": fi, "evalItemIds": sorted(eval_ids),
            "train": train_info,
            "head": {"perItem": head_rows, "pooled": pooled(head_rows)},
            "programRule": {"perItem": prog_rows, "pooled": pooled(prog_rows)},
        })

    all_head = [r for f in folds for r in f["head"]["perItem"]]
    all_prog = [r for f in folds for r in f["programRule"]["perItem"]]
    hard_fails = [r["itemId"] for r in all_head
                  if r["invalid"] or r["unknownIds"] or r["forbiddenHits"]
                  or r["duplicateSelectedIds"] or r["mustRecall"] < 0.95]

    archive = {
        "purpose": "N2 encoder-head candidate arm (batch 2): MiniRBT-H256 "
                   "3-class salience head, item-level 2-fold CV on the "
                   "frozen v3 dev set, same frozen metric machinery as all "
                   "arms; program rule arm on identical folds as reference",
        "scopeNote": "development-grade numbers on C's dev set; folds never "
                     "train on their eval items, but this is NOT a "
                     "generalization claim; no formal held-out set exists "
                     "yet; 0.6B instruct arm not run (coordinator pause)",
        "model": {"dir": "minirbt-h256-snapshot",
                  "sha256": sha_file(pathlib.Path(args.model_dir) / "pytorch_model.bin")},
        "data": {"items": sha_file(args.items), "labels": sha_file(args.labels),
                 "folds": "item-level 2-fold (8/8), swap"},
        "config": {"epochs": args.epochs, "lr": 1e-4, "batch": 8,
                   "seed": 20261101, "device": device,
                   "selectionRule": "argmax(must)"},
        "environment": {"python": platform.python_version(),
                        "torch": torch.__version__,
                        "transformers": transformers.__version__,
                        "deviceName": (torch.cuda.get_device_name(0)
                                       if device == "cuda" else "cpu"),
                        "device": device},
        "folds": folds,
        "pooled": {"head": pooled(all_head), "programRule": pooled(all_prog)},
        "hardFails": hard_fails,
        "hardFailRule": "invalid/unknown/forbidden/duplicate selections or "
                        "mustRecall < 0.95 on any eval item",
        "pass": not hard_fails,
    }
    text = json.dumps(archive, ensure_ascii=False, indent=1) + "\n"
    pathlib.Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    hp, pp = archive["pooled"]["head"], archive["pooled"]["programRule"]
    print(f"head  must-R {hp['mustRecallMacro']:.3f} must-P {hp['mustPrecisionMacroNonempty']}")
    print(f"rule  must-R {pp['mustRecallMacro']:.3f} must-P {pp['mustPrecisionMacroNonempty']}")
    print("hardFails:", hard_fails or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
