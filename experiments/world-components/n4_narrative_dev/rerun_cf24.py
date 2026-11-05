"""Re-run one frozen checkpoint on the corrected cf24 inputs (v2). No training."""
import argparse, json, pathlib, sys, time

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sequence_policy import generate_greedy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=("paragraph", "fact", "group"), required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--materials", required=True)
    ap.add_argument("--groups", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget", type=float, default=20.0)
    args = ap.parse_args()

    tok = T5Tokenizer.from_pretrained(args.ckpt, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(
        args.ckpt, torch_dtype=torch.float32)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()
    mat = json.loads(pathlib.Path(args.materials).read_text(encoding="utf-8"))
    groups = {}
    for g in json.loads(pathlib.Path(args.groups).read_text(encoding="utf-8"))["groups"]:
        groups.setdefault(g["sourceId"], []).append(g)

    rows = []
    for s in mat["sources"]:
        started = time.perf_counter()
        if args.arm == "paragraph":
            enc = tok(s["paragraphInput"], return_tensors="pt", truncation=False).to(device)
            ids, meta = generate_greedy(model, enc, args.budget)
            text, complete = tok.decode(ids[0], skip_special_tokens=True), meta["complete"]
            calls = [{"factId": None, **{k: meta[k] for k in ("stopReason", "complete", "newTokens")}}]
        else:
            units = ([{"factId": f["factId"], "input": s["unitInputs"][f["factId"]]}
                      for f in s["facts"]] if args.arm == "fact"
                     else [{"factId": ", ".join(g["factIds"]), "input": g["input"]}
                           for g in groups[s["id"]]])
            parts, calls, complete = [], [], True
            for u in units:
                left = args.budget - (time.perf_counter() - started)
                if left <= 0:
                    calls.append({"factId": u["factId"], "stopReason": "budget-exhausted",
                                  "complete": False, "newTokens": 0})
                    complete = False
                    continue
                enc = tok(u["input"], return_tensors="pt", truncation=False).to(device)
                ids, meta = generate_greedy(model, enc, left)
                calls.append({"factId": u["factId"], "stopReason": meta["stopReason"],
                              "complete": meta["complete"], "newTokens": meta["newTokens"]})
                parts.append(tok.decode(ids[0], skip_special_tokens=True))
                complete = complete and meta["complete"]
            text = "".join(parts)
        rows.append({"sourceId": s["id"], "pattern": s["pattern"],
                     "output": text, "complete": complete,
                     "seconds": round(time.perf_counter() - started, 3), "calls": calls})
        print(f"[{args.arm}] {s['id']} {len(text)} chars", flush=True)
    out = {"arm": args.arm, "checkpoint": args.ckpt, "materials": args.materials,
           "budget": args.budget, "sources": rows}
    pathlib.Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print("->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
