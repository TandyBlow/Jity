"""Isolated conversion evidence. Never returns a Completion or a D provider.

Every run is a new immutable identity. Numerical failure is recorded, not an
execution exception; diagnostic completion cannot authorize world mutation.
"""
from __future__ import annotations
import argparse,copy,gzip,json,sys,time,shutil,platform,importlib.metadata
from pathlib import Path
import short_qwen_export as export
from lab import sha256_file
from run_pilot import digest,exclusive
from short_qwen_codec import prompt_packet,tokenize_prompt

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
LOCAL=export.LOCAL/'conversion-diagnostics'
SETTINGS={'validationAtol':1e-4,'validationRtol':1e-5,'fixedSteps':16,'maxNewTokens':128,
 'maxInputTokens':8192,'seed':7,'threads':1,'sampling':'greedy','numBeams':1,
 'repetitionPenalty':1.0,'enableThinking':False,'optimization':'ORT_DISABLE_ALL',
 'quantizedOptimization':'ORT_ENABLE_BASIC','qualification':'conversion_unqualified',
 'label':'转换未合格','formalEvaluationAllowed':False,'worldWriteAllowed':False,
 'semanticGate':{'newCriticalErrorsAllowed':0,'normalEosRequired':True,
 'referenceAndActionCoverageRegressionAllowed':False,'reviewRequired':True},
 'numericGate':'unchanged_original_threshold; no automatic promotion',
 'maxWallSeconds':7200}


def read(path):return json.loads(Path(path).read_text())
def entry(path):
    path=Path(path).resolve();return {'path':str(path),'sha256':sha256_file(path),'bytes':path.stat().st_size}
def check(item):
    if sha256_file(item['path'])!=item['sha256']:raise ValueError('diagnostic_identity_drift:'+item['path'])
def save(path,value):exclusive(Path(path),value)


def freeze(run_id,model_path):
    from transformers import AutoTokenizer
    if not run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in run_id):raise ValueError('invalid_run_id')
    directory=LOCAL/run_id
    if directory.exists():raise FileExistsError('new diagnostic identity required')
    model=read(model_path);export.training_codec_identity(model)
    for folder in ('sourceModel','merged'):
        for f in model[folder]['files']:
            check({'path':str(Path(model[folder]['directory'])/f['path']),'sha256':f['sha256']})
    check(model['training']['checkpoint'])
    source_plan=read(model['planPath']);data=source_plan['data']['supervision.jsonl.gz'];check(data)
    with gzip.open(data['path'],'rt') as stream:rows=[json.loads(x) for x in stream]
    # Fixed deterministic selection before any conversion outputs are seen.
    selectors=[('D01.1.name',None),('D02.2.text','natural'),
               ('D04.1.text',None),('D05.3.text',None),('U4.2',None),('D08.1.amount',None)]
    tokenizer=AutoTokenizer.from_pretrained(model['merged']['directory'],local_files_only=True)
    cases=[]
    for component,representation in selectors:
        eligible=[r for r in rows if r['split']=='development' and r['component']==component
                  and (representation is None or r['input'].get('representation','natural')==representation)]
        if not eligible:raise ValueError('missing_registered_diagnostic_case:'+component+str(representation))
        row=sorted(eligible,key=lambda r:r['exampleId'])[0]
        packet=prompt_packet(component,row['input']);ids=tokenize_prompt(tokenizer,component,row['input'],SETTINGS['maxInputTokens'])
        target=row['target'];target=target if isinstance(target,str) else str(target)
        fixed=tokenizer.encode(target,add_special_tokens=False)+[tokenizer.eos_token_id]
        cases.append({'caseId':row['exampleId'],'component':component,'sourceGroup':row['sourceGroup'],
                      'payload':row['input'],'packet':packet,'inputIds':ids,'inputIdsSha256':digest(ids),
                      'fixedTokenIds':fixed[:SETTINGS['fixedSteps']], 'draftTarget':target,
                      'reviewStatus':'assistant_draft_not_human_ground_truth'})
    directory.mkdir(parents=True)
    code=[]
    for name in ('short_qwen_export.py','short_qwen_diagnostic.py','short_qwen_diagnostic_browser.py',
                 'short_qwen_codec.py','short_qwen_training.py','short_webgpu/diagnostic.mjs','short_webgpu/diagnostic.html'):
        src=BASE/name;dst=directory/'code'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        code.append({'source':str(src),**entry(dst)})
    plan={'schema':'jity-qwen-conversion-diagnostic-v1','runId':run_id,'settings':SETTINGS,
          'modelManifest':entry(model_path),'model':model,'dataset':data,'cases':cases,'code':code,
          'pairs':['adapter_bf16_to_merged_bf16','merged_fp32_to_fp32_onnx','fp32_onnx_to_q4f16_onnx','q4f16_cpu_to_webgpu'],
          'additionalControls':['merged_mps_bf16_to_cpu_fp32','native_to_export_patched_pytorch','untrained_same_base_pipeline'],
          'environment':{'python':sys.version,'platform':platform.platform(),
            'versions':{n:importlib.metadata.version(n) for n in export.VERSIONS}},
          'generation':{'maxNewTokens':SETTINGS['maxNewTokens'],'eosTokenIds':read(Path(model['merged']['directory'])/'generation_config.json')['eos_token_id']},
          'oldFailures':[entry(export.ART/(f'qwen-short-time-export-20261109-r{i}.summary.json')) for i in (2,4)],
          'semanticReview':'paired full input/output; no exact-match semantic scoring',
          'trainingPaused':True,'fullChainPaused':True,'formalEvaluationAllowed':False,'worldWriteAllowed':False}
    save(directory/'plan.json',plan);return directory/'plan.json'


