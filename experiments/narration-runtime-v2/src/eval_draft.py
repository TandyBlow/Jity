# -*- coding: utf-8 -*-
"""Grade a draft-rewrite GGUF on held-out rows through llama-server.

Why a server and not llama-cli: the page's wllama engine applies the model's chat
template, so the model must see the same chat shape here. llama-cli with `-f`
runs in raw completion mode and the model then continues the prompt tokens, which
looks like corruption but is a harness artefact. llama-server applies the
template and also loads the model once, so many rows cost one load.

This is offline screening, not product acceptance: 09's real page run and 01's
review decide quality.

    python src/eval_draft.py --gguf <path> --split dev --limit 14 \
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
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
DEFAULT_SERVER = "D:/others/Jity/.local/llama-cpp/llama-server.exe"
DATA = os.path.join(V2, "data", "train-page-v3.jsonl")

FILLER = ("气氛", "仿佛", "似乎", "像是", "好像", "显得", "某种", "不由得", "不禁")
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


def cn_number(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    if value < 20:
        return "十" + (digits[value % 10] if value % 10 else "")
    if value < 100:
        return digits[value // 10] + "十" + (digits[value % 10] if value % 10 else "")
    return str(value)


def time_spoken(prose: str, amount: int, unit: str) -> bool:
    cn = cn_number(amount)
    variants = {cn, str(amount)}
    if amount == 2:
        variants.add("两")
    if not any(text in prose for text in variants if text):
        return False
    return unit in prose or ("小时" in prose and unit == "分钟" and amount == 60)


def covers(prose: str, clause: str) -> bool:
    """A draft clause counts as carried when its names appear and at least half
    of its 2-char pieces do."""
    time = re.match(r"时间过去了?约?(\d+)(秒|分钟|小时|天|个月|年)", clause)
    if time:
        return time_spoken(prose, int(time.group(1)), time.group(2))
    if re.match(r"^.+?里，", clause):
        # Scenery is optional detail: the page allows one or two touches, so a
        # missing scenery clause is not a fact miss.
        return True
    if clause.endswith("没有出声。") or clause.endswith("没有出声"):
        return True
    names = re.findall(r"[\u4e00-\u9fff]{2,3}(?=从|完成了|多了一条|的精神值)", clause)
    for name in names:
        if name and name not in prose:
            return False
    strong = pieces(clause)
    if not strong:
        return True
    hits = sum(1 for piece in strong if piece in prose)
    return hits >= max(1, len(strong) // 2)


def start_server(server: str, gguf: str, port: int, threads: int, ctx: int) -> subprocess.Popen:
    process = subprocess.Popen(
        [server, "-m", gguf, "--host", "127.0.0.1", "--port", str(port),
         "-c", str(ctx), "-t", str(threads), "-ngl", "0", "--no-webui"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                if response.status == 200:
                    return process
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    process.terminate()
    raise SystemExit("llama-server did not become healthy in 120 s")


def chat(port: int, prompt: str, max_new: int, temperature: float) -> str:
    body = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature, "max_tokens": max_new,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=600) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gguf", required=True)
    parser.add_argument("--data", default=DATA)
    parser.add_argument("--split", default="dev")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--port", type=int, default=18099)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--ctx", type=int, default=4096)
    parser.add_argument("--max-new", type=int, default=220)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    rows = [row for row in read_jsonl(args.data) if row["split"] == args.split]
    if args.limit:
        rows = rows[:args.limit]
    process = start_server(args.server, args.gguf, args.port, args.threads, args.ctx)
    graded: List[Dict[str, Any]] = []
    passed = 0
    try:
        for row in rows:
            started = time.time()
            prose = chat(args.port, row["user"], args.max_new, args.temperature).strip()
            seconds = round(time.time() - started, 2)
            clauses = [clause for clause in re.split(r"(?<=。)", row["draft"]) if clause.strip()]
            missing = [clause for clause in clauses if not covers(prose, clause)]
            allowed = set(re.findall(r"[0-9]+", row["draft"] + row["user"]))
            invented = [number for number in re.findall(r"[0-9]+", prose) if number not in allowed]
            filler = [word for word in FILLER if word in prose]
            issues = []
            if not prose:
                issues.append("empty")
            if missing:
                issues.append(f"missing_draft:{len(missing)}")
            if invented:
                issues.append("invented_number:" + ",".join(invented[:2]))
            if filler:
                issues.append("filler:" + ",".join(filler[:2]))
            if len(prose) > 320:
                issues.append("too_long")
            dialogue = bool(re.search(r"[「“『]", prose)) and not re.search(r"[「“『]", row["draft"])
            if dialogue:
                # Reported, not failed: a licensed fact can legitimately be
                # spoken, but the page forbids new dialogue, so reviewers must see it.
                issues.append("dialogue_added")
            ok = not issues
            passed += 1 if ok else 0
            graded.append({"id": row["id"], "draft": row["draft"], "prose": prose,
                           "target": row["target"], "missingClauses": missing,
                           "issues": issues, "ok": ok, "seconds": seconds})
            print(f"{row['id']} {len(prose)}ch {seconds}s {'ok' if ok else ','.join(issues)}",
                  flush=True)
    finally:
        process.terminate()

    summary = {
        "gguf": args.gguf,
        "ggufSha256": hashlib_of(args.gguf),
        "data": args.data,
        "split": args.split,
        "rows": len(rows),
        "passed": passed,
        "passRate": round(passed / len(rows), 3) if rows else 0,
        "temperature": args.temperature,
        "maxNew": args.max_new,
        "servedBy": "llama-server /v1/chat/completions (chat template applied, CPU -ngl 0)",
        "notProductAcceptance": "offline screening only; the real page and 01's review decide quality",
        "rowsDetail": graded,
    }
    print(json.dumps({key: summary[key] for key in ("rows", "passed", "passRate")}))
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
    return 0


def hashlib_of(path: str) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
