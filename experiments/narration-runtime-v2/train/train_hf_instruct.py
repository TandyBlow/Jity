# -*- coding: utf-8 -*-
"""Instruction-tuned causal-LM trainer for the v2 result-block rows.

This is the generic HPC entry for an instruct base (Qwen/ChatML-style).  It is
deliberately separate from the YuYan arm because the tokenizer, chat template
and model class differ.  The config is a template until a base is selected; the
script refuses a config whose `status` is still `pending`.

Contract:

  prompt   = tokenizer.apply_chat_template(system + user, add_generation_prompt=True)
  target   = row.y + tokenizer.eos_token
  labels   = [-100] * len(prompt_ids) + target_ids

The prompt tokens never receive a loss; the target text and every 40-character
run of it are checked against the prompt before training.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import random
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(V2, "..", ".."))


def resolve_path(value: str) -> str:
    value = os.path.expanduser(value)
    if not os.path.isabs(value):
        value = os.path.join(REPO, value)
    return os.path.abspath(value)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def atomic_json(path: str, value: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def hash_directory(path: str) -> Dict[str, Any]:
    records: Dict[str, Any] = {}
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        if os.path.isfile(full):
            records[name] = {"bytes": os.path.getsize(full), "sha256": sha256_file(full)}
    payload = "\n".join(f"{name}\t{record['sha256']}" for name, record in records.items())
    return {"files": records, "combinedSha256": sha256_text(payload)}


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                              check=True, capture_output=True, text=True).stdout.strip()
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--data", default="")
    parser.add_argument("--base", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--resume", default="", help="resume.pt path, or 'auto'")
    parser.add_argument("--epochs", type=int, default=0)
    args = parser.parse_args()

    with io.open(args.config, encoding="utf-8") as handle:
        config = json.load(handle)
    if config.get("status") == "pending":
        raise SystemExit("config is still a template (status=pending); select a base and tokenizer "
                         "and fill their hashes before submitting")
    config_sha = sha256_text(json.dumps(config, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")))
    data_path = resolve_path(args.data or config["data"]["file"])
    base_path = resolve_path(args.base or config["base"]["file"])
    splits_path = resolve_path(config["splits"]["file"])
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available():
        raise SystemExit("no CUDA device; this trainer is meant for the GPU node")
    device = "cuda"

    data_sha = sha256_file(data_path)
    if config["data"].get("sha256") and data_sha != config["data"]["sha256"]:
        raise SystemExit(f"data sha256 {data_sha} != config {config['data']['sha256']}")
    split_sha = sha256_file(splits_path)
    if config["splits"].get("sha256Lf"):
        with open(splits_path, "rb") as handle:
            lf = hashlib.sha256(handle.read().replace(b"\r\n", b"\n")).hexdigest()
        if lf != config["splits"]["sha256Lf"]:
            raise SystemExit(f"split LF sha256 {lf} != config {config['splits']['sha256Lf']}")
    base_hashes = hash_directory(base_path)
    if config["base"].get("combinedSha256") and \
            base_hashes["combinedSha256"] != config["base"]["combinedSha256"]:
        raise SystemExit("base directory combined hash differs from config")

    rows = read_jsonl(data_path)
    by_id = {row["id"]: row for row in rows}
    with io.open(splits_path, encoding="utf-8") as handle:
        split = json.load(handle)
    train_ids, dev_ids, test_ids = split["train"], split["dev"], split["test"]
    if (set(train_ids) & set(dev_ids)) or (set(train_ids) & set(test_ids)) or \
            (set(dev_ids) & set(test_ids)):
        raise SystemExit("split sets overlap")
    missing = (set(train_ids) | set(dev_ids) | set(test_ids)) - set(by_id)
    if missing:
        raise SystemExit(f"split ids missing: {sorted(missing)[:5]}")
    train_rows = [by_id[row_id] for row_id in train_ids]
    dev_rows = [by_id[row_id] for row_id in dev_ids]
    test_rows = [by_id[row_id] for row_id in test_ids]

    template = config["template"]
    tokenizer = AutoTokenizer.from_pretrained(base_path, local_files_only=True,
                                              trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    eos = tokenizer.eos_token
    if eos is None:
        raise SystemExit("tokenizer has no eos token")

    def build(row: Dict[str, Any], max_len: int) -> Optional[Tuple[List[int], List[int],
                                                                   Dict[str, Any]]]:
        user = template["userPrefix"] + row["xProse"] + template["userSuffix"]
        prompt_text = tokenizer.apply_chat_template(
            [{"role": "system", "content": template["system"]},
             {"role": "user", "content": user}],
            tokenize=False, add_generation_prompt=True)
        prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        target_text = row[template.get("targetField", "y")] + eos
        target_ids = tokenizer(target_text, add_special_tokens=False)["input_ids"]
        keep = max_len - len(target_ids)
        if keep < 64:
            return None
        if len(prompt_ids) > keep:
            prompt_ids = prompt_ids[-keep:]
        prompt_len = len(prompt_ids)
        labels = [-100] * prompt_len + target_ids
        return prompt_ids + target_ids, labels, {
            "promptTokens": prompt_len, "targetTokens": len(target_ids),
            "promptTextSha256": sha256_text(prompt_text),
            "inputTokens": prompt_len + len(target_ids),
        }

    max_len = int(config["training"]["maxSeqLen"])
    built = []
    for row in rows:
        item = build(row, max_len)
        if item is None:
            raise SystemExit(f"{row['id']}: target too long for maxSeqLen {max_len}")
        prompt_ids, labels, stats = item
        prompt_len = stats["promptTokens"]
        if len(labels) != len(prompt_ids):
            raise SystemExit(f"{row['id']}: response mask length mismatch")
        if any(label != -100 for label in labels[:prompt_len]):
            raise SystemExit(f"{row['id']}: prompt token received a supervised label")
        if any(label == -100 for label in labels[prompt_len:]):
            raise SystemExit(f"{row['id']}: target token lost its label")
        prompt_text = tokenizer.decode(prompt_ids)
        target_text = row[template.get("targetField", "y")]
        if target_text.strip() and target_text.strip() in prompt_text:
            raise SystemExit(f"{row['id']}: target text leaked into the prompt")
        for start in range(0, max(len(target_text) - 40, 0), 40):
            chunk = target_text[start:start + 40]
            if chunk and chunk in prompt_text:
                raise SystemExit(f"{row['id']}: 40-char target run leaked into the prompt")
        built.append({"row": row, "ids": prompt_ids, "labels": labels, **stats})
    by_built = {item["row"]["id"]: item for item in built}

    dtype_name = config["training"].get("dtype", "bfloat16")
    dtype = {"bfloat16": torch.bfloat16, "float16": torch.float16,
             "float32": torch.float32}[dtype_name]
    model = AutoModelForCausalLM.from_pretrained(base_path, local_files_only=True,
                                                 trust_remote_code=False,
                                                 torch_dtype=dtype)
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model.to(device)
    from peft import LoraConfig, get_peft_model
    lora = config["training"]["lora"]
    model = get_peft_model(model, LoraConfig(
        r=int(lora["r"]), lora_alpha=int(lora["alpha"]),
        lora_dropout=float(lora.get("dropout", 0.05)), bias="none",
        task_type="CAUSAL_LM", target_modules=list(lora["targetModules"])))
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=float(config["training"]["lr"]),
                                  weight_decay=float(config["training"].get("weightDecay", 0.0)))
    seed = int(config.get("seed", 20261109))
    torch.manual_seed(seed)
    random.seed(seed)
    torch.cuda.manual_seed_all(seed)

    def collate(items: List[Dict[str, Any]]) -> Tuple[Any, Any, Any]:
        width = max(len(item["ids"]) for item in items)
        x = torch.full((len(items), width), tokenizer.pad_token_id, dtype=torch.long)
        y = torch.full((len(items), width), -100, dtype=torch.long)
        mask = torch.zeros((len(items), width), dtype=torch.long)
        for index, item in enumerate(items):
            x[index, :len(item["ids"])] = torch.tensor(item["ids"])
            y[index, :len(item["labels"])] = torch.tensor(item["labels"])
            mask[index, :len(item["ids"])] = 1
        return x.to(device), y.to(device), mask.to(device)

    def evaluate(subset: List[Dict[str, Any]]) -> Tuple[float, List[Dict[str, Any]]]:
        model.eval()
        total, count = 0.0, 0
        per_row = []
        with torch.no_grad():
            for start in range(0, len(subset), 2):
                items = [by_built[row["id"]] for row in subset[start:start + 2]]
                x, y, mask = collate(items)
                out = model(input_ids=x, attention_mask=mask, labels=y)
                tokens = int((y != -100).sum())
                total += float(out.loss.item()) * tokens
                count += tokens
                per_row.append({"ids": [item["row"]["id"] for item in items],
                                "loss": round(float(out.loss.item()), 4),
                                "tokens": tokens})
        model.train()
        return round(total / max(count, 1), 4), per_row

    resume_path = ""
    if args.resume == "auto":
        candidate = os.path.join(out_dir, "resume.pt")
        resume_path = candidate if os.path.exists(candidate) else ""
    elif args.resume:
        resume_path = os.path.abspath(args.resume)
    start_epoch = 1
    best = {"devLoss": float("inf"), "epoch": 0, "adapter": None}
    history: List[Dict[str, Any]] = []
    if resume_path:
        state = torch.load(resume_path, map_location="cpu", weights_only=False)
        missing, unexpected = model.load_state_dict(state["adapter"], strict=False)
        if unexpected:
            raise SystemExit(f"resume adapter has unexpected tensors: {unexpected[:5]}")
        optimizer.load_state_dict(state["optimizer"])
        start_epoch = int(state["epoch"]) + 1
        best = state["best"]
        history = state.get("history", [])
        torch.set_rng_state(state["torchRng"])
        random.setstate(state["pythonRng"])
        if state.get("cudaRng"):
            torch.cuda.set_rng_state_all(state["cudaRng"])
        print(f"resumed from {resume_path} at epoch {start_epoch}", flush=True)

    epochs = args.epochs or int(config["training"]["epochs"])
    batch_size = int(config["training"]["batch"])
    started = time.time()
    for epoch in range(start_epoch, epochs + 1):
        epoch_started = time.time()
        random.shuffle(train_rows)
        model.train()
        total, steps = 0.0, 0
        for start in range(0, len(train_rows), batch_size):
            items = [by_built[row["id"]] for row in train_rows[start:start + batch_size]]
            x, y, mask = collate(items)
            out = model(input_ids=x, attention_mask=mask, labels=y)
            (out.loss / len(items)).backward()
            torch.nn.utils.clip_grad_norm_(trainable,
                                           float(config["training"].get("gradClip", 1.0)))
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            total += float(out.loss.item())
            steps += 1
        dev_loss, per_row = evaluate(dev_rows)
        entry = {"epoch": epoch, "trainLoss": round(total / max(steps, 1), 4),
                 "devLoss": dev_loss, "devPerRow": per_row,
                 "seconds": round(time.time() - epoch_started, 1),
                 "peakAllocatedMb": round(torch.cuda.max_memory_allocated() / 2**20)}
        history.append(entry)
        if dev_loss < best["devLoss"]:
            best = {"devLoss": dev_loss, "epoch": epoch,
                    "adapter": {name: tensor.detach().cpu().clone()
                                for name, tensor in model.named_parameters()
                                if tensor.requires_grad}}
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        adapter_now = {name: tensor.detach().cpu()
                       for name, tensor in model.named_parameters() if tensor.requires_grad}
        torch.save(adapter_now, os.path.join(out_dir, f"adapter-epoch-{epoch}.pt"))
        torch.save({"epoch": epoch, "adapter": adapter_now,
                    "optimizer": optimizer.state_dict(), "best": best,
                    "history": history, "torchRng": torch.get_rng_state(),
                    "pythonRng": random.getstate(),
                    "cudaRng": torch.cuda.get_rng_state_all(),
                    "configSha256": config_sha, "dataSha256": data_sha,
                    "baseCombinedSha256": base_hashes["combinedSha256"]},
                   os.path.join(out_dir, "resume.pt"))
        if best["epoch"] == epoch:
            torch.save(best["adapter"], os.path.join(out_dir, "adapter-best.pt"))

    if best["adapter"] is not None:
        missing, unexpected = model.load_state_dict(best["adapter"], strict=False)
        if unexpected:
            raise SystemExit(f"best adapter has unexpected tensors: {unexpected[:5]}")
    train_loss, _ = evaluate(train_rows)
    dev_loss, dev_per_row = evaluate(dev_rows)
    test_loss, test_per_row = evaluate(test_rows) if test_rows else (None, [])
    samples = []
    model.eval()
    for row in (dev_rows[:2] + test_rows[:2] + train_rows[:1]):
        prompt = tokenizer.apply_chat_template(
            [{"role": "system", "content": template["system"]},
             {"role": "user", "content": template["userPrefix"] + row["xProse"] +
              template["userSuffix"]}],
            tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(device)
        with torch.no_grad():
            output = model.generate(**inputs, max_new_tokens=int(config["training"].get(
                "sampleMaxNew", 600)), do_sample=False,
                eos_token_id=tokenizer.eos_token_id,
                pad_token_id=tokenizer.pad_token_id)
        text = tokenizer.decode(output[0, inputs["input_ids"].shape[1]:],
                                skip_special_tokens=True)
        samples.append({"id": row["id"], "trainedOnThisRow": row in train_rows,
                        "targetChars": len(row["y"]), "chars": len(text),
                        "stopReason": "eos" if output[0, -1].item() == tokenizer.eos_token_id
                        else "length", "text": text})
    with io.open(os.path.join(out_dir, "samples.txt"), "w", encoding="utf-8",
                 newline="\n") as handle:
        for sample in samples:
            handle.write(f"=== {sample['id']} trained={sample['trainedOnThisRow']} "
                         f"target={sample['targetChars']}\n{sample['text']}\n\n")

    report = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "runId": config.get("runId", "instruct-result-v2"),
        "codeCommit": git_commit(),
        "configPath": os.path.abspath(args.config),
        "configSha256": config_sha,
        "backend": "hf-causal",
        "device": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "identity": {
            "dataPath": os.path.abspath(data_path), "dataSha256": data_sha,
            "splitsPath": os.path.abspath(splits_path), "splitSha256Lf": split_sha,
            "basePath": os.path.abspath(base_path), "baseHashes": base_hashes,
            "tokenizerPath": os.path.abspath(base_path),
            "trainIdsSha256": sha256_text("\n".join(train_ids) + "\n"),
            "devIdsSha256": sha256_text("\n".join(dev_ids) + "\n"),
            "testIdsSha256": sha256_text("\n".join(test_ids) + "\n"),
            "trainRows": len(train_ids), "devRows": len(dev_ids), "testRows": len(test_ids),
            "seed": seed,
        },
        "template": template,
        "responseMask": {
            "policy": "target_only",
            "promptLabels": -100,
            "targetLabels": "token ids",
            "eos": eos,
            "lengths": {
                "inputTokens": {"min": min(item["inputTokens"] for item in built),
                                "max": max(item["inputTokens"] for item in built),
                                "mean": round(sum(item["inputTokens"] for item in built) /
                                              len(built), 1)},
                "targetTokens": {"min": min(item["targetTokens"] for item in built),
                                 "max": max(item["targetTokens"] for item in built),
                                 "mean": round(sum(item["targetTokens"] for item in built) /
                                               len(built), 1)},
            },
        },
        "hyper": config["training"],
        "history": history,
        "best": {"epoch": best["epoch"], "devLoss": best["devLoss"]},
        "final": {"trainLoss": train_loss, "devLoss": dev_loss, "testLoss": test_loss,
                  "devPerRow": dev_per_row, "testPerRow": test_per_row},
        "samples": samples,
        "seconds": round(time.time() - started, 1),
    }
    atomic_json(os.path.join(out_dir, "report.json"), report)
    print(json.dumps({"runId": report["runId"], "best": report["best"],
                      "final": {"trainLoss": train_loss, "devLoss": dev_loss,
                                "testLoss": test_loss}, "seconds": report["seconds"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
