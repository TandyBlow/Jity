"""Run the 24 multi-fact sources through one frozen checkpoint."""
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
    ap.add_argument("--materials", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget", type=float, default=20.0)
    args = ap.parse_args()

    tok = T5Tokenizer.from_pretrained(args.ckpt, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(
        args.ckpt, torch_dtype=torch.float32)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()
    mat = json.loads(pathlib.Path(args.materials).read_text(encoding="utf-8"))
    rows = []
    for s in mat["sources"]:
        if args.arm == "paragraph":
            enc = tok(s["paragraphInput"], return_tensors="pt", truncation=False).to(device)
            t = time.perf_counter()
            ids, meta = generate_greedy(model, enc, args.budget)
            text = tok.decode(ids[0], skip_special_tokens=True)
            calls = [dict(meta, factId=None)]
            complete = meta["complete"]
        else:
            started = time.perf_counter()
            parts, calls, complete = [], [], True
            for fid in s["mustExpress"]:
                left = args.budget - (time.perf_counter() - started)
                if left <= 0:
                    calls.append({"factId": fid, "stopReason": "budget-exhausted",
                                  "complete": False, "newTokens": 0, "seconds": 0})
                    complete = False
                    continue
                enc = tok(s["unitInputs"][fid], return_tensors="pt",
                          truncation=False).to(device)
                t = time.perf_counter()
                ids, meta = generate_greedy(model, enc, left)
                calls.append(dict(meta, factId=fid))
                parts.append(tok.decode(ids[0], skip_special_tokens=True))
                complete = complete and meta["complete"]
            text = "".join(parts)
        rows.append({"sourceId": s["id"], "pattern": s["pattern"],
                     "facts": s["mustExpress"], "output": text,
                     "complete": complete,
                     "seconds": round(time.perf_counter() - t, 3) if args.arm == "paragraph"
                     else round(time.perf_counter() - started, 3),
                     "calls": [{k: c.get(k) for k in
                                ("factId", "stopReason", "complete", "newTokens")}
                               for c in calls]})
        print(f"[{args.arm}] {s['id']} complete={complete} {len(text)} chars", flush=True)
    out = {"arm": args.arm, "checkpoint": args.ckpt, "budgetSeconds": args.budget,
           "sources": rows}
    pathlib.Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print("->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
