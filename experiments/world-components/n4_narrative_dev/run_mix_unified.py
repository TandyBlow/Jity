"""训练输入统一实验：4+3+1、同 seed、同采样 ID 序列；保存 step240 与 dev 最优两个检查点。"""
import argparse, json, pathlib, random, sys, time
import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import fact_contract as FC
from sequence_policy import encode_training_batch, generate_greedy, rethrow_oom
SEED=20261102; LR=3e-4; BATCH=8; MIX=(4,3,1); MAX_UPDATES=2880; EVAL_EVERY=240
def rows(p): return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
ap=argparse.ArgumentParser()
for k in ("manifest","units","expand","objects"): ap.add_argument("--"+k,required=True)
ap.add_argument("--base",required=True); ap.add_argument("--out",required=True)
ap.add_argument("--ckpt240",required=True); ap.add_argument("--ckptbest",required=True)
a=ap.parse_args()
man=json.loads(pathlib.Path(a.manifest).read_text(encoding="utf-8"))
sp={s["sourceId"]:s["split"] for s in man["sources"]}
base_rows=rows(a.units)
orig=[u for u in base_rows if sp.get(u["sourceId"])=="formal-train"]
dev=[u for u in base_rows if sp.get(u["sourceId"])=="formal-dev"]
expand=rows(a.expand); obj=rows(a.objects)
FC.check_units(orig+expand+obj)          # 三池全部走契约校验
tok=T5Tokenizer.from_pretrained(a.base,legacy=False,local_files_only=True)
model=T5ForConditionalGeneration.from_pretrained(a.base,torch_dtype=torch.float32)
device="cuda" if torch.cuda.is_available() else "cpu"; model.to(device)
torch.manual_seed(SEED)
opt=torch.optim.AdamW(model.parameters(),lr=LR)
rngs=[random.Random(SEED+i) for i in range(3)]
pools=[orig,expand,obj]; orders=[list(range(len(p))) for p in pools]; cur=[0,0,0]
rep={"arm":"unified_431","mix":list(MIX),"seed":SEED,"counts":{"orig":len(orig),"expand":len(expand),"object":len(obj),"dev":len(dev)},"history":[]}
ids=[]; tok_total=0
def eval_dev():
    model.eval(); tot,n=0.0,0
    with torch.inference_mode():
        for i in range(0,len(dev),BATCH):
            b=dev[i:i+BATCH]; enc,labels=encode_training_batch(tok,b)
            enc={k:v.to(device) for k,v in enc.items()}
            out=model(**enc,labels=labels.input_ids.to(device))
            tot+=float(out.loss)*len(b); n+=len(b)
    model.train(); return round(tot/max(n,1),4)
model.train(); t0=time.perf_counter(); best=None
for step in range(1,MAX_UPDATES+1):
    batch=[]
    for pi,take in enumerate(MIX):
        if take==0: continue
        if cur[pi]+take>len(orders[pi]): rngs[pi].shuffle(orders[pi]); cur[pi]=0
        for j in orders[pi][cur[pi]:cur[pi]+take]: batch.append(pools[pi][j])
        cur[pi]+=take
    for u in batch: ids.append(u.get("unitId") or u.get("pairId")
                                or f'{u.get("sourceId")}:{u.get("factId")}')
    enc,labels=encode_training_batch(tok,batch)
    enc={k:v.to(device) for k,v in enc.items()}; lab=labels.input_ids.to(device)
    try: out=model(**enc,labels=lab)
    except torch.cuda.OutOfMemoryError as exc: rethrow_oom(exc,enc,lab)
    opt.zero_grad(); out.loss.backward(); opt.step()
    tok_total+=int(labels.input_ids.ne(-100).sum())
    if step==240:
        model.save_pretrained(a.ckpt240); tok.save_pretrained(a.ckpt240)
        rep["ckpt240"]={"step":240,"devLoss":eval_dev() if False else None}
        print(f"step 240 saved", flush=True)
    if step%EVAL_EVERY==0 or step==MAX_UPDATES:
        d=eval_dev(); rep["history"].append({"step":step,"devLoss":d})
        print(f"step {step} dev {d}",flush=True)
        if best is None or d<best["devLoss"]:
            best={"step":step,"devLoss":d,"state":{k:v.detach().clone() for k,v in model.state_dict().items()}}
rep["train"]={"updates":MAX_UPDATES,"wallSeconds":round(time.perf_counter()-t0,1),
              "peakAllocatedGB":round(torch.cuda.max_memory_allocated()/1024**3,3) if torch.cuda.is_available() else None}
rep["targetTokens"]={"effectiveTotal":tok_total,"perUpdate":round(tok_total/MAX_UPDATES,1)}
rep["selectedCheckpoint"]={"step":best["step"],"devLoss":best["devLoss"]}
model.load_state_dict(best["state"]); model.save_pretrained(a.ckptbest); tok.save_pretrained(a.ckptbest)
rep["drawIds"]=ids
pathlib.Path(a.out).write_text(json.dumps(rep,ensure_ascii=False,indent=1),encoding="utf-8")
print(json.dumps({k:rep[k] for k in ("train","targetTokens","selectedCheckpoint")},ensure_ascii=False))
