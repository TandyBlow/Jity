# -*- coding: utf-8 -*-
"""YuYan LoRA trainer for the v2 result-block rows.

This is the controlled diagnostic arm for the format fix.  It reuses the frozen
v1 model definition, checkpoint loader and LoRA implementation by importing
`experiments/world-components/narration-dataset-v1/yuyan/train_yuyan.py`, but
adds what the v1 script lacks:

  * a config file with fixed data / base / tokenizer / seed identities;
  * a response mask that scores only `yMarked` + EOS;
  * checkpoints that can be resumed (adapter + optimizer + epoch + RNG);
  * a report that records the actual hashes, row ids and response counts.

Nothing in this file writes to the source dataset or the source worktree.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
import os
import random
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(V2, "..", ".."))
SOURCE_TRAIN = os.environ.get("NARR_SOURCE_TRAIN") or os.path.join(
    REPO, "experiments", "world-components", "narration-dataset-v1",
    "yuyan", "train_yuyan.py")
SOURCE_TRAIN_SHA256_LF = "7c04d652c3ee0b77513bac20bc95e8c216e287ffaa274674c369cae737643f4e"


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def lf_sha256_file(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read().replace(b"\r\n", b"\n")).hexdigest()


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


def load_source_module():
    if not os.path.exists(SOURCE_TRAIN):
        raise SystemExit(f"source trainer not found: {SOURCE_TRAIN}")
    actual = lf_sha256_file(SOURCE_TRAIN)
    if actual != SOURCE_TRAIN_SHA256_LF:
        raise SystemExit(
            f"source trainer LF sha256 {actual} != registered {SOURCE_TRAIN_SHA256_LF}; "
            "record the new identity before training")
    spec = importlib.util.spec_from_file_location("frozen_train_yuyan", SOURCE_TRAIN)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot import source trainer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_path(value: str) -> str:
    """Resolve config paths: ~ expands, relative paths are repo-relative."""
    value = os.path.expanduser(value)
    if not os.path.isabs(value):
        value = os.path.join(REPO, value)
    return os.path.abspath(value)


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
    parser.add_argument("--dict", default="")
    parser.add_argument("--splits", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--resume", default="", help="resume.pt path, or 'auto'")
    parser.add_argument("--epochs", type=int, default=0)
    parser.add_argument("--lr", type=float, default=0.0)
    parser.add_argument("--mode", default="")
    args = parser.parse_args()

    with io.open(args.config, encoding="utf-8") as handle:
        config = json.load(handle)
    config_sha = sha256_text(json.dumps(config, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")))

    data_path = resolve_path(args.data or config["data"]["file"])
    base_path = resolve_path(args.base or config["base"]["file"])
    dict_path = resolve_path(args.dict or config["tokenizer"]["file"])
    splits_path = resolve_path(args.splits or config["splits"]["file"])
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    source = load_source_module()
    device = "cuda"
    if not torch.cuda.is_available():
        raise SystemExit("no CUDA device; this trainer is meant for the GPU node")
    device_name = torch.cuda.get_device_name(0)

    # ---- identities -----------------------------------------------------
    if not os.path.exists(data_path):
        raise SystemExit(f"data not found: {data_path}")
    if not os.path.exists(base_path):
        raise SystemExit(f"base checkpoint not found: {base_path}")
    if not os.path.exists(dict_path):
        raise SystemExit(f"tokenizer dict not found: {dict_path}")
    if not os.path.exists(splits_path):
        raise SystemExit(f"splits not found: {splits_path}")

    data_sha = sha256_file(data_path)
    expected_data = config["data"].get("sha256")
    if expected_data and data_sha != expected_data:
        raise SystemExit(f"data sha256 {data_sha} != config {expected_data}")
    split_sha = lf_sha256_file(splits_path)
    expected_split = config["splits"].get("sha256Lf")
    if expected_split and split_sha != expected_split:
        raise SystemExit(f"split sha256 {split_sha} != config {expected_split}")
    dict_sha = sha256_file(dict_path)
    expected_dict = config["tokenizer"].get("sha256")
    if expected_dict and dict_sha != expected_dict:
        raise SystemExit(f"tokenizer sha256 {dict_sha} != config {expected_dict}")

    print(f"hashing base checkpoint: {base_path}", flush=True)
    base_sha = sha256_file(base_path)
    expected_base = config["base"].get("sha256")
    if expected_base and base_sha != expected_base:
        raise SystemExit(f"base sha256 {base_sha} != config {expected_base}")

    manifest_path = (resolve_path(config["data"]["manifest"])
                     if config["data"].get("manifest") else "")
    manifest_sha = (sha256_file(manifest_path)
                    if manifest_path and os.path.exists(manifest_path) else None)

    # ---- data -----------------------------------------------------------
    rows = read_jsonl(data_path)
    by_id = {row["id"]: row for row in rows}
    with io.open(splits_path, encoding="utf-8") as handle:
        split = json.load(handle)
    train_ids = list(split["train"])
    dev_ids = list(split["dev"])
    test_ids = list(split["test"])
    if set(train_ids) & set(dev_ids) or set(train_ids) & set(test_ids) or \
            set(dev_ids) & set(test_ids):
        raise SystemExit("split sets overlap")
    missing = (set(train_ids) | set(dev_ids) | set(test_ids)) - set(by_id)
    if missing:
        raise SystemExit(f"split ids missing from data: {sorted(missing)[:5]}")
    train_rows = [by_id[row_id] for row_id in train_ids]
    dev_rows = [by_id[row_id] for row_id in dev_ids]
    test_rows = [by_id[row_id] for row_id in test_ids]

    # answer isolation and response-mask preconditions
    leak_problems: List[str] = []
    for row in rows:
        x = row["xProse"]
        y = row["y"]
        if y.strip() and y.strip() in x:
            leak_problems.append(f"{row['id']}: target in xProse")
        for start in range(0, max(len(y) - 40, 0), 40):
            chunk = y[start:start + 40]
            if chunk and chunk in x:
                leak_problems.append(f"{row['id']}: 40-char target run at {start}")
                break
    if leak_problems:
        raise SystemExit("answer isolation failed: " + "; ".join(leak_problems[:5]))

    mode = args.mode or config["base"].get("mode", "lora")
    hyper = dict(config["training"])
    if args.epochs:
        hyper["epochs"] = args.epochs
    if args.lr:
        hyper["lr"] = args.lr
    seed = int(config.get("seed", 20261109))
    torch.manual_seed(seed)
    random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    # ---- model ----------------------------------------------------------
    tokens = source.load_vocab(dict_path)
    index = {char: i for i, char in enumerate(tokens)}
    eos = index["</s>"]
    checkpoint = source.load_checkpoint(base_path)
    cfg = checkpoint.get("cfg", {}).get("model", {}) or {}
    model, shape = source.build_from_state(checkpoint["model"],
                                            heads=cfg.get("decoder_attention_heads"))
    del checkpoint
    model = model.to(device)
    params = sum(p.numel() for p in model.parameters())
    if mode == "lora":
        model = source.apply_lora(model, int(hyper["rank"]), int(hyper["alpha"])).to(device)
    trainable = [p for p in model.parameters() if p.requires_grad]
    trainable_params = sum(p.numel() for p in trainable)
    optimizer = torch.optim.AdamW(trainable, lr=float(hyper["lr"]),
                                  weight_decay=float(hyper.get("weightDecay", 0.0)))
    max_len = int(hyper["maxLen"])
    batch_size = int(hyper.get("batch", 1))

    def pack(row: Dict[str, Any]) -> Tuple[List[int], List[int]]:
        prompt = source.encode(row["xProse"], index)
        target = source.encode(row["yMarked"], index) + [eos]
        ids = (prompt + target)[:max_len + 1]
        labels = [-100] * (len(prompt) - 1) + ids[len(prompt):]
        if len(labels) != len(ids) - 1:
            raise SystemExit("response mask length mismatch")
        if any(label != -100 for label in labels[:max(0, len(prompt) - 1)]):
            raise SystemExit("prompt token received a supervised label")
        return ids[:-1], labels

    # measure lengths and response-token counts
    lengths: List[Dict[str, Any]] = []
    for row in rows:
        ids, labels = pack(row)
        prompt_len = len(ids) - sum(1 for label in labels if label != -100)
        target_len = sum(1 for label in labels if label != -100)
        lengths.append({"id": row["id"], "inputTokens": len(ids),
                        "promptTokens": prompt_len, "targetTokens": target_len,
                        "truncated": len(row["xProse"]) + len(row["yMarked"]) > max_len})
    if any(item["truncated"] for item in lengths):
        raise SystemExit("a row was truncated; refusing to train silently")

    # ---- resume ---------------------------------------------------------
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
        if not os.path.exists(resume_path):
            raise SystemExit(f"resume checkpoint not found: {resume_path}")
        state = torch.load(resume_path, map_location="cpu", weights_only=False)
        adapter = state["adapter"]
        missing, unexpected = model.load_state_dict(adapter, strict=False)
        if unexpected:
            raise SystemExit(f"resume adapter has unexpected tensors: {unexpected[:5]}")
        if not any(key.endswith("down.weight") or key.endswith("up.weight")
                   for key in adapter):
            raise SystemExit("resume adapter contains no LoRA tensors")
        optimizer.load_state_dict(state["optimizer"])
        start_epoch = int(state["epoch"]) + 1
        best = state["best"]
        history = state.get("history", [])
        torch.set_rng_state(state["torchRng"])
        random.setstate(state["pythonRng"])
        if torch.cuda.is_available() and state.get("cudaRng"):
            torch.cuda.set_rng_state_all(state["cudaRng"])
        print(f"resumed from {resume_path} at epoch {start_epoch}", flush=True)

    def evaluate(subset: List[Dict[str, Any]]) -> Tuple[float, List[Dict[str, Any]]]:
        model.eval()
        total, count = 0.0, 0
        per_row: List[Dict[str, Any]] = []
        with torch.no_grad():
            for row in subset:
                ids, labels = pack(row)
                x = torch.tensor([ids], device=device)
                y = torch.tensor([labels], device=device)
                logits = model(x)[0]
                loss = torch.nn.functional.cross_entropy(
                    logits.view(-1, shape["vocab"]), y.view(-1),
                    ignore_index=-100, reduction="sum")
                tokens_seen = int((y != -100).sum())
                total += float(loss.item())
                count += tokens_seen
                per_row.append({"id": row["id"], "loss": round(float(loss.item() /
                                                                    max(tokens_seen, 1)), 4),
                                "tokens": tokens_seen})
        model.train()
        return round(total / max(count, 1), 4), per_row

    def generate(row: Dict[str, Any], max_new: int, temperature: float = 0.0,
                 seed_value: int = 42, min_new: int = 16) -> Dict[str, Any]:
        model.eval()
        ids = source.encode(row["xProse"], index)
        x = torch.tensor([ids], device=device)
        torch.manual_seed(seed_value)
        with torch.no_grad():
            for _ in range(max_new):
                logits = model(x[:, -max_len:])[0, -1].clone()
                produced = x.shape[1] - len(ids)
                if produced < min_new:
                    logits[eos] = -1e9
                if temperature == 0:
                    nxt = int(logits.argmax())
                else:
                    probs = torch.softmax(logits / temperature, dim=-1)
                    nxt = int(torch.multinomial(probs, 1))
                if nxt == eos:
                    break
                x = torch.cat([x, torch.tensor([[nxt]], device=device)], dim=1)
        text = "".join(tokens[i] for i in x[0, len(ids):].tolist())
        text = text.replace(source.PARA_MARK, "\n\n")
        grams = [text[i:i + 4] for i in range(max(len(text) - 3, 0))]
        counts: Dict[str, int] = {}
        for gram in grams:
            counts[gram] = counts.get(gram, 0) + 1
        stop = "eos" if x.shape[1] > len(ids) and int(x[0, -1]) == eos else "length"
        model.train()
        return {"id": row["id"], "targetChars": len(row["y"]),
                "chars": len(text), "maxRepeat4": max(counts.values()) if counts else 0,
                "distinct4": round(len(counts) / len(grams), 3) if grams else 0.0,
                "stopReason": stop, "text": text}

    started = time.time()
    max_epochs = int(hyper["epochs"])
    print(json.dumps({"rows": len(rows), "train": len(train_rows), "dev": len(dev_rows),
                      "test": len(test_rows), "trainableParams": trainable_params,
                      "params": params, "dataSha256": data_sha, "baseSha256": base_sha,
                      "dictSha256": dict_sha, "seed": seed, "mode": mode,
                      "maxLen": max_len}), ensure_ascii=False, flush=True)

    for epoch in range(start_epoch, max_epochs + 1):
        epoch_started = time.time()
        random.shuffle(train_rows)
        total, steps = 0.0, 0
        batch_ids: List[List[int]] = []
        batch_labels: List[List[int]] = []

        def flush() -> None:
            nonlocal total, steps, batch_ids, batch_labels
            if not batch_ids:
                return
            width = max(len(item) for item in batch_ids)
            x = torch.full((len(batch_ids), width), index["<pad>"], device=device)
            y = torch.full((len(batch_ids), width), -100, device=device)
            for row_index, (ids, labels) in enumerate(zip(batch_ids, batch_labels)):
                x[row_index, :len(ids)] = torch.tensor(ids, device=device)
                y[row_index, :len(labels)] = torch.tensor(labels, device=device)
            logits = model(x)
            loss = torch.nn.functional.cross_entropy(
                logits.view(-1, shape["vocab"]), y.view(-1), ignore_index=-100)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, float(hyper.get("gradClip", 1.0)))
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            total += float(loss.item())
            steps += 1
            batch_ids, batch_labels = [], []

        for row in train_rows:
            ids, labels = pack(row)
            batch_ids.append(ids)
            batch_labels.append(labels)
            if len(batch_ids) == batch_size:
                flush()
        flush()
        dev_loss, dev_rows = evaluate(dev_rows)
        entry = {"epoch": epoch, "loss": round(total / max(steps, 1), 4),
                 "devLoss": dev_loss, "devPerRow": dev_rows,
                 "elapsedSec": round(time.time() - epoch_started, 1),
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
        torch.save({
            "epoch": epoch,
            "adapter": adapter_now,
            "optimizer": optimizer.state_dict(),
            "best": best,
            "history": history,
            "torchRng": torch.get_rng_state(),
            "pythonRng": random.getstate(),
            "cudaRng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
            "configSha256": config_sha,
            "dataSha256": data_sha,
            "baseSha256": base_sha,
            "dictSha256": dict_sha,
        }, os.path.join(out_dir, "resume.pt"))
        if best["epoch"] == epoch:
            torch.save(best["adapter"], os.path.join(out_dir, "adapter-best.pt"))

    # ---- final evaluation and samples ----------------------------------
    if best["adapter"] is not None:
        missing, unexpected = model.load_state_dict(best["adapter"], strict=False)
        if unexpected:
            raise SystemExit(f"best adapter has unexpected tensors: {unexpected[:5]}")
        print(f"reloaded best epoch {best['epoch']} dev {best['devLoss']}", flush=True)
    train_loss, _ = evaluate(train_rows)
    dev_loss, dev_per_row = evaluate(dev_rows)
    test_loss, test_per_row = evaluate(test_rows) if test_rows else (None, [])
    sample_rows = (dev_rows[:2] + test_rows[:2] + train_rows[:1])
    samples = []
    for row in sample_rows:
        greedy = generate(row, int(hyper.get("sampleMaxNew", 600)))
        sampled = generate(row, int(hyper.get("sampleMaxNew", 600)), temperature=0.8)
        samples.append({"id": row["id"], "trainedOnThisRow": row in train_rows,
                        "targetChars": len(row["y"]),
                        "greedy": greedy, "sampled": sampled})
    with io.open(os.path.join(out_dir, "samples.txt"), "w", encoding="utf-8",
                 newline="\n") as handle:
        for sample in samples:
            handle.write(f"=== {sample['id']} trained={sample['trainedOnThisRow']} "
                         f"target={sample['targetChars']}\n-- greedy --\n"
                         f"{sample['greedy']['text']}\n-- sampled --\n"
                         f"{sample['sampled']['text']}\n\n")

    report = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "runId": config.get("runId", "yuyan-lora-v2"),
        "codeCommit": git_commit(),
        "configPath": os.path.abspath(args.config),
        "configSha256": config_sha,
        "backend": "yuyan",
        "mode": mode,
        "device": device_name,
        "torch": torch.__version__,
        "shape": shape,
        "params": params,
        "trainableParams": trainable_params,
        "identity": {
            "dataPath": os.path.abspath(data_path),
            "dataSha256": data_sha,
            "dataManifest": os.path.abspath(manifest_path) if manifest_path else None,
            "dataManifestSha256": manifest_sha,
            "splitsPath": os.path.abspath(splits_path),
            "splitSha256Lf": split_sha,
            "basePath": os.path.abspath(base_path),
            "baseSha256": base_sha,
            "dictPath": os.path.abspath(dict_path),
            "dictSha256": dict_sha,
            "trainIdsSha256": sha256_text("\n".join(train_ids) + "\n"),
            "devIdsSha256": sha256_text("\n".join(dev_ids) + "\n"),
            "testIdsSha256": sha256_text("\n".join(test_ids) + "\n"),
            "trainRows": len(train_ids), "devRows": len(dev_ids),
            "testRows": len(test_ids),
            "seed": seed,
        },
        "responseMask": {
            "policy": "target_only",
            "promptField": "xProse",
            "targetField": "yMarked",
            "eos": "</s>",
            "promptLabels": -100,
            "targetLabels": "token ids",
            "lengths": {
                "inputTokens": {"min": min(item["inputTokens"] for item in lengths),
                                "max": max(item["inputTokens"] for item in lengths),
                                "mean": round(sum(item["inputTokens"] for item in lengths) /
                                              len(lengths), 1)},
                "targetTokens": {"min": min(item["targetTokens"] for item in lengths),
                                 "max": max(item["targetTokens"] for item in lengths),
                                 "mean": round(sum(item["targetTokens"] for item in lengths) /
                                               len(lengths), 1)},
                "truncatedRows": sum(1 for item in lengths if item["truncated"]),
            },
        },
        "hyper": hyper,
        "history": history,
        "best": {"epoch": best["epoch"], "devLoss": best["devLoss"]},
        "final": {"trainLoss": train_loss, "devLoss": dev_loss,
                  "testLoss": test_loss, "devPerRow": dev_per_row,
                  "testPerRow": test_per_row},
        "samples": samples,
        "resume": {"path": resume_path or None,
                   "startEpoch": start_epoch,
                   "checkpoint": os.path.join(out_dir, "resume.pt")},
        "seconds": round(time.time() - started, 1),
    }
    atomic_json(os.path.join(out_dir, "report.json"), report)
    print(json.dumps({"runId": report["runId"], "best": report["best"],
                      "final": {"trainLoss": train_loss, "devLoss": dev_loss,
                                "testLoss": test_loss},
                      "seconds": report["seconds"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
