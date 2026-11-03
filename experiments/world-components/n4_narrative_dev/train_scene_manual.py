# Train on the HAND-WRITTEN scene corpus (season/weather varied) and test
# whether the model follows the scene instead of defaulting to snow.
#
# Train: nouns seen in the manual corpus except HOLDOUT (which never appear).
# Eval : holdout nouns, each in four different seasons; the same noun must
#        produce different, season-appropriate sentences.
#
# Violation = output contains snow/ice words while the scene has no snow/ice,
# or the reverse. Run: python train_scene_manual.py --epochs 40

import argparse
import json
import pathlib
import random
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE / "scene_manual.jsonl"
HOLDOUT = ["瓦檐", "石碑", "铁锁", "布幌", "芦苇", "冰锥", "草垛", "木桶",
           "石径", "旧布", "草绳", "霜凌"]
COLD = ["雪", "霜", "冰", "冻", "寒"]
MAX_IN, MAX_OUT = 192, 48


def load():
    return [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def build_input(noun, loc, scene):
    return (
        "场景短句。\n"
        f"地点={loc}\n"
        f"场景={scene}\n"
        f"现象={noun}\n"
        "要求：围绕现象写一到两句环境描写；只写这个季节和天气下看得见的东西；"
        "不写人物动作、任务、数值、时长；不新增人物、物品、地点。\n"
        "短句："
    )


def norm(t):
    return t.replace("，", ",").replace("；", ";").strip("。")


def cold_violation(scene, text):
    scene_cold = any(w in scene for w in COLD)
    text_cold = any(w in text for w in COLD)
    return scene_cold != text_cold


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--base", default="base/randeng-t5-77m")
    ap.add_argument("--out", default="ckpt-scene-manual")
    args = ap.parse_args()

    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    rows = load()
    train = [r for r in rows if r["noun"] not in HOLDOUT]
    hold = [r for r in rows if r["noun"] in HOLDOUT]
    for r in train:
        r["input"] = build_input(r["noun"], r["loc"], r["scene"])
    for r in hold:
        r["input"] = build_input(r["noun"], r["loc"], r["scene"])
    dev = train[::8]
    train = [r for r in train if r not in dev]
    print(f"train {len(train)} dev {len(dev)} holdout {len(hold)} "
          f"(held-out nouns {len({r['noun'] for r in hold})})")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = T5Tokenizer.from_pretrained(args.base, legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        args.base, torch_dtype=torch.float32).to(device)
    torch.manual_seed(20261106)
    random.seed(20261106)
    BATCH, LR = 8, 1e-4

    def encode(batch):
        enc = tok([r["input"] for r in batch], padding=True, truncation=True,
                  max_length=MAX_IN, return_tensors="pt")
        with tok.as_target_tokenizer():
            lab = tok([r["target"] for r in batch], padding=True,
                      truncation=True, max_length=MAX_OUT,
                      return_tensors="pt")
        lab.input_ids[lab.input_ids == tok.pad_token_id] = -100
        return enc, lab

    opt = torch.optim.AdamW(model.parameters(), lr=LR)
    order = list(range(len(train)))
    model.train()
    for epoch in range(1, args.epochs + 1):
        random.shuffle(order)
        tot = 0.0
        for s in range(0, len(order), BATCH):
            batch = [train[i] for i in order[s:s + BATCH]]
            enc, lab = encode(batch)
            enc = {k: v.to(device) for k, v in enc.items()}
            out = model(**enc, labels=lab.input_ids.to(device))
            opt.zero_grad()
            out.loss.backward()
            opt.step()
            tot += float(out.loss)
        if epoch % 10 == 0 or epoch == args.epochs:
            print(f"epoch {epoch} loss {tot / ((len(order) + BATCH - 1) // BATCH):.4f}",
                  flush=True)
    pathlib.Path(args.out).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out)
    tok.save_pretrained(args.out)
    model.eval()

    def gen(rows_):
        outs = []
        for r in rows_:
            enc = tok(r["input"], return_tensors="pt", truncation=True,
                      max_length=MAX_IN).to(device)
            with torch.no_grad():
                g = model.generate(**enc, max_new_tokens=MAX_OUT,
                                   num_beams=1, do_sample=False)
            outs.append(tok.decode(g[0], skip_special_tokens=True))
        return outs

    def report(rows_, label):
        outs = gen(rows_)
        named = sum(1 for r, t in zip(rows_, outs) if r["noun"] in t)
        verb = sum(1 for r, t in zip(rows_, outs)
                   if norm(t) in {norm(x["target"]) for x in train})
        viol = sum(1 for r, t in zip(rows_, outs)
                   if cold_violation(r["scene"], t))
        print(f"{label}: named {named}/{len(rows_)} verbatim {verb} "
              f"season-violation {viol}", flush=True)
        for r, t in zip(rows_, outs):
            print(f"  {r['noun']:5s} [{r['scene']:16s}] {t}", flush=True)
        return {"rows": len(rows_), "named": named, "verbatim": verb,
                "seasonViolation": viol,
                "samples": [{"noun": r["noun"], "loc": r["loc"],
                             "scene": r["scene"], "target": r["target"],
                             "output": t} for r, t in zip(rows_, outs)]}

    out = {"device": torch.cuda.get_device_name(0) if device == "cuda"
           else device, "epochs": args.epochs, "trainRows": len(train)}
    out["dev"] = report(dev, "dev")
    out["holdout"] = report(hold, "holdout(held-out nouns, 4 seasons each)")
    pathlib.Path("scene-manual-report.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
