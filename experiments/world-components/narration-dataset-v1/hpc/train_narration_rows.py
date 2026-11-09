"""Train the narration rows. Submission-friendly: every input is a flag,
every artefact is written into --out, and the report records the hashes.

Input  X = the row's data as one JSON string (no instruction)
Target y = the hand-written narrative

This run cannot show quality: 18 training rows overfit quickly. It answers
whether the model, the tokenizer and this data shape work together, at what
cost, and what comes out at the end.

  python train_narration_rows.py \
    --data rows-xy.jsonl --base <dir with config.json + model.safetensors + spiece.model> \
    --out runs/narr-01 --epochs 8 --lr 3e-4 --holdout row-0010,row-0017
"""

import argparse
import hashlib
import io
import json
import os
import random
import time

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

from narration_text import decode_output, encode_target


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--max-input", type=int, default=1280)
    parser.add_argument("--max-target", type=int, default=1150)
    parser.add_argument("--holdout", default="row-0010,row-0017")
    parser.add_argument("--seed", type=int, default=20261109)
    parser.add_argument("--save-ckpt", action="store_true")
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--repetition-penalty", type=float, default=1.05)
    parser.add_argument("--no-repeat-ngram", type=int, default=4)
    parser.add_argument("--snapshot-epochs", default="",
                        help="comma separated epochs at which to generate a sample")
    parser.add_argument("--snapshot-rows", default="",
                        help="comma separated row ids; default: first train row + holdout")
    args = parser.parse_args()

    started = time.time()
    os.makedirs(args.out, exist_ok=True)
    holdout = [name.strip() for name in args.holdout.split(",") if name.strip()]

    if not torch.cuda.is_available():
        raise SystemExit("no CUDA device; this run is meant for the GPU node")
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    device = "cuda"
    device_name = torch.cuda.get_device_name(0)

    tokenizer = T5Tokenizer(vocab_file=os.path.join(args.base, "spiece.model"),
                            extra_ids=0, legacy=True)
    model = T5ForConditionalGeneration.from_pretrained(args.base).to(device)
    model.train()
    params = sum(p.numel() for p in model.parameters())

    rows = [json.loads(line) for line in io.open(args.data, encoding="utf-8")]
    by_id = {row["id"]: row for row in rows}
    train = [row for row in rows if row["id"] not in holdout]
    hold = [row for row in rows if row["id"] in holdout]
    if len(hold) != len(holdout):
        raise SystemExit(f"holdout ids not found: {sorted({r['id'] for r in hold})}")

    lengths = {"input": [], "target": []}
    for row in rows:
        lengths["input"].append(len(tokenizer(row["xText"], truncation=False)["input_ids"]))
        lengths["target"].append(len(tokenizer(encode_target(row["y"]), truncation=False)["input_ids"]))
    over_input = [row["id"] for row, n in zip(rows, lengths["input"]) if n > args.max_input]
    over_target = [row["id"] for row, n in zip(rows, lengths["target"]) if n > args.max_target]

    def teacher_forced(rows_subset):
        """Loss with the model in eval mode: no dropout, no updates."""
        model.eval()
        total, count = 0.0, 0
        rows_loss = []
        with torch.no_grad():
            for row in rows_subset:
                x = tokenizer(row["xText"], truncation=True, max_length=args.max_input,
                              return_tensors="pt").to(device)
                y = tokenizer(encode_target(row["y"]), truncation=True, max_length=args.max_target,
                              return_tensors="pt").to(device)
                labels = y["input_ids"]
                labels[labels == tokenizer.pad_token_id] = -100
                out = model(input_ids=x["input_ids"], attention_mask=x["attention_mask"],
                            labels=labels)
                tokens = int((labels != -100).sum())
                total += out.loss.item() * tokens
                count += tokens
                rows_loss.append({"id": row["id"], "loss": round(out.loss.item(), 4),
                                  "tokens": tokens})
        model.train()
        return (round(total / max(count, 1), 4), rows_loss)

    no_decay = ("bias", "LayerNorm.weight", "layer_norm.weight", "relative_attention_bias")
    decay = [p for n, p in model.named_parameters()
             if not any(marker in n for marker in no_decay)]
    keep = [p for n, p in model.named_parameters()
            if any(marker in n for marker in no_decay)]
    optimizer = torch.optim.AdamW(
        [{"params": decay, "weight_decay": args.weight_decay},
         {"params": keep, "weight_decay": 0.0}],
        lr=args.lr)
    decay_params = sum(p.numel() for p in decay)
    keep_params = sum(p.numel() for p in keep)
    def snapshot_generate(row):
        x = tokenizer(row["xText"], truncation=True, max_length=args.max_input,
                      return_tensors="pt").to(device)
        with torch.no_grad():
            generated = model.generate(
                **x, max_new_tokens=args.max_target, num_beams=1, do_sample=False,
                eos_token_id=tokenizer.eos_token_id, pad_token_id=tokenizer.pad_token_id,
                repetition_penalty=args.repetition_penalty,
                no_repeat_ngram_size=max(args.no_repeat_ngram, 0))
        text = decode_output(tokenizer.decode(generated[0], skip_special_tokens=True))
        grams = [text[i:i + 4] for i in range(max(len(text) - 3, 0))]
        counts = {}
        for gram in grams:
            counts[gram] = counts.get(gram, 0) + 1
        return {"chars": len(text), "output": text,
                "newTokens": int(generated.shape[1]),
                "stopReason": "eos" if int(generated[0, -1]) == tokenizer.eos_token_id
                else "length",
                "maxRepeat4": max(counts.values()) if counts else 0,
                "distinct4": round(len(counts) / len(grams), 3) if grams else 0.0}

    snapshot_epochs = {int(v) for v in args.snapshot_epochs.split(",") if v.strip()}
    snapshot_rows = ([by_id[name.strip()] for name in args.snapshot_rows.split(",")
                      if name.strip()] if args.snapshot_rows
                     else [train[0]] + hold)
    snapshots = []

    history = []
    best = {"epoch": None, "holdoutLossTF": None, "state": None}
    for epoch in range(1, args.epochs + 1):
        random.shuffle(train)
        total, steps = 0.0, 0
        for row in train:
            x = tokenizer(row["xText"], truncation=True, max_length=args.max_input,
                          return_tensors="pt").to(device)
            y = tokenizer(encode_target(row["y"]), truncation=True, max_length=args.max_target,
                          return_tensors="pt").to(device)
            labels = y["input_ids"]
            labels[labels == tokenizer.pad_token_id] = -100
            out = model(input_ids=x["input_ids"], attention_mask=x["attention_mask"],
                        labels=labels)
            out.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            optimizer.zero_grad()
            total += out.loss.item()
            steps += 1
        mean = total / max(steps, 1)
        train_loss, _ = teacher_forced(train)
        hold_loss, hold_rows = teacher_forced(hold)
        if best["holdoutLossTF"] is None or hold_loss < best["holdoutLossTF"]:
            best = {"epoch": epoch, "holdoutLossTF": hold_loss,
                    "state": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}
        if epoch in snapshot_epochs:
            model.eval()
            for row in snapshot_rows:
                record = snapshot_generate(row)
                record["epoch"] = epoch
                record["id"] = row["id"]
                snapshots.append(record)
            model.train()
        history.append({"epoch": epoch, "loss": round(mean, 4),
                        "trainLossTF": train_loss, "holdoutLossTF": hold_loss,
                        "elapsedSec": round(time.time() - started, 1),
                        "peakAllocatedMb": round(torch.cuda.max_memory_allocated() / 2**20)})
        print(f"epoch {epoch} loss {mean:.4f} elapsed {time.time() - started:.1f}s", flush=True)

    model.eval()
    _, final_train_rows = teacher_forced(train)
    _, final_hold_rows = teacher_forced(hold)

    eos_probe = []
    with torch.no_grad():
        for row in hold + train[:2]:
            x = tokenizer(row["xText"], truncation=True, max_length=args.max_input,
                          return_tensors="pt").to(device)
            y = tokenizer(encode_target(row["y"]), truncation=True, max_length=args.max_target,
                          return_tensors="pt").to(device)
            logits = model(input_ids=x["input_ids"], attention_mask=x["attention_mask"],
                           decoder_input_ids=torch.cat([torch.zeros_like(y["input_ids"][:, :1]), y["input_ids"][:, :-1]], dim=1)).logits
            last = logits[0, -1]
            probs = torch.softmax(last.float(), dim=-1)
            top = torch.topk(probs, 3)
            eos_probe.append({"id": row["id"],
                              "pEos": round(float(probs[tokenizer.eos_token_id]), 6),
                              "topTokens": [tokenizer.decode([int(i)]) for i in top.indices],
                              "topProbs": [round(float(p), 4) for p in top.values]})

    def coverage(target, output, n=4):
        grams = {target[i:i + n] for i in range(max(len(target) - n + 1, 0))}
        if not grams:
            return 0.0
        return round(sum(1 for gram in grams if gram in output) / len(grams), 3)

    def generate_with(row, tag):
        x = tokenizer(row["xText"], truncation=True, max_length=args.max_input,
                      return_tensors="pt").to(device)
        begin = time.time()
        with torch.no_grad():
            generated = model.generate(
                **x, max_new_tokens=args.max_target, num_beams=1, do_sample=False,
                eos_token_id=tokenizer.eos_token_id, pad_token_id=tokenizer.pad_token_id,
                repetition_penalty=args.repetition_penalty,
                no_repeat_ngram_size=max(args.no_repeat_ngram, 0))
        text = decode_output(tokenizer.decode(generated[0], skip_special_tokens=True))
        return {"id": row["id"], "weights": tag, "trainedOnThisRow": row in train,
                "targetChars": len(row["y"]), "target": row["y"],
                "outputChars": len(text), "output": text,
                "newTokens": int(generated.shape[1]),
                "stopReason": "eos" if int(generated[0, -1]) == tokenizer.eos_token_id else "length",
                "targetCoverage4": coverage(row["y"], text),
                "seconds": round(time.time() - begin, 2)}

    final_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    samples = []
    if best["state"] is not None:
        model.load_state_dict({k: v.to(device) for k, v in best["state"].items()})
        model.eval()
        samples += [generate_with(row, f"best(epoch {best['epoch']})")
                    for row in [train[0]] + hold]
    model.load_state_dict({k: v.to(device) for k, v in final_state.items()})
    model.eval()
    samples += [generate_with(row, "finalEpoch") for row in hold]

    if args.save_ckpt:
        model.save_pretrained(os.path.join(args.out, "ckpt"))
        tokenizer.save_pretrained(os.path.join(args.out, "ckpt"))

    report = {
        "purpose": "narration rows: plumbing run, overfitting expected, no quality claim",
        "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "host": {"deviceName": device_name, "torch": torch.__version__,
                 "cuda": torch.version.cuda,
                 "transformers": __import__("transformers").__version__},
        "data": {"path": os.path.basename(args.data), "sha256": sha256(args.data),
                 "rows": len(rows), "trainRows": len(train), "holdout": holdout},
        "base": {"files": {name: sha256(os.path.join(args.base, name))
                           for name in ("config.json", "model.safetensors", "spiece.model")},
                 "params": params},
        "lengths": {"maxInput": max(lengths["input"]), "maxTarget": max(lengths["target"]),
                    "meanInput": round(sum(lengths["input"]) / len(rows)),
                    "meanTarget": round(sum(lengths["target"]) / len(rows)),
                    "overMaxInput": over_input, "overMaxTarget": over_target},
        "hyper": {k: v for k, v in vars(args).items() if k != "base"},
        "regularisation": {"weightDecay": args.weight_decay,
                           "decayParams": decay_params, "noDecayParams": keep_params},
        "decoding": {"repetitionPenalty": args.repetition_penalty,
                     "noRepeatNgramSize": args.no_repeat_ngram,
                     "eosTokenId": tokenizer.eos_token_id},
        "bestHoldout": {"epoch": best["epoch"], "holdoutLossTF": best["holdoutLossTF"]},
        "history": history,
        "snapshots": snapshots,
        "splitLoss": {"trainPerRow": final_train_rows, "holdoutPerRow": final_hold_rows},
        "eosProbe": eos_probe,
        "samples": samples,
        "totalSeconds": round(time.time() - started, 1),
    }
    with io.open(os.path.join(args.out, "report.json"), "w", encoding="utf-8",
                 newline="\n") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({"out": args.out, "epochs": args.epochs, "finalLoss": history[-1]["loss"],
                      "maxInput": report["lengths"]["maxInput"],
                      "maxTarget": report["lengths"]["maxTarget"],
                      "seconds": report["totalSeconds"],
                      "outputTokens": [s["newTokens"] for s in samples]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
