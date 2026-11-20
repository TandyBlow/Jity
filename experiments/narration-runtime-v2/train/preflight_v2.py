# -*- coding: utf-8 -*-
"""CPU-only preflight for the v2 training arms.

Run this on the login node before `sbatch`.  It never touches CUDA and never
loads model weights; for the YuYan arm it reads the character vocabulary and
computes exact prompt/target lengths, and for an instruct arm it loads only the
tokenizer and applies the configured chat template.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from typing import Any, Dict, List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(V2, "..", ".."))

sys.path.insert(0, os.path.join(V2, "src"))

import legacy_compat as legacy
import v2_render as v2
from tokenizer_profile import load_tokenizer_profile, validate_tokenizer_text


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


def load_yuyan_vocab(path: str) -> Tuple[List[str], Dict[str, int]]:
    special = ["<s>", "<pad>", "</s>", "<unk>"]
    entries = []
    with io.open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if line:
                entries.append(line.split(" ")[0])
    tokens = special + entries
    return tokens, {token: index for index, token in enumerate(tokens)}


def yuyan_lengths(config: Dict[str, Any], rows: List[Dict[str, Any]],
                  dict_path: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    tokens, index = load_yuyan_vocab(dict_path)
    eos = index["</s>"]
    max_len = int(config["training"]["maxLen"])
    lengths = []
    problems = []
    for row in rows:
        try:
            prompt = [index[char] for char in row["xProse"]]
            target = [index[char] for char in row["yMarked"]] + [eos]
        except KeyError as error:
            problems.append(f"{row['id']}: character {error.args[0]!r} is outside the dict")
            continue
        total = len(prompt) + len(target)
        if total > max_len:
            problems.append(f"{row['id']}: {total} tokens > maxLen {max_len}")
        if row["y"].strip() and row["y"].strip() in row["xProse"]:
            problems.append(f"{row['id']}: target text in xProse")
        labels = [-100] * len(prompt) + target
        if any(label != -100 for label in labels[:len(prompt)]):
            problems.append(f"{row['id']}: prompt received a label")
        if any(label == -100 for label in labels[len(prompt):]):
            problems.append(f"{row['id']}: target lost its label")
        lengths.append({"id": row["id"], "promptTokens": len(prompt),
                        "targetTokens": len(target), "inputTokens": total,
                        "truncated": total > max_len})
    def stats(key: str) -> Dict[str, Any]:
        values = [item[key] for item in lengths]
        return {"min": min(values), "max": max(values),
                "mean": round(sum(values) / len(values), 1)}
    return {"ok": not problems, "problems": problems,
            "vocabSize": len(tokens), "eos": eos,
            "lengths": {"prompt": stats("promptTokens"),
                        "target": stats("targetTokens"),
                        "input": stats("inputTokens")},
            "rowsOverMaxLen": sum(1 for item in lengths if item["truncated"])}


def hf_lengths(config: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if config.get("status") == "pending":
        return {"ok": True, "skipped": "config status=pending; no base/tokenizer selected",
                "problems": []}
    base = resolve_path(config["base"]["file"])
    tokenizer_path = base
    if config.get("tokenizer", {}).get("file"):
        tokenizer_path = resolve_path(config["tokenizer"]["file"])
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True,
                                              trust_remote_code=False)
    if tokenizer.eos_token is None:
        return {"ok": False, "problems": ["tokenizer has no eos token"], "lengths": {}}
    template = config["template"]
    max_len = int(config["training"]["maxSeqLen"])
    lengths = []
    problems = []
    for row in rows:
        user = template["userPrefix"] + row["xProse"] + template["userSuffix"]
        prompt_text = tokenizer.apply_chat_template(
            [{"role": "system", "content": template["system"]},
             {"role": "user", "content": user}],
            tokenize=False, add_generation_prompt=True)
        prompt = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        target = tokenizer(row[template.get("targetField", "y")] + tokenizer.eos_token,
                           add_special_tokens=False)["input_ids"]
        total = len(prompt) + len(target)
        if total > max_len:
            problems.append(f"{row['id']}: {total} tokens > maxSeqLen {max_len}")
        if row["y"].strip() and row["y"].strip() in prompt_text:
            problems.append(f"{row['id']}: target text in prompt")
        lengths.append({"id": row["id"], "promptTokens": len(prompt),
                        "targetTokens": len(target), "inputTokens": total})
    def stats(key: str) -> Dict[str, Any]:
        values = [item[key] for item in lengths]
        return {"min": min(values), "max": max(values),
                "mean": round(sum(values) / len(values), 1)}
    return {"ok": not problems, "problems": problems,
            "lengths": {"prompt": stats("promptTokens"), "target": stats("targetTokens"),
                        "input": stats("inputTokens")},
            "rowsOverMaxLen": sum(1 for item in lengths if item["inputTokens"] > max_len)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--data", default="")
    parser.add_argument("--dict", default="")
    parser.add_argument("--splits", default="")
    parser.add_argument("--hash-base", action="store_true")
    args = parser.parse_args()

    with io.open(args.config, encoding="utf-8") as handle:
        config = json.load(handle)
    problems: List[str] = []
    summary: Dict[str, Any] = {"config": os.path.abspath(args.config), "backend": config.get(
        "backend"), "status": config.get("status", "active")}

    data_path = resolve_path(args.data or config["data"]["file"])
    rows = read_jsonl(data_path)
    data_sha = sha256_file(data_path)
    summary["data"] = {"path": data_path, "sha256": data_sha, "rows": len(rows)}
    if config["data"].get("sha256") and config["data"]["sha256"] != data_sha:
        problems.append(f"data sha256 {data_sha} != config {config['data']['sha256']}")
    manifest_path = config["data"].get("manifest")
    if manifest_path:
        manifest_path = resolve_path(manifest_path)
        summary["data"]["manifest"] = manifest_path
        summary["data"]["manifestSha256"] = sha256_file(manifest_path)

    splits_path = resolve_path(args.splits or config["splits"]["file"])
    with open(splits_path, "rb") as handle:
        split_lf = hashlib.sha256(handle.read().replace(b"\r\n", b"\n")).hexdigest()
    summary["splits"] = {"path": splits_path, "sha256Lf": split_lf}
    if config["splits"].get("sha256Lf") and config["splits"]["sha256Lf"] != split_lf:
        problems.append(f"split sha256 {split_lf} != config {config['splits']['sha256Lf']}")

    # Frozen-source checks are available in the development tree.  The HPC
    # package carries the already-built v2 data, so skip them with an explicit
    # note instead of failing on a missing read-only source directory.
    if os.path.isdir(legacy.SOURCE_DIR):
        legacy_bytes = legacy.compare_legacy_bytes()
        if not legacy_bytes["ok"]:
            problems.extend(legacy_bytes["problems"])
        split_identity = legacy.split_identity()
        if not split_identity["ok"]:
            problems.append(f"split identity failed: {split_identity}")
        summary["sourceChecks"] = {"legacyBytesOk": legacy_bytes["ok"],
                                   "splitIdentityOk": split_identity["ok"]}
    else:
        summary["sourceChecks"] = {"skipped": "frozen source directory is not present",
                                   "sourceDir": legacy.SOURCE_DIR}

    tokenizer_file = args.dict or config.get("tokenizer", {}).get("file", "")
    dict_path = resolve_path(tokenizer_file) if tokenizer_file else ""
    profile = None
    if dict_path and os.path.isfile(dict_path):
        profile = load_tokenizer_profile(dict_path)
        summary["tokenizer"] = {key: value for key, value in profile.items() if key != "vocab"}
        if config.get("tokenizer", {}).get("sha256") and \
                config["tokenizer"]["sha256"] != profile["sha256"]:
            problems.append(f"dict sha256 {profile['sha256']} != config")
        bad = []
        for row in rows:
            try:
                validate_tokenizer_text(row["xProse"], profile)
            except Exception as error:  # noqa: BLE001
                bad.append({"id": row["id"], "error": str(error)})
        if bad:
            problems.append(f"{len(bad)} row(s) are not encodable: {bad[:3]}")
    else:
        summary["tokenizer"] = {"status": "not-provided"}

    base_path = config.get("base", {}).get("file", "")
    if base_path:
        base_path = resolve_path(base_path)
        summary["base"] = {"path": base_path, "exists": os.path.exists(base_path)}
        if not os.path.exists(base_path):
            problems.append(f"base not found: {base_path}")
        elif args.hash_base:
            summary["base"]["sha256"] = sha256_file(base_path)
            if config["base"].get("sha256") and \
                    summary["base"]["sha256"] != config["base"]["sha256"]:
                problems.append("base sha256 differs from config")

    if config.get("backend") == "yuyan":
        if not dict_path or not os.path.exists(dict_path):
            problems.append("YuYan arm needs a tokenizer dict")
        else:
            result = yuyan_lengths(config, rows, dict_path, profile)
            summary["lengths"] = result
            problems.extend(result["problems"])
    elif config.get("backend") == "hf-causal":
        result = hf_lengths(config, rows)
        summary["lengths"] = result
        problems.extend(result["problems"])
    else:
        problems.append(f"unknown backend {config.get('backend')!r}")

    summary["ok"] = not problems
    summary["problems"] = problems
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
