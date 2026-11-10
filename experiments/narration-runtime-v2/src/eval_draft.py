# -*- coding: utf-8 -*-
"""Grade a draft-rewrite GGUF on held-out rows, using the real prompt.

This is an offline screening tool, not product acceptance: it runs the same
prompt the page would send, records the raw prose, and counts
  * draft facts that the prose does not carry,
  * numbers/names the draft does not contain,
  * filler and multi-paragraph answers.
09's real page run and 01's sentence review remain the quality evidence.

    python src/eval_draft.py --gguf <path> --split dev --limit 20 \
        --out hpc/runs/<job>/eval-dev.json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
DEFAULT_LLAMA = "D:/others/Jity/.local/llama-cpp/llama-cli.exe"
DATA = os.path.join(V2, "data", "train-draft-v1.jsonl")

FILLER = ("空气里", "气氛", "仿佛", "似乎", "像是", "好像", "显得", "某种", "不由得", "不禁")
STOP = {"这个", "那个", "一件", "事情", "自己", "已经", "没有", "什么", "一直",
        "一个", "的是", "了的", "里的", "把", "了", "的", "在", "和", "与"}


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def pieces(text: str) -> List[str]:
    out = []
    for index in range(len(text) - 1):
        piece = text[index:index + 2]
        if piece not in STOP and not re.search(r"[，。、：；「」（）]", piece):
            out.append(piece)
    return out


def covers(prose: str, clause: str) -> bool:
    """A draft clause counts as carried when at least half of its 2-char pieces
    appear, and every proper name in it appears."""
    names = re.findall(r"[\u4e00-\u9fff]{2,3}(?=从|完成了|多了一条|的精神值)", clause)
    for name in names:
        if name and name not in prose:
            return False
    strong = pieces(clause)
    if not strong:
        return True
    hits = sum(1 for piece in strong if piece in prose)
    return hits >= max(1, len(strong) // 2)


def run_llama(gguf: str, prompt: str, llama: str, threads: int, max_new: int,
              temperature: float) -> str:
    with io.open(".eval-prompt.txt", "w", encoding="utf-8", newline="") as handle:
        handle.write(prompt)
    result = subprocess.run(
        [llama, "-m", gguf, "-f", ".eval-prompt.txt", "--single-turn",
         "--temp", str(temperature), "-n", str(max_new), "--threads", str(threads),
         "--no-display-prompt", "--log-disable"],
        capture_output=True)
    os.remove(".eval-prompt.txt")
    text = result.stdout.decode("utf-8", "replace").split("[ Prompt:")[0]
    lines, seen = [], False
    for line in text.splitlines():
        if line.startswith(">"):
            seen = True
            continue
        if seen and line.strip() and not line.startswith("  /"):
            lines.append(line.strip())
    return " ".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gguf", required=True)
    parser.add_argument("--data", default=DATA)
    parser.add_argument("--split", default="dev")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--llama", default=DEFAULT_LLAMA)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--max-new", type=int, default=160)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    rows = [row for row in read_jsonl(args.data) if row["split"] == args.split]
    if args.limit:
        rows = rows[:args.limit]
    graded: List[Dict[str, Any]] = []
    passed = 0
    for row in rows:
        prose = run_llama(args.gguf, row["user"], args.llama, args.threads,
                          args.max_new, args.temperature)
        clauses = [clause for clause in re.split(r"(?<=。)", row["draft"]) if clause.strip()]
        missing = [clause for clause in clauses if not covers(prose, clause)]
        allowed = set(re.findall(r"[0-9]+", row["draft"] + row["user"]))
        invented = [number for number in re.findall(r"[0-9]+", prose) if number not in allowed]
        filler = [word for word in FILLER if word in prose]
        issues = []
        if not prose.strip():
            issues.append("empty")
        if missing:
            issues.append(f"missing_draft:{len(missing)}")
        if invented:
            issues.append("invented_number:" + ",".join(invented[:2]))
        if filler:
            issues.append("filler:" + ",".join(filler[:2]))
        if len(prose) > 220:
            issues.append("too_long")
        if "\n\n" in prose:
            issues.append("multiple_paragraphs")
        ok = not issues
        passed += 1 if ok else 0
        graded.append({"id": row["id"], "draft": row["draft"], "prose": prose,
                       "missingClauses": missing, "issues": issues, "ok": ok})
    summary = {
        "gguf": args.gguf,
        "split": args.split,
        "rows": len(rows),
        "passed": passed,
        "passRate": round(passed / len(rows), 3) if rows else 0,
        "temperature": args.temperature,
        "maxNew": args.max_new,
        "notProductAcceptance": "offline screening only; real page text and 01's review decide quality",
        "rowsDetail": graded,
    }
    print(json.dumps({k: summary[k] for k in ("rows", "passed", "passRate", "gguf")},
                     ensure_ascii=False, indent=1))
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
