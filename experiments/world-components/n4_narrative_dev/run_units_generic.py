"""Run a frozen checkpoint over a units jsonl (each row has unitId + input)."""
import argparse, json, pathlib, sys
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
tok = T5Tokenizer.from_pretrained(a.ckpt, legacy=False, local_files_only=True)
m = T5ForConditionalGeneration.from_pretrained(a.ckpt, torch_dtype=torch.float32)
dev = "cuda" if torch.cuda.is_available() else "cpu"
m.to(dev).eval()
rows = [json.loads(l) for l in pathlib.Path(a.units).read_text(encoding="utf-8").splitlines() if l.strip()]
FC.check_units(rows)          # 生成前校验，格式不符直接退出
out = []
for u in rows:
    enc = tok(u["input"], return_tensors="pt", truncation=False).to(dev)
    ids, meta = generate_greedy(m, enc, a.budget)
    out.append({"unitId": u["unitId"], "category": u.get("category"),
                "text": tok.decode(ids[0], skip_special_tokens=True),
                "stopReason": meta["stopReason"], "complete": meta["complete"]})
    print(u["unitId"], out[-1]["text"][:40], flush=True)
pathlib.Path(a.out).write_text(json.dumps({"rows": out}, ensure_ascii=False, indent=1), encoding="utf-8")
print("->", a.out)
