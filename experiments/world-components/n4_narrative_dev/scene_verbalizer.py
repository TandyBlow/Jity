# Scene verbalizer: N4.0 supplies the phenomenon, the model writes the sentence.
#
# Split rationale: the earlier scene model had to choose *which* phenomenon and
# *how* to phrase it, and produced collocation errors (壶烧得发软). Selection is
# deterministic (N4.0 / slot selector); phrasing is the model's job, exactly as
# the fact verbalizer works (fact given -> 22/23).
#
# Train: 17 phenomena x 5 variants = 85 pairs from the surface bank.
# Eval A: the 6th variant of each phenomenon (unseen surface, seen phenomenon).
# Eval B: the 12 new-world scenes, phenomenon chosen by the slot selector.
#
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/scene_verbalizer.py --mode build
#      python -X utf8 experiments/world-components/n4_narrative_dev/scene_verbalizer.py --mode train

import argparse
import json
import os
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import scene_bank  # noqa: E402

# Local-env workaround (N4_STUB_SKLEARN=1): this machine's pyarrow was built
# against numpy 1.x while numpy 2.2 is installed, so importing sklearn raises
# and transformers.generation cannot load. The stub only satisfies
# transformers' optional candidate-generator import.
if os.environ.get("N4_STUB_SKLEARN") == "1":
    import importlib.machinery
    import types
    for name in ("sklearn", "sklearn.metrics"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        mod.__spec__ = importlib.machinery.ModuleSpec(name, None,
                                                      is_package=True)
        sys.modules.setdefault(name, mod)
    sys.modules["sklearn.metrics"].roc_curve = lambda *a, **k: None

OUT_TRAIN = HERE / "scenevb_pairs.jsonl"
OUT_EVALA = HERE / "scenevb_holdout.jsonl"
OUT_EVALB = HERE / "scenevb_cases.jsonl"

# head word per phenomenon: outputs may drop the modifier (屋檐挂着一排冰凌)
HEAD = {
    "屋檐冰凌": "冰凌", "木门": "门", "炭火": "炭", "石阶": "石阶",
    "石道": "石道", "雪粒": "雪粒", "石堆": "石堆", "经幡": "经幡",
    "旧马棚": "马棚", "石桥": "石桥", "冰面": "冰面", "枯草": "枯草",
    "溪水": "溪水", "石台": "石台", "木梯": "木梯",
    "铜铃架": "铜铃", "铃绳": "铃绳",
}


def names_phenomenon(phenomenon, text):
    return HEAD.get(phenomenon, phenomenon) in text


def build_input(loc_name, scene_line, phenomenon, pov):
    return (
        "场景短句。\n"
        f"地点={loc_name}\n"
        f"场景={scene_line}\n"
        f"现象={phenomenon}\n"
        f"视角={pov}\n"
        "要求：围绕现象写一到两句环境描写；只引用现象与场景给的东西；"
        "不写人物动作、任务、数值、时长；不新增人物、物品、地点。\n"
        "短句："
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["build", "train"], default="build")
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--base", default="base/randeng-t5-77m")
    ap.add_argument("--eval-only", action="store_true")
    args = ap.parse_args()

    world = json.loads((HERE / "holdout_world.json").read_text(encoding="utf-8"))
    loc_of = {}
    for loc in world["locations"].values():
        for p in loc.get("features", []):
            loc_of.setdefault(p, loc["name"])
    # bank phenomena that are features of a location, with that scene frame
    frames = {
        "云关驿": "傍晚；雪，屋檐挂冰凌；低（石墙挡风）；炭火",
        "风口岭": "清晨；雪，横风；高（山口横风）；灰白",
        "雪溪": "清晨；雪，溪面结冰；中（溪谷风）；灰白",
        "望雪台": "黄昏；雪，风；高（台顶直风）；灰白天色",
    }
    pov = world["characters"]["char_lu"]["name"]

    if args.mode == "build":
        train, evala = [], []
        for phen, variants in scene_bank.SURFACE.items():
            loc = loc_of.get(phen)
            if loc is None:
                raise SystemExit(f"phenomenon not a location feature: {phen}")
            for i, text in enumerate(variants):
                row = {"phenomenon": phen, "location": loc, "target": text,
                       "input": build_input(loc, frames[loc], phen, pov)}
                (evala if i == len(variants) - 1 else train).append(row)
        OUT_TRAIN.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in train) + "\n",
            encoding="utf-8", newline="\n")
        OUT_EVALA.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in evala) + "\n",
            encoding="utf-8", newline="\n")

        cases = [json.loads(l) for l in
                 (HERE / "holdout_corpus.jsonl").read_text(
                     encoding="utf-8").splitlines() if l.strip()]
        rows_b = []
        for idx, c in enumerate(cases):
            sc = c["sceneState"]
            root = sc["locationPath"][0]
            loc = world["locations"][root]["name"]
            pool = [p for p in scene_bank.SURFACE
                    if p in world["locations"][root].get("features", [])]
            if not pool:
                continue
            phen = pool[idx % len(pool)]
            scene_line = "；".join([sc["time"], sc["weather"], sc["wind"],
                                   sc["light"]]).strip("；")
            rows_b.append({"id": c["id"], "phenomenon": phen, "location": loc,
                           "input": build_input(loc, scene_line, phen, pov)})
        OUT_EVALB.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows_b) + "\n",
            encoding="utf-8", newline="\n")
        print(f"train {len(train)} evala {len(evala)} cases {len(rows_b)}")
        return 0

    # ---- train ----
    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    train = [json.loads(l) for l in OUT_TRAIN.read_text(
        encoding="utf-8").splitlines() if l.strip()]
    evala = [json.loads(l) for l in OUT_EVALA.read_text(
        encoding="utf-8").splitlines() if l.strip()]
    cases = [json.loads(l) for l in OUT_EVALB.read_text(
        encoding="utf-8").splitlines() if l.strip()]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    base = "ckpt-scenevb" if args.eval_only else args.base
    tok = T5Tokenizer.from_pretrained(base, legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        base, torch_dtype=torch.float32).to(device)
    torch.manual_seed(20261104)
    random.seed(20261104)
    BATCH, LR, MAX_IN, MAX_OUT = 8, 1e-4, 192, 48

    def encode(batch):
        enc = tok([r["input"] for r in batch], padding=True, truncation=True,
                  max_length=MAX_IN, return_tensors="pt")
        with tok.as_target_tokenizer():
            lab = tok([r["target"] for r in batch], padding=True,
                      truncation=True, max_length=MAX_OUT,
                      return_tensors="pt")
        lab.input_ids[lab.input_ids == tok.pad_token_id] = -100
        return enc, lab

    if args.eval_only:
        model.eval()

        def gen_only(rows):
            out = []
            for r in rows:
                enc = tok(r["input"], return_tensors="pt", truncation=True,
                          max_length=MAX_IN).to(device)
                with torch.no_grad():
                    g = model.generate(**enc, max_new_tokens=MAX_OUT,
                                       num_beams=1, do_sample=False)
                out.append(tok.decode(g[0], skip_special_tokens=True))
            return out

        res = {}
        for label, rows in (("evalA", evala), ("evalB", cases)):
            texts = gen_only(rows)
            res[label] = [{"row": r, "output": t,
                           "phenomenonNamed": names_phenomenon(
                               r["phenomenon"], t)}
                          for r, t in zip(rows, texts)]
            ok = sum(1 for x in res[label] if x["phenomenonNamed"])
            print(f"{label}: phenomenon named {ok}/{len(rows)}", flush=True)
            for x in res[label]:
                mark = "OK " if x["phenomenonNamed"] else "MIS"
                print(f"  {mark} {x['row'].get('id', '')} "
                      f"[{x['row']['phenomenon']}] {x['output']}", flush=True)
        pathlib.Path("scenevb-report.json").write_text(
            json.dumps({"mode": "eval-only", "evalA": res["evalA"],
                        "evalB": res["evalB"]}, ensure_ascii=False, indent=1)
            + chr(10), encoding="utf-8")
        return 0

    opt = torch.optim.AdamW(model.parameters(), lr=LR)
    order = list(range(len(train)))
    model.train()
    for epoch in range(1, args.epochs + 1):
        random.shuffle(order)
        total = 0.0
        for s in range(0, len(order), BATCH):
            batch = [train[i] for i in order[s:s + BATCH]]
            enc, lab = encode(batch)
            enc = {k: v.to(device) for k, v in enc.items()}
            out = model(**enc, labels=lab.input_ids.to(device))
            opt.zero_grad()
            out.loss.backward()
            opt.step()
            total += float(out.loss)
        if epoch % 50 == 0 or epoch == args.epochs:
            print(f"epoch {epoch} loss {total / max(1, (len(order) + BATCH - 1) // BATCH):.4f}",
                  flush=True)
    model.save_pretrained("ckpt-scenevb")
    tok.save_pretrained("ckpt-scenevb")
    model.eval()

    def gen(rows):
        outs = []
        for r in rows:
            enc = tok(r["input"], return_tensors="pt", truncation=True,
                      max_length=MAX_IN).to(device)
            with torch.no_grad():
                g = model.generate(**enc, max_new_tokens=MAX_OUT,
                                   num_beams=1, do_sample=False)
            outs.append(tok.decode(g[0], skip_special_tokens=True))
        return outs

    def report(rows, label):
        texts = gen(rows)
        ok = sum(1 for r, t in zip(rows, texts)
                 if names_phenomenon(r["phenomenon"], t))
        print(f"{label}: phenomenon named {ok}/{len(rows)}", flush=True)
        for r, t in zip(rows, texts):
            mark = "OK " if names_phenomenon(r["phenomenon"], t) else "MIS"
            print(f"  {mark} {r.get('id', '')} [{r['phenomenon']}] {t}",
                  flush=True)
        return [{"row": r, "output": t,
                 "phenomenonNamed": names_phenomenon(r["phenomenon"], t)}
                for r, t in zip(rows, texts)]

    a = report(evala, "evalA-unseen-surface")
    b = report(cases, "evalB-new-world-cases")
    pathlib.Path("scenevb-report.json").write_text(
        json.dumps({"device": torch.cuda.get_device_name(0) if device == "cuda"
                    else device, "epochs": args.epochs, "rows": len(train),
                    "evalA": a, "evalB": b}, ensure_ascii=False, indent=1)
        + chr(10), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
