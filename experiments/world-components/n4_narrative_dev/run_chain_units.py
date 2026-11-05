"""给两条来自真实链条的单元各生成一句（u240，贪心，20 秒预算）。"""
import argparse, json, pathlib, sys, time
import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fact_contract as FC
from sequence_policy import generate_greedy

ap = argparse.ArgumentParser()
ap.add_argument("--ckpt", required=True)
ap.add_argument("--units", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--budget", type=float, default=20.0)
a = ap.parse_args()
units = [json.loads(l) for l in pathlib.Path(a.units).read_text(encoding="utf-8").splitlines() if l.strip()]
FC.check_units(units)
tok = T5Tokenizer.from_pretrained(a.ckpt, legacy=False, local_files_only=True)
model = T5ForConditionalGeneration.from_pretrained(a.ckpt, torch_dtype=torch.float32)
dev = "cuda" if torch.cuda.is_available() else "cpu"
model.to(dev).eval()
rows = []
for u in units:
    started = time.perf_counter()
    enc = tok(u["input"], return_tensors="pt", truncation=False).to(dev)
    ids, meta = generate_greedy(model, enc, a.budget)
    rows.append({"unitId": u["unitId"], "factId": u["fact"]["factId"],
                 "kind": u["kind"], "name": u["fact"]["name"],
                 "text": tok.decode(ids[0], skip_special_tokens=True),
                 "complete": meta["complete"],
                 "seconds": round(time.perf_counter() - started, 2)})
    print(rows[-1], flush=True)
pathlib.Path(a.out).write_text(json.dumps({"arm": "u240", "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
print("done")
