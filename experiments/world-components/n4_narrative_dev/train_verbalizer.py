# Train and evaluate the N4 fact verbalizer (one fact -> one bound sentence).
#
# Same-world dev pairs are held out from the 229-pair training set; the
# 23 new-world pairs are zero-shot. Strict binding is checked: the fact
# subject must appear, the result/destination must be covered, and no other
# named person or place may appear.
#
# Usage: python train_verbalizer.py --epochs 150
# Output: ckpt-verbalizer/ + verbalizer-report.json

import argparse
import json
import pathlib
import random
import re
import sys
import time

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

from sequence_policy import (DEFAULT_GENERATION_TIMEOUT, encode_training_batch,
                             rethrow_oom,
                             generate_greedy, generation_timeout, sequence_policy)

HERE = pathlib.Path(__file__).resolve().parent
TRAIN = HERE / "verbalizer_pairs.jsonl"
HOLDOUT = HERE / "verbalizer_holdout.jsonl"
BASE = pathlib.Path("base/randeng-t5-77m")
SEED = 20261103
BATCH = 8
LR = 1e-4
DEV_EVERY = 7

PEOPLE, PLACES = set(), set()
# furniture owned by exactly one top-level location; used to catch leakage
# such as 钟架/木桩 appearing at 云关驿.
LOC_FURNITURE = {}
ELEVATION = {"望雪台": 3, "风口岭": 2, "云关驿": 1, "雪溪": 1}
for w in ("world.json", "holdout_world.json"):
    world = json.loads((HERE / w).read_text(encoding="utf-8"))
    for ch in world["characters"].values():
        PEOPLE.add(ch["name"])
    for root_id, loc in world["locations"].items():
        props = set(loc.get("features", []))
        for sub in loc.get("sublocations", []):
            props.add(sub["name"])
            props.update(sub.get("features", []))
        for it in world["items"].values():
            cont = it.get("position", {}).get("containerId", "")
            if cont == root_id or any(
                    s["id"] == cont for s in loc.get("sublocations", [])):
                props.add(it["name"])
        LOC_FURNITURE[loc["name"]] = props
        PLACES.add(loc["name"])
EXCLUSIVE = {}
for name, props in LOC_FURNITURE.items():
    for p_ in props:
        owners = [n for n, q in LOC_FURNITURE.items() if p_ in q]
        if owners == [name]:
            EXCLUSIVE[p_] = name

NUM = re.compile(r"[0-9０-９]+(分钟|小时|秒|点|刻|步)"
                 r"|[一二三四五六七八九十百千]+(分钟|小时|刻钟)")


def norm_punct(t):
    return (t.replace("，", ",").replace("；", ";")
             .replace("：", ":").replace("？", "?").replace("！", "!"))


def core_hit(text, phrase):
    chars = [c for c in phrase if "\u4e00" <= c <= "\u9fff"]
    if not chars:
        return 1.0
    return sum(1 for c in chars if c in text) / len(chars)


def place_hit(text, place):
    return place in text or (len(place) >= 2 and place[-2:] in text)


