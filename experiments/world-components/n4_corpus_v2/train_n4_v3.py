# N4 v3 optimization finetune: full-parameter finetune of the
# Randeng-T5-77M base on corpus_v3/train-v3.jsonl. The v3 corpus keeps the
# v2 facts/worlds but uses the current N3 guard-on plans and the merged
# same-entity target composer (compose_v3). The dev split is held out for
# the pronoun threshold; the reused family-C holdout never enters training.
#
# This script runs ON THE HPC (dispatched by the local-only tooling, the
# same channel as the batch-2 N2 head run per the coordinator's training
# directive). Inputs are the shared renderer's bytes: render_v2.py builds
# the training inputs, so runtime prompts and training inputs cannot drift.
#
# Fixed settings (the proven r3-direction contract):
# - tokenizer T5Tokenizer(legacy=False); full-parameter finetune, fp32, cuda
# - AdamW lr 1e-4, batch 8, seed 20261102; steps = epochs x stepsPerEpoch
#   computed from the corpus (epochs chosen to land in the proven 300-500
#   step band for a 77M model on a few hundred pairs)
# - max_input 160 real tokens (the grouped interface is slightly longer
#   than the flat one), max_output 96
# - the script REFUSES to run if the frozen holdout file's sha differs from
#   the freeze registration (train-time proof the test set did not move)
#
# Usage (on the HPC): python train_n4_v2.py --epochs 6
# Output: ckpt-v3/ (checkpoint) + train-v3-report.json

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
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "n4_corpus_v2"))
sys.path.insert(0, str(HERE.parent / "n4_corpus"))

from render_v2 import render_input_v2  # noqa: E402  (the single renderer)

CORPUS = HERE / "corpus_v3" / "train-v3.jsonl"
HOLDOUT = HERE / "corpus_v3" / "holdout-v3.jsonl"
FREEZE = HERE / "corpus_v3" / "holdout-v3-freeze.json"
BASE = pathlib.Path("base/randeng-t5-77m")
SEED = 20261102
BATCH = 8
LR = 1e-4
MAX_INPUT = 160
MAX_OUTPUT = 96


def sha_file(p) -> str:
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--base", default=str(BASE))
    parser.add_argument("--out", default="ckpt-v3")
    args = parser.parse_args()

    # the freeze must hold at training time: the holdout bytes the trainer
    # sees are exactly the frozen registration's bytes
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    got = sha_file(HOLDOUT)
    if got != freeze["sha256"]:
        print(f"REFUSED: holdout sha {got[:16]} != frozen "
              f"{freeze['sha256'][:16]} — the test set moved after the "
              "freeze")
        return 2
    rows = [json.loads(l) for l in
            CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]
    train = [r for r in rows if r["split"] == "train"]
    dev = [r for r in rows if r["split"] == "dev"]
    if any(r["familyId"] == "v2-c-salt" for r in train + dev):
        print("REFUSED: family-C rows in the training pool")
        return 2
    pairs = [{"input": r["input"], "target": r["text"]} for r in train]
    # the single-renderer discipline, made real: every stored training
    # input must be byte-identical to a fresh render of its plan
    for r in rows:
        if r["split"] not in ("train", "dev"):
            continue
        if render_input_v2(r["plan"], r["facts"]) != r["input"]:
            print(f"REFUSED: renderer drift on {r['rowId']} — the stored "
                  "input is not what render_v2 produces today")
            return 2
    print(f"train pairs {len(pairs)} (dev held out: {len(dev)}); "
          f"epochs {args.epochs}")

    tok = T5Tokenizer.from_pretrained(args.base, legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        args.base, torch_dtype=torch.float32)
    assert torch.cuda.is_available(), "the v2 finetune runs on the HPC GPU"
    device = "cuda"
    model.to(device)
    torch.manual_seed(SEED)
    random.seed(SEED)

    def encode(pairs):
        enc = tok([p["input"] for p in pairs], padding=True,
                  truncation=True, max_length=MAX_INPUT,
                  return_tensors="pt")
        with tok.as_target_tokenizer():
            labels = tok([p["target"] for p in pairs], padding=True,
                         truncation=True, max_length=MAX_OUTPUT,
                         return_tensors="pt")
        labels.input_ids[labels.input_ids == tok.pad_token_id] = -100
        return enc, labels

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    order = list(range(len(pairs)))
    steps_per_epoch = (len(pairs) + BATCH - 1) // BATCH
    total_steps = steps_per_epoch * args.epochs
    step, t0 = 0, time.perf_counter()
    losses = []
    model.train()
    for epoch in range(args.epochs):
        random.shuffle(order)
        for start in range(0, len(order), BATCH):
            idx = order[start:start + BATCH]
            enc, labels = encode([pairs[i] for i in idx])
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
    report = {
        "purpose": "N4 v3 optimization finetune (guard-on N3 plans + merged "
                   "same-entity targets)",
        "base": {"dir": args.base, "sha256": sha_file(
            pathlib.Path(args.base) / "model.safetensors")},
        "data": {"corpus": "corpus_v3/train-v3.jsonl",
                 "corpusSha256": sha_file(CORPUS),
                 "trainPairs": len(pairs), "devHeldOut": len(dev),
                 "holdoutFrozen": {"rows": freeze["rows"],
                                   "sha256": freeze["sha256"]}},
        "hyper": {"seed": SEED, "epochs": args.epochs,
                  "steps": total_steps, "batch": BATCH, "lr": LR,
                  "optimizer": "AdamW", "precision": "fp32",
                  "maxInput": MAX_INPUT, "maxOutput": MAX_OUTPUT,
                  "device": torch.cuda.get_device_name(0)
                  if torch.cuda.is_available() else "cpu"},
        "lossFirst5": losses[:5], "lossLast5": losses[-5:],
        "wallSeconds": wall,
    }
    (pathlib.Path("train-v3-report.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("done:", json.dumps(report["hyper"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
