#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A vs B_h sentence-training run on pairs-v2.jsonl.

Fixed protocol (see design/world-engine-reports/components/material-scaleup-v1.md):
- base: Randeng-T5-77M (local)
- 24 train / 8 dev / 12 fixed holdout; 1 source per step; grad-accum 4
- 20 epochs = 120 optimizer updates; dev eval every epoch
- select by dev fact S-rate, tie-break lower dev loss; run all epochs (no patience)
- holdout once after selection; A and B_h differ only by the plan block
"""
import argparse, hashlib, json, os, random, re, sys, tempfile
from pathlib import Path

# This Anaconda environment has NumPy 2.x with sklearn/pyarrow/h5py built for 1.x.
# Transformers only needs sklearn.metrics.roc_curve for assisted decoding, which we do not use.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
_stub = Path(tempfile.mkdtemp()) / "sklearn"
_stub.mkdir()
(_stub / "__init__.py").write_text("")
(_stub / "metrics.py").write_text("def roc_curve(*a, **k):" + chr(10) + "    raise RuntimeError('sklearn stub')" + chr(10))
sys.path.insert(0, str(_stub.parent))

import numpy as np
import torch
from torch.optim import AdamW
from transformers import T5ForConditionalGeneration, T5Tokenizer, get_linear_schedule_with_warmup

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "artifacts/world-components/organize-wording/pairs-v2.jsonl"
VARIANTS = ROOT / "artifacts/world-components/organize-wording/plan-variants-v1.jsonl"
OUT = ROOT / "artifacts/world-components/organize-wording/ab-run-v1"
MODEL = ROOT / "experiments/world-components/assets/randeng-t5-77m"
SEED = 13
EPOCHS = 20
STEPS_PER_EPOCH = 24
ACCUM = 4
TOTAL_UPDATES = EPOCHS * STEPS_PER_EPOCH // ACCUM  # 120
WARMUP = 12
LR = 5e-4
MAX_IN = 512
MAX_TGT = 128
MAX_NEW = 128


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_rows(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines()]


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


def prompt(r, with_plan):
    c = r["context"]
    lines = ["叙事任务。",
             f"地点={c.get('place','')}",
             f"地点可见={c.get('visible','')}",
             f"场景={c.get('scene','')}",
             f"视角={c.get('viewpoint','')}"]
    edges = r["plan"].get("edges", [])
    if edges:
        rel = "；".join(f"{e['from']} before {e['to']}（{e['mode']}）" for e in edges)
    else:
        rel = "无"
    lines += [f"授权关系={rel}", "事实（按顺序）："]
    lines += [fact_line(f) for f in r["facts"]]
    if with_plan:
        plan = {"groups": r["plan"]["groups"], "refs": r["plan"]["refs"], "edges": edges}
        lines += ["表达计划：", json.dumps(plan, ensure_ascii=False, separators=(",", ":")),
                  "要求：按计划的组和衔接写；组内可用逗号或分号，组间至少分号；edges 里 required 的关系必须写出，optional 可不写。"]
    lines += ["要求：把全部事实写成一段连贯中文；按给定顺序；不新增人物、物品、地点、动作、关系；不写任务标题、数值、时长、字段名；不写代词，需要称呼时用姓名或承前省略。",
              "正文："]
    return "\n".join(lines) + "\n"


def sent_split(text):
    parts = [p.strip() for p in re.split(r"(?<=[。！？])", text) if p.strip()]
    return parts


def grams(s, n=3):
    s = re.sub(r"\s", "", s)
    return {s[i:i+n] for i in range(max(0, len(s)-n+1))} or {s}


def recall(a, b):
    ga, gb = grams(a), grams(b)
    if not ga:
        return 0.0
    return len(ga & gb) / len(ga)


SYM = ("心里", "脑子", "胸口", "发紧", "发沉", "松快", "清亮", "发慌", "清醒")


def fact_span(f, sents):
    k = f["kind"]
    if k == "moved":
        text = "".join(sents)
        i, j = text.find(f["from"]), text.find(f["to"])
        ok = i >= 0 and j > i
        pos = j if j >= 0 else 0
    elif k == "no_change":
        text = "".join(sents)
        ok = any(x in text for x in ("没有", "没再", "没发生"))
        pos = text.find("没有")
        if pos < 0:
            pos = 0
    elif k == "sanity_changed":
        text = "".join(sents)
        ok = any(x in text for x in SYM) and not re.search(r"\d", text)
        pos = max([text.find(x) for x in SYM] + [0])
    else:
        best, bi, pos = 0.0, -1, 0
        for i, s in enumerate(sents):
            r = recall(f.get("text", ""), s)
            if r > best:
                best, bi = r, i
        ok = best >= 0.5
        pos = 0
        # map to sentence index directly
        if bi >= 0:
            return ok, bi, best
        return ok, 0, best
    # map char pos to sentence
    acc = 0
    for i, s in enumerate(sents):
        acc += len(s)
        if pos < acc:
            return ok, i, 1.0 if ok else 0.0
    return ok, max(0, len(sents)-1), 1.0 if ok else 0.0


def check(r, text):
    sents = sent_split(text)
    info = {}
    for f in r["facts"]:
        ok, si, sc = fact_span(f, sents)
        info[f["factId"]] = {"support": bool(ok), "sent": int(si), "score": round(float(sc), 3),
                             "sentence": sents[si] if sents else ""}
    plan = r["plan"]
    merged = []
    for g in plan["groups"]:
        if len(g["facts"]) > 1:
            sids = [info[i]["sent"] for i in g["facts"]]
            merged.append({"group": g["facts"], "same_sentence": len(set(sids)) == 1, "sents": sids})
    separated = []
    for a, b in zip(plan["groups"], plan["groups"][1:]):
        x, y = a["facts"][-1], b["facts"][0]
        separated.append({"pair": [x, y], "different": info[x]["sent"] != info[y]["sent"],
                          "sents": [info[x]["sent"], info[y]["sent"]]})
    rel = []
    for e in plan.get("edges", []):
        x, y = e["from"], e["to"]
        ok = ("随后" in text) and info[x]["sent"] != info[y]["sent"]
        rel.append({"edge": [x, y], "ok": bool(ok), "sents": [info[x]["sent"], info[y]["sent"]]})
    supported = sum(1 for v in info.values() if v["support"])
    return {
        "text": text,
        "sentences": sents,
        "facts": info,
        "fact_supported": supported,
        "fact_total": len(info),
        "fact_score": supported / max(1, len(info)),
        "merged": merged,
        "separated": separated,
        "relations": rel,
        "omissions": [i for i, v in info.items() if not v["support"]],
        "contains_pronoun": bool(re.search(r"[他她]", text)),
        "contains_digit": bool(re.search(r"\d", text)),
        "contains_simultaneous": "同时" in text or "与此同时" in text,
    }


def tokenize(tok, p, t):
    x = tok(p, return_tensors="pt", truncation=True, max_length=MAX_IN)
    y = tok(t, return_tensors="pt", truncation=True, max_length=MAX_TGT)
    return x.input_ids[0], x.attention_mask[0], y.input_ids[0]


def gen(model, tok, p, device):
    x = tok(p, return_tensors="pt", truncation=True, max_length=MAX_IN).to(device)
    with torch.no_grad():
        out = model.generate(**x, max_new_tokens=MAX_NEW, num_beams=1, do_sample=False)
    return tok.decode(out[0], skip_special_tokens=True).strip()


def gen_batch(model, tok, prompts, device, batch=8):
    outs = []
    for i in range(0, len(prompts), batch):
        chunk = prompts[i:i+batch]
        x = tok(chunk, padding=True, truncation=True, max_length=MAX_IN, return_tensors="pt").to(device)
        with torch.no_grad():
            out = model.generate(**x, max_new_tokens=MAX_NEW, num_beams=1, do_sample=False)
        outs += [tok.decode(o, skip_special_tokens=True).strip() for o in out]
    return outs


def dev_loss(model, tok, rows, device, with_plan):
    model.eval()
    total, n = 0.0, 0
    with torch.no_grad():
        for r in rows:
            inp, mask, lab = tokenize(tok, prompt(r, with_plan), r["target"])
            inp, mask, lab = inp.unsqueeze(0).to(device), mask.unsqueeze(0).to(device), lab.unsqueeze(0).to(device)
            loss = model(input_ids=inp, attention_mask=mask, labels=lab).loss
            total += float(loss); n += 1
    return total / max(1, n)


def train_arm(arm, rows, device, log):
    assert arm in ("A", "B_h")
    torch.manual_seed(SEED); random.seed(SEED); np.random.seed(SEED)
    tok = T5Tokenizer.from_pretrained(str(MODEL), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(MODEL), torch_dtype=torch.float32).to(device)
    opt = AdamW(model.parameters(), lr=LR, betas=(0.9, 0.999), eps=1e-8, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, WARMUP, TOTAL_UPDATES)
    train = [r for r in rows if r["split"] == "train"]
    dev = [r for r in rows if r["split"] == "dev"]
    best = {"score": -1.0, "loss": 1e9, "epoch": 0, "state": None}
    hist = []
    step_in_epoch = 0
    update = 0
    opt.zero_grad()
    for epoch in range(1, EPOCHS + 1):
        model.train()
        order = list(train); random.Random(SEED + epoch).shuffle(order)
        for r in order:
            inp, mask, lab = tokenize(tok, prompt(r, arm == "B_h"), r["target"])
            inp, mask, lab = inp.unsqueeze(0).to(device), mask.unsqueeze(0).to(device), lab.unsqueeze(0).to(device)
            loss = model(input_ids=inp, attention_mask=mask, labels=lab).loss / ACCUM
            loss.backward()
            step_in_epoch += 1
            if step_in_epoch % ACCUM == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step(); sched.step(); opt.zero_grad()
                update += 1
        dl = dev_loss(model, tok, dev, device, arm == "B_h")
        texts = gen_batch(model, tok, [prompt(r, arm == "B_h") for r in dev], device)
        evals = [{"sourceId": r["pairId"], **check(r, t)} for r, t in zip(dev, texts)]
        score = sum(e["fact_score"] for e in evals) / max(1, len(evals))
        hist.append({"epoch": epoch, "update": update, "dev_loss": dl, "dev_fact_score": score,
                     "dev": [{"sourceId": e["sourceId"], "fact_score": e["fact_score"], "omissions": e["omissions"]} for e in evals]})
        log(f"[{arm}] epoch {epoch} update {update} dev_loss {dl:.4f} dev_fact {score:.3f}")
        better = score > best["score"] or (score == best["score"] and dl < best["loss"])
        if better:
            best = {"score": score, "loss": dl, "epoch": epoch, "state": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}
    model.load_state_dict(best["state"]); model.to(device)
    return model, tok, best, hist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    logf = open(OUT / "run.log", "w", encoding="utf-8")
    def log(s):
        print(s, flush=True); logf.write(s + "\n"); logf.flush()

    rows = load_rows(DATA)
    train = [r for r in rows if r["split"] == "train"]
    dev = [r for r in rows if r["split"] == "dev"]
    hold = [r for r in rows if r["split"] == "holdout"]
    assert len(train) == 24 and len(dev) == 8 and len(hold) == 12

    config = {"base": str(MODEL), "base_model_sha256": sha(MODEL / "model.safetensors"),
              "base_spiece_sha256": sha(MODEL / "spiece.model"), "data": str(DATA), "data_sha256": sha(DATA),
              "variants": str(VARIANTS), "variants_sha256": sha(VARIANTS),
              "seed": SEED, "epochs": EPOCHS, "steps_per_epoch": STEPS_PER_EPOCH, "accum": ACCUM,
              "total_updates": TOTAL_UPDATES, "warmup": WARMUP, "lr": LR, "max_in": MAX_IN,
              "max_tgt": MAX_TGT, "max_new": MAX_NEW, "device": args.device,
              "torch": torch.__version__, "cuda": torch.cuda.get_device_name(0) if args.device == "cuda" else None}
    result = {"config": config, "arms": {}, "plan_response": {}}

    models = {}
    for arm in ("A", "B_h"):
        log(f"=== arm {arm} ===")
        model, tok, best, hist = train_arm(arm, rows, args.device, log)
        models[arm] = (model, tok)
        texts = gen_batch(model, tok, [prompt(r, arm == "B_h") for r in hold], args.device, batch=6)
        hold_out = [{"sourceId": r["pairId"], "split": "holdout", "target": r["target"], **check(r, t)}
                    for r, t in zip(hold, texts)]
        result["arms"][arm] = {"selected_epoch": best["epoch"], "selected_update": best["epoch"] * STEPS_PER_EPOCH // ACCUM,
                               "selected_dev_loss": best["loss"], "selected_dev_fact_score": best["score"],
                               "history": hist, "holdout": hold_out}

    # plan response on 4 dev sources, using the selected B_h checkpoint
    variants = load_rows(VARIANTS)
    model, tok = models["B_h"]
    for v in variants:
        r = next(x for x in rows if x["pairId"] == v["sourceId"])
        p1 = dict(r); p1["plan"] = v["planA"]
        p2 = dict(r); p2["plan"] = v["planB"]
        t1 = gen(model, tok, prompt(p1, True), args.device)
        t2 = gen(model, tok, prompt(p2, True), args.device)
        result["plan_response"][v["sourceId"]] = {"planA": check(p1, t1), "planB": check(p2, t2)}

    result["model_state_sha256"] = None
    out = OUT / "results.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"wrote {out}")
    logf.close()


if __name__ == "__main__":
    main()