def verify(path):
    plan=read(path)
    if plan['schema']!='jity-qwen-conversion-diagnostic-v1' or plan['settings']!=SETTINGS:raise ValueError('diagnostic_settings_drift')
    check(plan['modelManifest']);check(plan['dataset'])
    check(plan['model']['training']['checkpoint'])
    for section in ('sourceModel','merged'):
        for item in plan['model'][section]['files']:
            check({'path':str(Path(plan['model'][section]['directory'])/item['path']),'sha256':item['sha256']})
    if plan['environment']['python']!=sys.version:raise ValueError('diagnostic Python drift')
    for name,version in plan['environment']['versions'].items():
        if importlib.metadata.version(name)!=version:raise ValueError('diagnostic dependency drift:'+name)
    for c in plan['code']:
        check(c);check({'path':c['source'],'sha256':c['sha256']})
    for old in plan['oldFailures']:check(old)
    return plan


def session(graph,quantized=False):
    import onnxruntime as ort
    options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
    options.graph_optimization_level=getattr(ort.GraphOptimizationLevel,SETTINGS['quantizedOptimization' if quantized else 'optimization'])
    return ort.InferenceSession(str(graph),sess_options=options,providers=['CPUExecutionProvider'])


def feeds(ids,cache,cfg):
    import numpy as np
    past=0 if not cache else next(iter(cache.values())).shape[-2]
    values={'input_ids':np.array([ids],dtype=np.int64),'attention_mask':np.ones((1,past+len(ids)),dtype=np.int64),
            'position_ids':np.arange(past,past+len(ids),dtype=np.int64)[None,:]}
    for i in range(cfg['num_hidden_layers']):
        for kind in ('key','value'):
            name=f'past_key_values.{i}.{kind}'
            values[name]=cache[name] if cache else np.zeros((1,cfg['num_key_value_heads'],0,cfg['head_dim']),dtype=np.float32)
    return values


def torch_forward(model,values,patched=False,full=False):
    import torch
    from transformers import DynamicCache
    inputs={k:torch.from_numpy(v.copy()).to(model.device) for k,v in values.items() if not k.startswith('past_key_values.')}
    dtype=next(model.parameters()).dtype
    legacy=tuple(tuple(torch.from_numpy(values[f'past_key_values.{i}.{kind}'].copy()).to(model.device,dtype=dtype) for kind in ('key','value')) for i in range(model.config.num_hidden_layers))
    inputs['past_key_values']=legacy if patched else DynamicCache.from_legacy_cache(legacy)
    inputs['use_cache']=True
    if not full:inputs['logits_to_keep']=1
    with torch.inference_mode():out=model(**inputs)
    cache=out['past_key_values'];cache=cache.to_legacy_cache() if hasattr(cache,'to_legacy_cache') else cache
    result={'logits':out['logits'].detach().float().cpu().numpy()}
    result.update({f'present.{i}.{kind}':tensor.detach().float().cpu().numpy() for i,pair in enumerate(cache) for kind,tensor in zip(('key','value'),pair)})
    return result


def next_cache(out):return {k.replace('present.','past_key_values.'):v for k,v in out.items() if k.startswith('present.')}

