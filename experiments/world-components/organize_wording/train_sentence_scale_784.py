#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Randeng-T5-784M B-large replay run.

Frozen protocol: artifacts/world-components/organize-wording/sentence-base-784m-freeze-v1.json
- replay the 480 B-large-77 calls in exact order
- same material/targets/optimizer; only the base model changes
- 120 updates, final point, greedy; no selection
- save final weights + identity; record generated tokens and stop reason
"""
import argparse, hashlib, json, os, re, time
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

import numpy as np
import torch
from torch.optim import AdamW
from transformers import T5ForConditionalGeneration, T5Tokenizer, get_linear_schedule_with_warmup

SEED = 13
STEPS = 480
ACCUM = 4
UPDATES = 120
MAX_IN = 512
MAX_NEW = 128
SYM = ("心里", "脑子", "胸口", "发紧", "发沉", "松快", "清亮", "发慌", "清醒")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_jsonl(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


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


def facts_of(r):
    return {f["factId"]: f for f in r["facts"]}


def prompt_call(r, call, idx, total):
    c = r["context"]; fm = facts_of(r)
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


def tokenize(tok, p, t):
    x = tok(p, return_tensors="pt", truncation=True, max_length=MAX_IN)
    y = tok(t, return_tensors="pt", truncation=True, max_length=MAX_NEW)
    return x.input_ids[0], x.attention_mask[0], y.input_ids[0]


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
                         "timeout": False,
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


def group_text(r, calls, outputs, group_facts, edges):
    cs = [c for c in calls if set(c["factIds"]) <= set(group_facts)]
    assert cs, (r["sourceId"], group_facts)
    return assemble(cs, outputs, edges)


def sent_split(text):
    return [p.strip() for p in re.split(r"(?<=[。！？])", text) if p.strip()]


def grams(s, n=3):
    s = re.sub(r"\s", "", s)
    return {s[i:i+n] for i in range(max(0, len(s)-n+1))} or {s}


def recall(a, b):
    ga, gb = grams(a), grams(b)
    return len(ga & gb) / len(ga) if ga else 0.0


def fact_span(f, sents):
    k = f["kind"]
    if k == "moved":
        text = "".join(sents); i, j = text.find(f["from"]), text.find(f["to"])
        ok = i >= 0 and j > i; pos = j if j >= 0 else 0
    elif k == "no_change":
        text = "".join(sents); ok = any(x in text for x in ("没有", "没再", "没发生")); pos = text.find("没有");
        if pos < 0: pos = 0
    elif k == "sanity_changed":
        text = "".join(sents); ok = any(x in text for x in SYM) and not re.search(r"\d", text)
        pos = max([text.find(x) for x in SYM] + [0])
    else:
        best, bi = 0.0, -1
        for i, s in enumerate(sents):
            r = recall(f.get("text", ""), s)
            if r > best: best, bi = r, i
        return best >= 0.5, max(0, bi), best
    acc = 0
    for i, s in enumerate(sents):
        acc += len(s)
        if pos < acc: return ok, i, 1.0 if ok else 0.0
    return ok, max(0, len(sents)-1), 1.0 if ok else 0.0


def fact_pass(f, text):
    return bool(fact_span(f, sent_split(text))[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--material", required=True)
    ap.add_argument("--replay", required=True)
    ap.add_argument("--freeze", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    freeze = json.loads(Path(args.freeze).read_text(encoding="utf-8"))
    assert sha(args.material) == freeze["fixed_material"]["sha256"]
    assert sha(args.replay) == freeze["sampling_replay"]["reference_sha256"]
    rows = load_jsonl(args.material); by = {r["sourceId"]: r for r in rows}
    replay = load_jsonl(args.replay)
    assert len(replay) == STEPS
    # exact replay validation
    for e in replay:
        r = by[e["sourceId"]]
        c = next((c for c in r["B"]["calls"] if c["callId"] == e["callId"]), None)
        assert c is not None, e["callId"]
        assert c["factIds"] == e["factIds"], e["callId"]
        assert c["target"], e["callId"]
    # load/lock
    base = Path(args.base)
    tok = T5Tokenizer.from_pretrained(str(base), legacy=False)
    tok_hash = sha(base / "spiece.model")
    config_hash = sha(base / "config.json")
    weight_hash = sha(base / "pytorch_model.bin")
    assert tok_hash == freeze["model"]["tokenizer_sha256"]
    assert config_hash == freeze["model"]["config_sha256"]
    assert weight_hash == freeze["model"]["weights_sha256"]
    # length audit, no silent truncation
    max_in = max_out = 0
    target_mismatch = 0
    for e in replay:
        r = by[e["sourceId"]]; calls = r["B"]["calls"]
        c = next(c for c in calls if c["callId"] == e["callId"])
        idx = next(i for i, x in enumerate(calls) if x["callId"] == c["callId"]) + 1
        ni = len(tok(prompt_call(r, c, idx, len(calls)), add_special_tokens=False)["input_ids"])
        no = len(tok(c["target"], add_special_tokens=False)["input_ids"])
        assert ni <= MAX_IN and no <= MAX_NEW, (e["callId"], ni, no)
        max_in = max(max_in, ni); max_out = max(max_out, no)
        target_mismatch += int(no != e["targetTokens"])
    assert target_mismatch == 0
    # training
    torch.manual_seed(SEED); np.random.seed(SEED)
    model = T5ForConditionalGeneration.from_pretrained(str(base), torch_dtype=torch.float32).to("cuda")
    opt = AdamW(model.parameters(), lr=5e-4, betas=(0.9, 0.999), eps=1e-8, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, 12, UPDATES)
    model.train(); opt.zero_grad()
    t_start = time.time(); peak = 0; logs = []
    for i, e in enumerate(replay):
        r = by[e["sourceId"]]; calls = r["B"]["calls"]
        c = next(c for c in calls if c["callId"] == e["callId"])
        idx = next(j for j, x in enumerate(calls) if x["callId"] == c["callId"]) + 1
        inp, mask, lab = tokenize(tok, prompt_call(r, c, idx, len(calls)), c["target"])
        inp, mask, lab = inp.unsqueeze(0).to("cuda"), mask.unsqueeze(0).to("cuda"), lab.unsqueeze(0).to("cuda")
        loss = model(input_ids=inp, attention_mask=mask, labels=lab).loss / ACCUM
        loss.backward()
        if (i + 1) % ACCUM == 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad()
        peak = max(peak, torch.cuda.max_memory_allocated() if torch.cuda.is_available() else 0)
        logs.append({"step": i+1, "update": (i+1)//ACCUM, "callId": e["callId"], "sourceId": e["sourceId"],
                     "factIds": e["factIds"], "targetTokens": len(tok(c["target"], add_special_tokens=False)["input_ids"])})
        if (i + 1) % 40 == 0:
            print(f"step {i+1} update {(i+1)//ACCUM}", flush=True)
    wall = round(time.time() - t_start, 2)
    # save final
    ckpt = out / "ckpt-final"; ckpt.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(ckpt), safe_serialization=True)
    tok.save_pretrained(str(ckpt))
    model.eval()
    def eval_split(name, rs):
        res = {}
        for r in rs:
            calls = r["B"]["calls"]
            ps = [prompt_call(r, c, i+1, len(calls)) for i, c in enumerate(calls)]
            gs = gen_batch_exact(model, tok, ps, "cuda")
            got = {c["callId"]: g for c, g in zip(calls, gs)}
            text = assemble(calls, got, r["plan"].get("edges", []))
            groups = []; fm = facts_of(r)
            for g in r["plan"]["groups"]:
                if len(g["facts"]) < 2: continue
                a = group_text(r, calls, got, g["facts"], r["plan"].get("edges", []))
                groups.append({"facts": g["facts"], "text": a, "factPass": all(fact_pass(fm[f], a) for f in g["facts"])})
            res[r["sourceId"]] = {"assembled": text, "calls": got, "groups": groups}
        return res
    fixed = [r for r in rows if r["split"] == "fixed"]
    reg = [r for r in rows if r["split"] == "regression"]
    fx = eval_split("fixed", fixed); rg = eval_split("regression", reg)
    # identity
    files = {}
    for f in ("model.safetensors", "config.json", "spiece.model", "special_tokens_map.json", "tokenizer_config.json"):
        p = ckpt / f
        files[f] = {"size": p.stat().st_size, "sha256": sha(p)} if p.exists() else None
    result = {
        "base": str(base), "material": args.material, "material_sha256": sha(args.material),
        "replay": args.replay, "replay_sha256": sha(args.replay), "freeze": args.freeze, "freeze_sha256": sha(args.freeze),
        "identity": {"base_weights_sha256": weight_hash, "base_config_sha256": config_hash, "tokenizer_sha256": tok_hash,
                     "final_files": files},
        "stats": {"steps": STEPS, "updates": UPDATES, "replay_calls": len(replay), "unique_calls": len({e["callId"] for e in replay}),
                  "max_input_tokens": max_in, "max_target_tokens": max_out, "target_token_mismatches": target_mismatch,
                  "wall_seconds": wall, "peak_cuda_bytes": int(peak), "target_tokens": sum(x["targetTokens"] for x in logs),
                  "facts_exposed": sum(len(e["factIds"]) for e in replay)},
        "fixed": fx, "regression": rg, "sampled_log": logs
    }
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "run.log").write_text(f"wall_seconds={wall}\npeak_cuda_bytes={peak}\n", encoding="utf-8", newline="\n")
    print("wrote", out / "results.json", "wall", wall, "peak", peak)


if __name__ == "__main__":
    main()
