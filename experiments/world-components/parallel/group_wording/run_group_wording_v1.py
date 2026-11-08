#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Group-wording v1: joint group call (J) vs per-fact call + organizer (S).

Frozen by freeze-v1.json. Inference only, no training.
The J arm must reproduce the recorded 784M assembled text byte-for-byte,
otherwise the run is marked non-comparable and exits non-zero.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import organizer_v1

MAX_IN = 512
MAX_NEW = 128


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def gen_batch_exact(model, tok, prompts, device, batch=6):
    outs = []
    for i in range(0, len(prompts), batch):
        chunk = prompts[i:i + batch]
        x = tok(chunk, padding=True, truncation=True, max_length=MAX_IN, return_tensors="pt").to(device)
        t0 = time.time()
        with torch.no_grad():
            o = model.generate(**x, max_new_tokens=MAX_NEW, num_beams=1, do_sample=False,
                               return_dict_in_generate=True)
        elapsed = round(time.time() - t0, 4)
        for seq in o.sequences:
            n = int(seq.shape[0] - 1)
            outs.append({"text": tok.decode(seq, skip_special_tokens=True).strip(),
                         "new_tokens": n,
                         "stop": "cap" if n >= MAX_NEW else "eos",
                         "elapsed_s": elapsed})
    return outs


def assemble(calls, outputs, edges):
    parts = []
    for call in calls:
        t = outputs[call["callId"]]["text"].strip()
        t = re.sub(r"^随后，", "", t).rstrip("。").strip()
        if any(e["to"] in call["factIds"] for e in edges):
            t = "随后，" + t
        parts.append(t)
    return "。".join(parts) + "。"


def group_text(row, outputs, group_facts):
    edges = row["plan"].get("edges", [])
    cs = [c for c in row["B_calls"] if set(c["factIds"]) <= set(group_facts)]
    assert cs, (row["sourceId"], group_facts)
    return assemble(cs, outputs, edges)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--freeze", required=True)
    ap.add_argument("--freeze-sha", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    freeze_path = Path(args.freeze)
    freeze_sha = sha(freeze_path)
    assert freeze_sha == args.freeze_sha, (freeze_sha, args.freeze_sha)
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))

    base = Path(args.base)
    model_sha = sha(base / "model.safetensors")
    assert model_sha == freeze["checkpoint"]["model_sha256"], (model_sha, freeze["checkpoint"]["model_sha256"])
    assert sha(base / "spiece.model") == freeze["checkpoint"]["spiece_sha256"]
    org_sha = sha(Path(organizer_v1.__file__))
    assert org_sha == freeze["organizer"]["sha256"], (org_sha, freeze["organizer"]["sha256"])

    device = "cuda" if torch.cuda.is_available() else "cpu"
    assert device == "cuda", "GPU job required"
    tok = T5Tokenizer.from_pretrained(str(base), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(base), torch_dtype=torch.float32).to(device)
    model.eval()

    results = {
        "protocol": freeze["protocol"],
        "freeze_sha256": freeze_sha,
        "material_sha256": freeze["material"]["sha256"],
        "checkpoint_sha256": model_sha,
        "organizer_sha256": org_sha,
        "script_sha256": sha(Path(__file__)),
        "device": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "transformers": __import__("transformers").__version__,
        "decoding": freeze["decoding"],
        "rows": {},
        "samples": {},
        "determinism_ok": True,
    }

    for row in freeze["rows"]:
        sid = row["sourceId"]
        print(f"[{sid}] J: {len(row['B_calls'])} calls", flush=True)
        b_prompts = [freeze["prompts"]["B:" + c["callId"]] for c in row["B_calls"]]
        b_outs = gen_batch_exact(model, tok, b_prompts, device)
        b_map = {c["callId"]: o for c, o in zip(row["B_calls"], b_outs)}
        j_text = assemble([{"callId": c["callId"], "factIds": c["factIds"]} for c in row["B_calls"]],
                          b_map, row["plan"].get("edges", []))
        j_ok = j_text == row["recorded_784_assembled"]
        if not j_ok:
            results["determinism_ok"] = False
            print(f"[{sid}] J MISMATCH\n  got: {j_text}\n  rec: {row['recorded_784_assembled']}", flush=True)

        print(f"[{sid}] S: {len(row['A_calls'])} calls", flush=True)
        a_prompts = [freeze["prompts"]["A:" + c["callId"]] for c in row["A_calls"]]
        a_outs = gen_batch_exact(model, tok, a_prompts, device)
        a_map = {c["callId"]: o for c, o in zip(row["A_calls"], a_outs)}
        fact_sents = {}
        for c in row["A_calls"]:
            assert len(c["factIds"]) == 1, c
            fact_sents[c["factIds"][0]] = a_map[c["callId"]]["text"]
        s_text = organizer_v1.organize(row, fact_sents)

        results["rows"][sid] = {
            "split": row["split"],
            "J": {"calls": b_map, "assembled": j_text, "matches_recorded_784": j_ok,
                  "recorded_784_assembled": row["recorded_784_assembled"]},
            "S": {"calls": a_map, "fact_sentences": fact_sents, "assembled": s_text},
        }

    for s in freeze["samples"]:
        row = next(r for r in freeze["rows"] if r["sourceId"] == s["sourceId"])
        rr = results["rows"][s["sourceId"]]
        results["samples"][s["sampleId"]] = {
            "sourceId": s["sourceId"],
            "groupFacts": s["groupFacts"],
            "role": s["role"],
            "J_text": group_text(row, rr["J"]["calls"], s["groupFacts"]),
            "S_text": organizer_v1.group_span(row, s["groupFacts"], rr["S"]["fact_sentences"]),
        }
        print(f"[{s['sampleId']}] J: {results['samples'][s['sampleId']]['J_text']}", flush=True)
        print(f"[{s['sampleId']}] S: {results['samples'][s['sampleId']]['S_text']}", flush=True)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n",
                                      encoding="utf-8", newline="\n")
    print("wrote", out / "results.json", flush=True)
    if not results["determinism_ok"]:
        print("STOP: arm J did not reproduce the recorded 784M text", flush=True)
        sys.exit(3)


if __name__ == "__main__":
    main()
