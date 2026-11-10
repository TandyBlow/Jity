#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""HPC-only generation entry for the best-of-N experiment.

The runner is deliberately dumb: it reads prepared requests (already frozen by
`prepare.ts` and checked by `verify_pack.py`), applies the model's chat template,
generates ONE sample per (case, seed), and writes the raw text with real timings
and environment identity. It owns no prompt logic, no checking and no selection.

Executed by lane 10 only:
    python -X utf8 generate_hpc.py --requests data/b01/requests.jsonl \
        --config configs/b01.json --preregistration preregistration.json \
        --expected-prereg-sha256 <sha256> --out-dir results/b01 --model ~/qwen15b

Writes `<out-dir>/raw.jsonl`, `<out-dir>/env.json`, `<out-dir>/run.log`.
Refuses to overwrite an existing raw.jsonl (use a new run directory).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.abspath(os.path.join(HERE, ".."))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl_atomic(path: str, rows: List[Dict[str, Any]]) -> None:
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def write_json_atomic(path: str, value: Any) -> None:
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def git_state() -> Dict[str, Any]:
    def run(*args: str) -> str:
        try:
            return subprocess.check_output(["git", *args], cwd=EXP, text=True,
                                           stderr=subprocess.DEVNULL).strip()
        except Exception:  # noqa: BLE001 - identity is best effort, recorded as unknown
            return "unknown"
    return {"head": run("rev-parse", "HEAD"), "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
            "status": run("status", "--porcelain")[:4000]}


def nvidia_smi() -> List[str]:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu,driver_version",
             "--format=csv,noheader"], text=True, stderr=subprocess.DEVNULL)
        return [line.strip() for line in out.splitlines() if line.strip()]
    except Exception:  # noqa: BLE001
        return []


def model_identity(model_path: str) -> Dict[str, Any]:
    identity: Dict[str, Any] = {"path": model_path}
    try:
        from transformers import AutoConfig
        config = AutoConfig.from_pretrained(model_path, local_files_only=True)
        identity["config"] = {
            "model_type": getattr(config, "model_type", None),
            "architectures": getattr(config, "architectures", None),
            "hidden_size": getattr(config, "hidden_size", None),
            "num_hidden_layers": getattr(config, "num_hidden_layers", None),
            "vocab_size": getattr(config, "vocab_size", None),
            "max_position_embeddings": getattr(config, "max_position_embeddings", None),
            "_name_or_path": getattr(config, "_name_or_path", None),
        }
    except Exception as error:  # noqa: BLE001
        identity["configError"] = f"{type(error).__name__}:{error}"
    files: Dict[str, str] = {}
    try:
        for name in sorted(os.listdir(model_path)):
            path = os.path.join(model_path, name)
            if not os.path.isfile(path) or os.path.getsize(path) > (8 << 30):
                continue
            if name.endswith((".safetensors", ".bin", ".json", ".model", ".txt", ".tiktoken")):
                files[name] = sha256_file(path)
    except Exception as error:  # noqa: BLE001
        identity["fileHashError"] = f"{type(error).__name__}:{error}"
    identity["files"] = files
    return identity


def build_prompt(tokenizer, system: str, user: str) -> str:
    if not getattr(tokenizer, "chat_template", None):
        raise SystemExit("tokenizer has no chat_template; refusing to guess a prompt")
    return tokenizer.apply_chat_template(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        tokenize=False, add_generation_prompt=True)


