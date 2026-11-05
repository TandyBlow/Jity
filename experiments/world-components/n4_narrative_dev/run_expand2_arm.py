"""Round-2 expansion arm: 4 original + 2 expand80 + 2 object units per batch.

2880 updates, original dev for checkpoint selection, fixed evaluation cadence.
Evaluates on the object confirmation set, the round-1 confirmation set and cf24 v2.
"""
import argparse
import json
import pathlib
import random
import sys
import time

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sequence_policy import encode_training_batch, generate_greedy, rethrow_oom

SEED = 20261102
LR = 3e-4
BATCH = 8
MIX = (4, 2, 2)          # original, expand80, object
MAX_UPDATES = 2880
EVAL_EVERY = 240


def rows(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8")
            .splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--units", required=True)
    ap.add_argument("--expand", required=True)
    ap.add_argument("--objects", required=True)
    ap.add_argument("--confirm-object", required=True)
    ap.add_argument("--confirm40", required=True)
    ap.add_argument("--cf24", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", default=None)
    ap.add_argument("--budget", type=float, default=20.0)
    args = ap.parse_args()

    man = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    src_split = {s["sourceId"]: s["split"] for s in man["sources"]}
    base_units = rows(args.units)
    orig = [u for u in base_units if src_split.get(u["sourceId"]) == "formal-train"]
    dev = [u for u in base_units if src_split.get(u["sourceId"]) == "formal-dev"]
    expand = rows(args.expand)
    obj = rows(args.objects)

    tok = T5Tokenizer.from_pretrained(args.base, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(args.base,
                                                       torch_dtype=torch.float32)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    torch.manual_seed(SEED)
    random.seed(SEED)
    opt = torch.optim.AdamW(model.parameters(), lr=LR)

    rep = {"arm": "expand_obj", "seed": SEED, "lr": LR, "batch": BATCH,
           "mixPerBatch": {"original": MIX[0], "expand80": MIX[1], "object": MIX[2]},
           "maxUpdates": MAX_UPDATES, "evalEveryUpdates": EVAL_EVERY,
           "base": args.base,
           "counts": {"original": len(orig), "expand80": len(expand),
                      "object": len(obj), "dev": len(dev)},
           "history": []}

    def eval_dev():
        model.eval()
        tot, n = 0.0, 0
        with torch.inference_mode():
            for i in range(0, len(dev), BATCH):
                b = dev[i:i + BATCH]
                enc, labels = encode_training_batch(tok, b)
                enc = {k: v.to(device) for k, v in enc.items()}
                out = model(**enc, labels=labels.input_ids.to(device))
                tot += float(out.loss) * len(b)
                n += len(b)
        model.train()
        return round(tot / max(n, 1), 4)

    model.train()
    t0 = time.perf_counter()
    best = None
    pools = [list(range(len(orig))), list(range(len(expand))), list(range(len(obj)))]
    cursors = [0, 0, 0]
    data = [orig, expand, obj]
    for step in range(1, MAX_UPDATES + 1):
        batch = []
        for pi, take in enumerate(MIX):
            if cursors[pi] + take > len(pools[pi]):
                random.shuffle(pools[pi])
                cursors[pi] = 0
            batch += [data[pi][j] for j in pools[pi][cursors[pi]:cursors[pi] + take]]
            cursors[pi] += take
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
            out.append({"unitId": u["unitId"],
                        "text": tok.decode(ids[0], skip_special_tokens=True),
                        "stopReason": meta["stopReason"], "complete": meta["complete"]})
            complete = complete and meta["complete"]
        return out, complete

    rep["confirmObject"] = run_units(rows(args.confirm_object), args.budget)[0]
    rep["confirm40"] = run_units(rows(args.confirm40), args.budget)[0]
    mat = json.loads(pathlib.Path(args.cf24).read_text(encoding="utf-8"))
    cf = []
    for s in mat["sources"]:
        units = [{"unitId": f'{s["id"]}:{f["factId"]}',
                  "input": s["unitInputs"][f["factId"]]} for f in s["facts"]]
        outs, complete = run_units(units, args.budget)
        cf.append({"sourceId": s["id"], "complete": complete,
                   "output": "".join(o["text"] for o in outs), "units": outs})
        print(f'cf24 {s["id"]}', flush=True)
    rep["cf24"] = cf
    rep["summary"] = {"cf24Complete": sum(1 for r in cf if r["complete"]),
                      "cf24Sources": len(cf)}
    pathlib.Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(json.dumps(rep["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
