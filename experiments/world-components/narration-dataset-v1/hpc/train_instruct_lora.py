# -*- coding: utf-8 -*-
"""LoRA the browser narration model on (settled facts -> fact-clean prose).

The prompt is byte-identical to the dataset builder's, which in turn mirrors
`instructNarrationInput` in the frontend. Only the target tokens are scored.
"""
import argparse
import json
import math
import os
import random
import time

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer


def build(model_dir, tokenizer, row, max_len):
    prefix = tokenizer.apply_chat_template(
        [{"role": "user", "content": row["prompt"]}], tokenize=False, add_generation_prompt=True)
    prompt_ids = tokenizer(prefix, add_special_tokens=False)["input_ids"]
    target_ids = tokenizer(row["target"] + tokenizer.eos_token, add_special_tokens=False)["input_ids"]
    keep = max_len - len(target_ids)
    if keep < 64:
        return None
    if len(prompt_ids) > keep:
        prompt_ids = prompt_ids[-keep:]
    return prompt_ids + target_ids, [-100] * len(prompt_ids) + target_ids


def collate(batch, pad_id):
    width = max(len(ids) for ids, _ in batch)
    x = torch.full((len(batch), width), pad_id, dtype=torch.long)
    y = torch.full((len(batch), width), -100, dtype=torch.long)
    mask = torch.zeros((len(batch), width), dtype=torch.long)
    for i, (ids, labels) in enumerate(batch):
        x[i, :len(ids)] = torch.tensor(ids)
        y[i, :len(labels)] = torch.tensor(labels)
        mask[i, :len(ids)] = 1
    return x, y, mask


def evaluate(model, rows, tokenizer, args, pad_id):
    model.eval()
    total, count = 0.0, 0
    with torch.no_grad():
        for start in range(0, len(rows), 2):
            batch = [build(args.model, tokenizer, row, args.max_len) for row in rows[start:start + 2]]
            batch = [item for item in batch if item]
            if not batch:
                continue
            x, y, mask = collate(batch, pad_id)
            out = model(input_ids=x.cuda(), attention_mask=mask.cuda(), labels=y.cuda())
            tokens = int((y != -100).sum())
            total += out.loss.item() * tokens
            count += tokens
    return round(total / max(count, 1), 4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="instruct/rows-instruct.jsonl")
    parser.add_argument("--model", default="qwen05b")
    parser.add_argument("--out", default="instruct/lora-run")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-len", type=int, default=1152)
    parser.add_argument("--holdout", default="row-0010,row-0017,row-0031,row-0065,row-0102,row-0148")
    parser.add_argument("--seed", type=int, default=20261110)
    parser.add_argument("--r", type=int, default=16)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--no-checkpoint", action="store_true")
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    random.seed(args.seed)
    os.makedirs(args.out, exist_ok=True)
    rows = [json.loads(line) for line in open(args.data, encoding="utf-8")]
    holdout = {name.strip() for name in args.holdout.split(",") if name.strip()}
    train = [row for row in rows if row["id"] not in holdout]
    dev = [row for row in rows if row["id"] in holdout]
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.bfloat16).cuda()
    if not args.no_checkpoint:
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()
    config = LoraConfig(r=args.r, lora_alpha=args.r * 2, lora_dropout=0.05, bias="none",
                        task_type="CAUSAL_LM",
                        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(model, config)
    model.print_trainable_parameters()
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr)
    pad_id = tokenizer.pad_token_id or tokenizer.eos_token_id
    baseline = evaluate(model, dev, tokenizer, args, pad_id)
    print(json.dumps({"baselineDev": baseline, "train": len(train), "dev": len(dev)}), flush=True)
    history = []
    best = (baseline, None)
    for epoch in range(1, args.epochs + 1):
        started = time.time()
        random.shuffle(train)
        model.train()
        total, steps = 0.0, 0
        for start in range(0, len(train), args.batch):
            batch = [build(args.model, tokenizer, row, args.max_len) for row in train[start:start + args.batch]]
            batch = [item for item in batch if item]
            if not batch:
                continue
            x, y, mask = collate(batch, pad_id)
            out = model(input_ids=x.cuda(), attention_mask=mask.cuda(), labels=y.cuda())
            (out.loss / len(batch)).backward()
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
            optimizer.step()
            optimizer.zero_grad()
            total += out.loss.item()
            steps += 1
        dev_loss = evaluate(model, dev, tokenizer, args, pad_id)
        record = {"epoch": epoch, "trainLoss": round(total / max(steps, 1), 4), "devLoss": dev_loss,
                  "seconds": round(time.time() - started, 1)}
        history.append(record)
        print(json.dumps(record), flush=True)
        if dev_loss < best[0]:
            best = (dev_loss, epoch)
            model.save_pretrained(os.path.join(args.out, "lora-best"))
            tokenizer.save_pretrained(os.path.join(args.out, "lora-best"))
    model.save_pretrained(os.path.join(args.out, "lora-final"))
    tokenizer.save_pretrained(os.path.join(args.out, "lora-final"))
    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as handle:
        json.dump({"args": vars(args), "history": history, "best": {"devLoss": best[0], "epoch": best[1]}}, handle, ensure_ascii=False, indent=1)
    print("DONE", best)


if __name__ == "__main__":
    main()
