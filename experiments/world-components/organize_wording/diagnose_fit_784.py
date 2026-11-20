#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fit diagnostic for the saved B-large-784 checkpoint.

Reuse only. No training, no target change, no parameter change, no output repair.
Evaluate every saved B group call on:
  - train (seen during the 480-call replay)
  - fixed
  - regression (separate old-regression reference)
Then score complete targets with teacher forcing and actual greedy outputs with
generation scores. The token tables are descriptive, not causal.
"""
import argparse, hashlib, json, os, re
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

import torch
from transformers import T5ForConditionalGeneration, T5Tokenizer

MAX_IN = 512
MAX_NEW = 128
SYM = ("心里", "脑子", "胸口", "发紧", "发沉", "松快", "清亮", "发慌", "清醒")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


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
    c = r["context"]; fm = {f["factId"]: f for f in r["facts"]}
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
        text = "".join(sents); ok = any(x in text for x in ("没有", "没再", "没发生")); pos = text.find("没有")
        if pos < 0: pos = 0
    elif k == "sanity_changed":
        text = "".join(sents); ok = any(x in text for x in SYM) and not re.search(r"\d", text)
        pos = max([text.find(x) for x in SYM] + [0])
    else:
        best, bi = 0.0, -1
        for i, s in enumerate(sents):
            rr = recall(f.get("text", ""), s)
            if rr > best: best, bi = rr, i
        return best >= 0.5, max(0, bi), best
    acc = 0
    for i, s in enumerate(sents):
        acc += len(s)
        if pos < acc: return ok, i, 1.0 if ok else 0.0
    return ok, max(0, len(sents)-1), 1.0 if ok else 0.0


def fact_pass(f, text):
    return bool(fact_span(f, sent_split(text))[0])


def meta(facts):
    names = {f.get("name") for f in facts if f.get("name")}
    return {"size": len(facts), "names": sorted(names),
            "relation": "same" if len(names) == 1 else ("cross" if len(names) > 1 else "unknown"),
            "kinds": [f["kind"] for f in facts]}


def logprob_table(tok, token_ids, scores, skip_special=True):
    rows = []
    for i, tid in enumerate(token_ids):
        s = scores[i]
        lp = torch.log_softmax(s, dim=-1)[tid].item()
        txt = tok.convert_ids_to_tokens(int(tid))
        rows.append({"i": i, "id": int(tid), "token": txt, "logprob": round(lp, 6), "p": round(float(torch.exp(torch.tensor(lp))), 6)})
    return rows


def target_scores(model, tok, prompt, target, device):
    enc = tok(prompt, return_tensors="pt", truncation=True, max_length=MAX_IN).to(device)
    lab = tok(target, return_tensors="pt").input_ids.to(device)
    with torch.no_grad():
        out = model(input_ids=enc.input_ids, attention_mask=enc.attention_mask, labels=lab)
        logits = out.logits[0]  # [L, vocab]
        lp = torch.log_softmax(logits, dim=-1)
        ids = lab[0]
        vals = [lp[i, ids[i]].item() for i in range(ids.shape[0])]
        loss = out.loss.item()
    rows = []
    for i, (tid, v) in enumerate(zip(ids.tolist(), vals)):
        rows.append({"i": i, "id": int(tid), "token": tok.convert_ids_to_tokens(int(tid)), "logprob": round(v, 6),
                     "p": round(float(torch.exp(torch.tensor(v))), 6)})
    return rows, sum(vals), loss


def gen_one(model, tok, prompt, device):
    enc = tok(prompt, return_tensors="pt", truncation=True, max_length=MAX_IN).to(device)
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=MAX_NEW, num_beams=1, do_sample=False,
                             return_dict_in_generate=True, output_scores=True)
    seq = out.sequences[0]
    gen_ids = seq[1:].tolist()
    scores = list(out.scores)
    n = min(len(gen_ids), len(scores))
    gen_ids = gen_ids[:n]
    rows = []
    for i, tid in enumerate(gen_ids):
        lp = torch.log_softmax(scores[i], dim=-1)[0, tid].item()
        rows.append({"i": i, "id": int(tid), "token": tok.convert_ids_to_tokens(int(tid)), "logprob": round(lp, 6),
                     "p": round(float(torch.exp(torch.tensor(lp))), 6)})
    text = tok.decode(seq, skip_special_tokens=True).strip()
    eos = bool(gen_ids and gen_ids[-1] == tok.eos_token_id)
    return {"text": text, "tokens": rows, "new_tokens": n, "stop": "eos" if eos else "cap",
            "timeout": False, "total_logprob": sum(r["logprob"] for r in rows), "eos": eos}


def summarize(calls):
    total_calls = len(calls); total_facts = sum(c["size"] for c in calls)
    passed_calls = sum(1 for c in calls if c["group_pass"])
    # calls list only; facts counts are attached below
    by_size = {}; by_rel = {}; by_kind = {}
    for c in calls:
        s = str(c["size"])
        by_size.setdefault(s, {"calls": 0, "calls_pass": 0, "calls_fail": 0, "facts": 0, "facts_pass": 0, "facts_fail": 0})
        by_size[s]["calls"] += 1; by_size[s]["calls_pass"] += int(c["group_pass"]); by_size[s]["calls_fail"] += int(not c["group_pass"])
        by_size[s]["facts"] += c["size"]; by_size[s]["facts_pass"] += c["passed_fact_count"]; by_size[s]["facts_fail"] += c["size"] - c["passed_fact_count"]
        by_rel.setdefault(c["relation"], {"calls": 0, "calls_pass": 0, "calls_fail": 0, "facts": 0, "facts_pass": 0, "facts_fail": 0})
        by_rel[c["relation"]]["calls"] += 1; by_rel[c["relation"]]["calls_pass"] += int(c["group_pass"]); by_rel[c["relation"]]["calls_fail"] += int(not c["group_pass"])
        by_rel[c["relation"]]["facts"] += c["size"]; by_rel[c["relation"]]["facts_pass"] += c["passed_fact_count"]; by_rel[c["relation"]]["facts_fail"] += c["size"] - c["passed_fact_count"]
        for f in c["fact_results"]:
            by_kind.setdefault(f["kind"], {"facts": 0, "facts_pass": 0, "facts_fail": 0, "calls_with_kind": 0, "calls_with_fail": 0})
            by_kind[f["kind"]]["facts"] += 1; by_kind[f["kind"]]["facts_pass"] += int(f["pass"]); by_kind[f["kind"]]["facts_fail"] += int(not f["pass"])
            by_kind[f["kind"]]["calls_with_kind"] += 1
        for k in {f["kind"] for f in c["fact_results"]}:
            if not c["group_pass"]:
                by_kind[k]["calls_with_fail"] += 1
    return {"calls": total_calls, "calls_pass": passed_calls, "calls_fail": total_calls - passed_calls,
            "facts": total_facts, "facts_pass": sum(c["passed_fact_count"] for c in calls),
            "facts_fail": sum(c["size"] - c["passed_fact_count"] for c in calls),
            "by_size": by_size, "by_relation": by_rel, "by_kind": by_kind}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--material", required=True)
    ap.add_argument("--previous", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    ckpt = Path(args.ckpt)
    ck_hash = sha(ckpt / "model.safetensors")
    tok_hash = sha(ckpt / "spiece.model")
    rows = load_jsonl(args.material)
    prev = json.loads(Path(args.previous).read_text(encoding="utf-8"))
    tok = T5Tokenizer.from_pretrained(str(ckpt), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(ckpt), torch_dtype=torch.float32).to("cuda").eval()
    result = {"checkpoint": {"path": str(ckpt), "weights_sha256": ck_hash, "tokenizer_sha256": tok_hash},
              "material": args.material, "material_sha256": sha(args.material),
              "previous": args.previous, "previous_sha256": sha(args.previous),
              "max_input": MAX_IN, "max_new": MAX_NEW, "splits": {}, "omission_details": []}
    for split in ("train", "fixed", "regression"):
        split_rows = [r for r in rows if r["split"] == split]
        calls = []
        for r in split_rows:
            fm = {f["factId"]: f for f in r["facts"]}
            for ci, call in enumerate(r["B"]["calls"]):
                prompt = prompt_call(r, call, ci + 1, len(r["B"]["calls"]))
                g = gen_one(model, tok, prompt, "cuda")
                facts = [fm[fid] for fid in call["factIds"]]
                fr = [{"factId": f["factId"], "kind": f["kind"], "name": f.get("name", ""),
                       "pass": fact_pass(f, g["text"])} for f in facts]
                passed_fact_count = sum(1 for x in fr if x["pass"])
                m = meta(facts)
                rec = {"sourceId": r["sourceId"], "callId": call["callId"], "size": m["size"],
                       "relation": m["relation"], "kinds": m["kinds"], "facts": call["factIds"],
                       "group_pass": passed_fact_count == len(facts), "passed_fact_count": passed_fact_count,
                       "fact_results": fr, "target": call["target"], "actual": g["text"],
                       "new_tokens": g["new_tokens"], "stop": g["stop"], "timeout": g["timeout"],
                       "actual_total_logprob": round(g["total_logprob"], 6)}
                calls.append(rec)
                if passed_fact_count < len(facts):
                    tr, tsum, tloss = target_scores(model, tok, prompt, call["target"], "cuda")
                    # actual token table recomputed from generated rows by gen_one is already available; recompute text only.
                    rec["omissions"] = [x for x in fr if not x["pass"]]
                    rec["actual_token_table"] = g["tokens"]
                    rec["target_token_table"] = tr
                    rec["target_total_logprob"] = round(tsum, 6)
                    rec["target_avg_logprob"] = round(tsum / max(1, len(tr)), 6)
                    rec["actual_avg_logprob"] = round(g["total_logprob"] / max(1, len(g["tokens"])), 6)
                    rec["target_loss"] = round(tloss, 6)
                    rec["target_eos_logprob"] = tr[-1]["logprob"] if tr and tr[-1]["id"] == tok.eos_token_id else None
                    rec["actual_eos_logprob"] = g["tokens"][-1]["logprob"] if g["eos"] else None
                    rec["actual_eos"] = g["eos"]
                    # target/actual char lengths and whether actual ends before the target's first omitted text word.
                    rec["target_chars"] = len(call["target"]); rec["actual_chars"] = len(g["text"])
                    result["omission_details"].append({"split": split, "sourceId": r["sourceId"], "callId": call["callId"]})
        result["splits"][split] = {"summary": summarize(calls), "calls": calls}
        print(split, summarize(calls), flush=True)
    # output consistency with the saved final run for fixed/regression
    consistency = {"checked": 0, "same": 0, "different": []}
    for split in ("fixed", "regression"):
        for sid, x in prev[split].items():
            cur = next(c for c in result["splits"][split]["calls"] if c["sourceId"] == sid)
            # compare each call by id
            for cid, old in x["calls"].items():
                now = next((c for c in result["splits"][split]["calls"] if c["callId"] == cid), None)
                if now is None: continue
                consistency["checked"] += 1
                if old["text"] == now["actual"]:
                    consistency["same"] += 1
                else:
                    consistency["different"].append({"split": split, "sourceId": sid, "callId": cid,
                                                     "old": old["text"], "new": now["actual"]})
    result["consistency_with_previous"] = consistency
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("wrote", out, "omissions", len(result["omission_details"]), "consistency", consistency["checked"], consistency["same"], len(consistency["different"]), flush=True)


if __name__ == "__main__":
    main()
