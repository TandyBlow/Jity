#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Identify the local 77M checkpoint in .local/models by replaying recorded calls.

No training, greedy decode only. Uses the exact prompt format of
train_sentence_scale_784.py (full-width separators).
"""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
_stub = Path(tempfile.mkdtemp()) / "sklearn"
_stub.mkdir()
(_stub / "__init__.py").write_text("")
(_stub / "metrics.py").write_text("def roc_curve(*a, **k):\n    raise RuntimeError('sklearn stub')\n")
sys.path.insert(0, str(_stub.parent))

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

ROOT = Path(__file__).resolve().parents[4]
MATERIAL = ROOT / "artifacts/world-components/organize-wording/sentence-scale-v1.jsonl"
WEIGHTS = Path("D:/others/Jity/.local/models")

MAX_IN = 512
MAX_NEW = 128


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def facts_of(r):
    return {f["factId"]: f for f in r["facts"]}


def fact_line(f):
    k = f["kind"]
    if k == "moved":
        return f"{f['factId']}｜移动｜{f['name']}｜{f['from']}→{f['to']}｜方向={f.get('direction','平')}"
    if k == "outcome":
        return f"{f['factId']}｜结果｜{f['name']}｜{f['text']}"
    if k == "appearance_changed":
        return f"{f['factId']}｜外观｜{f['name']}｜{f['text']}"
    if k == "sanity_changed":
        return f"{f['factId']}｜理智｜{f['name']}｜{f['from']}→{f['to']}"
    if k == "no_change":
        return f"{f['factId']}｜无变化"
    if k == "time":
        return f"{f['factId']}｜时间"
    if k == "position_relative":
        return f"{f['factId']}｜位置｜{f['name']}｜{f['text']}"
    return f"{f['factId']}｜{k}｜{f.get('name','')}｜{f.get('text','')}"


def prompt_call(r, call, idx, total):
    c = r["context"]
    fm = facts_of(r)
    lines = ["叙事任务。",
             f"地点={c.get('place','')}",
             f"地点可见={c.get('visible','')}",
             f"场景={c.get('scene','')}",
             f"视角={c.get('viewpoint','')}",
             f"本组={idx}/{total}",
             "事实（只列本组，按顺序）："]
    lines += [fact_line(fm[fid]) for fid in call["factIds"]]
    lines += ["要求：只写本组；组内可联合多条事实；组间边界由程序负责；不新增人物、物品、地点、动作、关系；不写代词、数字、字段名；需要称呼时用姓名。",
              "正文："]
    return "\n".join(lines) + "\n"


def main():
    rows = [json.loads(l) for l in MATERIAL.read_text(encoding="utf-8").splitlines()]
    r = next(x for x in rows if x["sourceId"] == "n4n-109")
    recorded = json.loads((ROOT / "artifacts/world-components/organize-wording/sentence-scale-run-v1/results.json").read_text(encoding="utf-8"))
    rec784 = json.loads((ROOT / "artifacts/world-components/organize-wording/sentence-base-784m-run-v1/results.json").read_text(encoding="utf-8"))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = T5Tokenizer.from_pretrained(str(WEIGHTS), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(WEIGHTS), dtype=torch.float32).to(device)
    model.eval()

    probes = [("A", "n4n-109:f1"), ("B", "n4n-109:g2")]
    info = {"weights": {"model.sha256": sha(WEIGHTS / "model.safetensors"),
                        "spiece.sha256": sha(WEIGHTS / "spiece.model")},
            "device": device, "calls": []}
    for arm, call_id in probes:
        calls = r[arm]["calls"]
        call = next(c for c in calls if c["callId"] == call_id)
        prompt = prompt_call(r, call, calls.index(call) + 1, len(calls))
        x = tok([prompt], padding=True, truncation=True, max_length=MAX_IN, return_tensors="pt").to(device)
        with torch.no_grad():
            o = model.generate(**x, max_new_tokens=MAX_NEW, num_beams=1, do_sample=False)
        text = tok.decode(o[0], skip_special_tokens=True).strip()
        info["calls"].append({"arm": arm, "callId": call_id, "prompt": prompt, "generated": text,
                              "recorded_A_large": recorded["arms"]["A-large"]["fixed"]["n4n-109"]["calls"].get(call_id, {}).get("text"),
                              "recorded_B_large": recorded["arms"]["B-large"]["fixed"]["n4n-109"]["calls"].get(call_id, {}).get("text"),
                              "recorded_784": rec784["fixed"]["n4n-109"]["calls"].get(call_id, {}).get("text")})
        print("==", arm, call_id)
        print("generated:", text)
        print("recorded A:", info["calls"][-1]["recorded_A_large"])
        print("recorded B:", info["calls"][-1]["recorded_B_large"])
        print("recorded 784:", info["calls"][-1]["recorded_784"])
    out = ROOT / "experiments/world-components/parallel/group_wording/probe-identity-v1.json"
    out.write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
