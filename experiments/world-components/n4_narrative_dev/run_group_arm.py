"""Train and evaluate the human-plan group arm.

One exposure = one pass over that source's groups, so a source is seen once per
epoch exactly as in the other two arms. Generation uses one 20 s budget per
source: the group calls share it, and any unfinished group makes the source
incomplete.
"""
import argparse, json, pathlib, random, sys, time
from collections import defaultdict

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sequence_policy import encode_training_batch, generate_greedy, rethrow_oom

SEED = 20261102
BATCH = 8
LR = 3e-4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--budget", type=float, default=20.0)
    ap.add_argument("--save-ckpt", default=None)
    args = ap.parse_args()

    plan = json.loads(pathlib.Path(args.plan).read_text(encoding="utf-8"))
    units = plan["units"]
    by_source = defaultdict(list)
    for u in units:
        by_source[u["sourceId"]].append(u)
    for s in by_source.values():
        s.sort(key=lambda u: u["groupId"])

    train = [u for u in units if u["split"] == "formal-train"]
    dev = [u for u in units if u["split"] == "formal-dev"]
    test_sources = sorted({u["sourceId"] for u in units if u["split"] == "formal-holdout"})

    tok = T5Tokenizer.from_pretrained(args.base, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(args.base,
                                                       torch_dtype=torch.float32)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    torch.manual_seed(SEED)
    random.seed(SEED)
    opt = torch.optim.AdamW(model.parameters(), lr=LR)

    report = {"experiment": "人工计划条件下的句组臂", "seed": SEED, "batch": BATCH,
              "lr": LR, "epochs": args.epochs, "base": args.base,
              "budgetSecondsPerSource": args.budget,
              "counts": {"sources": len(by_source), "units": len(units),
                         "trainUnits": len(train), "devUnits": len(dev),
                         "testSources": len(test_sources),
                         "targetTokensPerEpoch": sum(
                             len(tok(u["target"], truncation=False).input_ids)
                             for u in train)},
              "history": []}

    def eval_loss(rows):
        model.eval()
        total, n = 0.0, 0
        with torch.inference_mode():
            for i in range(0, len(rows), BATCH):
                batch = rows[i:i + BATCH]
                enc, labels = encode_training_batch(tok, batch)
                enc = {k: v.to(device) for k, v in enc.items()}
                out = model(**enc, labels=labels.input_ids.to(device))
                total += float(out.loss) * len(batch)
                n += len(batch)
        model.train()
        return round(total / max(n, 1), 4)

    model.train()
    t0, steps, best = time.perf_counter(), 0, None
    for epoch in range(1, args.epochs + 1):
        order = list(range(len(train)))
        random.shuffle(order)
        for i in range(0, len(order), BATCH):
            batch = [train[j] for j in order[i:i + BATCH]]
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
            steps += 1
        if epoch % 10 == 0 or epoch == args.epochs:
            d = eval_loss(dev)
            report["history"].append({"epoch": epoch, "devLoss": d})
            print(f"epoch {epoch} step {steps} dev {d}", flush=True)
            if best is None or d < best["devLoss"]:
                best = {"epoch": epoch, "devLoss": d,
                        "state": {k: v.detach().clone()
                                  for k, v in model.state_dict().items()}}
    report["train"] = {"optimizerSteps": steps,
                       "wallSeconds": round(time.perf_counter() - t0, 1),
                       "peakAllocatedGB": round(torch.cuda.max_memory_allocated() / 1024 ** 3, 3)
                       if torch.cuda.is_available() else None}
    if best:
        model.load_state_dict(best["state"])
        report["selectedCheckpoint"] = {"epoch": best["epoch"],
                                        "devLoss": best["devLoss"]}
    if args.save_ckpt:
        model.save_pretrained(args.save_ckpt)
        tok.save_pretrained(args.save_ckpt)
        report["savedCheckpoint"] = args.save_ckpt
    model.eval()

    def compose(rows):
        started = time.perf_counter()
        parts, calls, complete = [], [], True
        for u in rows:
            left = args.budget - (time.perf_counter() - started)
            if left <= 0:
                calls.append({"groupId": u["groupId"], "stopReason": "budget-exhausted",
                              "complete": False, "newTokens": 0, "seconds": 0})
                complete = False
                continue
            enc = tok(u["input"], return_tensors="pt", truncation=False).to(device)
            t = time.perf_counter()
            ids, meta = generate_greedy(model, enc, left)
            calls.append(dict(meta, groupId=u["groupId"],
                              factIds=u["factIds"],
                              text=tok.decode(ids[0], skip_special_tokens=True),
                              seconds=round(time.perf_counter() - t, 3)))
            parts.append(tok.decode(ids[0], skip_special_tokens=True))
            complete = complete and meta["complete"]
        return {"text": "".join(parts), "calls": calls, "complete": complete,
                "seconds": round(time.perf_counter() - started, 3)}

    report["test"] = []
    for sid in test_sources:
        g = compose(by_source[sid])
        report["test"].append({"sourceId": sid, "complete": g["complete"],
                               "seconds": g["seconds"], "output": g["text"],
                               "calls": [{k: c.get(k) for k in
                                          ("groupId", "factIds", "stopReason",
                                           "complete", "newTokens", "seconds", "text")}
                                         for c in g["calls"]]})
        print(f"test {sid} complete={g['complete']} {g['seconds']}s", flush=True)

    cf = defaultdict(list)
    for u in plan["cf24Groups"]:
        cf[u["sourceId"]].append(u)
    report["cf24"] = []
    for sid in sorted(cf):
        g = compose(cf[sid])
        report["cf24"].append({"sourceId": sid, "complete": g["complete"],
                               "seconds": g["seconds"], "output": g["text"],
                               "calls": [{k: c.get(k) for k in
                                          ("groupId", "factIds", "stopReason",
                                           "complete", "newTokens", "seconds", "text")}
                                         for c in g["calls"]]})
        print(f"cf24 {sid} complete={g['complete']} {g['seconds']}s", flush=True)

    report["summary"] = {
        "testComplete": sum(1 for r in report["test"] if r["complete"]),
        "testSources": len(report["test"]),
        "testLatencySeconds": round(sum(r["seconds"] for r in report["test"]), 3),
        "cf24Complete": sum(1 for r in report["cf24"] if r["complete"]),
        "cf24Sources": len(report["cf24"]),
        "cf24LatencySeconds": round(sum(r["seconds"] for r in report["cf24"]), 3),
    }
    pathlib.Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
