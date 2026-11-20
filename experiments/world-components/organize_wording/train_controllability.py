#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plan-controllability training: one sentence model, two plans per source.

Frozen protocol: design/world-engine-reports/components/plan-controllability-v1.md
- 36 sources, 20 train / 6 dev / 10 fixed holdout; both plans of a source in the same split
- 1 source-plan per step, grad-accum 4, 12 epochs x 40 steps = 120 updates
- dev paired success selects the checkpoint, tie lower dev loss; no patience
- holdout once; exact token counts and stop reasons are saved
"""
import json, random, sys, hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_ab as T
import numpy as np
import torch
from torch.optim import AdamW
from transformers import T5ForConditionalGeneration, T5Tokenizer, get_linear_schedule_with_warmup

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "artifacts/world-components/organize-wording/controllability-v1.jsonl"
FREEZE = ROOT / "artifacts/world-components/organize-wording/controllability-freeze-v1.json"
OUT = ROOT / "artifacts/world-components/organize-wording/controllability-run-v1"
OUT.mkdir(parents=True, exist_ok=True)
SEED = 13
EPOCHS = 12
STEPS_PER_EPOCH = 40
ACCUM = 4
UPDATES = 120
MAX_IN = 512
MAX_NEW = 128


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_rows():
    return [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines()]


def prompt_plan(r, pk):
    p = r["plans"][pk]["plan"]
    c = r["context"]
    lines = ["叙事任务。",
             f"地点={c.get('place','')}",
             f"地点可见={c.get('visible','')}",
             f"场景={c.get('scene','')}",
             f"视角={c.get('viewpoint','')}"]
    edges = p.get("edges", [])
    rel = "；".join(f"{e['from']} before {e['to']}（{e['mode']}）" for e in edges) if edges else "无"
    lines += [f"授权关系={rel}", "事实（按顺序）："]
    lines += [T.fact_line(f) for f in r["facts"]]
    plan = {"groups": p["groups"], "refs": p["refs"], "edges": edges}
    lines += ["表达计划：", json.dumps(plan, ensure_ascii=False, separators=(",", ":")),
              "要求：按计划的组和衔接写；组内可用逗号或分号，组间至少分号；edges 里 required 的关系必须写出，optional 可不写。"]
    lines += ["要求：把全部事实写成一段连贯中文；按给定顺序；不新增人物、物品、地点、动作、关系；不写任务标题、数值、时长、字段名；不写代词，需要称呼时用姓名或承前省略。",
              "正文："]
    return "\n".join(lines) + "\n"


def check_plan(r, pk, text):
    return T.check({"facts": r["facts"], "plan": r["plans"][pk]["plan"]}, text)


def fact_ok(chk):
    return chk["fact_supported"] == chk["fact_total"]


def plan_ok(chk):
    return (all(m["same_sentence"] for m in chk["merged"])
            and all(s["different"] for s in chk["separated"])
            and all(x["ok"] for x in chk["relations"]))


def diff_ok(r, chkA, chkB):
    for g in r["plans"]["A"]["plan"]["groups"]:
        if len(g["facts"]) < 2:
            continue
        for a, b in zip(g["facts"], g["facts"][1:]):
            if chkA["facts"][a]["sent"] != chkA["facts"][b]["sent"]:
                return False
            if chkB["facts"][a]["sent"] == chkB["facts"][b]["sent"]:
                return False
    return True


def paired(r, chkA, chkB):
    return fact_ok(chkA) and fact_ok(chkB) and plan_ok(chkA) and plan_ok(chkB) and diff_ok(r, chkA, chkB)


def dev_loss(model, tok, rows, device):
    model.eval()
    total, n = 0.0, 0
    with torch.no_grad():
        for r in rows:
            for pk in ("A", "B"):
                inp, mask, lab = T.tokenize(tok, prompt_plan(r, pk), r["plans"][pk]["target"])
                inp, mask, lab = inp.unsqueeze(0).to(device), mask.unsqueeze(0).to(device), lab.unsqueeze(0).to(device)
                total += model(input_ids=inp, attention_mask=mask, labels=lab).loss.item()
                n += 1
    return total / max(1, n)


def gen_batch_exact(model, tok, prompts, device, batch=6):
    outs = []
    for i in range(0, len(prompts), batch):
        chunk = prompts[i:i+batch]
        x = tok(chunk, padding=True, truncation=True, max_length=MAX_IN, return_tensors="pt").to(device)
        with torch.no_grad():
            out = model.generate(**x, max_new_tokens=MAX_NEW, num_beams=1, do_sample=False,
                                 return_dict_in_generate=True)
        for seq in out.sequences:
            new_tokens = int(seq.shape[0] - 1)
            outs.append({"text": tok.decode(seq, skip_special_tokens=True).strip(),
                         "new_tokens": new_tokens,
                         "stop": "cap" if new_tokens >= MAX_NEW else "eos"})
    return outs


def eval_rows(model, tok, rows, device):
    prompts = [prompt_plan(r, pk) for r in rows for pk in ("A", "B")]
    outs = gen_batch_exact(model, tok, prompts, device)
    by = {}
    k = 0
    for r in rows:
        by[r["pairId"]] = {}
        for pk in ("A", "B"):
            o = outs[k]; k += 1
            chk = check_plan(r, pk, o["text"])
            by[r["pairId"]][pk] = {"new_tokens": o["new_tokens"], "stop": o["stop"], **chk}
    return by


def main():
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    actual = sha(DATA)
    assert actual == freeze["material_sha256"], (actual, freeze["material_sha256"])
    rows = load_rows()
    train = [r for r in rows if r["split"] == "train"]
    dev = [r for r in rows if r["split"] == "dev"]
    hold = [r for r in rows if r["split"] == "holdout"]
    assert len(train) == 20 and len(dev) == 6 and len(hold) == 10

    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(SEED); random.seed(SEED); np.random.seed(SEED)
    tok = T5Tokenizer.from_pretrained(str(T.MODEL), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(T.MODEL), torch_dtype=torch.float32).to(device)
    opt = AdamW(model.parameters(), lr=T.LR, betas=(0.9, 0.999), eps=1e-8, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, T.WARMUP, UPDATES)
    step_in_epoch = 0
    update = 0
    best = {"success": -1, "loss": 1e9, "epoch": 0, "updates": 0, "state": None}
    history = []
    opt.zero_grad()

    for epoch in range(1, EPOCHS + 1):
        model.train()
        order = list(train); random.Random(SEED + epoch).shuffle(order)
        for r in order:
            for pk in ("A", "B"):
                inp, mask, lab = T.tokenize(tok, prompt_plan(r, pk), r["plans"][pk]["target"])
                inp, mask, lab = inp.unsqueeze(0).to(device), mask.unsqueeze(0).to(device), lab.unsqueeze(0).to(device)
                loss = model(input_ids=inp, attention_mask=mask, labels=lab).loss / ACCUM
                loss.backward()
                step_in_epoch += 1
                if step_in_epoch % ACCUM == 0:
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    opt.step(); sched.step(); opt.zero_grad()
                    update += 1
        dl = dev_loss(model, tok, dev, device)
        by = eval_rows(model, tok, dev, device)
        successes = []
        for r in dev:
            ok = paired(r, by[r["pairId"]]["A"], by[r["pairId"]]["B"])
            successes.append({"sourceId": r["pairId"], "success": ok})
        ns = sum(1 for x in successes if x["success"])
        history.append({"epoch": epoch, "updates": update, "dev_loss": round(dl, 4),
                        "dev_success": ns, "dev_total": len(dev), "sources": successes})
        print(f"epoch {epoch} update {update} dev_loss {dl:.4f} dev_success {ns}/{len(dev)}", flush=True)
        for x in successes:
            print("  ", x["sourceId"], "OK" if x["success"] else "no", flush=True)
        if ns > best["success"] or (ns == best["success"] and dl < best["loss"]):
            best = {"success": ns, "loss": dl, "epoch": epoch, "updates": update,
                    "state": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}
            print(f"  -> best so far epoch {epoch} update {update}", flush=True)

    model.load_state_dict(best["state"])
    model.eval()
    hold_by = eval_rows(model, tok, hold, device)
    holdout = []
    for r in hold:
        a = hold_by[r["pairId"]]["A"]; b = hold_by[r["pairId"]]["B"]
        holdout.append({"sourceId": r["pairId"], "A": a, "B": b,
                        "paired_success": paired(r, a, b)})
    result = {
        "material": str(DATA), "material_sha256": actual,
        "freeze": str(FREEZE), "freeze_sha256": sha(FREEZE),
        "config": {"base": str(T.MODEL), "seed": SEED, "epochs": EPOCHS, "steps_per_epoch": STEPS_PER_EPOCH,
                   "accum": ACCUM, "updates": UPDATES, "lr": T.LR, "warmup": T.WARMUP,
                   "max_in": MAX_IN, "max_new": MAX_NEW, "decode": "greedy", "device": device},
        "counts": {"train_sources": len(train), "dev_sources": len(dev), "holdout_sources": len(hold)},
        "history": history,
        "selected": {"epoch": best["epoch"], "updates": best["updates"],
                     "dev_success": best["success"], "dev_loss": round(best["loss"], 4)},
        "holdout": holdout,
        "holdout_success": sum(1 for x in holdout if x["paired_success"]),
    }
    (OUT / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("selected", result["selected"], "holdout", result["holdout_success"], "/", len(holdout), flush=True)
    for x in holdout:
        print(x["sourceId"], "PAIR-OK" if x["paired_success"] else "PAIR-FAIL",
              "A:", x["A"]["text"], "|", x["A"]["stop"], x["A"]["new_tokens"],
              "B:", x["B"]["text"], "|", x["B"]["stop"], x["B"]["new_tokens"], flush=True)


if __name__ == "__main__":
    main()
