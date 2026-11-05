import argparse, json, pathlib, sys
import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sequence_policy import generate_greedy
ap = argparse.ArgumentParser()
ap.add_argument("--variant", choices=("A","B"), required=True)
ap.add_argument("--ckpt", required=True)
ap.add_argument("--materials", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--budget", type=float, default=20.0)
a = ap.parse_args()
tok = T5Tokenizer.from_pretrained(a.ckpt, legacy=False, local_files_only=True)
m = T5ForConditionalGeneration.from_pretrained(a.ckpt, torch_dtype=torch.float32)
dev = "cuda" if torch.cuda.is_available() else "cpu"
m.to(dev).eval()
mat = json.loads(pathlib.Path(a.materials).read_text(encoding="utf-8"))
rows = []
for u in mat["units"]:
    enc = tok(u["input"+a.variant], return_tensors="pt", truncation=False).to(dev)
    ids, meta = generate_greedy(m, enc, a.budget)
    txt = tok.decode(ids[0], skip_special_tokens=True)
    rows.append({"unitId": u["unitId"], "category": u["category"],
                 "subjectIsPov": u["subjectIsPov"], "output": txt,
                 "stopReason": meta["stopReason"], "complete": meta["complete"],
                 "newTokens": meta["newTokens"]})
    print(u["unitId"], txt[:40], flush=True)
pathlib.Path(a.out).write_text(json.dumps({"variant": a.variant, "rows": rows},
                                          ensure_ascii=False, indent=1), encoding="utf-8")
print("->", a.out)