def convert(path,kind):
    import torch
    from transformers import AutoModelForCausalLM
    from optimum.exporters.onnx.convert import onnx_export_from_model
    plan=verify(path);root=Path(path).parent;dest=root/kind;dest.mkdir(exist_ok=False)
    source=plan['model']['sourceModel' if kind=='base' else 'merged']['directory']
    torch.set_num_threads(1);torch.manual_seed(SETTINGS['seed'])
    model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,torch_dtype=torch.float32,attn_implementation='eager').eval()
    onnx_export_from_model(model,dest/'float',task=export.CONFIG['task'],opset=18,device='cpu',do_validation=False,
                           no_post_process=True,batch_size=1,sequence_length=8)
    raw=dest/'float/model.onnx';cfg=export.qwen_onnx_config(model,export.CONFIG['task'])
    try:export.validate_float(model,cfg,raw,export.CONFIG)
    except ValueError as e:
        if str(e)!='strict_float_export_numerical_validation_failed':raise
    del model
    packaged=dest/'webgpu';(packaged/'onnx').mkdir(parents=True)
    for name in ('config.json','generation_config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','chat_template.jinja'):
        f=Path(source)/name
        if f.exists():shutil.copyfile(f,packaged/name)
    tc=read(packaged/'tokenizer_config.json')
    if 'chat_template' not in tc and (packaged/'chat_template.jinja').exists():
        tc['chat_template']=(packaged/'chat_template.jinja').read_text();(packaged/'tokenizer_config.json').write_text(json.dumps(tc,ensure_ascii=False))
    graph=export.quantize_q4f16(raw,packaged/'onnx/model_q4f16.onnx',export.CONFIG)
    export.bind_cache_dtype(packaged,graph)
    # Different schema from any model/provider asset; regular browser rejects it.
    save(dest/'assets.json',{'schema':'jity-qwen-unqualified-diagnostic-assets-v1',
         'qualification':'conversion_unqualified','label':'转换未合格','worldWriteAllowed':False,
         'plan':entry(path),'kind':kind,'files':[entry(p) for p in sorted(dest.rglob('*')) if p.is_file()]})
    print('CONVERTED_DIAGNOSTIC',kind,flush=True)


def run(path,engine):
    import torch,numpy as np
    from transformers import AutoModelForCausalLM,AutoTokenizer
    from short_qwen_training import install_lora,restore_adapter
    plan=verify(path);root=Path(path).parent;dest=root/'runs'/engine;dest.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(1);torch.manual_seed(SETTINGS['seed'])
    cfg=read(Path(plan['model']['merged']['directory'])/'config.json')
    tokenizer=AutoTokenizer.from_pretrained(plan['model']['merged']['directory'],local_files_only=True)
    native=engine in ('adapter_bf16','merged_bf16','merged_fp32','base_fp32')
    if native:
        adapter=engine=='adapter_bf16';bf16=engine.endswith('bf16')
        source=plan['model']['sourceModel' if adapter or engine=='base_fp32' else 'merged']['directory']
        model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,torch_dtype=torch.bfloat16 if bf16 else torch.float32,
                       attn_implementation='sdpa' if bf16 else 'eager').to('mps' if bf16 else 'cpu').eval()
        if adapter:
            install_lora(torch,model,read(plan['model']['planPath'])['config'])
            restore_adapter(torch,model,torch.load(plan['model']['training']['checkpoint']['path'],map_location='cpu',weights_only=True))
        call=lambda v:torch_forward(model,v)
    else:
        kind='base' if engine.startswith('base_') else 'trained';quantized=engine.endswith('q4')
        assets=read(root/kind/'assets.json')
        for item in assets['files']:check(item)
        graph=root/kind/('webgpu/onnx/model_q4f16.onnx' if quantized else 'float/model.onnx')
        ort=session(graph,quantized);call=lambda v:dict(zip([o.name for o in ort.get_outputs()],ort.run(None,v)))
    records=[]
    for ci,case in enumerate(plan['cases']):
        for mode in ('fixed','free'):
            cache={};tokens=[];steps=[];ids=case['inputIds'];logits={}
            limit=len(case['fixedTokenIds'])+1 if mode=='fixed' else SETTINGS['maxNewTokens']
            start=time.monotonic()
            for step in range(limit):
                values=feeds(ids,cache,cfg);out=call(values);last=out['logits'][:,-1:,:].copy();chosen=int(last.argmax(-1).item())
                logits[f'step_{step}']=last
                steps.append({'step':step,'phase':'prefill' if step==0 else 'decode',
                              'inputs':{k:export.array_identity(v) for k,v in values.items()},
                              'logits':export.array_identity(last),'top1':chosen,
                              'cacheOutputs':{k:export.array_identity(v) for k,v in out.items() if k.startswith('present.')}})
                cache=next_cache(out)
                if mode=='fixed':
                    if step==0 and engine in ('merged_fp32','base_fp32'):
                        with (dest/f'{ci}.prefill-cache.npz').open('xb') as f:np.savez(f,**cache)
                    if step==limit-1:break
                    token=case['fixedTokenIds'][step]
                else:token=chosen
                tokens.append(token);ids=[token]
                if mode=='free' and token in plan['generation']['eosTokenIds']:break
                if time.monotonic()-start>600:raise TimeoutError('diagnostic_case_deadline')
            with (dest/f'{ci}.{mode}.logits.npz').open('xb') as f:np.savez(f,**logits)
            record={'caseId':case['caseId'],'engine':engine,'mode':mode,'inputIdsSha256':case['inputIdsSha256'],
                    'rawTokenIds':tokens,'rawText':tokenizer.decode(tokens,skip_special_tokens=True),
                    'eosReached':bool(tokens and tokens[-1] in plan['generation']['eosTokenIds']),
                    'elapsedSeconds':time.monotonic()-start,'steps':steps,'qualification':'conversion_unqualified',
                    'worldWriteAllowed':False}
            save(dest/f'{ci}.{mode}.json',record);records.append({k:v for k,v in record.items() if k!='steps'})
            print('CASE',engine,ci,mode,len(tokens),record['eosReached'],round(record['elapsedSeconds'],2),flush=True)
    save(dest/'summary.json',{'plan':entry(path),'engine':engine,'records':records,'formalEvaluationAllowed':False})


