"""Single-fact expansion arm: mixed batches (4 original + 4 new), 2880 updates.

Same base, same input format, same optimizer/lr. Dev loss is the original dev
set, evaluated on a fixed update-step cadence; the checkpoint with the best dev
loss is used for generation.
"""
import argparse
import json
import pathlib
import random
import sys
import time
from collections import defaultdict

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sequence_policy import encode_training_batch, generate_greedy, rethrow_oom

SEED = 20261102
LR = 3e-4
BATCH = 8
N_NEW_PER_BATCH = 4
MAX_UPDATES = 2880
EVAL_EVERY = 240


def rows(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8")
            .splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--units", required=True)
    ap.add_argument("--new-units", required=True)
    ap.add_argument("--confirm", required=True)
    ap.add_argument("--cf24", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", default=None)
    ap.add_argument("--budget", type=float, default=20.0)
    args = ap.parse_args()

    man = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    src_split = {s["sourceId"]: s["split"] for s in man["sources"]}
    base_units = rows(args.units)
    train = [u for u in base_units if src_split.get(u["sourceId"]) == "formal-train"]
    dev = [u for u in base_units if src_split.get(u["sourceId"]) == "formal-dev"]
    new = rows(args.new_units)

    tok = T5Tokenizer.from_pretrained(args.base, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(args.base,
                                                       torch_dtype=torch.float32)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    torch.manual_seed(SEED)
    random.seed(SEED)
    opt = torch.optim.AdamW(model.parameters(), lr=LR)

    rep = {"arm": "expand80", "seed": SEED, "lr": LR, "batch": BATCH,
           "mixPerBatch": {"original": BATCH - N_NEW_PER_BATCH,
                           "new": N_NEW_PER_BATCH},
           "maxUpdates": MAX_UPDATES, "evalEveryUpdates": EVAL_EVERY,
           "base": args.base,
           "counts": {"originalTrainUnits": len(train), "newUnits": len(new),
                      "devUnits": len(dev)},
           "targetTokens": {
               "originalPerEpoch": sum(len(tok(u["target"], truncation=False).input_ids)
                                       for u in train),
               "newPerEpoch": sum(len(tok(u["target"], truncation=False).input_ids)
                                  for u in new)},
           "history": []}

    def eval_dev():
        model.eval()
        total, n = 0.0, 0
        with torch.inference_mode():
            for i in range(0, len(dev), BATCH):
                batch = dev[i:i + BATCH]
                enc, labels = encode_training_batch(tok, batch)
                enc = {k: v.to(device) for k, v in enc.items()}
                out = model(**enc, labels=labels.input_ids.to(device))
                total += float(out.loss) * len(batch)
                n += len(batch)
        model.train()
        return round(total / max(n, 1), 4)

    model.train()
    t0 = time.perf_counter()
    best = None
    order_o, order_n = list(range(len(train))), list(range(len(new)))
    io = inn = 0
    for step in range(1, MAX_UPDATES + 1):
        if io + BATCH // 2 > len(order_o):
            random.shuffle(order_o)
            io = 0
        if inn + N_NEW_PER_BATCH > len(order_n):
            random.shuffle(order_n)
            inn = 0
        batch = [train[j] for j in order_o[io:io + BATCH // 2]]
        io += BATCH // 2
        batch += [new[j] for j in order_n[inn:inn + N_NEW_PER_BATCH]]
        inn += N_NEW_PER_BATCH
        enc, labels = encode_training_batch(tok, batch)
        enc = {k: v.to(device) for k, v in enc.items()}
        lab = labels.input_ids.to(device)
        try:
            out = model(**enc, labels=lab)
        except torch.cuda.OutOfMemoryError as exc:
            rethrow_oom(exc, enc, lab)
        opt.zero_grad()
        out.loss.backward()
        opt.step()
        if step % EVAL_EVERY == 0 or step == MAX_UPDATES:
            d = eval_dev()
            rep["history"].append({"step": step, "devLoss": d})
            print(f"step {step} dev {d}", flush=True)
            if best is None or d < best["devLoss"]:
                best = {"step": step, "devLoss": d,
                        "state": {k: v.detach().clone()
                                  for k, v in model.state_dict().items()}}
    rep["train"] = {"updates": MAX_UPDATES,
                    "wallSeconds": round(time.perf_counter() - t0, 1),
                    "peakAllocatedGB": round(torch.cuda.max_memory_allocated() / 1024 ** 3, 3)
                    if torch.cuda.is_available() else None}
    if best:
        model.load_state_dict(best["state"])
        rep["selectedCheckpoint"] = {"step": best["step"], "devLoss": best["devLoss"]}
    if args.ckpt:
        model.save_pretrained(args.ckpt)
        tok.save_pretrained(args.ckpt)
        rep["savedCheckpoint"] = args.ckpt
    model.eval()

    def run_units(units, budget):
        started = time.perf_counter()
        out, complete = [], True
        for u in units:
            left = budget - (time.perf_counter() - started)
            if left <= 0:
                complete = False
                break
            enc = tok(u["input"], return_tensors="pt", truncation=False).to(device)
            ids, meta = generate_greedy(model, enc, left)
            out.append({"unitId": u.get("unitId"), "text":
                        tok.decode(ids[0], skip_special_tokens=True),
                        "stopReason": meta["stopReason"], "complete": meta["complete"]})
            complete = complete and meta["complete"]
        return out, complete, round(time.perf_counter() - started, 3)

    conf = rows(args.confirm)
    rep["confirm"] = run_units(conf, args.budget)[0]
    mat = json.loads(pathlib.Path(args.cf24).read_text(encoding="utf-8"))
    cf_rows = []
    for s in mat["sources"]:
        units = [{"unitId": f'{s["id"]}:{f["factId"]}', "input": s["unitInputs"][f["factId"]]}
                 for f in s["facts"]]
        outs, complete, secs = run_units(units, args.budget)
        cf_rows.append({"sourceId": s["id"], "complete": complete, "seconds": secs,
                        "output": "".join(o["text"] for o in outs),
                        "units": outs})
        print(f'cf24 {s["id"]} {secs}s', flush=True)
    rep["cf24"] = cf_rows
    rep["summary"] = {
        "confirmComplete": sum(1 for r in rep["confirm"] if r["complete"]),
        "confirmUnits": len(rep["confirm"]),
        "cf24Complete": sum(1 for r in cf_rows if r["complete"]),
        "cf24Sources": len(cf_rows),
        "cf24Latency": round(sum(r["seconds"] for r in cf_rows), 2)}
    pathlib.Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(json.dumps(rep["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
