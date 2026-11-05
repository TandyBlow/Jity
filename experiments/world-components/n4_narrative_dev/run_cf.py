"""Run the paired counterfactual inputs through one frozen checkpoint.

Each variant is a single generation call under the same per-item budget the
two-arm run used. No candidate filtering, no post-editing.
"""
import argparse, json, pathlib, sys, time

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sequence_policy import generate_greedy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=("paragraph", "fact"), required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget", type=float, default=20.0)
    args = ap.parse_args()

    tok = T5Tokenizer.from_pretrained(args.ckpt, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(
        args.ckpt, torch_dtype=torch.float32)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()

    pairs = json.loads(pathlib.Path(args.pairs).read_text(encoding="utf-8"))["pairs"]
    rows = []
    for p in pairs:
        if p["family"] == "A":
            scope = "both"
        elif p["family"] == "B":
            scope = "paragraph"
        elif p["family"] == "C":
            scope = "both"
        else:
            scope = "fact"
        if scope != "both" and scope != args.arm:
            continue
        for v in p["variants"]:
            enc = tok(v["input"], return_tensors="pt", truncation=False).to(device)
            t = time.perf_counter()
            ids, meta = generate_greedy(model, enc, args.budget)
            text = tok.decode(ids[0], skip_special_tokens=True)
            rows.append({"pairId": p["pairId"], "family": p["family"],
                         "sourceId": p["sourceId"], "factId": p["factId"],
                         "variant": v["variant"], "expect": p["expect"],
                         "output": text, "stopReason": meta["stopReason"],
                         "complete": meta["complete"],
                         "newTokens": meta["newTokens"],
                         "seconds": round(time.perf_counter() - t, 3)})
            print(f"[{args.arm}] {p['pairId']} {v['variant']} "
                  f"complete={meta['complete']} {text[:40]}", flush=True)
    out = {"arm": args.arm, "checkpoint": args.ckpt,
           "budgetSeconds": args.budget, "rows": rows}
    pathlib.Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
