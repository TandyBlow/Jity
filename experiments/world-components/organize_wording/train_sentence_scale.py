#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sentence-scale three-arm run.

Frozen protocol: design/world-engine-reports/components/sentence-scale-v1.md
A-large: 80 sources, one fact/call
B-large: same 80 sources, one plan group/call
B-small: clean-group original 20 training sources, one plan group/call
Each arm: 480 calls, grad-accum 4, 120 updates, final point only, no selection.
"""
import gc, json, random, re, sys, hashlib, pathlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_ab as T
import numpy as np
import torch
from torch.optim import AdamW
from transformers import T5ForConditionalGeneration, T5Tokenizer, get_linear_schedule_with_warmup

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "artifacts/world-components/organize-wording/sentence-scale-v1.jsonl"
FREEZE = ROOT / "artifacts/world-components/organize-wording/sentence-scale-freeze-v1.json"
OUT = ROOT / "artifacts/world-components/organize-wording/sentence-scale-run-v1"
OUT.mkdir(parents=True, exist_ok=True)

SEED = 13
STEPS = 480
ACCUM = 4
UPDATES = 120
MAX_IN = 512
MAX_NEW = 128


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def facts_of(r):
    return {f["factId"]: f for f in r["facts"]}


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
    lines += [T.fact_line(fm[fid]) for fid in call["factIds"]]
    lines += ["要求：只写本组；组内可联合多条事实；组间边界由程序负责；不新增人物、物品、地点、动作、关系；不写代词、数字、字段名；需要称呼时用姓名。",
              "正文："]
    return "\n".join(lines) + "\n"


def gen_batch_exact(model, tok, prompts, device, batch=6):
    outs = []
    for i in range(0, len(prompts), batch):
        chunk = prompts[i:i + batch]
        x = tok(chunk, padding=True, truncation=True, max_length=MAX_IN, return_tensors="pt").to(device)
        with torch.no_grad():
            o = model.generate(**x, max_new_tokens=MAX_NEW, num_beams=1, do_sample=False,
                               return_dict_in_generate=True)
        for seq in o.sequences:
            n = int(seq.shape[0] - 1)
            outs.append({"text": tok.decode(seq, skip_special_tokens=True).strip(),
                         "new_tokens": n,
                         "stop": "cap" if n >= MAX_NEW else "eos"})
    return outs


def assemble(calls, outputs, edges):
    parts = []
    for call in calls:
        t = outputs[call["callId"]]["text"].strip()
        t = re.sub(r"^随后，", "", t)
        t = t.rstrip("。").strip()
        if any(e["to"] in call["factIds"] for e in edges):
            t = "随后，" + t
        parts.append(t)
    return "。".join(parts) + "。"


def group_text(r, calls, outputs, group_facts, edges):
    cs = [c for c in calls if set(c["factIds"]) <= set(group_facts)]
    assert cs, (r["sourceId"], group_facts)
    return assemble(cs, outputs, edges)


def fact_pass(f, text):
    ok, _, _ = T.fact_span(f, T.sent_split(text))
    return bool(ok)


def target_tokens(tok, calls):
    return sum(len(tok(c["target"], add_special_tokens=False)["input_ids"]) for c in calls)


def sequence_for(calls):
    seq = []
    ep = 0
    while len(seq) < STEPS:
        order = list(calls)
        random.Random(SEED + ep).shuffle(order)
        seq.extend(order)
        ep += 1
    return seq[:STEPS]


def train_arm(rows, arm, arm_name, tok, device):
    if arm == "A":
        source_rows = [r for r in rows if r["split"] == "train"]
    else:
        source_rows = [r for r in rows if r["split"] == "train" and (arm_name != "B-small" or r.get("bSmallTrain"))]
    calls = []
    for r in source_rows:
        calls += r[arm]["calls"]
    seq = sequence_for(calls)
    unique = {c["callId"] for c in calls}
    sampled = {c["callId"] for c in seq}
    stats = {
        "arm": arm_name,
        "train_sources": len(source_rows),
        "train_calls": len(calls),
        "steps": STEPS,
        "updates": UPDATES,
        "passes": round(STEPS / max(1, len(calls)), 2),
        "sampled_unique_calls": len(sampled),
        "all_calls": len(unique),
        "unseen_calls": sorted(unique - sampled),
        "sampled_fact_exposures": sum(len(c["factIds"]) for c in seq),
        "sampled_target_tokens": target_tokens(tok, seq),
        "facts_per_update": round(sum(len(c["factIds"]) for c in seq) / UPDATES, 2),
        "target_tokens_per_update": round(target_tokens(tok, seq) / UPDATES, 2),
    }

    torch.manual_seed(SEED); random.seed(SEED); np.random.seed(SEED)
    model = T5ForConditionalGeneration.from_pretrained(str(T.MODEL), torch_dtype=torch.float32).to(device)
    opt = AdamW(model.parameters(), lr=T.LR, betas=(0.9, 0.999), eps=1e-8, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, T.WARMUP, UPDATES)
    model.train(); opt.zero_grad()
    sampled_log = []
    for i, c in enumerate(seq):
        r = next(x for x in source_rows if x["sourceId"] == c["callId"].split(":")[0])
        call_list = r[arm]["calls"]
        idx = next(j for j, x in enumerate(call_list) if x["callId"] == c["callId"]) + 1
        inp, mask, lab = T.tokenize(tok, prompt_call(r, c, idx, len(call_list)), c["target"])
        inp, mask, lab = inp.unsqueeze(0).to(device), mask.unsqueeze(0).to(device), lab.unsqueeze(0).to(device)
        loss = model(input_ids=inp, attention_mask=mask, labels=lab).loss / ACCUM
        loss.backward()
        if (i + 1) % ACCUM == 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad()
        if (i + 1) % 40 == 0:
            print(f"{arm_name} step {i+1} update {(i+1)//ACCUM}", flush=True)
        sampled_log.append({"step": i + 1, "update": (i + 1) // ACCUM, "sourceId": c["callId"].split(":")[0],
                            "callId": c["callId"], "factIds": c["factIds"],
                            "targetTokens": len(tok(c["target"], add_special_tokens=False)["input_ids"])})
    return model, stats, sampled_log


def eval_arm(model, tok, rows, arm, device):
    out = {}
    for r in rows:
        calls = r[arm]["calls"]
        prompts = [prompt_call(r, c, i + 1, len(calls)) for i, c in enumerate(calls)]
        gs = gen_batch_exact(model, tok, prompts, device)
        by = {c["callId"]: g for c, g in zip(calls, gs)}
        text = assemble(calls, by, r["plan"].get("edges", []))
        groups = []
        fm = facts_of(r)
        for g in r["plan"]["groups"]:
            if len(g["facts"]) < 2:
                continue
            a = group_text(r, calls, by, g["facts"], r["plan"].get("edges", []))
            groups.append({"facts": g["facts"], "text": a,
                           "factPass": all(fact_pass(fm[f], a) for f in g["facts"])})
        out[r["sourceId"]] = {"assembled": text, "calls": by, "groups": groups}
    return out


def main():
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert sha(DATA) == freeze["material_sha256"], (sha(DATA), freeze["material_sha256"])
    rows = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines()]
    fixed = [r for r in rows if r["split"] == "fixed"]
    reg = [r for r in rows if r["split"] == "regression"]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = T5Tokenizer.from_pretrained(str(T.MODEL), legacy=False)
    results = {"material": str(DATA), "material_sha256": sha(DATA),
               "freeze": str(FREEZE), "freeze_sha256": sha(FREEZE),
               "config": freeze["config"], "counts": freeze["counts"], "arms": {}}
    for arm, arm_name in (("A", "A-large"), ("B", "B-large"), ("B", "B-small")):
        print("== training", arm_name, flush=True)
        model, stats, sampled_log = train_arm(rows, arm, arm_name, tok, device)
        model.eval()
        with (OUT / f"sampled_calls-{arm_name}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for x in sampled_log:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        print("== fixed", arm_name, flush=True)
        fx = eval_arm(model, tok, fixed, arm, device)
        print("== regression", arm_name, flush=True)
        rg = eval_arm(model, tok, reg, arm, device)
        results["arms"][arm_name] = {"stats": stats, "fixed": fx, "regression": rg}
        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n",
                                      encoding="utf-8", newline="\n")
    print("wrote", OUT / "results.json")
    for name in ("A-large", "B-large", "B-small"):
        s = results["arms"][name]["stats"]
        print(name, json.dumps({k: s[k] for k in ("train_sources", "train_calls", "passes", "sampled_unique_calls", "all_calls", "unseen_calls", "sampled_fact_exposures", "sampled_target_tokens")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
