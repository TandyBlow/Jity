# -*- coding: utf-8 -*-
"""Does the model read the input at all?

Five versions of the same row's input, same weights, same decoding:

  full           the row's input as it is
  changesOnly    only the 本回合变化 block, the state and result removed
  shuffled       the same text with its sentences shuffled (same length, same words)
  truncated200   only the first 200 tokens
  empty          "{}"

If the encoder is doing its job, these five produce visibly different stories, and
the entities named in 本回合变化 show up in the ones that still contain that block.
If the five come out nearly the same, the decoder is writing from the target side's
habit and the input is decoration.

Similarity between two outputs is measured as 4-gram containment: how much of the
shorter one's 4-character runs appear in the longer one. 1.0 means same text.

  python probe_x_ablation.py --data rows-xy.jsonl --base <dir> --out probe-01
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


def ngrams(text, n=4):
    return {text[i:i + n] for i in range(max(len(text) - n + 1, 0))}


def containment(a, b):
    """How much of the shorter text appears in the longer one."""
    ga, gb = ngrams(a), ngrams(b)
    if not ga or not gb:
        return 0.0
    return round(len(ga & gb) / min(len(ga), len(gb)), 3)


def variants(row, tokenizer, seed=7):
    text = row["xText"]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    out = {"full": text}
    if isinstance(parsed, dict) and "本回合变化" in parsed:
        out["changesOnly"] = json.dumps({"本回合变化": parsed["本回合变化"]},
                                        ensure_ascii=False)
    else:
        out["changesOnly"] = text
    parts = [p for p in text.split("。") if p.strip()]
    random.Random(seed).shuffle(parts)
    out["shuffled"] = "。".join(p + "。" for p in parts)
    out["truncated200"] = tokenizer.decode(
        tokenizer(text, truncation=True, max_length=200)["input_ids"])
    out["empty"] = "{}"
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--holdout", default="row-0010,row-0017")
    parser.add_argument("--epochs", type=int, default=9)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=20261109)
    parser.add_argument("--probe-rows", default="row-0010,row-0017,row-0065,row-0085")
    parser.add_argument("--max-input", type=int, default=1280)
    parser.add_argument("--max-target", type=int, default=1150)
    parser.add_argument("--repetition-penalty", type=float, default=1.05)
    parser.add_argument("--no-repeat-ngram", type=int, default=4)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    device = "cuda"
    if not torch.cuda.is_available():
        raise SystemExit("no CUDA device")
    device_name = torch.cuda.get_device_name(0)
    holdout = [v.strip() for v in args.holdout.split(",")]

    tokenizer = T5Tokenizer(vocab_file=os.path.join(args.base, "spiece.model"),
                            extra_ids=0, legacy=True)
    rows = [json.loads(line) for line in io.open(args.data, encoding="utf-8")]
    by_id = {row["id"]: row for row in rows}
    train = [row for row in rows if row["id"] not in holdout]
    hold = [row for row in rows if row["id"] in holdout]

    torch.manual_seed(args.seed)
    random.seed(args.seed)
    model = T5ForConditionalGeneration.from_pretrained(args.base).to(device)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

    started = time.time()
    history = []
    for epoch in range(1, args.epochs + 1):
        total, steps = 0.0, 0
        for row in train:
            x = tokenizer(row["xText"], truncation=True, max_length=args.max_input,
                          return_tensors="pt").to(device)
            y = tokenizer(encode_target(row["y"]), truncation=True, max_length=args.max_target,
                          return_tensors="pt").to(device)
            labels = y["input_ids"]
            labels[labels == tokenizer.pad_token_id] = -100
            loss = model(input_ids=x["input_ids"], attention_mask=x["attention_mask"],
                         labels=labels).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            total += loss.item()
            steps += 1
        history.append({"epoch": epoch, "loss": round(total / max(steps, 1), 4)})
        print(f"epoch {epoch} loss {history[-1]['loss']} "
              f"elapsed {round(time.time() - started, 1)}s", flush=True)

    model.eval()

    def run(text):
        x = tokenizer(text, truncation=True, max_length=args.max_input,
                      return_tensors="pt").to(device)
        begin = time.time()
        with torch.no_grad():
            generated = model.generate(
                **x, max_new_tokens=args.max_target, num_beams=1, do_sample=False,
                eos_token_id=tokenizer.eos_token_id, pad_token_id=tokenizer.pad_token_id,
                repetition_penalty=args.repetition_penalty,
                no_repeat_ngram_size=args.no_repeat_ngram)
        return tokenizer.decode(generated[0], skip_special_tokens=True), \
            int(generated.shape[1]), round(time.time() - begin, 2)

    probe_ids = [v.strip() for v in args.probe_rows.split(",") if v.strip()]
    results = []
    for row_id in probe_ids:
        row = by_id[row_id]
        entry = {"id": row_id, "trainedOnThisRow": row in train,
                 "targetChars": len(row["y"]), "target": row["y"], "variants": {}}
        for name, text in variants(row, tokenizer).items():
            output, tokens, seconds = run(text)
            called = [name for name in row.get("names", [])
                      if name in output]
            entry["variants"][name] = {"chars": len(output), "tokens": tokens,
                                       "seconds": seconds, "output": output,
                                       "mentionsNamedEntity": called}
        names = list(entry["variants"])
        entry["pairwise"] = {}
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                entry["pairwise"][f"{names[i]}~{names[j]}"] = containment(
                    entry["variants"][names[i]]["output"],
                    entry["variants"][names[j]]["output"])
        entry["variants"] = {k: {"chars": v["chars"], "tokens": v["tokens"],
                                 "seconds": v["seconds"], "output": v["output"]}
                             for k, v in entry["variants"].items()}
        results.append(entry)
        print(f"\n== {row_id} trained={entry['trainedOnThisRow']} "
              f"target={entry['targetChars']} chars")
        for name, info in entry["variants"].items():
            print(f"   {name:<13} {info['chars']:>4} chars  {info['tokens']:>4} tok")
        print("   full vs others:",
              {k: v for k, v in entry["pairwise"].items() if k.startswith("full~")})

    means = {}
    for name in results[0]["variants"]:
        means[name] = round(sum(len(r["variants"][name]["output"]) for r in results)
                            / len(results), 1)
    full_means = round(sum(v for r in results for k, v in r["pairwise"].items()
                           if k.startswith("full~")) /
                       max(sum(1 for r in results for k in r["pairwise"]
                               if k.startswith("full~")), 1), 3)

    report = {"when": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "host": {"deviceName": device_name, "torch": torch.__version__},
              "data": {"path": os.path.basename(args.data), "sha256": sha256(args.data),
                       "rows": len(rows), "trainRows": len(train), "holdout": holdout},
              "training": {"epochs": args.epochs, "lr": args.lr, "seed": args.seed,
                           "history": history},
              "decoding": {"repetitionPenalty": args.repetition_penalty,
                           "noRepeatNgram": args.no_repeat_ngram},
              "meanCharsByVariant": means,
              "meanContainmentFullVsOther": full_means,
              "probes": results,
              "seconds": round(time.time() - started, 1)}
    with io.open(os.path.join(args.out, "probe.json"), "w", encoding="utf-8",
                 newline="\n") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"meanCharsByVariant": means,
                      "meanContainmentFullVsOther": full_means},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
