# Train the scene-sentence model on the generated corpus and evaluate
# composition: unseen nouns (new props) and an unseen frame.
#
# Metrics:
#   named    the sentence names the given phenomenon (noun or its head)
#   checker  a second person wrote it; the LLM's own rules forbid
#   verbatim output equals some training target (memorisation, 0 is good)
#   novel4   share of 4-grams absent from all training targets (higher = more
#            composition, though novelty alone is not quality)
#
# Run: python train_scene_gen.py --epochs 30 --base base/randeng-t5-77m

import argparse
import json
import pathlib
import random
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

TRAIN = HERE / "scenegen_pairs.jsonl"
DEV = HERE / "scenegen_dev.jsonl"
HN = HERE / "scenegen_holdout_noun.jsonl"
HF = HERE / "scenegen_holdout_frame.jsonl"
MAX_IN, MAX_OUT = 192, 48
HEAD = {"屋檐冰凌": "冰凌"}


def load(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def norm(t):
    return (t.replace("，", ",").replace("；", ";").replace("：", ":")
             .replace("？", "?").replace("！", "!"))


def named(noun, text):
    return noun in text or HEAD.get(noun, noun) in text


def grams4(texts):
    out = set()
    for t in texts:
        out |= {t[i:i + 4] for i in range(max(0, len(t) - 3))}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--base", default="base/randeng-t5-77m")
    ap.add_argument("--out", default="ckpt-scenegen")
    args = ap.parse_args()

    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    train, dev, hn, hf = load(TRAIN), load(DEV), load(HN), load(HF)
    print(f"train {len(train)} dev {len(dev)} "
          f"holdout_noun {len(hn)} holdout_frame {len(hf)}")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = T5Tokenizer.from_pretrained(args.base, legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        args.base, torch_dtype=torch.float32).to(device)
    torch.manual_seed(20261105)
    random.seed(20261105)
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
            print(f"epoch {epoch} loss {total / ((len(order) + BATCH - 1) // BATCH):.4f}",
                  flush=True)
    pathlib.Path(args.out).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out)
    tok.save_pretrained(args.out)
    model.eval()

    train_targets = {norm(r["target"]) for r in train}
    train4 = grams4([r["target"] for r in train])

    def evaluate(rows, label):
        outs = []
        for r in rows:
            enc = tok(r["input"], return_tensors="pt", truncation=True,
                      max_length=MAX_IN).to(device)
            with torch.no_grad():
                g = model.generate(**enc, max_new_tokens=MAX_OUT,
                                   num_beams=1, do_sample=False)
            outs.append(tok.decode(g[0], skip_special_tokens=True))
        named_n = sum(1 for r, t in zip(rows, outs) if named(r["noun"], t))
        verbatim = sum(1 for t in outs if norm(t) in train_targets)
        novel = []
        for t in outs:
            g = {t[i:i + 4] for i in range(max(0, len(t) - 3))}
            novel.append(1 - (len(g & train4) / max(1, len(g))))
        res = {"rows": len(rows), "named": named_n, "verbatim": verbatim,
               "novel4": round(sum(novel) / max(1, len(novel)), 3)}
        print(f"{label}: {res}", flush=True)
        for r, t in list(zip(rows, outs))[:12]:
            print(f"  {r['noun']:6s} [{r['frame']}] -> {t}", flush=True)
        return res, outs

    out = {"device": torch.cuda.get_device_name(0) if device == "cuda"
           else device, "epochs": args.epochs}
    for label, rows in (("dev", dev), ("holdout_noun", hn),
                        ("holdout_frame", hf)):
        res, outs = evaluate(rows, label)
        out[label] = res
        out[label + "_samples"] = [
            {"noun": r["noun"], "frame": r["frame"], "target": r["target"],
             "output": t} for r, t in zip(rows, outs)]
    pathlib.Path("scenegen-report.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
