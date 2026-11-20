# -*- coding: utf-8 -*-
"""Batch offline screening: one GGUF, one frozen case file, raw text out.

Shared service for 11 (candidate screening) and 12 (multi-seed repetition).
It never decides quality: it records the raw text, the wall time, and the
program-side fact checks that already exist offline, so 01 can review the text
and the requester can compute their own rates.

Case file (JSONL, hash frozen in the preregistration):
  {"id": "...", "prompt": "...", "draft": "optional settled-fact draft",
   "licensed": ["names/places the prose may mention"]}

Usage:
  python hpc/batch_screen.py --gguf <model.gguf> --cases <cases.jsonl> \
      --out runs/screen-<id> --seeds 1,2,3 --temperature 0.7 --max-new 220

Output:
  runs/screen-<id>/raw.jsonl   one row per (case, seed) with the raw text
  runs/screen-<id>/summary.json hashes, counts, timings, throughput
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
DEFAULT_LLAMA = "D:/others/Jity/.local/llama-cpp/llama-cli.exe"
FILLER = ("气氛", "仿佛", "似乎", "像是", "好像", "显得", "某种", "不由得", "不禁")


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def run_one(gguf: str, prompt: str, llama: str, threads: int, max_new: int,
            temperature: float, seed: int, tmp_dir: str) -> tuple[str, float]:
    prompt_path = os.path.join(tmp_dir, "prompt.txt")
    with io.open(prompt_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(prompt)
    started = time.time()
    result = subprocess.run(
        [llama, "-m", gguf, "-f", prompt_path, "--single-turn", "--temp", str(temperature),
         "-s", str(seed), "-n", str(max_new), "--threads", str(threads),
         "--no-display-prompt", "--log-disable"],
        capture_output=True)
    seconds = time.time() - started
    raw = result.stdout.decode("utf-8", "replace").split("[ Prompt:")[0]
    lines, seen = [], False
    for line in raw.splitlines():
        if line.startswith(">"):
            seen = True
            continue
        if seen and line.strip() and not line.startswith("  /"):
            lines.append(line.strip())
    return " ".join(lines), round(seconds, 2)


def checks(text: str, case: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[str] = []
    draft = case.get("draft") or ""
    if not text.strip():
        issues.append("empty")
    if len(text) > 400:
        issues.append("too_long")
    for word in FILLER:
        if word in text:
            issues.append(f"filler:{word}")
    allowed = set(re.findall(r"[0-9]+", draft))
    for number in re.findall(r"[0-9]+", text):
        if number not in allowed:
            issues.append(f"invented_number:{number}")
    if re.search(r"[「“『]", text) and not re.search(r"[「“『]", draft):
        issues.append("added_dialogue")
    for licensed in case.get("licensed") or []:
        if licensed and licensed not in text:
            issues.append(f"missing_licensed:{licensed}")
    return {"issues": issues, "chars": len(text)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gguf", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seeds", default="1")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-new", type=int, default=220)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--llama", default=DEFAULT_LLAMA)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    seeds = [int(part) for part in args.seeds.split(",") if part.strip()]
    cases = read_jsonl(args.cases)
    if args.limit:
        cases = cases[:args.limit]
    os.makedirs(args.out, exist_ok=True)
    tmp_dir = os.path.join(args.out, ".tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    started = time.time()
    total_chars = 0
    for case in cases:
        for seed in seeds:
            text, seconds = run_one(args.gguf, case["prompt"], args.llama, args.threads,
                                    args.max_new, args.temperature, seed, tmp_dir)
            total_chars += len(text)
            row = {"id": case["id"], "seed": seed, "text": text, "seconds": seconds,
                   "checks": checks(text, case)}
            rows.append(row)
            print(f"{case['id']}#{seed} {len(text)}ch {seconds}s "
                  f"{'ok' if not row['checks']['issues'] else ','.join(row['checks']['issues'])}",
                  flush=True)
    os.remove(os.path.join(tmp_dir, "prompt.txt"))
    os.rmdir(tmp_dir)
    wall = round(time.time() - started, 2)

    raw_path = os.path.join(args.out, "raw.jsonl")
    with io.open(raw_path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    clean = sum(1 for row in rows if not row["checks"]["issues"])
    summary = {
        "gguf": args.gguf,
        "ggufSha256": sha256(args.gguf),
        "casesFile": args.cases,
        "casesSha256": sha256(args.cases),
        "cases": len(cases),
        "seeds": seeds,
        "generations": len(rows),
        "temperature": args.temperature,
        "maxNew": args.max_new,
        "threads": args.threads,
        "wallSeconds": wall,
        "meanSecondsPerGeneration": round(wall / len(rows), 2) if rows else None,
        "charsPerSecond": round(total_chars / wall, 1) if wall else None,
        "programChecksClean": clean,
        "programChecksNote": "cheap offline checks only; not a quality judgement",
        "output": raw_path,
        "measuredBy": "llama-cli wall clock on this host; no GPU utilisation claim",
    }
    with io.open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({key: summary[key] for key in
                      ("generations", "wallSeconds", "programChecksClean", "ggufSha256")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