def trace(path,kind):
    """Compare full prefill and a cached decode with identical reference cache.

    Also replay historical random tensors, to explain the original failed gate.
    """
    import torch,numpy as np,onnx
    from transformers import AutoModelForCausalLM
    plan=verify(path);root=Path(path).parent;dest=root/kind/'trace';dest.mkdir(exist_ok=False)
    torch.set_num_threads(1)
    source=plan['model']['sourceModel' if kind=='base' else 'merged']['directory']
    model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,torch_dtype=torch.float32,attn_implementation='eager').eval()
    config=export.qwen_onnx_config(model,export.CONFIG['task']);raw=root/kind/'float/model.onnx'
    taps=export.diagnostic_graph(raw,dest/'trace.onnx',model.config.num_hidden_layers)
    cfg=model.config.to_dict()
    scenarios=[('historical_random',dict(np.load(root/kind/'float/strict-float-validation.inputs.npz')))]
    case=plan['cases'][1];scenarios.append(('full_prefill',feeds(case['inputIds'],{},cfg)))
    cache=dict(np.load(root/'runs'/('base_fp32' if kind=='base' else 'merged_fp32')/'1.prefill-cache.npz'))
    scenarios.append(('shared_cache_decode',feeds(case['fixedTokenIds'][:1],cache,cfg)))
    for name,values in scenarios:
        # Preserve every input byte, including mask, positions and all cache tensors.
        with (dest/(name+'.inputs.npz')).open('xb') as f:np.savez(f,**values)
        handles,native=capture=export.capture_modules(model,taps)
        try:ref=torch_forward(model,values,full=False)
        finally:
            for h in handles:h.remove()
        handles,patched=export.capture_modules(model,taps)
        try:
            with config.patch_model_for_export(model):torch_forward(model,values,patched=True,full=False)
        finally:
            for h in handles:h.remove()
        patch_checks=[export.compare_diagnostic(t['module'],native[t['module']],patched[t['module']]) for t in taps]
        del patched
        # Do not retain two 3 GB runtime weight sessions at the same time.
        original=session(raw)
        unchanged=dict(zip([o.name for o in original.get_outputs()],original.run(None,values)))
        del original
        ort=session(dest/'trace.onnx')
        out=dict(zip([o.name for o in ort.get_outputs()],ort.run(None,values)))
        del ort
        instrumentation=[export.compare_diagnostic(k,unchanged[k],out[k]) for k in unchanged]
        del unchanged
        checks=[export.compare_diagnostic(t['module'],native[t['module']],out[t['output']]) for t in taps]
        final=[export.compare_diagnostic(k,ref[k],out[k][:,-1:,:] if k=='logits' else out[k]) for k in ref]
        result={'scenario':name,'inputs':{k:export.array_identity(v) for k,v in values.items()},
                'inputArchive':entry(dest/(name+'.inputs.npz')),'moduleMapping':taps,'layers':checks,
                'nativeVsExportPatch':patch_checks,'outputs':final,'instrumentationVsOriginal':instrumentation,
                'firstToleranceBreach':next((c['name'] for c in checks if not c['valuesClose']),None),
                'firstNonzeroDifference':next((c['name'] for c in checks if c['maxAbsError']),None),
                'scope':'all-token module boundaries and caches; final logits last token; not proof of unique causal operator',
                'qualification':'conversion_unqualified','worldWriteAllowed':False}
        save(dest/(name+'.json'),result)
        print('TRACE',kind,name,result['firstToleranceBreach'],flush=True)
        del out,ref,native,capture


