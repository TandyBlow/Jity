# N4 structured-input overfit sanity check (runs on the HPC GPU).
#
# This is NOT a quality or generalization experiment. It trains on 9 of the
# 12 approved cases and checks whether the model can fit the N4.0 structured
# record -> 75-99 token narrative mapping at all. The 3 check rows are from
# the same dev set; their results are diagnostic only.
#
# Usage (on the HPC): python train_n4_struct.py --epochs 60
# Output: ckpt-struct/ + train-struct-report.json

import argparse
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
PAIRS = HERE / "training_pairs.jsonl"
BASE = pathlib.Path("base/randeng-t5-77m")
SEED = 20261102
BATCH = 3
LR = 1e-4
MAX_INPUT = 512
MAX_OUTPUT = 128


def sha_file(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def norm_punct(text):
    """Compare on the tokenizer's ASCII punctuation; the T5 spiece model
    normalizes full-width ，；：？！ to ASCII before tokenization."""
    return (text.replace("，", ",").replace("；", ";")
                .replace("：", ":").replace("？", "?")
                .replace("！", "!"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--base", default=str(BASE))
    parser.add_argument("--out", default="ckpt-struct")
    parser.add_argument("--pairs", default=str(PAIRS))
    args = parser.parse_args()

    rows = [json.loads(line) for line in
            pathlib.Path(args.pairs).read_text(encoding="utf-8").splitlines()
            if line.strip()]
    train = [r for r in rows if r["split"] == "overfit-train"]
    check = [r for r in rows if r["split"] == "overfit-check"]
    assert len(train) == 9 and len(check) == 3, (len(train), len(check))
    print(f"train {len(train)} / check {len(check)}; epochs {args.epochs}")

    tok = T5Tokenizer.from_pretrained(args.base, legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        args.base, torch_dtype=torch.float32)
    assert torch.cuda.is_available(), "the HPC overfit check expects a GPU"
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

    def row_loss(row):
        enc, labels = encode([row])
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            out = model(**enc, labels=labels.input_ids.to(device))
        return round(float(out.loss), 4)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    order = list(range(len(train)))
    steps_per_epoch = (len(train) + BATCH - 1) // BATCH
    total_steps = steps_per_epoch * args.epochs
    step, t0 = 0, time.perf_counter()
    losses = []
    model.train()
    for _ in range(args.epochs):
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
            losses.append(round(float(out.loss), 4))
            if step % 20 == 0:
                print(f"step {step}/{total_steps} loss {out.loss:.4f}",
                      flush=True)
    wall = round(time.perf_counter() - t0, 1)

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
            "rowId": r["rowId"],
            "split": r["split"],
            "inputTokens": r["inputTokens"],
            "targetTokens": r["targetTokens"],
            "outputTokens": len(tok(text).input_ids),
            "loss": row_loss(r),
            "exact": text == r["target"],
            "exactNormalized": norm_punct(text) == norm_punct(r["target"]),
            "output": text,
            "target": r["target"],
        })
        print(f"{r['split']} {r['rowId']}: {text[:80]}", flush=True)

    train_loss = sum(s["loss"] for s in samples
                     if s["split"] == "overfit-train") / len(train)
    train_exact = sum(1 for s in samples
                       if s["split"] == "overfit-train" and s["exactNormalized"])
    check_exact = sum(1 for s in samples
                      if s["split"] == "overfit-check" and s["exactNormalized"])
    check_loss = sum(s["loss"] for s in samples
                     if s["split"] == "overfit-check") / len(check)
    report = {
        "purpose": "N4 structured-input overfit sanity check; not quality",
        "base": {"dir": "base/randeng-t5-77m",
                 "sha256": sha_file(pathlib.Path(args.base) / "model.safetensors")},
        "data": {"pairs": "training_pairs.jsonl",
                 "sha256": sha_file(args.pairs),
                 "train": len(train), "check": len(check)},
        "hyper": {
            "seed": SEED, "epochs": args.epochs, "steps": total_steps,
            "batch": BATCH, "lr": LR, "optimizer": "AdamW",
            "precision": "fp32", "maxInput": MAX_INPUT,
            "maxOutput": MAX_OUTPUT,
            "device": torch.cuda.get_device_name(0),
        },
        "lossFirst10": losses[:10],
        "lossLast10": losses[-10:],
        "trainMeanLoss": round(train_loss, 4),
        "checkMeanLoss": round(check_loss, 4),
        "trainExactNormalized": train_exact,
        "checkExactNormalized": check_exact,
        "wallSeconds": wall,
        "samples": samples,
        "notes": [
            "9 training rows from an approved 12-case dev set; 3 check rows "
            "are diagnostic only, not a formal holdout.",
            "A good train fit does not prove generalization; a bad train fit "
            "stops the corpus expansion and points at the input/model.",
        ],
    }
    pathlib.Path("train-struct-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("done:", json.dumps(report["hyper"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
