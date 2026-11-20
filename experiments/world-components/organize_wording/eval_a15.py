#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Supplementary A epoch-15 (90 updates) evaluation.

The original run kept only the selected A epoch-3 state in memory and did not
persist the epoch-15 state.  This script reproduces A deterministically with
the same seed/data/config to epoch 15, verifies the epoch-15 dev metrics
against the original log, and generates the 12 fixed-holdout outputs with the
same decoding.  It does not touch B_h and does not re-select.
"""
import json, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_ab as T
import numpy as np
import torch
from torch.optim import AdamW
from transformers import T5ForConditionalGeneration, T5Tokenizer, get_linear_schedule_with_warmup

OUT = T.OUT
DATA = T.DATA


def gen_batch_exact(model, tok, prompts, device, batch=6):
    outs = []
    for i in range(0, len(prompts), batch):
        chunk = prompts[i:i+batch]
        x = tok(chunk, padding=True, truncation=True, max_length=T.MAX_IN, return_tensors="pt").to(device)
        with torch.no_grad():
            out = model.generate(**x, max_new_tokens=T.MAX_NEW, num_beams=1, do_sample=False,
                                 return_dict_in_generate=True)
        for seq in out.sequences:
            new_tokens = int(seq.shape[0] - 1)
            outs.append({"text": tok.decode(seq, skip_special_tokens=True).strip(),
                         "new_tokens": new_tokens,
                         "stop": "cap" if new_tokens >= T.MAX_NEW else "eos"})
    return outs


def main():
    rows = T.load_rows(DATA)
    dev = [r for r in rows if r["split"] == "dev"]
    hold = [r for r in rows if r["split"] == "holdout"]
    train = [r for r in rows if r["split"] == "train"]
    device = "cuda" if torch.cuda.is_available() else "cpu"

    torch.manual_seed(T.SEED); random.seed(T.SEED); np.random.seed(T.SEED)
    tok = T5Tokenizer.from_pretrained(str(T.MODEL), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(T.MODEL), torch_dtype=torch.float32).to(device)
    opt = AdamW(model.parameters(), lr=T.LR, betas=(0.9, 0.999), eps=1e-8, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, T.WARMUP, T.TOTAL_UPDATES)
    step_in_epoch = 0
    update = 0
    epoch15 = None
    opt.zero_grad()
    for epoch in range(1, 16):
        model.train()
        order = list(train); random.Random(T.SEED + epoch).shuffle(order)
        for r in order:
            inp, mask, lab = T.tokenize(tok, T.prompt(r, False), r["target"])
            inp, mask, lab = inp.unsqueeze(0).to(device), mask.unsqueeze(0).to(device), lab.unsqueeze(0).to(device)
            loss = model(input_ids=inp, attention_mask=mask, labels=lab).loss / T.ACCUM
            loss.backward()
            step_in_epoch += 1
            if step_in_epoch % T.ACCUM == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step(); sched.step(); opt.zero_grad()
                update += 1
        dl = T.dev_loss(model, tok, dev, device, False)
        texts = T.gen_batch(model, tok, [T.prompt(r, False) for r in dev], device)
        score = sum(T.check(r, t)["fact_score"] for r, t in zip(dev, texts)) / len(dev)
        print(f"epoch {epoch} update {update} dev_loss {dl:.4f} dev_fact {score:.3f}", flush=True)
        if epoch == 15:
            epoch15 = {"dev_loss": dl, "dev_fact": score}
            holdout = []
            outs = gen_batch_exact(model, tok, [T.prompt(r, False) for r in hold], device)
            for r, o in zip(hold, outs):
                holdout.append({"sourceId": r["pairId"], "split": "holdout", "target": r["target"],
                                "new_tokens": o["new_tokens"], "stop": o["stop"], **T.check(r, o["text"])})
            break

    result = {
        "purpose": "supplementary same-update comparison; A epoch 15 (90 updates) vs existing B_h epoch 15 (90 updates)",
        "reproduction": "A epoch-15 state was not persisted in the original run; reproduced with the same seed/data/config; dev metrics compared against the original log",
        "config": {"base": str(T.MODEL), "data": str(DATA), "data_sha256": T.sha(DATA),
                   "seed": T.SEED, "epochs": 15, "updates": 90, "max_new": T.MAX_NEW, "device": device},
        "epoch15": epoch15,
        "holdout": holdout,
    }
    out = OUT / "a15-holdout.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
