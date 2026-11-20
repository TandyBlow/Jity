"""Mix-ratio comparison arms: 4+2+2 vs 4+3+1 over cleaned pools.

Each pool has its own RNG stream, so the four original units drawn at a given
step are exactly the same in both arms. Every draw is logged with unit id,
pool and fact kind, and the effective target tokens are summed.
"""
import argparse
import json
import pathlib
import random
import sys
import time
from collections import Counter, defaultdict

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sequence_policy import encode_training_batch, generate_greedy, rethrow_oom

SEED = 20261102
LR = 3e-4
BATCH = 8
MAX_UPDATES = 2880
EVAL_EVERY = 240


def rows(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8")
            .splitlines() if l.strip()]


def kind_of(u):
    if "kind" in u:
        return u["kind"]
    tag = u["input"].split("事实=")[1].splitlines()[0].split("｜")[0]
    return {"移动": "moved", "结果": "outcome", "外观": "appearance_changed",
            "无变化": "no_change"}.get(tag, tag)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mix", required=True, help="e.g. 4,2,2")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--units", required=True)
    ap.add_argument("--expand", required=True)
    ap.add_argument("--objects", required=True)
    ap.add_argument("--confirm-object", required=True)
    ap.add_argument("--confirm-expand", required=True)
    ap.add_argument("--cf24", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", default=None)
    ap.add_argument("--budget", type=float, default=20.0)
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    mix = tuple(int(x) for x in args.mix.split(","))
    assert sum(mix) == BATCH and len(mix) == 3, "mix must sum to 8"

    man = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    src_split = {s["sourceId"]: s["split"] for s in man["sources"]}
    units = rows(args.units)
    orig = [u for u in units if src_split.get(u["sourceId"]) == "formal-train"]
    dev = [u for u in units if src_split.get(u["sourceId"]) == "formal-dev"]
    expand = rows(args.expand)
    obj = rows(args.objects)
    pools = [orig, expand, obj]

    tok = T5Tokenizer.from_pretrained(args.base, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(args.base,
                                                       torch_dtype=torch.float32)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    torch.manual_seed(SEED)
    opt = torch.optim.AdamW(model.parameters(), lr=LR)

    # 每个池一条独立随机流，orig 池两臂同 seed → 每步的原数据 4 条完全一致
    rngs = [random.Random(SEED + i) for i in range(3)]
    orders = [list(range(len(p))) for p in pools]
    cursors = [0, 0, 0]

    rep = {"arm": "mix_" + args.mix.replace(",", "_"), "mix": mix, "seed": SEED,
           "lr": LR, "batch": BATCH, "maxUpdates": MAX_UPDATES,
           "evalEveryUpdates": EVAL_EVERY, "base": args.base,
           "counts": {"orig": len(orig), "expand": len(expand), "object": len(obj),
                      "dev": len(dev)},
           "history": [], "sampling": {}, "targetTokens": {}}

    draw_log = []
    kind_draws = Counter()
    pool_draws = Counter()
    token_total = 0

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
    for step in range(1, MAX_UPDATES + 1):
        batch = []
        for pi, take in enumerate(mix):
            if take == 0:
                continue
            if cursors[pi] + take > len(orders[pi]):
                rngs[pi].shuffle(orders[pi])
                cursors[pi] = 0
            for j in orders[pi][cursors[pi]:cursors[pi] + take]:
                batch.append(pools[pi][j])
            cursors[pi] += take
        # 与原实现一致：同一批内先原数据、再扩容、再物件
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
        for u, pi in zip(batch, [p for p, t in enumerate(mix) for _ in range(t)]):
            pool_draws[["orig", "expand", "object"][pi]] += 1
            kind_draws[kind_of(u)] += 1
            draw_log.append({"step": step, "pool": ["orig", "expand", "object"][pi],
                             "unitId": u.get("unitId") or u.get("pairId")
                             or u.get("sourceId"), "kind": kind_of(u)})
        token_total += int(labels.input_ids.ne(-100).sum())
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
    rep["sampling"] = {"poolDraws": dict(pool_draws),
                       "kindDraws": dict(kind_draws),
                       "movedDraws": kind_draws["moved"],
                       "movedShare": round(kind_draws["moved"]
                                           / max(sum(kind_draws.values()), 1), 4)}
    rep["targetTokens"] = {"effectiveTotal": token_total,
                           "perUpdate": round(token_total / MAX_UPDATES, 1)}
    if best:
        model.load_state_dict(best["state"])
        rep["selectedCheckpoint"] = {"step": best["step"], "devLoss": best["devLoss"]}
    if args.ckpt:
        model.save_pretrained(args.ckpt)
        tok.save_pretrained(args.ckpt)
        rep["savedCheckpoint"] = args.ckpt
    model.eval()

    def run_units(us, budget):
        started = time.perf_counter()
        out, ok = [], True
        for u in us:
            left = budget - (time.perf_counter() - started)
            if left <= 0:
                ok = False
                break
            enc = tok(u["input"], return_tensors="pt", truncation=False).to(device)
            ids, meta = generate_greedy(model, enc, left)
            out.append({"unitId": u["unitId"],
                        "text": tok.decode(ids[0], skip_special_tokens=True),
                        "complete": meta["complete"]})
            ok = ok and meta["complete"]
        return out, ok

    rep["confirmObject"] = run_units(rows(args.confirm_object), args.budget)[0]
    rep["confirmExpand"] = run_units(rows(args.confirm_expand), args.budget)[0]
    mat = json.loads(pathlib.Path(args.cf24).read_text(encoding="utf-8"))
    cf = []
    for s in mat["sources"]:
        us = [{"unitId": f'{s["id"]}:{f["factId"]}',
               "input": s["unitInputs"][f["factId"]]} for f in s["facts"]]
        outs, ok = run_units(us, args.budget)
        cf.append({"sourceId": s["id"], "complete": ok,
                   "output": "".join(o["text"] for o in outs)})
        print(f"cf24 {s['id']}", flush=True)
    rep["cf24"] = cf
    pathlib.Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    if args.log:
        pathlib.Path(args.log).write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in draw_log) + "\n",
            encoding="utf-8")
    print(json.dumps({"sampling": rep["sampling"], "tokens": rep["targetTokens"],
                      "selected": rep.get("selectedCheckpoint")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
