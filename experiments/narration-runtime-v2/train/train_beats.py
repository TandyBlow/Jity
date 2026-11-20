# -*- coding: utf-8 -*-
"""LoRA fine-tune of a Qwen2.5 instruct base on beat and scene narration.

Two sample shapes, both chat-templated with the tokenizer's own template:

  beat  : system = the published style line, user = the beat prompt
          (【场景】…【本拍事实】…【正文】), assistant = the verified 1-2 sentence
          target.
  scene : system = the same style line, user = the yuyan-prose-result-v2
          xProse text, assistant = the hand-written scene target.

Loss is computed on the assistant tokens only. The run refuses to start when a
target is too long for the window or when the prompt already contains the
target (answer leak). Identity (data/base/tokenizer hashes, seed, template) is
written into the report so a candidate can be registered without guessing.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import torch
import torch.nn.functional as F
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

# Must equal the system message the GGUF chat template inserts when the
# browser passes a single user turn (Qwen2.5 default). Training with a custom
# Chinese system line and inferring without it silently changes the prefix.
SYSTEM = "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."

MOUNT = ""


def configure_paths(root: str, mount: str) -> None:
    global ROOT, MOUNT
    ROOT = root
    MOUNT = mount


def sha256_file(path: str) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def resolve(path: str) -> str:
    if path.startswith("hpc:"):
        return os.path.expanduser(path[4:])
    if path.startswith("~"):
        return os.path.expanduser(path)
    if os.path.isabs(path):
        return path
    base = os.environ.get("NARR_ROOT") or MOUNT or ROOT
    return os.path.normpath(os.path.join(base, path))


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_items(tokenizer, beats: List[Dict[str, Any]], scenes: List[Dict[str, Any]],
                max_len: int, variants: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for beat in beats:
        target = (beat.get("target") or "").strip()
        if not target:
            continue
        user = beat["prompt"]
        prompt_text = tokenizer.apply_chat_template(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            tokenize=False, add_generation_prompt=True)
        prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        target_ids = tokenizer(target + tokenizer.eos_token, add_special_tokens=False)["input_ids"]
        if len(prompt_ids) + len(target_ids) > max_len:
            raise SystemExit(f"{beat['id']}: {len(prompt_ids)}+{len(target_ids)} > {max_len}")
        if len(target) >= 8 and target[:8] in user:
            raise SystemExit(f"{beat['id']}: target leak into prompt")
        items.append({"id": beat["id"], "kind": "beat", "split": beat["split"],
                      "promptIds": prompt_ids, "targetIds": target_ids,
                      "prompt": prompt_text, "target": target})
    for row in scenes:
        target = row["y"].strip()
        shapes = variants or ["xProse"]
        for shape in shapes:
            user = row.get(shape)
            if not user:
                continue
            prompt_text = tokenizer.apply_chat_template(
                [{"role": "system", "content": SYSTEM},
                 {"role": "user", "content": user}],
                tokenize=False, add_generation_prompt=True)
            prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
            target_ids = tokenizer(target + tokenizer.eos_token, add_special_tokens=False)["input_ids"]
            if len(prompt_ids) + len(target_ids) > max_len:
                raise SystemExit(f"scene {row['id']}/{shape}: "
                                 f"{len(prompt_ids)}+{len(target_ids)} > {max_len}")
            items.append({"id": f"{row['id']}:{shape}", "kind": "scene", "split": row["split"],
                          "promptIds": prompt_ids, "targetIds": target_ids,
                          "prompt": prompt_text, "target": target})
    return items


def build_mix_items(tokenizer, rows: List[Dict[str, Any]], max_len: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        prompt_text = tokenizer.apply_chat_template(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": row["user"]}],
            tokenize=False, add_generation_prompt=True)
        prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        target = row["target"].strip()
        if not target:
            raise SystemExit(f"{row['id']}: empty target")
        target_ids = tokenizer(target + tokenizer.eos_token, add_special_tokens=False)["input_ids"]
        if len(prompt_ids) + len(target_ids) > max_len:
            raise SystemExit(f"{row['id']}: {len(prompt_ids)}+{len(target_ids)} > {max_len}")
        if target in row["user"]:
            raise SystemExit(f"{row['id']}: the whole target is copied from the prompt")
        for _ in range(int(row.get("weight", 1))):
            items.append({"id": row["id"], "kind": row.get("mode", "scene"),
                          "split": row["split"], "promptIds": prompt_ids,
                          "targetIds": target_ids, "prompt": prompt_text,
                          "target": target})
    return items


def batch(items: List[Dict[str, Any]], pad_id: int):
    width = max(len(item["promptIds"]) + len(item["targetIds"]) for item in items)
    ids = torch.full((len(items), width), pad_id, dtype=torch.long)
    labels = torch.full((len(items), width), -100, dtype=torch.long)
    attention = torch.zeros((len(items), width), dtype=torch.long)
    for index, item in enumerate(items):
        whole = item["promptIds"] + item["targetIds"]
        ids[index, :len(whole)] = torch.tensor(whole)
        labels[index, len(item["promptIds"]):len(whole)] = torch.tensor(item["targetIds"])
        attention[index, :len(whole)] = 1
    return ids, labels, attention


def eval_dtype(device) -> "torch.dtype":
    """Autocast dtype for evaluation must match the training computation dtype."""
    if getattr(device, "type", str(device)) == "cuda":
        return torch.float16 if str(device) == "cuda" and AMP_STATE.get("fp16") else torch.bfloat16
    return torch.bfloat16


AMP_STATE: Dict[str, Any] = {"fp16": False, "enabled": False}


def evaluate(model, items: List[Dict[str, Any]], pad_id: int, device, batch_size: int) -> float:
    model.eval()
    total, tokens = 0.0, 0
    with torch.no_grad():
        for start in range(0, len(items), batch_size):
            chunk = items[start:start + batch_size]
            ids, labels, attention = batch(chunk, pad_id)
            ids, labels, attention = ids.to(device), labels.to(device), attention.to(device)
            with torch.autocast(device_type=str(device).split(":")[0],
                                dtype=eval_dtype(device),
                                enabled=AMP_STATE["enabled"]):
                out = model(input_ids=ids, attention_mask=attention, labels=labels)
            count = int((labels != -100).sum().item())
            total += float(out.loss.item()) * count
            tokens += count
    model.train()
    return total / max(tokens, 1)


def sample(model, tokenizer, item: Dict[str, Any], device, max_new: int) -> str:
    model.eval()
    ids = torch.tensor([item["promptIds"]], device=device)
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tokenizer.pad_token_id,
                             eos_token_id=tokenizer.eos_token_id)
    text = tokenizer.decode(out[0, ids.shape[1]:], skip_special_tokens=True)
    model.train()
    return text.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--resume", default="")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--epochs", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--precision", default="auto",
                        choices=("auto", "bf16", "fp16", "fp32"),
                        help="compute precision; fp16 is for GPUs without bf16 support (e.g. V100)")
    parser.add_argument("--sample-n", type=int, default=3)
    args = parser.parse_args()

    with io.open(args.config, encoding="utf-8") as handle:
        config = json.load(handle)
    configure_paths(config.get("root", os.getcwd()), config.get("mount", ""))
    seed = int(config.get("seed", 20261110))
    random.seed(seed)
    torch.manual_seed(seed)

    beats_file = config.get("beats", {}).get("file")
    beats_all = read_jsonl(resolve(beats_file)) if beats_file else []
    beats_hash = sha256_file(resolve(beats_file)) if beats_file else None
    scenes_all: List[Dict[str, Any]] = []
    scenes_hash = None
    if config.get("scenes", {}).get("file"):
        scenes_all = read_jsonl(resolve(config["scenes"]["file"]))
        scenes_hash = sha256_file(resolve(config["scenes"]["file"]))
    if config.get("beats", {}).get("keepKinds"):
        keep = set(config["beats"]["keepKinds"])
        beats_all = [beat for beat in beats_all if beat["fact"]["kind"] in keep]

    train = [beat for beat in beats_all if beat["split"] == "train"]
    dev = [beat for beat in beats_all if beat["split"] == "dev"]
    test = [beat for beat in beats_all if beat["split"] == "test"]
    mix_all: List[Dict[str, Any]] = []
    mix_hash = None
    if config.get("data", {}).get("file"):
        mix_all = read_jsonl(resolve(config["data"]["file"]))
        mix_hash = sha256_file(resolve(config["data"]["file"]))
        mix_train = [row for row in mix_all if row["split"] == "train"]
        mix_dev = [row for row in mix_all if row["split"] == "dev"]
        mix_test = [row for row in mix_all if row["split"] == "test"]
    else:
        mix_train = mix_dev = mix_test = []
    if config.get("splits", {}).get("file"):
        with io.open(resolve(config["splits"]["file"]), encoding="utf-8") as handle:
            split = json.load(handle)
        scene_split = {}
        for name in ("train", "dev", "test"):
            for row_id in split.get(name, []):
                scene_split[row_id] = name
        scenes = []
        for row in scenes_all:
            name = scene_split.get(row["id"])
            if not name:
                continue
            row = dict(row)
            row["split"] = name
            scenes.append(row)
        scenes_train = [row for row in scenes if row["split"] == "train"]
        scenes_dev = [row for row in scenes if row["split"] == "dev"]
        scenes_test = [row for row in scenes if row["split"] == "test"]
    else:
        scenes_train = scenes_dev = scenes_test = []

    base_path = resolve(config["base"]["file"])
    tokenizer_path = resolve(config.get("tokenizer", {}).get("file") or config["base"]["file"])
    base_hash = sha256_file(os.path.join(base_path, "model.safetensors")) \
        if os.path.isdir(base_path) else sha256_file(base_path)
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"

    max_len = int(config["training"]["maxLen"])
    variants = config.get("scenes", {}).get("variants", ["xProse"])
    if mix_train:
        train_items = build_mix_items(tokenizer, mix_train, max_len)
        dev_items = build_mix_items(tokenizer, mix_dev, max_len)
        test_items = build_mix_items(tokenizer, mix_test, max_len)
    else:
        train_items = build_items(tokenizer, train, scenes_train, max_len, variants)
        dev_items = build_items(tokenizer, dev, scenes_dev, max_len, variants)
        test_items = build_items(tokenizer, test, scenes_test, max_len, variants)
    if not train_items:
        raise SystemExit("no training items")

    precision = args.precision
    if precision == "auto":
        precision = "bf16" if (args.device != "cuda" or torch.cuda.is_bf16_supported()) else "fp16"
    model_dtype = {"fp16": torch.float16, "bf16": torch.bfloat16,
                   "fp32": torch.float32}[precision]
    model = AutoModelForCausalLM.from_pretrained(
        base_path, local_files_only=True, torch_dtype=model_dtype,
        device_map={"": 0} if args.device == "cuda" else None)
    if config["training"].get("gradientCheckpointing", True):
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()
    lora = config["training"]["lora"]
    peft_config = LoraConfig(
        r=int(lora["r"]), lora_alpha=int(lora["alpha"]),
        lora_dropout=float(lora.get("dropout", 0.05)),
        target_modules=list(lora["targetModules"]), bias="none",
        task_type="CAUSAL_LM")
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()
    device = next(model.parameters()).device
    pad_id = tokenizer.pad_token_id

    trainable = [param for param in model.parameters() if param.requires_grad]
    if precision == "fp16":
        # Keep the LoRA master weights in fp32; the forward/backward matmuls run
        # in fp16 through autocast and the scaler, which is what V100 supports.
        for param in trainable:
            param.data = param.data.float()
    AMP_STATE.update({"fp16": precision == "fp16",
                      "enabled": precision in ("fp16", "bf16") and args.device == "cuda"})
    scaler = torch.amp.GradScaler("cuda", enabled=AMP_STATE["fp16"])
    optimizer = torch.optim.AdamW(trainable, lr=float(config["training"]["lr"]),
                                  weight_decay=float(config["training"].get("weightDecay", 0.0)))
    batch_size = int(config["training"].get("batch", 1))
    grad_accum = int(config["training"].get("gradAccum", 1))
    epochs = args.epochs or int(config["training"]["epochs"])

    os.makedirs(args.out, exist_ok=True)
    start_epoch = 1
    best = {"epoch": 0, "devLoss": float("inf")}
    history: List[Dict[str, Any]] = []
    resume_path = args.resume
    if resume_path == "auto":
        candidate = os.path.join(args.out, "resume.pt")
        resume_path = candidate if os.path.exists(candidate) else ""
    if resume_path:
        state = torch.load(resume_path, map_location="cpu", weights_only=False)
        model.load_state_dict(state["adapter"], strict=False)
        optimizer.load_state_dict(state["optimizer"])
        start_epoch = int(state["epoch"]) + 1
        best = state.get("best", best)
        history = state.get("history", history)
        random.setstate(state["pythonRandom"])
        torch.set_rng_state(state["torchRandom"])
        print(f"resumed at epoch {start_epoch}", flush=True)

    report: Dict[str, Any] = {
        "runId": config.get("runId", "qwen-beat-v1"),
        "precision": precision, "ampEnabled": AMP_STATE["enabled"], "device": args.device,
        "backend": "hf-causal-lora",
        "base": {"path": base_path, "sha256": base_hash},
        "tokenizer": {"path": tokenizer_path,
                      "sha256": sha256_file(os.path.join(tokenizer_path, "tokenizer.json"))
                      if os.path.isdir(tokenizer_path) else tokenizer_path},
        "data": {"mix": config.get("data", {}).get("file"), "mixSha256": mix_hash,
                 "beats": beats_file, "beatsSha256": beats_hash,
                 "scenes": config.get("scenes", {}).get("file"),
                 "scenesSha256": scenes_hash},
        "seed": seed,
        "template": {"system": SYSTEM,
                     "chatTemplate": "tokenizer.apply_chat_template(add_generation_prompt=True)",
                     "responseMask": "assistant-only"},
        "counts": {"train": len(train_items), "dev": len(dev_items), "test": len(test_items)},
        "hyper": config["training"],
        "history": history,
    }

    started = time.time()
    for epoch in range(start_epoch, epochs + 1):
        random.shuffle(train_items)
        order = list(range(len(train_items)))
        epoch_loss, steps = 0.0, 0
        optimizer.zero_grad()
        for index, position in enumerate(order):
            ids, labels, attention = batch([train_items[position]], pad_id)
            ids, labels, attention = ids.to(device), labels.to(device), attention.to(device)
            with torch.autocast(device_type="cuda" if args.device == "cuda" else "cpu",
                                dtype=model_dtype, enabled=AMP_STATE["enabled"]):
                out = model(input_ids=ids, attention_mask=attention, labels=labels)
            scaler.scale(out.loss / grad_accum).backward()
            epoch_loss += float(out.loss.item())
            if (index + 1) % grad_accum == 0 or index + 1 == len(order):
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(trainable, float(config["training"].get("gradClip", 1.0)))
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()
            steps += 1
            if args.max_steps and steps >= args.max_steps:
                break
        dev_loss = evaluate(model, dev_items, pad_id, device, batch_size)
        record = {"epoch": epoch, "trainLoss": round(epoch_loss / max(steps, 1), 4),
                  "devLoss": round(dev_loss, 4), "steps": steps,
                  "seconds": round(time.time() - started, 1)}
        history.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        adapter = {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()
                   if "lora" in name}
        torch.save(adapter, os.path.join(args.out, f"adapter-epoch-{epoch}.pt"))
        if dev_loss < best["devLoss"]:
            best = {"epoch": epoch, "devLoss": round(dev_loss, 4)}
            torch.save(adapter, os.path.join(args.out, "adapter-best.pt"))
        torch.save({"epoch": epoch, "adapter": adapter, "optimizer": optimizer.state_dict(),
                    "best": best, "history": history,
                    "pythonRandom": random.getstate(), "torchRandom": torch.get_rng_state()},
                   os.path.join(args.out, "resume.pt"))
        report["best"] = best
        with io.open(os.path.join(args.out, "report.json"), "w", encoding="utf-8",
                     newline="\n") as handle:
            handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    if os.path.exists(os.path.join(args.out, "adapter-best.pt")):
        state = torch.load(os.path.join(args.out, "adapter-best.pt"), map_location="cpu",
                           weights_only=False)
        model.load_state_dict(state, strict=False)
    test_loss = evaluate(model, test_items, pad_id, device, batch_size)
    report["testLoss"] = round(test_loss, 4)
    samples = []
    for item in (dev_items[:args.sample_n] if dev_items else train_items[:args.sample_n]):
        samples.append({"id": item["id"], "kind": item["kind"],
                        "target": item["target"][:400],
                        "generated": sample(model, tokenizer, item, device,
                                            int(config["training"].get("sampleMaxNew", 90)))})
    report["samples"] = samples
    report["seconds"] = round(time.time() - started, 1)
    with io.open(os.path.join(args.out, "report.json"), "w", encoding="utf-8",
                 newline="\n") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"best": report.get("best"), "testLoss": report["testLoss"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
