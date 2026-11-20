# Fact verbalizer with n-best filtering/reranking.
#
# Same checkpoint as train_verbalizer.py, but samples 6 candidates per fact
# and picks one that passes the deterministic checks (subject, destination,
# no foreign props outside 地点可见, no repetition, no duration). Uses only
# input-side information; targets are reported afterwards.
#
# Usage (HPC): python eval_verbalizer_rerank.py --ckpt ckpt-verbalizer2
# Output: verbalizer-rerank-report.json

import argparse
import json
import pathlib
import sys

import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from train_verbalizer import (  # noqa: E402
    HERE, MAX_INPUT, MAX_OUTPUT, check, norm_punct)
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration  # noqa: E402
from transformers.models.t5.tokenization_t5 import T5Tokenizer  # noqa: E402


def load(name):
    return [json.loads(l) for l in
            (HERE / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def visible_props(row):
    line = [x for x in row["input"].splitlines() if x.startswith("地点可见=")]
    if not line:
        return set()
    return set(p for p in line[0].split("=", 1)[1].split("、") if p)


def score(row, text, props):
    c = check(row, text)
    penalty = 10 * len(c["reasons"])
    # prefer candidates that stay inside the declared scene props
    outside = 0
    for p in props:
        pass
    for p in ("栈桥", "钟架", "木桩", "缆绳", "船灯", "渡船", "鱼筐",
              "案板", "天窗", "潮汐簿", "灯罩", "铃绳", "经幡", "铜铃"):
        if p in text and p not in props:
            outside += 1
    penalty += 4 * outside
    if len(text) < 8 or len(text) > 40:
        penalty += 2
    cover = 0.0
    for _ in (0,):
        pass
    return -(penalty), c, outside


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ckpt", default="ckpt-verbalizer2")
    ap.add_argument("--samples", type=int, default=6)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = T5Tokenizer.from_pretrained(args.ckpt, legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        args.ckpt, torch_dtype=torch.float32).to(device)
    model.eval()

    out = {}
    for label, name in (("dev", "verbalizer_pairs.jsonl"),
                        ("newWorld", "verbalizer_holdout.jsonl")):
        rows = load(name)
        if label == "dev":
            rows = [r for i, r in enumerate(rows) if i % 7 == 0]
        picked, first = [], []
        for r in rows:
            props = visible_props(r)
            enc = tok(r["input"], return_tensors="pt", truncation=True,
                      max_length=MAX_INPUT).to(device)
            with torch.no_grad():
                gen = model.generate(
                    **enc, max_new_tokens=MAX_OUTPUT, do_sample=True,
                    temperature=0.9, top_p=0.95,
                    num_return_sequences=args.samples)
            cands = [tok.decode(g, skip_special_tokens=True) for g in gen]
            scored = sorted(((score(r, t, props), t) for t in cands),
                            key=lambda x: x[0][0], reverse=True)
            (s, c, outside), best = scored[0]
            first.append((check(r, cands[0]), cands[0]))
            picked.append({
                "pairId": r["pairId"], "kind": r["kind"],
                "output": best, "target": r["target"],
                "reasons": c["reasons"], "outsideProps": outside,
                "binding": c["binding"],
                "firstSampleBinding": first[-1][0]["binding"],
                "exactNormalized": norm_punct(best) == norm_punct(r["target"]),
            })
        out[label] = picked
        print(label, "rerank binding", sum(p["binding"] for p in picked),
              "/", len(picked), "first-sample",
              sum(1 for f in first if f[0]["binding"]), flush=True)
        for p in picked:
            if not p["binding"]:
                print("  BAD", p["pairId"], p["reasons"], "|", p["output"],
                      flush=True)

    report = {
        "purpose": "fact verbalizer n-best filtering/reranking",
        "ckpt": args.ckpt,
        "samplesPerFact": args.samples,
        "results": {k: {"rows": len(v),
                        "rerankBinding": sum(p["binding"] for p in v),
                        "firstSampleBinding": sum(p["firstSampleBinding"]
                                                  for p in v),
                        "exactNormalized": sum(p["exactNormalized"] for p in v)}
                    for k, v in out.items()},
        "samples": out,
    }
    pathlib.Path("verbalizer-rerank-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8")
    print("results:", json.dumps(report["results"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
