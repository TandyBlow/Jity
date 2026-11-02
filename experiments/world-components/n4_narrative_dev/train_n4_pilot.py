# N4 32-case scaling pilot (runs on the HPC GPU).
#
# 22 train / 4 dev / 6 frozen same-world holdout. This is a scaling pilot,
# not a formal quality or generalization gate: the holdout comes from the
# same n4n-fog-harbor world and the 20 v1 cases were human-reviewed.
#
# Usage: python train_n4_pilot.py --epochs 120
# Output: ckpt-pilot/ + train-pilot-report.json

import argparse
import copy
import hashlib
import json
import pathlib
import random
import sys
import time

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
PAIRS = HERE / "pilot_pairs.jsonl"
FREEZE = HERE / "pilot-freeze.json"
BASE = pathlib.Path("base/randeng-t5-77m")
SEED = 20261102
BATCH = 4
LR = 1e-4
MAX_INPUT = 512
MAX_OUTPUT = 128


def sha_file(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def norm_punct(text):
    return (text.replace("，", ",").replace("；", ";")
                .replace("：", ":").replace("？", "?").replace("！", "!"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--eval-every", type=int, default=10)
    parser.add_argument("--patience", type=int, default=40)
    parser.add_argument("--no-early-stop", action="store_true",
                        help="train the full epoch budget; use the final "
                             "model for samples (scaling pilot)")
    parser.add_argument("--base", default=str(BASE))
    parser.add_argument("--out", default="ckpt-pilot")
    args = parser.parse_args()

    rows = [json.loads(line) for line in
            PAIRS.read_text(encoding="utf-8").splitlines() if line.strip()]
    train = [r for r in rows if r["split"] == "pilot-train"]
    dev = [r for r in rows if r["split"] == "pilot-dev"]
    hold = [r for r in rows if r["split"] == "pilot-holdout"]
    assert (len(train), len(dev), len(hold)) == (22, 4, 6), (
        len(train), len(dev), len(hold))
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    hold_hash = hashlib.sha256(
        "".join(r["input"] for r in hold).encode("utf-8")).hexdigest()
    if hold_hash != freeze["inputSha256"]:
        print("REFUSED: holdout input hash differs from the freeze")
        return 2
    print(f"train {len(train)} dev {len(dev)} holdout {len(hold)}; "
          f"epochs {args.epochs}")

    tok = T5Tokenizer.from_pretrained(args.base, legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        args.base, torch_dtype=torch.float32)
    assert torch.cuda.is_available(), "the pilot expects the HPC GPU"
    device = "cuda"
    model.to(device)
    torch.manual_seed(SEED)
    random.seed(SEED)

    def encode(batch):
        enc = tok([r["input"] for r in batch], padding=True,
                  truncation=True, max_length=MAX_INPUT,
                  return_tensors="pt")
        with tok.as_target_tokenizer():
            labels = tok([r["target"] for r in batch], padding=True,
                         truncation=True, max_length=MAX_OUTPUT,
                         return_tensors="pt")
        labels.input_ids[labels.input_ids == tok.pad_token_id] = -100
        return enc, labels

    def split_loss(batch):
        enc, labels = encode(batch)
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            out = model(**enc, labels=labels.input_ids.to(device))
        return round(float(out.loss), 4)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    order = list(range(len(train)))
    steps_per_epoch = (len(train) + BATCH - 1) // BATCH
    total_steps = steps_per_epoch * args.epochs
    step, t0 = 0, time.perf_counter()
    history = []
    best = {"epoch": 0, "dev": None, "state": None}
    model.train()
    for epoch in range(1, args.epochs + 1):
        random.shuffle(order)
        for start in range(0, len(order), BATCH):
            batch = [train[i] for i in order[start:start + BATCH]]
            enc, labels = encode(batch)
            enc = {k: v.to(device) for k, v in enc.items()}
            out = model(**enc, labels=labels.input_ids.to(device))
            optimizer.zero_grad()
            out.loss.backward()
            optimizer.step()
            step += 1
        if epoch % args.eval_every == 0 or epoch == args.epochs:
            dev_loss = split_loss(dev)
            history.append({"epoch": epoch, "dev": dev_loss})
            print(f"epoch {epoch} step {step}/{total_steps} dev {dev_loss:.4f}",
                  flush=True)
            if best["dev"] is None or dev_loss < best["dev"]:
                best = {"epoch": epoch, "dev": dev_loss,
                        "state": copy.deepcopy(model.state_dict())}
            elif (not args.no_early_stop
                  and epoch - best["epoch"] >= args.patience):
                print(f"early stop at epoch {epoch}; best {best['epoch']}",
                      flush=True)
                break
    wall = round(time.perf_counter() - t0, 1)
    selected = "final" if args.no_early_stop else "best-dev"
    if selected == "best-dev" and best["state"] is not None:
        model.load_state_dict(best["state"])
    out_dir = pathlib.Path(args.out)
    model.save_pretrained(str(out_dir))
    tok.save_pretrained(str(out_dir))

    model.eval()
    samples = []
    for r in rows:
        enc = tok(r["input"], return_tensors="pt", truncation=True,
                  max_length=MAX_INPUT).to(device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=MAX_OUTPUT,
                                 num_beams=1, do_sample=False)
        text = tok.decode(gen[0], skip_special_tokens=True)
        samples.append({
            "rowId": r["rowId"], "split": r["split"],
            "loss": split_loss([r]),
            "exactNormalized": norm_punct(text) == norm_punct(r["target"]),
            "output": text, "target": r["target"],
        })

    def mean_loss(split):
        vals = [s["loss"] for s in samples if s["split"] == split]
        return round(sum(vals) / len(vals), 4) if vals else None

    def exact_count(split):
        return sum(1 for s in samples
                   if s["split"] == split and s["exactNormalized"])

    report = {
        "purpose": "N4 32-case scaling pilot; not a formal quality gate",
        "data": {
            "pairs": "pilot_pairs.jsonl", "sha256": sha_file(PAIRS),
            "freeze": freeze,
            "train": len(train), "dev": len(dev), "holdout": len(hold),
        },
        "hyper": {
            "seed": SEED, "epochsRequested": args.epochs,
            "steps": total_steps, "batch": BATCH, "lr": LR,
            "optimizer": "AdamW", "precision": "fp32",
            "maxInput": MAX_INPUT, "maxOutput": MAX_OUTPUT,
            "evalEvery": args.eval_every, "patience": args.patience,
            "device": torch.cuda.get_device_name(0),
        },
        "selected": selected,
        "bestDev": {"epoch": best["epoch"], "devLoss": best["dev"]},
        "finalEpoch": epoch,
        "loss": {
            "train": mean_loss("pilot-train"),
            "dev": mean_loss("pilot-dev"),
            "holdout": mean_loss("pilot-holdout"),
        },
        "exactNormalized": {
            "train": exact_count("pilot-train"),
            "dev": exact_count("pilot-dev"),
            "holdout": exact_count("pilot-holdout"),
        },
        "history": history,
        "wallSeconds": wall,
        "samples": samples,
        "notes": [
            "Same-world holdout; not a final generalization set.",
            "Early stopping uses the 4-case dev split; the holdout is only "
            "reported at the best-dev checkpoint.",
            "Exact match is normalized for T5 punctuation.",
        ],
    }
    pathlib.Path("train-pilot-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("selected:", selected, "bestDev:",
          json.dumps(report["bestDev"], ensure_ascii=False))
    print("loss:", json.dumps(report["loss"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
