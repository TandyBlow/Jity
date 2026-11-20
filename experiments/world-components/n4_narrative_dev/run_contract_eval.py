"""用契约格式的固定诊断集跑一个检查点（不训练）。"""
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
ap.add_argument("--out", required=True)
ap.add_argument("--budget", type=float, default=20.0)
a = ap.parse_args()
ART = pathlib.Path(__file__).resolve().parent   # 远端把材料与脚本放同一目录
FILES = {"object18": "n4-object18-contract.jsonl",
         "expand36": "n4-expand36-contract.jsonl",
         "final24": "n4-final24-contract.jsonl",
         "cf24": "n4-cf24-contract.jsonl"}
tok = T5Tokenizer.from_pretrained(a.ckpt, legacy=False, local_files_only=True)
model = T5ForConditionalGeneration.from_pretrained(a.ckpt, torch_dtype=torch.float32)
dev = "cuda" if torch.cuda.is_available() else "cpu"
model.to(dev).eval()
out = {}
for name, fn in FILES.items():
    units = [json.loads(l) for l in (ART / fn).read_text(encoding="utf-8").splitlines()
             if l.strip()]
    FC.check_units(units)          # 生成前校验，格式不符直接退出
    started = time.perf_counter()
    rows = []
    for u in units:
        enc = tok(u["input"], return_tensors="pt", truncation=False).to(dev)
        ids, meta = generate_greedy(model, enc, a.budget)
        rows.append({"unitId": u["unitId"], "sourceId": u.get("sourceId"),
                     "kind": u["kind"],
                     "text": tok.decode(ids[0], skip_special_tokens=True),
                     "complete": meta["complete"]})
    out[name] = rows
    print(f'{name}: {len(rows)} 单元 {round(time.perf_counter()-started,1)}s', flush=True)
pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                               encoding="utf-8")
print("->", a.out)
