"""用指定检查点跑一批单元（确认集／诊断集），输出逐条文本与耗时。"""
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
ap.add_argument("--units", required=True, nargs="+")
ap.add_argument("--out", required=True)
ap.add_argument("--budget", type=float, default=20.0)
a = ap.parse_args()
tok = T5Tokenizer.from_pretrained(a.ckpt, legacy=False, local_files_only=True)
model = T5ForConditionalGeneration.from_pretrained(a.ckpt, torch_dtype=torch.float32)
dev = "cuda" if torch.cuda.is_available() else "cpu"
model.to(dev).eval()
out = {}
started_all = time.perf_counter()
for path in a.units:
    rows = [json.loads(l) for l in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    FC.check_units(rows)
    started = time.perf_counter()
    texts = []
    for u in rows:
        enc = tok(u["input"], return_tensors="pt", truncation=False).to(dev)
        ids, meta = generate_greedy(model, enc, a.budget)
        texts.append({"unitId": u["unitId"], "factId": u["fact"].get("factId"),
                      "name": u["fact"]["name"], "expected": u["fact"].get("text") or u["fact"].get("resultText") or "",
                      "text": tok.decode(ids[0], skip_special_tokens=True),
                      "complete": bool(meta["complete"])})
    out[pathlib.Path(path).stem] = texts
    print(f'{pathlib.Path(path).stem}: {len(texts)} 单元 {round(time.perf_counter()-started,1)}s', flush=True)
out["wallSeconds"] = round(time.perf_counter() - started_all, 1)
pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("done", out["wallSeconds"])
