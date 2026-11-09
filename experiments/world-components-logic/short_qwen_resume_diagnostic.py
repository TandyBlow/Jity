"""Continue missing ONNX diagnostic slots under a NEW batch identity.

Completed source outputs are inherited verbatim with hashes; failed attempts
remain failed. No overwrite, changed tokens, changed tolerances, or promotion.
"""
import argparse,shutil,time
from pathlib import Path
import short_qwen_diagnostic as d
import short_qwen_export as e


def fork(parent_path,run_id):
 parent=d.verify(parent_path);old=Path(parent_path).parent;plan=d.freeze(run_id,Path(parent['modelManifest']['path']));root=plan.parent
 for name in ('base','trained','runs'):
  if (old/name).exists():shutil.copytree(old/name,root/name,copy_function=lambda a,b:Path(b).hardlink_to(a))
 for name in ('ort.mjs','ort-build.json'):
  if (old/name).exists():shutil.copyfile(old/name,root/name)
 d.save(root/'inherited-slots.json',{'source':d.entry(parent_path),'sourceFailures':[d.entry(p) for p in old.glob('process*.log')],
  'files':[d.entry(p) for p in (old/'runs').rglob('*') if p.is_file()],
  'method':'inherit only fully written slot artifacts verbatim; retry missing slots in new identity; no historical rerun claim',
  'casesEqual':parent['cases']==d.read(plan)['cases'],'settingsEqual':parent['settings']==d.read(plan)['settings'],
  'qualification':'conversion_unqualified','worldWriteAllowed':False})
 print(plan,flush=True)


def run_missing(path,engine):
 import numpy as np
 from transformers import AutoTokenizer
 plan=d.verify(path);root=Path(path).parent;dest=root/'runs'/engine;dest.mkdir(parents=True,exist_ok=True)
 pending=[(ci,mode) for ci in range(len(plan['cases'])) for mode in ('fixed','free') if not (dest/f'{ci}.{mode}.json').exists()]
 if not pending:raise ValueError('no missing slots; do not relabel completed work')
 protocol={'plan':d.entry(path),'code':d.entry(__file__),'engine':engine,'pending':pending,
  'inheritedSlots':[d.entry(p) for p in dest.glob('*.json')], 'settings':d.SETTINGS,'caseDeadlineSeconds':600,
  'qualification':'conversion_unqualified','worldWriteAllowed':False}
 d.save(root/f'resume-{engine}-protocol.json',protocol);shutil.copyfile(__file__,root/f'resume-{engine}-code.py')
 cfg=d.read(Path(plan['model']['merged']['directory'])/'config.json')
 tokenizer=AutoTokenizer.from_pretrained(plan['model']['merged']['directory'],local_files_only=True)
 kind='base' if engine.startswith('base_') else 'trained';quantized=engine.endswith('q4')
 for item in d.read(root/kind/'assets.json')['files']:d.check(item)
 ort=d.session(root/kind/('webgpu/onnx/model_q4f16.onnx' if quantized else 'float/model.onnx'),quantized)
 for ci,mode in pending:
  case=plan['cases'][ci];cache={};tokens=[];steps=[];ids=case['inputIds'];logits={}
  limit=len(case['fixedTokenIds'])+1 if mode=='fixed' else d.SETTINGS['maxNewTokens'];start=time.monotonic()
  for step in range(limit):
   values=d.feeds(ids,cache,cfg);out=dict(zip([o.name for o in ort.get_outputs()],ort.run(None,values)))
   last=out['logits'][:,-1:,:].copy();chosen=int(last.argmax(-1).item());logits[f'step_{step}']=last
   steps.append({'step':step,'phase':'prefill' if step==0 else 'decode','inputs':{k:e.array_identity(v) for k,v in values.items()},
    'logits':e.array_identity(last),'top1':chosen,'cacheOutputs':{k:e.array_identity(v) for k,v in out.items() if k.startswith('present.')}})
   cache=d.next_cache(out)
   if mode=='fixed' and step==limit-1:break
   token=case['fixedTokenIds'][step] if mode=='fixed' else chosen;tokens.append(token);ids=[token]
   if mode=='free' and token in plan['generation']['eosTokenIds']:break
   if time.monotonic()-start>600:raise TimeoutError('diagnostic_case_deadline')
  with (dest/f'{ci}.{mode}.logits.npz').open('xb') as f:np.savez(f,**logits)
  record={'caseId':case['caseId'],'engine':engine,'mode':mode,'inputIdsSha256':case['inputIdsSha256'],
   'rawTokenIds':tokens,'rawText':tokenizer.decode(tokens,skip_special_tokens=True),'eosReached':bool(tokens and tokens[-1] in plan['generation']['eosTokenIds']),
   'elapsedSeconds':time.monotonic()-start,'steps':steps,'qualification':'conversion_unqualified','worldWriteAllowed':False,'executionProtocol':d.entry(root/f'resume-{engine}-protocol.json')}
  d.save(dest/f'{ci}.{mode}.json',record);print('CONTINUED_SLOT',engine,ci,mode,len(tokens),record['eosReached'],flush=True)
 d.save(root/f'resume-{engine}-summary.json',{'plan':d.entry(path),'executed':pending,'allSlotsPresent':all((dest/f'{ci}.{mode}.json').exists() for ci in range(len(plan['cases'])) for mode in ('fixed','free')),'qualification':'conversion_unqualified'})

if __name__=='__main__':
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
 f=s.add_parser('fork');f.add_argument('parent',type=Path);f.add_argument('--run-id',required=True)
 r=s.add_parser('run');r.add_argument('plan',type=Path);r.add_argument('--engine',required=True,choices=['trained_float','trained_q4','base_float','base_q4'])
 a=p.parse_args();fork(a.parent,a.run_id) if a.command=='fork' else run_missing(a.plan,a.engine)
