"""Generate the B (viewpoint-name removed) inputs with the frozen fact checkpoint."""
import argparse, json, pathlib, sys, time
import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sequence_policy import generate_greedy

ap = argparse.ArgumentParser()
ap.add_argument("--ckpt", required=True)
ap.add_argument("--materials", required=True)
ap.add_argument("--ablation", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--budget", type=float, default=20.0)
args = ap.parse_args()

tok = T5Tokenizer.from_pretrained(args.ckpt, legacy=False, local_files_only=True)
model = T5ForConditionalGeneration.from_pretrained(args.ckpt, torch_dtype=torch.float32)
dev = "cuda" if torch.cuda.is_available() else "cpu"
model.to(dev).eval()
mat = json.loads(pathlib.Path(args.materials).read_text(encoding="utf-8"))
ab = {s["id"]: s["unitInputs"] for s in
      json.loads(pathlib.Path(args.ablation).read_text(encoding="utf-8"))["sources"]}
rows = []
for s in mat["sources"]:
    started = time.perf_counter()
    parts, complete = [], True
    for f in s["facts"]:
        left = args.budget - (time.perf_counter() - started)
        if left <= 0:
            complete = False
            break
        enc = tok(ab[s["id"]][f["factId"]], return_tensors="pt",
                  truncation=False).to(dev)
        ids, meta = generate_greedy(model, enc, left)
        parts.append(tok.decode(ids[0], skip_special_tokens=True))
        complete = complete and meta["complete"]
    rows.append({"sourceId": s["id"], "output": "".join(parts), "complete": complete,
                 "seconds": round(time.perf_counter() - started, 3)})
    print(s["id"], len("".join(parts)), flush=True)
pathlib.Path(args.out).write_text(json.dumps({"arm": "fact-B", "sources": rows},
                                             ensure_ascii=False, indent=1), encoding="utf-8")
print("->", args.out)
