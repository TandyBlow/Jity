"""Train and evaluate one arm (paragraph or fact) on the shared source set.

One exposure = the source is seen once: the paragraph arm sees its one
paragraph row, the fact arm sees all of that source's fact units. Both arms
therefore run the same number of epochs and see every source the same number of
times; the step counts and token counts differ and are reported separately.

Generation for a source shares one wall-clock budget. In the fact arm every
unit call draws on the same budget; if a required unit cannot finish, the whole
source is incomplete and never counts as a success.
"""
import argparse
import hashlib
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
BATCH = 8
LR = 3e-4
EPOCHS = 120


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def check_freeze(freeze_path, files):
    want = json.loads(pathlib.Path(freeze_path).read_text(encoding="utf-8"))
    bad = []
    for name, path in files.items():
        got = sha(path)
        if want.get(name) != got:
            bad.append(f"{name}: want {want.get(name, '?')[:16]} got {got[:16]}")
    if bad:
        raise SystemExit("freeze mismatch, refusing to start:\n  " + "\n  ".join(bad))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=("paragraph", "fact"), required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--formal", required=True)
    ap.add_argument("--units", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--freeze", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    ap.add_argument("--save-ckpt", default=None,
                    help="save the dev-selected weights here so a later test "
                         "does not have to retrain")
    ap.add_argument("--budget", type=float, default=20.0,
                    help="per-source generation budget in seconds")
    args = ap.parse_args()

    check_freeze(args.freeze, {
        "formal_pairs.jsonl": args.formal,
        "verbalizer_pairs.jsonl": args.units,
        "two-arm-manifest.json": args.manifest,
        "run_arm.py": __file__,
        "sequence_policy.py": HERE / "sequence_policy.py",
    })

    man = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    formal = {r["sourceId"]: r for r in
              (json.loads(l) for l in pathlib.Path(args.formal)
               .read_text(encoding="utf-8").splitlines() if l.strip())}
    units = defaultdict(list)
    for line in pathlib.Path(args.units).read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            units[r["sourceId"]].append(r)

    sources = man["sources"]
    for s in sources:
        units[s["sourceId"]].sort(key=lambda r: s["units"].index(r["factId"]))

    train = [s for s in sources if s["split"] == "formal-train"]
    dev = [s for s in sources if s["split"] == "formal-dev"]
    test = [s for s in sources if s["split"] == "formal-holdout"]

    def unit_rows(s):
        if args.arm == "paragraph":
            return [formal[s["sourceId"]]]
        return [u for u in units[s["sourceId"]]]

    tok = T5Tokenizer.from_pretrained(args.base, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(args.base,
                                                       torch_dtype=torch.float32)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    torch.manual_seed(SEED)
    random.seed(SEED)

    opt = torch.optim.AdamW(model.parameters(), lr=LR)
    train_rows = [r for s in train for r in unit_rows(s)]
    target_tokens_per_epoch = sum(len(tok(r["target"], truncation=False).input_ids)
                                  for r in train_rows)
    report = {
        "arm": args.arm, "seed": SEED, "batch": BATCH, "lr": LR,
        "epochs": args.epochs, "base": args.base,
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "budgetSecondsPerSource": args.budget,
        "counts": {"sources": len(sources), "train": len(train), "dev": len(dev),
                   "test": len(test), "trainUnits": len(train_rows),
                   "targetTokensPerEpoch": target_tokens_per_epoch,
                   "exposuresPerSource": args.epochs},
        "steps": 0, "history": [],
    }

    model.train()
    t0 = time.perf_counter()
    steps = 0
    best = None
    dev_loss = None

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

    dev_rows = [r for s in dev for r in unit_rows(s)]
    for epoch in range(1, args.epochs + 1):
        order = list(range(len(train_rows)))
        random.shuffle(order)
        for i in range(0, len(order), BATCH):
            batch = [train_rows[j] for j in order[i:i + BATCH]]
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
            dev_loss = eval_loss(dev_rows)
            report["history"].append({"epoch": epoch, "devLoss": dev_loss})
            print(f"[{args.arm}] epoch {epoch} step {steps} dev {dev_loss}", flush=True)
            if best is None or dev_loss < best["devLoss"]:
                best = {"epoch": epoch, "devLoss": dev_loss,
                        "state": {k: v.detach().clone()
                                  for k, v in model.state_dict().items()}}
    wall = round(time.perf_counter() - t0, 1)
    report["train"] = {"optimizerSteps": steps, "wallSeconds": wall,
                       "targetTokensTotal": target_tokens_per_epoch * args.epochs,
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

    def generate_source(s):
        rows = unit_rows(s)
        if args.arm == "paragraph":
            enc = tok(rows[0]["input"], return_tensors="pt",
                      truncation=False).to(device)
            t = time.perf_counter()
            ids, meta = generate_greedy(model, enc, args.budget)
            text = tok.decode(ids[0], skip_special_tokens=True)
            return {"text": text, "calls": [meta],
                    "seconds": round(time.perf_counter() - t, 3),
                    "complete": meta["complete"], "stopReasons": [meta["stopReason"]]}
        # fact arm: fixed fact order, one budget shared by all calls
        started = time.perf_counter()
        parts, calls, complete = [], [], True
        for r in rows:
            left = args.budget - (time.perf_counter() - started)
            if left <= 0:
                complete = False
                calls.append({"factId": r["factId"], "stopReason": "budget-exhausted",
                              "complete": False, "newTokens": 0, "seconds": 0})
                continue
            enc = tok(r["input"], return_tensors="pt", truncation=False).to(device)
            t = time.perf_counter()
            ids, meta = generate_greedy(model, enc, left)
            calls.append(dict(meta, factId=r["factId"]))
            parts.append(tok.decode(ids[0], skip_special_tokens=True))
            complete = complete and meta["complete"]
        return {"text": "".join(parts), "calls": calls,
                "seconds": round(time.perf_counter() - started, 3),
                "complete": complete,
                "stopReasons": [c["stopReason"] for c in calls]}

    report["generation"] = {"dev": [], "test": []}
    for split, group in (("dev", dev), ("test", test)):
        for s in group:
            g = generate_source(s)
            report["generation"][split].append({
                "sourceId": s["sourceId"], "complete": g["complete"],
                "seconds": g["seconds"], "stopReasons": g["stopReasons"],
                "output": g["text"],
                "references": ([formal[s["sourceId"]]["target"]]
                               if args.arm == "paragraph"
                               else [u["target"] for u in units[s["sourceId"]]]),
                "calls": [{k: c[k] for k in ("factId", "stopReason", "complete",
                                             "newTokens", "seconds") if k in c}
                          for c in g["calls"]],
            })
            print(f"[{args.arm}] {split} {s['sourceId']} "
                  f"complete={g['complete']} {g['seconds']}s", flush=True)

    def total_latency(split):
        rows = report["generation"][split]
        return round(sum(r["seconds"] for r in rows), 3)

    report["summary"] = {
        "devComplete": sum(r["complete"] for r in report["generation"]["dev"]),
        "devSources": len(report["generation"]["dev"]),
        "testComplete": sum(r["complete"] for r in report["generation"]["test"]),
        "testSources": len(report["generation"]["test"]),
        "devLatencySeconds": total_latency("dev"),
        "testLatencySeconds": total_latency("test"),
    }
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