def generate_one(model, tokenizer, prompt: str, seed: int, sampling: Dict[str, Any],
                 device: str) -> Dict[str, Any]:
    import torch
    from transformers import TextIteratorStreamer

    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed % (2 ** 32))
    except Exception:  # noqa: BLE001
        pass
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    started = time.perf_counter()
    inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
    prompt_ms = (time.perf_counter() - started) * 1000
    inputs = {key: value.to(device) for key, value in inputs.items()}
    prompt_tokens = int(inputs["input_ids"].shape[1])

    eos_ids = set()
    for value in (tokenizer.eos_token_id, tokenizer.convert_tokens_to_ids("<|im_end|>")):
        if isinstance(value, int) and value >= 0:
            eos_ids.add(value)

    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True, timeout=600.0)
    generation_kwargs = {
        **inputs,
        "max_new_tokens": int(sampling["maxNewTokens"]),
        "do_sample": True,
        "temperature": float(sampling["temperature"]),
        "top_p": float(sampling["topP"]),
        "top_k": int(sampling["topK"]),
        "repetition_penalty": float(sampling.get("repetitionPenalty", 1.0)),
        "no_repeat_ngram_size": int(sampling.get("noRepeatNgramSize", 0)),
        "eos_token_id": sorted(eos_ids) or tokenizer.eos_token_id,
        "pad_token_id": tokenizer.pad_token_id or tokenizer.eos_token_id,
        "streamer": streamer,
    }
    holder: Dict[str, Any] = {}

    def run() -> None:
        try:
            holder["outputs"] = model.generate(**generation_kwargs)
        except Exception as error:  # noqa: BLE001
            holder["error"] = f"{type(error).__name__}:{error}"

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    first_token_ms = None
    chunks: List[str] = []
    try:
        for piece in streamer:
            if first_token_ms is None and piece:
                first_token_ms = (time.perf_counter() - started) * 1000
            if piece:
                chunks.append(piece)
    finally:
        thread.join(timeout=900)
    total_ms = (time.perf_counter() - started) * 1000
    if "error" in holder:
        raise RuntimeError(holder["error"])
    outputs = holder.get("outputs")
    if outputs is None:
        raise RuntimeError("generation returned no outputs")

    new_ids = outputs[0][prompt_tokens:].tolist()
    text = tokenizer.decode(new_ids, skip_special_tokens=True).strip()
    raw_text = tokenizer.decode(new_ids, skip_special_tokens=False)
    finish_reason = "stop" if new_ids and new_ids[-1] in eos_ids else "length"
    return {
        "text": text,
        "rawText": raw_text,
        "textSha256": sha256_bytes(text.encode("utf-8")),
        "finishReason": finish_reason,
        "timings": {
            "promptMs": prompt_ms,
            "firstTokenMs": first_token_ms,
            "totalMs": total_ms,
            "promptTokens": prompt_tokens,
            "newTokens": len(new_ids),
            "tokensPerSecond": (len(new_ids) / (total_ms / 1000)) if total_ms > 0 else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--preregistration", required=True)
    parser.add_argument("--expected-prereg-sha256", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float16"])
    parser.add_argument("--limit", type=int, default=0, help="smoke only; partial=true")
    args = parser.parse_args()

    prereg_bytes = open(args.preregistration, "rb").read()
    prereg_sha = sha256_bytes(prereg_bytes)
    if prereg_sha != args.expected_prereg_sha256:
        raise SystemExit(f"preregistration sha256 {prereg_sha} != expected; refusing to generate")
    prereg = json.loads(prereg_bytes.decode("utf-8"))
    config = json.load(open(args.config, encoding="utf-8"))
    if config["batchId"] not in [batch["batchId"] for batch in prereg["batches"]]:
        raise SystemExit("config batch is not in the preregistration")

    requests = load_jsonl(args.requests)
    if not requests:
        raise SystemExit("empty request file")
    for entry in requests:
        if sha256_bytes(entry["userPrompt"].encode("utf-8")) != entry["userPromptSha256"]:
            raise SystemExit(f"prompt sha mismatch in request {entry['callId']}")
        if entry["sampling"] != config["sampling"]:
            raise SystemExit(f"sampling differs from frozen config in {entry['callId']}")
    if args.limit:
        requests = requests[: args.limit]

    os.makedirs(args.out_dir, exist_ok=False)
    raw_path = os.path.join(args.out_dir, "raw.jsonl")
    env_path = os.path.join(args.out_dir, "env.json")
    log_path = os.path.join(args.out_dir, "run.log")

    def log(message: str) -> None:
        line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] {message}"
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    log(f"start host={socket.gethostname()} model={args.model} dtype={args.dtype}")
    gpu_before = nvidia_smi()
    log("nvidia-smi: " + " | ".join(gpu_before) if gpu_before else "nvidia-smi: unknown")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
    log(f"torch={torch.__version__} transformers={__import__('transformers').__version__}")

    load_start = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, local_files_only=True, torch_dtype=getattr(torch, args.dtype),
        low_cpu_mem_usage=True)
    model.to(args.device)
    model.eval()
    load_ms = (time.perf_counter() - load_start) * 1000
    log(f"loaded {load_ms:.0f} ms")

    identity = {
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": __import__("transformers").__version__,
        "device": args.device,
        "dtype": args.dtype,
        "cuda": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "cudaCapability": list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else None,
        "gpuBefore": gpu_before,
        "loadMs": load_ms,
        "model": model_identity(args.model),
        "git": git_state(),
        "preregistrationSha256": prereg_sha,
        "configSha256": sha256_file(args.config),
        "requestsSha256": sha256_file(args.requests),
        "partial": bool(args.limit),
    }
    write_json_atomic(env_path, identity)

    rows: List[Dict[str, Any]] = []
    for index, entry in enumerate(requests, start=1):
        log(f"call {index}/{len(requests)} {entry['callId']}")
        row: Dict[str, Any] = {
            "callId": entry["callId"],
            "caseId": entry["caseId"],
            "seed": entry["seed"],
            "inputSha256": entry["inputSha256"],
            "userPromptSha256": entry["userPromptSha256"],
            "modelPath": args.model,
            "modelCuda": identity["cuda"],
            "template": entry["template"],
            "sampling": entry["sampling"],
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "gpuDuring": nvidia_smi(),
        }
        try:
            prompt = build_prompt(tokenizer, entry["system"], entry["userPrompt"])
            row["promptSha256"] = sha256_bytes(prompt.encode("utf-8"))
            set_seed(entry["seed"])
            result = generate_one(model, tokenizer, prompt, entry["seed"], entry["sampling"], args.device)
            row.update(result)
            row["status"] = "ok" if result["text"] else "empty"
            log(f"  {row['status']} newTokens={result['timings']['newTokens']} "
                f"firstTokenMs={result['timings']['firstTokenMs']} totalMs={result['timings']['totalMs']:.0f}")
        except Exception as error:  # noqa: BLE001
            row["status"] = "error"
            row["error"] = f"{type(error).__name__}:{error}"
            row["text"] = ""
            row["rawText"] = ""
            row["textSha256"] = sha256_bytes(b"")
            row["finishReason"] = "error"
            row["timings"] = {"promptMs": None, "firstTokenMs": None, "totalMs": None,
                              "promptTokens": None, "newTokens": 0, "tokensPerSecond": None}
            log(f"  error {row['error']}")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        rows.append(row)
        write_jsonl_atomic(raw_path, rows)

    identity["gpuAfter"] = nvidia_smi()
    identity["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    identity["calls"] = len(rows)
    write_json_atomic(env_path, identity)
    log(f"done {len(rows)} calls -> {raw_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