def check(row, text):
    kind, sig = row["kind"], row["signature"]
    pov = re.search(r"视角=([^；]+)", row["input"]).group(1)
    loc = row["input"].split("地点=")[1].splitlines()[0]
    scene = row["input"].split("场景=")[1].splitlines()[0]
    reasons = []
    ok_action = True
    if kind == "no_change":
        ok_action = any(k in text for k in
                        ("没有", "什么", "再发生", "安静", "没有别的"))
        if not ok_action:
            reasons.append("no-no-change-wording")
    else:
        name = sig[1]
        if name not in text:
            reasons.append("missing-subject")
        if kind == "moved":
            ok_action = place_hit(text, sig[3])
            if not ok_action:
                reasons.append("missing-destination")
            a, b = ELEVATION.get(sig[2]), ELEVATION.get(sig[3])
            if a is not None and b is not None and a != b:
                if b > a and any(k in text for k in ("下来", "下去", "下到")):
                    reasons.append("wrong-direction-down")
                if b < a and any(k in text for k in ("上来", "上去", "上到", "爬上")):
                    reasons.append("wrong-direction-up")
        elif kind == "outcome":
            ok_action = core_hit(text, sig[2]) >= 0.5
            if not ok_action:
                reasons.append("weak-result")
        elif kind in ("appearance_changed", "personality_changed"):
            ok_action = core_hit(text, sig[2]) >= 0.4
            if not ok_action:
                reasons.append("weak-text")
        else:
            ok_action = any(k in text for k in
                            ("呼吸", "胸口", "手指", "心跳", "气"))
            if not ok_action:
                reasons.append("no-bodily-signal")
    for p_ in PEOPLE:
        if p_ in text and p_ not in (sig[1] if kind != "no_change" else "", pov):
            reasons.append(f"extra-person:{p_}")
    for p_ in PLACES:
        if p_ in text and not place_hit(row["input"], p_):
            reasons.append(f"extra-place:{p_}")
    if kind != "no_change":
        for prop, owner in EXCLUSIVE.items():
            if prop in text and owner != loc:
                reasons.append(f"foreign-prop:{prop}@{owner}")
    if "雪" in scene and any(k in text for k in ("雨声", "雨水", "雨丝")):
        reasons.append("weather-mismatch-rain")
    if "雨" in scene and any(k in text for k in ("雪粒", "雪花")):
        reasons.append("weather-mismatch-snow")
    grams = [text[i:i + 4] for i in range(max(0, len(text) - 3))]
    if grams and max(grams.count(g) for g in set(grams)) >= 3:
        reasons.append("repetition")
    if NUM.search(text):
        reasons.append("has-duration")
    return {"binding": not reasons, "reasons": reasons,
            "actionHit": bool(ok_action)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--eval-every", type=int, default=25)
    ap.add_argument("--base", default=str(BASE))
    ap.add_argument("--out", default="ckpt-verbalizer")
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--ckpt", default="ckpt-verbalizer")
    ap.add_argument("--generation-timeout", type=generation_timeout,
                    default=DEFAULT_GENERATION_TIMEOUT)
    args = ap.parse_args()

    rows = [json.loads(l) for l in TRAIN.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    dev = [r for i, r in enumerate(rows) if i % DEV_EVERY == 0]
    train = [r for i, r in enumerate(rows) if i % DEV_EVERY != 0]
    hold = [json.loads(l) for l in
            HOLDOUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"train {len(train)} dev {len(dev)} holdout {len(hold)}")

    if args.eval_only:
        tok = T5Tokenizer.from_pretrained(args.ckpt, legacy=False)
        model = T5ForConditionalGeneration.from_pretrained(
            args.ckpt, torch_dtype=torch.float32)
    else:
        tok = T5Tokenizer.from_pretrained(args.base, legacy=False)
        model = T5ForConditionalGeneration.from_pretrained(
            args.base, torch_dtype=torch.float32)
    assert torch.cuda.is_available(), "expects the HPC GPU"
    device = "cuda"
    model.to(device)
    torch.manual_seed(SEED)
    random.seed(SEED)

    def encode(batch):
        return encode_training_batch(tok, batch)

    def split_loss(batch):
        enc, lab = encode(batch)
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            out = model(**enc, labels=lab.input_ids.to(device))
        return round(float(out.loss), 4)

    def generate(batch):
        outs = []
        for r in batch:
            enc = tok(r["input"], return_tensors="pt", truncation=False).to(device)
            gen, completion = generate_greedy(model, enc, args.generation_timeout)
            outs.append((tok.decode(gen[0], skip_special_tokens=True), completion))
        return outs

    def scored_sample(row, generated):
        text, completion = generated
        result = check(row, text)
        if not completion["complete"]:
            result["binding"] = False
            result["actionHit"] = False
            result["reasons"].append("generation-incomplete")
        return dict(pairId=row["pairId"], kind=row["kind"],
                    signature=row["signature"], output=text, target=row["target"],
                    generation=completion,
                    exactNormalized=completion["complete"] and
                    norm_punct(text) == norm_punct(row["target"]), **result)

    if args.eval_only:
        model.eval()
        dev_samples = generate(dev)
        train_samples = generate(train)
        hold_samples = generate(hold)
        res = {}
        for label, batch, texts in (("train", train, train_samples),
                                    ("dev", dev, dev_samples),
                                    ("newWorld", hold, hold_samples)):
            samples = [scored_sample(r, generated)
                       for r, generated in zip(batch, texts)]
            res[label] = samples
            print(f"{label}: binding {sum(x['binding'] for x in samples)}"
                  f"/{len(samples)}", flush=True)
            for x in samples:
                if not x["binding"]:
                    print("  BAD", x["pairId"], x["reasons"], "|", x["output"],
                          flush=True)
        out = {
            "purpose": "N4 fact verbalizer eval-only",
            "ckpt": args.ckpt,
            "sequencePolicy": sequence_policy(args.generation_timeout),
            "results": {k: {"rows": len(v),
                            "binding": sum(x["binding"] for x in v),
                            "actionHit": sum(x["actionHit"] for x in v),
                            "exactNormalized": sum(x["exactNormalized"] for x in v)}
                        for k, v in res.items()},
            "samples": res,
        }
        pathlib.Path("verbalizer-report.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1)
            + chr(10),
            encoding="utf-8")
        print("results:", json.dumps(out["results"], ensure_ascii=False))
        return 0

    opt = torch.optim.AdamW(model.parameters(), lr=LR)
    order = list(range(len(train)))
    total = ((len(train) + BATCH - 1) // BATCH) * args.epochs
    step, t0 = 0, time.perf_counter()
    history = []
    model.train()
    for epoch in range(1, args.epochs + 1):
        random.shuffle(order)
        for s in range(0, len(order), BATCH):
            batch = [train[i] for i in order[s:s + BATCH]]
            enc, lab = encode(batch)
            enc = {k: v.to(device) for k, v in enc.items()}
            try:
                out = model(**enc, labels=lab.input_ids.to(device))
            except torch.cuda.OutOfMemoryError as exc:
                rethrow_oom(exc, enc, lab.input_ids)
            opt.zero_grad()
            out.loss.backward()
            opt.step()
            step += 1
        if epoch % args.eval_every == 0 or epoch == args.epochs:
            dv = split_loss(dev)
            history.append({"epoch": epoch, "devLoss": dv})
            print(f"epoch {epoch} step {step}/{total} dev {dv:.4f}", flush=True)
    wall = round(time.perf_counter() - t0, 1)
    out_dir = pathlib.Path(args.out)
    model.save_pretrained(str(out_dir))
    tok.save_pretrained(str(out_dir))

    model.eval()

    def evaluate(batch, label):
        texts = generate(batch)
        samples = []
        for r, generated in zip(batch, texts):
            samples.append(scored_sample(r, generated))
        print(f"{label}: binding {sum(s['binding'] for s in samples)}"
              f"/{len(samples)}", flush=True)
        return samples

    dev_samples = evaluate(dev, "dev")
    train_samples = evaluate(train, "train")
    hold_samples = evaluate(hold, "new-world")

    def summary(samples):
        return {
            "rows": len(samples),
            "binding": sum(s["binding"] for s in samples),
            "actionHit": sum(s["actionHit"] for s in samples),
            "exactNormalized": sum(s["exactNormalized"] for s in samples),
        }

    report = {
        "purpose": "N4 fact verbalizer: one fact -> one bound sentence",
        "data": {"train": len(train), "dev": len(dev),
                 "newWorldHoldout": len(hold)},
        "hyper": {"seed": SEED, "epochs": args.epochs, "batch": BATCH,
                  "lr": LR, "optimizer": "AdamW", "precision": "fp32",
                  "maxInput": None, "maxOutput": None,
                  "sequencePolicy": sequence_policy(args.generation_timeout),
                  "device": torch.cuda.get_device_name(0)},
        "loss": {"train": split_loss(train), "dev": split_loss(dev),
                 "newWorld": split_loss(hold)},
        "results": {
            "train": summary(train_samples),
            "dev": summary(dev_samples),
            "newWorld": summary(hold_samples),
        },
        "history": history,
        "wallSeconds": wall,
        "samples": {"train": train_samples, "dev": dev_samples,
                    "newWorld": hold_samples},
        "notes": [
            "Subject names are required in the output so binding is "
            "checkable; this is a control step, not final prose.",
            "New-world pairs are zero-shot: no shared signature except "
            "no_change.",
        ],
    }
    pathlib.Path("verbalizer-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("loss:", json.dumps(report["loss"], ensure_ascii=False))
    print("results:", json.dumps(report["results"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