def compare(path):
    import numpy as np
    plan=verify(path);root=Path(path).parent
    pairs=[('adapter_bf16','merged_bf16'),('merged_bf16','merged_fp32'),('merged_fp32','trained_float'),
           ('trained_float','trained_q4'),('base_fp32','base_float'),('base_float','base_q4'),('trained_q4','webgpu')]
    result=[]
    for left,right in pairs:
        for ci,case in enumerate(plan['cases']):
            a=root/'runs'/left;b=root/'runs'/right
            required=[directory/f'{ci}.{suffix}' for directory in (a,b)
                      for suffix in ('free.json','fixed.json','fixed.logits.npz')]
            missing=[str(f.relative_to(root)) for f in required if not f.is_file()]
            if missing:
                result.append({'pair':[left,right],'caseId':case['caseId'],'status':'incomplete',
                               'missingArtifacts':missing,'semanticReview':'pending','criticalErrorRegression':None})
                continue
            x=read(a/f'{ci}.free.json');y=read(b/f'{ci}.free.json')
            record={'pair':[left,right],'caseId':case['caseId'],'free':{'tokensEqual':x['rawTokenIds']==y['rawTokenIds'],
              'referenceText':x['rawText'],'actualText':y['rawText'],'referenceEos':x['eosReached'],'actualEos':y['eosReached'],
              'firstDifferentToken':next((i for i,(u,v) in enumerate(zip(x['rawTokenIds'],y['rawTokenIds'])) if u!=v),
                                         None if x['rawTokenIds']==y['rawTokenIds'] else min(len(x['rawTokenIds']),len(y['rawTokenIds'])))},
              'semanticReview':'pending','criticalErrorRegression':None}
            fixed_left=read(a/f'{ci}.fixed.json');fixed_right=read(b/f'{ci}.fixed.json')
            if fixed_left['rawTokenIds']!=case['fixedTokenIds'] or fixed_right['rawTokenIds']!=case['fixedTokenIds']:
                raise ValueError('forced token identity mismatch')
            with np.load(a/f'{ci}.fixed.logits.npz') as xa,np.load(b/f'{ci}.fixed.logits.npz') as ya:
                expected={f'step_{i}' for i in range(len(case['fixedTokenIds'])+1)}
                if set(xa.files)!=expected or set(ya.files)!=expected:raise ValueError('fixed step coverage mismatch')
                record['fixed']=[{'step':i,**export.compare_diagnostic('logits',xa[f'step_{i}'],ya[f'step_{i}'])} for i in range(len(xa.files))]
                record['cachePolicy']='independent cache per endpoint; identical forced tokens; shared-cache decode isolated separately'
            record['status']='compared_pending_semantic_review'
            result.append(record)
    complete=sum(r['status']=='compared_pending_semantic_review' for r in result)
    save(root/'comparison.json',{'plan':entry(path),'comparisons':result,'qualification':'conversion_unqualified',
         'coverage':{'expectedPairsTimesCases':len(pairs)*len(plan['cases']),'compared':complete,
                     'incomplete':len(result)-complete,'allArtifactsPresent':complete==len(pairs)*len(plan['cases'])},
         'acceptance':'not_promoted_pending_explanation_and_paired_semantic_review',
         'originalNumericThresholdsRetained':True,'formalEvaluationAllowed':False,'worldWriteAllowed':False})


def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    f=s.add_parser('freeze');f.add_argument('--run-id',required=True);f.add_argument('--model',type=Path,required=True)
    for command in ('convert','run','trace','compare'):
        q=s.add_parser(command);q.add_argument('plan',type=Path)
        if command in ('convert','trace'):q.add_argument('--kind',choices=['base','trained'],required=True)
        if command=='run':q.add_argument('--engine',required=True,choices=['adapter_bf16','merged_bf16','merged_fp32','base_fp32','trained_float','trained_q4','base_float','base_q4'])
    a=p.parse_args()
    if a.command=='freeze':print(freeze(a.run_id,a.model))
    elif a.command=='convert':convert(a.plan,a.kind)
    elif a.command=='run':run(a.plan,a.engine)
    elif a.command=='trace':trace(a.plan,a.kind)
    else:compare(a.plan)
if __name__=='__main__':main()
