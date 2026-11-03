# Train the generic scene describer on COCO-CN (MIT) and evaluate it on the
# 12 new-world scenes. The model writes weather/light/distance only; the slot
# bank writes the location's own props.
#
# Run: python train_scene_coco.py --epochs 30 --base base/randeng-t5-77m

import argparse
import json
import pathlib
import random
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
TRAIN = HERE / "coco_scene_pairs.jsonl"
DEV = HERE / "coco_scene_dev.jsonl"
HOLDOUT = HERE / "holdout_corpus.jsonl"
MAX_IN, MAX_OUT = 160, 48

BAN = ["人", "男", "女", "孩", "他", "她", "狗", "猫", "鸟", "鱼",
       "车", "飞机", "电脑", "手机", "电视", "床", "沙发", "柜"]
COLD = ["雪", "冰", "霜", "冻"]
RAIN = ["雨"]
FOG = ["雾"]


def load(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def build_input(loc, scene):
    parts = [
        "场景短句。",
        "地点=" + loc,
        "场景=" + scene,
        "要求：写一到两句这个场景里的环境；只写看得见的天光、天气、地面"
        "和远处的东西；不写人物、动物、车辆、室内家具；"
        "不写任务、数值、时长。",
        "短句：",
    ]
    return chr(10).join(parts) + chr(10)


def violation(scene, text):
    reasons = []
    for w in BAN:
        if w in text:
            reasons.append("banned:" + w)
    if any(w in text for w in COLD) and not any(w in scene for w in COLD):
        reasons.append("cold-without-cold-scene")
    if any(w in text for w in RAIN) and "雨" not in scene:
        reasons.append("rain-without-rain-scene")
    if any(w in text for w in FOG) and "雾" not in scene:
        reasons.append("fog-without-fog-scene")
    if not (10 <= len(text) <= 48):
        reasons.append("length")
    return reasons


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--base", default="base/randeng-t5-77m")
    ap.add_argument("--out", default="ckpt-scene-coco")
    args = ap.parse_args()

    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    train, dev = load(TRAIN), load(DEV)
    hold = load(HOLDOUT)
    world = json.loads((HERE / "holdout_world.json").read_text(encoding="utf-8"))
    print(f"train {len(train)} dev {len(dev)} holdout scenes {len(hold)}")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = T5Tokenizer.from_pretrained(args.base, legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        args.base, torch_dtype=torch.float32).to(device)
    torch.manual_seed(20261107)
    random.seed(20261107)
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
        if epoch % 5 == 0 or epoch == args.epochs:
            print(f"epoch {epoch} loss "
                  f"{total / ((len(order) + BATCH - 1) // BATCH):.4f}", flush=True)
    pathlib.Path(args.out).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out)
    tok.save_pretrained(args.out)
    model.eval()

    def gen(prompt):
        enc = tok(prompt, return_tensors="pt", truncation=True,
                  max_length=MAX_IN).to(device)
        with torch.no_grad():
            g = model.generate(**enc, max_new_tokens=MAX_OUT,
                               num_beams=1, do_sample=False)
        return tok.decode(g[0], skip_special_tokens=True)

    samples = []
    for case in hold:
        sc = case["sceneState"]
        scene = "；".join([sc["time"], sc["weather"], sc["wind"], sc["light"]])
        root = case["sceneState"]["locationPath"][0]
        loc = world["locations"][root]["name"]
        prompt = build_input(loc, scene)
        text = gen(prompt)
        samples.append({"id": case["id"], "loc": loc, "scene": scene,
                        "output": text, "reasons": violation(scene, text)})
    ok = sum(1 for s in samples if not s["reasons"])
    unique = len({s["output"] for s in samples})
    print(f"holdout clean {ok}/{len(samples)} unique {unique}", flush=True)
    for s in samples:
        print(f"  {s['id']} [{s['scene']}] -> {s['output']} {s['reasons']}",
              flush=True)
    report = {
        "purpose": "generic scene describer from COCO-CN, evaluated on new world",
        "source": "COCO-CN (MIT), li-xirong/coco-cn",
        "device": torch.cuda.get_device_name(0) if device == "cuda" else device,
        "epochs": args.epochs, "trainRows": len(train),
        "holdout": {"rows": len(samples), "clean": ok, "unique": unique,
                    "samples": samples},
    }
    pathlib.Path("scene-coco-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
