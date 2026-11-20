# Scene-sentence n-best filtering (deterministic, input-side only).
#
# Usage (HPC): python eval_scene_rerank.py --ckpt ckpt-scene
# Output: scene-rerank-report.json

import argparse
import json
import pathlib
import sys

import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from scene_check import check  # noqa: E402
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration  # noqa: E402
from transformers.models.t5.tokenization_t5 import T5Tokenizer  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
MAX_INPUT, MAX_OUTPUT = 256, 48

# furniture owned by exactly one top-level location
LOC_PROPS = {}
for w in ("world.json", "holdout_world.json"):
    world = json.loads((HERE / w).read_text(encoding="utf-8"))
    for loc in world["locations"].values():
        props = set(loc.get("features", []))
        for sub in loc.get("sublocations", []):
            props.add(sub["name"])
            props.update(sub.get("features", []))
        LOC_PROPS[loc["name"]] = props
EXCLUSIVE = {}
for name, props in LOC_PROPS.items():
    for p in props:
        if [n for n, q in LOC_PROPS.items() if p in q] == [name]:
            EXCLUSIVE[p] = name


def visible(row):
    line = [x for x in row["input"].splitlines() if x.startswith("地点可见=")]
    return set(line[0].split("=", 1)[1].split("、")) if line else set()


def score(row, text):
    c = check(row, text)
    props = visible(row)
    foreign = [p for p, owner in EXCLUSIVE.items()
               if p in text and owner != row["input"].split("地点=")[1]
               .splitlines()[0]]
    inside = sum(1 for p in props if p in text)
    return -(10 * len(c["reasons"]) + 5 * len(foreign) - 1 * inside), c, foreign


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ckpt", default="ckpt-scene")
    ap.add_argument("--samples", type=int, default=6)
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = T5Tokenizer.from_pretrained(args.ckpt, legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        args.ckpt, torch_dtype=torch.float32).to(device)
    model.eval()

    out = {}
    for label, name, step in (("dev", "scene_pairs.jsonl", 8),
                              ("newWorld", "scene_holdout.jsonl", 1)):
        rows = [json.loads(l) for l in
                (HERE / name).read_text(encoding="utf-8").splitlines()
                if l.strip()]
        if label == "dev":
            rows = [r for i, r in enumerate(rows) if i % step == 0]
        picked = []
        for r in rows:
            enc = tok(r["input"], return_tensors="pt", truncation=True,
                      max_length=MAX_INPUT).to(device)
            with torch.no_grad():
                gen = model.generate(**enc, max_new_tokens=MAX_OUTPUT,
                                     do_sample=True, temperature=0.9,
                                     top_p=0.95,
                                     num_return_sequences=args.samples)
            cands = [tok.decode(g, skip_special_tokens=True) for g in gen]
            scored = sorted(((score(r, t), t) for t in cands),
                            key=lambda x: x[0][0], reverse=True)
            (s, c, foreign), best = scored[0]
            picked.append({"pairId": r["pairId"], "key": r["key"],
                           "candidates": [
                               {"text": t, "ok": check(r, t)["ok"],
                                "reasons": check(r, t)["reasons"]}
                               for t in cands],
                           "output": best, "target": r["target"],
                           "reasons": c["reasons"], "foreignProps": foreign,
                           "ok": c["ok"],
                           "firstSampleOk": check(r, cands[0])["ok"]})
        out[label] = picked
        print(label, "rerank ok", sum(p["ok"] for p in picked),
              "/", len(picked), "first-sample",
              sum(1 for p in picked if p["firstSampleOk"]), flush=True)
        for p in picked:
            if not p["ok"]:
                print("  BAD", p["pairId"], p["reasons"], "|", p["output"],
                      flush=True)

    report = {"purpose": "scene sentence n-best filtering", "ckpt": args.ckpt,
              "samplesPerScene": args.samples,
              "results": {k: {"rows": len(v), "rerankOk": sum(p["ok"] for p in v),
                              "firstSampleOk": sum(1 for p in v if p["firstSampleOk"])}
                          for k, v in out.items()},
              "samples": out}
    pathlib.Path("scene-rerank-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8")
    print("results:", json.dumps(report["results"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
