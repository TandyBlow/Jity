# -*- coding: utf-8 -*-
"""Grid search over learning rate and weight decay, then over decoding.

Two separate questions, measured separately:

1. Training: lr x weight-decay, each with two seeds, 30 epochs. Every run
   records the teacher-forced loss on the training rows and on the held-out
   rows at every epoch, so the comparison is "best holdout epoch", not
   "loss at whatever epoch the run happened to end on".
2. Decoding: at the best training setting, repetition penalty x no-repeat
   n-gram size. Four held-out rows each, scored on length against the target,
   whether it stopped on EOS, and how badly it loops.

With four held-out rows the second decimal of a loss is noise; the report keeps
every per-row number so the spread is visible instead of hidden behind a mean.

  python grid_narration_rows.py --data rows-xy.jsonl --base <dir> --out grid-01
"""

import argparse
import hashlib
import io
import json
import math
import os
import random
import time

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def text_stats(text, target, n=4):
    grams = [target[i:i + n] for i in range(max(len(target) - n + 1, 0))]
    hits = sum(1 for gram in grams if gram in text) / len(grams) if grams else 0.0
    out_grams = [text[i:i + n] for i in range(max(len(text) - n + 1, 0))]
    counts = {}
    for gram in out_grams:
        counts[gram] = counts.get(gram, 0) + 1
    max_repeat = max(counts.values()) if counts else 0
    distinct = len(counts) / len(out_grams) if out_grams else 0.0
    return {"coverage4": round(hits, 3), "maxRepeat4": max_repeat,
            "distinct4": round(distinct, 3)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--holdout", default="row-0010,row-0017,row-0021,row-0030")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--lrs", default="1e-4,3e-4,1e-3")
    parser.add_argument("--wds", default="0,0.01,0.1")
    parser.add_argument("--seeds", default="20261109,7")
    parser.add_argument("--max-input", type=int, default=1280)
    parser.add_argument("--max-target", type=int, default=1150)
    parser.add_argument("--decode-rp", default="1.0,1.05,1.1,1.2,1.3")
    parser.add_argument("--decode-ngram", default="0,3,4,5")
    parser.add_argument("--decode-rows", type=int, default=4)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    device = "cuda"
    if not torch.cuda.is_available():
        raise SystemExit("no CUDA device")
    device_name = torch.cuda.get_device_name(0)
    holdout = [name.strip() for name in args.holdout.split(",") if name.strip()]

    tokenizer = T5Tokenizer(vocab_file=os.path.join(args.base, "spiece.model"),
                            extra_ids=0, legacy=True)
    rows = [json.loads(line) for line in io.open(args.data, encoding="utf-8")]
    train = [row for row in rows if row["id"] not in holdout]
    hold = [row for row in rows if row["id"] in holdout]
    if len(hold) != len(holdout):
        raise SystemExit("holdout ids not found")

    def fresh_model(seed):
        torch.manual_seed(seed)
        random.seed(seed)
        model = T5ForConditionalGeneration.from_pretrained(args.base).to(device)
        model.train()
        return model

    def teacher_forced(model, subset):
        model.eval()
        total, count, per_row = 0.0, 0, []
        with torch.no_grad():
            for row in subset:
                x = tokenizer(row["xText"], truncation=True, max_length=args.max_input,
                              return_tensors="pt").to(device)
                y = tokenizer(row["y"], truncation=True, max_length=args.max_target,
                              return_tensors="pt").to(device)
                labels = y["input_ids"]
                labels[labels == tokenizer.pad_token_id] = -100
                out = model(input_ids=x["input_ids"], attention_mask=x["attention_mask"],
                            labels=labels)
                tokens = int((labels != -100).sum())
                total += out.loss.item() * tokens
                count += tokens
                per_row.append({"id": row["id"], "loss": round(out.loss.item(), 4)})
        return round(total / max(count, 1), 4), per_row

    no_decay = ("bias", "LayerNorm.weight", "layer_norm.weight", "relative_attention_bias")

    def train_once(lr, wd, seed, epochs):
        model = fresh_model(seed)
        decay = [p for n, p in model.named_parameters()
                 if not any(m in n for m in no_decay)]
        keep = [p for n, p in model.named_parameters()
                if any(m in n for m in no_decay)]
        optimizer = torch.optim.AdamW(
            [{"params": decay, "weight_decay": wd},
             {"params": keep, "weight_decay": 0.0}], lr=lr)
        history, best = [], {"epoch": None, "holdout": None, "state": None}
        for epoch in range(1, epochs + 1):
            total, steps = 0.0, 0
            for row in train:
                x = tokenizer(row["xText"], truncation=True, max_length=args.max_input,
                              return_tensors="pt").to(device)
                y = tokenizer(row["y"], truncation=True, max_length=args.max_target,
                              return_tensors="pt").to(device)
                labels = y["input_ids"]
                labels[labels == tokenizer.pad_token_id] = -100
                out = model(input_ids=x["input_ids"], attention_mask=x["attention_mask"],
                            labels=labels)
                out.loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                total += out.loss.item()
                steps += 1
            hold_loss, hold_rows = teacher_forced(model, hold)
            if epoch == 1 or epoch % 5 == 0 or epoch == epochs:
                train_loss, _ = teacher_forced(model, train)
            else:
                train_loss = None
            model.train()
            if best["holdout"] is None or hold_loss < best["holdout"]:
                best = {"epoch": epoch, "holdout": hold_loss,
                        "state": {k: v.detach().cpu().clone()
                                  for k, v in model.state_dict().items()}}
            history.append({"epoch": epoch, "loss": round(total / max(steps, 1), 4),
                            "train": train_loss, "holdout": hold_loss,
                            "holdoutPerRow": hold_rows})
            print(f"  lr={lr} wd={wd} seed={seed} ep{epoch:>3} "
                  f"train={train_loss} holdout={hold_loss} best={best['epoch']}",
                  flush=True)
        del model
        torch.cuda.empty_cache()
        return {"lr": lr, "wd": wd, "seed": seed, "history": history,
                "best": best}

    started = time.time()
    runs = []
    for lr in [float(v) for v in args.lrs.split(",")]:
        for wd in [float(v) for v in args.wds.split(",")]:
            for seed in [int(v) for v in args.seeds.split(",")]:
                result = train_once(lr, wd, seed, args.epochs)
                runs.append({k: v for k, v in result.items() if k != "best"} | {
                    "bestEpoch": result["best"]["epoch"],
                    "bestHoldout": result["best"]["holdout"]})
                # keep the state of the overall best run in memory for decoding
                if not runs or result["best"]["holdout"] <= min(r["bestHoldout"] for r in runs):
                    best_run = result

    table = {}
    for run in runs:
        key = f"lr={run['lr']},wd={run['wd']}"
        table.setdefault(key, []).append({"seed": run["seed"],
                                          "bestEpoch": run["bestEpoch"],
                                          "bestHoldout": run["bestHoldout"]})
    ranking = sorted(
        ({"setting": key,
          "meanBestHoldout": round(sum(r["bestHoldout"] for r in items) / len(items), 4),
          "runs": items,
          "epochs": [r["bestEpoch"] for r in items]} for key, items in table.items()),
        key=lambda entry: entry["meanBestHoldout"])

    model = fresh_model(best_run["seed"])
    model.load_state_dict({k: v.to(device) for k, v in best_run["best"]["state"].items()})
    model.eval()
    decode_rows = hold[:args.decode_rows]
    sweep = []
    for rp in [float(v) for v in args.decode_rp.split(",")]:
        for ngram in [int(v) for v in args.decode_ngram.split(",")]:
            entry = {"repetitionPenalty": rp, "noRepeatNgram": ngram, "rows": []}
            for row in decode_rows:
                x = tokenizer(row["xText"], truncation=True, max_length=args.max_input,
                              return_tensors="pt").to(device)
                begin = time.time()
                with torch.no_grad():
                    generated = model.generate(
                        **x, max_new_tokens=args.max_target, num_beams=1, do_sample=False,
                        eos_token_id=tokenizer.eos_token_id,
                        pad_token_id=tokenizer.pad_token_id,
                        repetition_penalty=rp,
                        no_repeat_ngram_size=max(ngram, 0))
                text = tokenizer.decode(generated[0], skip_special_tokens=True)
                entry["rows"].append({
                    "id": row["id"], "targetChars": len(row["y"]), "chars": len(text),
                    "lengthRatio": round(len(text) / max(len(row["y"]), 1), 2),
                    "stopReason": "eos" if int(generated[0, -1]) == tokenizer.eos_token_id
                    else "length",
                    "seconds": round(time.time() - begin, 2),
                    "output": text,
                    **text_stats(text, row["y"])})
            ok = [r for r in entry["rows"]
                  if r["stopReason"] == "eos" and 0.5 <= r["lengthRatio"] <= 1.6
                  and r["maxRepeat4"] <= 3]
            entry["acceptable"] = len(ok)
            entry["meanLengthRatio"] = round(
                sum(r["lengthRatio"] for r in entry["rows"]) / len(entry["rows"]), 2)
            entry["meanCoverage4"] = round(
                sum(r["coverage4"] for r in entry["rows"]) / len(entry["rows"]), 3)
            entry["worstRepeat4"] = max(r["maxRepeat4"] for r in entry["rows"])
            sweep.append(entry)
            print(f"  rp={rp} ngram={ngram} acceptable={entry['acceptable']}/"
                  f"{len(entry['rows'])} lenRatio={entry['meanLengthRatio']} "
                  f"cov4={entry['meanCoverage4']} worstRepeat={entry['worstRepeat4']}",
                  flush=True)

    report = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "host": {"deviceName": device_name, "torch": torch.__version__,
                 "transformers": __import__("transformers").__version__},
        "data": {"path": os.path.basename(args.data), "sha256": sha256(args.data),
                 "rows": len(rows), "trainRows": len(train),
                 "holdout": holdout},
        "search": {"lrs": args.lrs, "wds": args.wds, "seeds": args.seeds,
                   "epochs": args.epochs},
        "ranking": ranking,
        "runs": runs,
        "decodingOnBest": {"fromRun": {"lr": best_run["lr"], "wd": best_run["wd"],
                                       "seed": best_run["seed"],
                                       "bestEpoch": best_run["best"]["epoch"],
                                       "bestHoldout": best_run["best"]["holdout"]},
                           "sweep": sweep},
        "seconds": round(time.time() - started, 1),
        "notes": "the encoder-decoder trains at batch 1; the held-out set is four "
                 "rows from four different worlds, so per-run differences below "
                 "about 0.05 are not meaningful",
    }
    with io.open(os.path.join(args.out, "grid.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"ranking": ranking, "seconds": report["seconds"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
