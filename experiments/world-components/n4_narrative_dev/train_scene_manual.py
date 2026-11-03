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
CORPUS = HERE / "scene_manual_v2.jsonl"
HOLDOUT = ["瓦檐", "石碑", "铁锁", "布幌", "芦苇", "冰锥", "草垛", "木桶",
           "石径", "旧布", "草绳", "霜凌"]
COLD = ["雪", "霜", "冰", "冻", "寒"]
MAX_IN, MAX_OUT = 224, 48

# What the thing actually is. N4.0 can supply this from item/location data;
# without it the model can only swap nouns into known sentence skeletons.
DESC = {
    "石阶": "一级一级的石制台阶", "石墙": "石块垒成的墙",
    "石板": "铺地的平整石块", "石桥": "跨溪的石拱桥",
    "门槛": "门下横着的木条或石条", "木门": "木板拼成的门",
    "门板": "门上可拆卸的木板", "木梯": "木制的梯子",
    "木栏": "木制的栏杆", "窗框": "固定窗纸的木框",
    "木凳": "木制的坐凳", "铁链": "一环扣一环的铁链",
    "铜铃": "铜制的小铃", "灯罩": "罩住灯火的罩子",
    "铜壶": "烧水用的铜壶", "麻绳": "麻纤维绞成的绳",
    "草帘": "草茎编成的帘子", "帆布": "厚布做的篷布",
    "窗纸": "糊窗的薄纸", "冰面": "结冰的水面",
    "水洼": "积在低处的水", "溪水": "溪里流动的水",
    "枯草": "干枯的草", "树枝": "树的枝条",
    "苔藓": "贴地生长的绿苔", "炭火": "烧红的炭",
    "油灯": "烧油的灯", "纸灯笼": "纸糊的灯笼",
    "雪粒": "细小的雪", "雾气": "悬浮在空中的小水珠",
    "浪头": "涌起的波浪",
    "瓦檐": "屋檐最外一溜瓦", "石碑": "路边刻字的石头",
    "铁锁": "挂在门上的铁锁", "布幌": "铺面外挂的布招牌",
    "芦苇": "水边空心的髙草", "冰锥": "檐下结的尖冰",
    "草垛": "堆起来的干草", "木桶": "箍着铁圈的木容器",
}


def load():
    return [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def build_input(noun, loc, scene):
    parts = [
        "场景短句。",
        "地点=" + loc,
        "场景=" + scene,
        "现象=" + noun,
        "现象说明=" + DESC[noun],
        "要求：围绕现象写一到两句环境描写；只写这个地点、天气和光线下"
        "看得见的东西；不写人物动作、任务、数值、时长；"
        "不新增人物、物品、地点。",
        "短句：",
    ]
    return chr(10).join(parts) + chr(10)


def norm(t):
    return t.replace("，", ",").replace("；", ";").strip("。")


def grams4(t):
    return {t[i:i + 4] for i in range(max(0, len(t) - 3))}


def foreign_overlap(text, own_noun, by_noun):
    """Largest 4-gram overlap with any sentence of a DIFFERENT noun.
    High values mean the model borrowed another object's wording."""
    g = grams4(text)
    if not g:
        return 0.0
    best = 0.0
    for other, targets in by_noun.items():
        if other == own_noun:
            continue
        for t in targets:
            ov = len(g & grams4(t)) / len(g)
            best = max(best, ov)
    return best


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

    by_noun = {}
    for r in train:
        by_noun.setdefault(r["noun"], []).append(r["target"])

    def report(rows_, label):
        outs = gen(rows_)
        named = sum(1 for r, t in zip(rows_, outs) if r["noun"] in t)
        verb = sum(1 for r, t in zip(rows_, outs)
                   if norm(t) in {norm(x["target"]) for x in train})
        viol = sum(1 for r, t in zip(rows_, outs)
                   if cold_violation(r["scene"], t))
        foreign = [foreign_overlap(t, r["noun"], by_noun)
                   for r, t in zip(rows_, outs)]
        f_mean = round(sum(foreign) / max(1, len(foreign)), 3)
        f_bad = sum(1 for x in foreign if x >= 0.5)
        print(f"{label}: named {named}/{len(rows_)} verbatim {verb} "
              f"condition-violation {viol} foreign4 {f_mean} "
              f"(>=0.5: {f_bad})", flush=True)
        for r, t in zip(rows_, outs):
            print(f"  {r['noun']:5s} [{r['scene']:16s}] {t}", flush=True)
        return {"rows": len(rows_), "named": named, "verbatim": verb,
                "conditionViolation": viol, "foreign4Mean": f_mean,
                "foreign4Bad": f_bad,
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
