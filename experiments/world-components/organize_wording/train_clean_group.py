#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clean-supervision A/B: one fact per call vs one group per call.

Frozen protocol: design/world-engine-reports/components/clean-group-comparison-v1.md
- 36 sources, 20/6/10; A one fact/call, B one group/call; same base/config
- 480 steps, grad-accum 4, 120 optimizer updates; final point only, no selection
- program assembles boundaries and the required before-marker; exact stop reasons
"""
import json, random, re, sys, hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_ab as T
import numpy as np
import torch
from torch.optim import AdamW
from transformers import T5ForConditionalGeneration, T5Tokenizer, get_linear_schedule_with_warmup

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "artifacts/world-components/organize-wording/clean-group-v1.jsonl"
FREEZE = ROOT / "artifacts/world-components/organize-wording/clean-group-freeze-v1.json"
OUT = ROOT / "artifacts/world-components/organize-wording/clean-group-run-v1"
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
        chunk = prompts[i:i+batch]
        x = tok(chunk, padding=True, truncation=True, max_length=MAX_IN, return_tensors="pt").to(device)
        with torch.no_grad():
            o = model.generate(**x, max_new_tokens=MAX_NEW, num_beams=1, do_sample=False,
                               return_dict_in_generate=True)
        for seq in o.sequences:
            n = int(seq.shape[0] - 1)
            outs.append({"text": tok.decode(seq, skip_special_tokens=True).strip(),
                         "new_tokens": n, "stop": "cap" if n >= MAX_NEW else "eos"})
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


def train_arm(rows, arm, tok, device):
    calls = []
    for r in rows:
        if r["split"] == "train":
            calls += r[arm]["calls"]
    seq = []
    ep = 0
    while len(seq) < STEPS:
        order = list(calls); random.Random(SEED + ep).shuffle(order)
        seq += order; ep += 1
    seq = seq[:STEPS]
    sampled_facts = sum(len(c["factIds"]) for c in seq)
    sampled_tokens = target_tokens(tok, seq)
    stats = {"arm": arm, "train_calls": len(calls), "steps": STEPS, "passes": round(STEPS / max(1, len(calls)), 2),
             "sampled_fact_exposures": sampled_facts, "sampled_target_tokens": sampled_tokens,
             "facts_per_update": round(sampled_facts / UPDATES, 2),
             "target_tokens_per_update": round(sampled_tokens / UPDATES, 2)}

    torch.manual_seed(SEED); random.seed(SEED); np.random.seed(SEED)
    model = T5ForConditionalGeneration.from_pretrained(str(T.MODEL), torch_dtype=torch.float32).to(device)
    opt = AdamW(model.parameters(), lr=T.LR, betas=(0.9, 0.999), eps=1e-8, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, T.WARMUP, UPDATES)
    model.train(); opt.zero_grad()
    for i, c in enumerate(seq):
        r = next(x for x in rows if x["sourceId"] == c["callId"].split(":")[0])
        call_list = r[arm]["calls"]
        idx = next(i for i, x in enumerate(call_list) if x["callId"] == c["callId"]) + 1
        inp, mask, lab = T.tokenize(tok, prompt_call(r, c, idx, len(call_list)), c["target"])
        inp, mask, lab = inp.unsqueeze(0).to(device), mask.unsqueeze(0).to(device), lab.unsqueeze(0).to(device)
        loss = model(input_ids=inp, attention_mask=mask, labels=lab).loss / ACCUM
        loss.backward()
        if (i + 1) % ACCUM == 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad()
        if (i + 1) % 40 == 0:
            print(f"{arm} step {i+1} update {(i+1)//ACCUM}", flush=True)
    return model, stats


def eval_arm(model, tok, rows, arm, device):
    out = {}
    for r in rows:
        calls = r[arm]["calls"]
        prompts = [prompt_call(r, c, i + 1, len(calls)) for i, c in enumerate(calls)]
        gs = gen_batch_exact(model, tok, prompts, device)
        by = {c["callId"]: g for c, g in zip(calls, gs)}
        text = assemble(calls, by, r["plan"].get("edges", []))
        groups = []
        for g in r["plan"]["groups"]:
            if len(g["facts"]) < 2:
                continue
            a = group_text(r, calls, by, g["facts"], r["plan"].get("edges", []))
            fm = facts_of(r)
            groups.append({"facts": g["facts"], "text": a,
                           "factPass": all(fact_pass(fm[f], a) for f in g["facts"])})
        out[r["sourceId"]] = {"assembled": text, "calls": by, "groups": groups}
    return out


def main():
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert sha(DATA) == freeze["material_sha256"]
    rows = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines()]
    dev = [r for r in rows if r["split"] == "dev"]
    hold = [r for r in rows if r["split"] == "holdout"]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = T5Tokenizer.from_pretrained(str(T.MODEL), legacy=False)

    results = {"material": str(DATA), "material_sha256": sha(DATA),
               "freeze": str(FREEZE), "freeze_sha256": sha(FREEZE),
               "config": freeze["config"], "counts": freeze["counts"], "arms": {}}
    for arm in ("A", "B"):
        print("== training", arm, flush=True)
        model, stats = train_arm(rows, arm, tok, device)
        model.eval()
        print("== dev", arm, flush=True)
        d = eval_arm(model, tok, dev, arm, device)
        print("== holdout", arm, flush=True)
        h = eval_arm(model, tok, hold, arm, device)
        results["arms"][arm] = {"stats": stats, "dev": d, "holdout": h}
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n",
                                      encoding="utf-8", newline="\n")
    print("wrote", OUT / "results.json")
    # print holdout pair summary
    for r in hold:
        a = results["arms"]["A"]["holdout"][r["sourceId"]]
        b = results["arms"]["B"]["holdout"][r["sourceId"]]
        print("\n", r["sourceId"], "\n A", a["assembled"], "\n B", b["assembled"])
        for g in b["groups"]:
            ag = next(x for x in a["groups"] if x["facts"] == g["facts"])
            print("  group", g["facts"], "A", ag["text"], "| B", g["text"], "| fact", ag["factPass"], g["factPass"])


if __name__ == "__main__":
    main()
