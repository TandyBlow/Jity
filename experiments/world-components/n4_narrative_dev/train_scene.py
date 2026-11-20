# Train and evaluate the N4 scene-sentence step (environment + interiority).
#
# Same-world dev pairs are held out from the 229-pair training set; the
# 23 new-world pairs are zero-shot. Strict binding is checked: the fact
# subject must appear, the result/destination must be covered, and no other
# named person or place may appear.
#
# Usage: python train_verbalizer.py --epochs 150
# Output: ckpt-verbalizer/ + verbalizer-report.json

import argparse
import json
import pathlib
import random
import re
import sys
import time

import torch
from scene_check import check as scene_check
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
TRAIN = HERE / "scene_pairs.jsonl"
HOLDOUT = HERE / "scene_holdout.jsonl"
BASE = pathlib.Path("base/randeng-t5-77m")
SEED = 20261103
BATCH = 8
LR = 1e-4
MAX_INPUT = 256
MAX_OUTPUT = 48
DEV_EVERY = 8

def norm_punct(t):
    return (t.replace("，", ",").replace("；", ";")
             .replace("：", ":").replace("？", "?").replace("！", "!"))


def check(row, text):
    c = scene_check(row, text)
    return {"binding": c["ok"], "reasons": c["reasons"],
            "actionHit": c["ok"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--eval-every", type=int, default=25)
    ap.add_argument("--base", default=str(BASE))
    ap.add_argument("--out", default="ckpt-scene")
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--ckpt", default="ckpt-scene")
    args = ap.parse_args()

    rows = [json.loads(l) for l in TRAIN.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    dev = [r for i, r in enumerate(rows) if i % DEV_EVERY == 0]
    train = [r for i, r in enumerate(rows) if i % DEV_EVERY != 0]
    hold = [json.loads(l) for l in
            HOLDOUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"train {len(train)} dev {len(dev)} holdout {len(hold)}")

    if args.eval_only:
        tok = T5Tokenizer.from_pretrained(args.ckpt, legacy=False)
        model = T5ForConditionalGeneration.from_pretrained(
            args.ckpt, torch_dtype=torch.float32)
    else:
        tok = T5Tokenizer.from_pretrained(args.base, legacy=False)
        model = T5ForConditionalGeneration.from_pretrained(
            args.base, torch_dtype=torch.float32)
    assert torch.cuda.is_available(), "expects the HPC GPU"
    device = "cuda"
    model.to(device)
    torch.manual_seed(SEED)
    random.seed(SEED)

    def encode(batch):
        enc = tok([r["input"] for r in batch], padding=True, truncation=True,
                  max_length=MAX_INPUT, return_tensors="pt")
        with tok.as_target_tokenizer():
            lab = tok([r["target"] for r in batch], padding=True,
                      truncation=True, max_length=MAX_OUTPUT,
                      return_tensors="pt")
        lab.input_ids[lab.input_ids == tok.pad_token_id] = -100
        return enc, lab

    def split_loss(batch):
        enc, lab = encode(batch)
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            out = model(**enc, labels=lab.input_ids.to(device))
        return round(float(out.loss), 4)

    def generate(batch):
        outs = []
        for r in batch:
            enc = tok(r["input"], return_tensors="pt", truncation=True,
                      max_length=MAX_INPUT).to(device)
            with torch.no_grad():
                gen = model.generate(**enc, max_new_tokens=MAX_OUTPUT,
                                     num_beams=1, do_sample=False)
            outs.append(tok.decode(gen[0], skip_special_tokens=True))
        return outs

    if args.eval_only:
        model.eval()
        dev_samples = generate(dev)
        train_samples = generate(train)
        hold_samples = generate(hold)
        res = {}
        for label, batch, texts in (("train", train, train_samples),
                                    ("dev", dev, dev_samples),
                                    ("newWorld", hold, hold_samples)):
            samples = [dict(pairId=r["pairId"], kind=r["kind"],
                            signature=[r["key"]], output=t,
                            target=r["target"],
                            exactNormalized=norm_punct(t) == norm_punct(r["target"]),
                            **check(r, t))
                       for r, t in zip(batch, texts)]
            res[label] = samples
            print(f"{label}: binding {sum(x['binding'] for x in samples)}"
                  f"/{len(samples)}", flush=True)
            for x in samples:
                if not x["binding"]:
                    print("  BAD", x["pairId"], x["reasons"], "|", x["output"],
                          flush=True)
        out = {
            "purpose": "N4 fact verbalizer eval-only",
            "ckpt": args.ckpt,
            "results": {k: {"rows": len(v),
                            "binding": sum(x["binding"] for x in v),
                            "actionHit": sum(x["actionHit"] for x in v),
                            "exactNormalized": sum(x["exactNormalized"] for x in v)}
                        for k, v in res.items()},
            "samples": res,
        }
        pathlib.Path("scene-report.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1)
            + chr(10),
            encoding="utf-8")
        print("results:", json.dumps(out["results"], ensure_ascii=False))
        return 0

    opt = torch.optim.AdamW(model.parameters(), lr=LR)
    order = list(range(len(train)))
    total = ((len(train) + BATCH - 1) // BATCH) * args.epochs
    step, t0 = 0, time.perf_counter()
    history = []
    model.train()
    for epoch in range(1, args.epochs + 1):
        random.shuffle(order)
        for s in range(0, len(order), BATCH):
            batch = [train[i] for i in order[s:s + BATCH]]
            enc, lab = encode(batch)
            enc = {k: v.to(device) for k, v in enc.items()}
            out = model(**enc, labels=lab.input_ids.to(device))
            opt.zero_grad()
            out.loss.backward()
            opt.step()
            step += 1
        if epoch % args.eval_every == 0 or epoch == args.epochs:
            dv = split_loss(dev)
            history.append({"epoch": epoch, "devLoss": dv})
            print(f"epoch {epoch} step {step}/{total} dev {dv:.4f}", flush=True)
    wall = round(time.perf_counter() - t0, 1)
    out_dir = pathlib.Path(args.out)
    model.save_pretrained(str(out_dir))
    tok.save_pretrained(str(out_dir))

    model.eval()

    def evaluate(batch, label):
        texts = generate(batch)
        samples = []
        for r, t in zip(batch, texts):
            c = check(r, t)
            samples.append({
                "pairId": r["pairId"], "kind": "scene",
                "signature": [r["key"]], "output": t,
                "target": r["target"],
                "exactNormalized": norm_punct(t) == norm_punct(r["target"]),
                **c,
            })
        print(f"{label}: binding {sum(s['binding'] for s in samples)}"
              f"/{len(samples)}", flush=True)
        return samples

    dev_samples = evaluate(dev, "dev")
    train_samples = evaluate(train, "train")
    hold_samples = evaluate(hold, "new-world")

    def summary(samples):
        return {
            "rows": len(samples),
            "binding": sum(s["binding"] for s in samples),
            "actionHit": sum(s["actionHit"] for s in samples),
            "exactNormalized": sum(s["exactNormalized"] for s in samples),
        }

    report = {
        "purpose": "N4 scene sentence: environment + POV interiority",
        "data": {"train": len(train), "dev": len(dev),
                 "newWorldHoldout": len(hold)},
        "hyper": {"seed": SEED, "epochs": args.epochs, "batch": BATCH,
                  "lr": LR, "optimizer": "AdamW", "precision": "fp32",
                  "maxInput": MAX_INPUT, "maxOutput": MAX_OUTPUT,
                  "device": torch.cuda.get_device_name(0)},
        "loss": {"train": split_loss(train), "dev": split_loss(dev),
                 "newWorld": split_loss(hold)},
        "results": {
            "train": summary(train_samples),
            "dev": summary(dev_samples),
            "newWorld": summary(hold_samples),
        },
        "history": history,
        "wallSeconds": wall,
        "samples": {"train": train_samples, "dev": dev_samples,
                    "newWorld": hold_samples},
        "notes": [
            "Scene sentences may not narrate events, name people, or add "
            "places; the fact clauses come from the verbalizer step.",
            "New-world pairs are zero-shot: unseen location, weather and "
            "props.",
        ],
    }
    pathlib.Path("scene-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("loss:", json.dumps(report["loss"], ensure_ascii=False))
    print("results:", json.dumps(report["results"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
