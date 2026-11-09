"""Isolated causal-LM short-task training, with the common D supervisor/journal.

No legacy generator is loaded. Qwen training on MPS is separate from subsequent
ONNX/WebGPU evidence. Full prompts are retained; only response tokens incur loss.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import time

import experiment as common
from lab import sha256_file
from run_pilot import digest, exclusive, save, timestamp
from short_qwen_codec import CODEC, TASKS, prompt_packet, tokenize_prompt
from short_training import training_schedule, validate_rows

ROOT=Path(__file__).resolve().parents[2];BASE=Path(__file__).resolve().parent
ART=ROOT/'artifacts/world-components-logic/qwen-short'
LOCAL=Path.home()/'.cache/jity-d-short-semantics-20261109/qwen'
DATA=BASE/'data/short-semantics/supervision.jsonl.gz'
ARMS=('qwen_baseline','qwen_train','qwen_after','qwen_merge')
CONFIG={'device':'mps','basePrecision':'bfloat16','adapterPrecision':'float32','seed':42,
 'steps':112,'batchSize':1,'rank':4,'alpha':8,'learningRate':0.0001,'weightDecay':0.01,
 'maxGradNorm':1.0,'maxInputTokens':8192,'maxTargetTokens':128,'maxNewTokens':128,
 'gradientCheckpointing':True,'gradientCheckpointingReentrant':False,'trainingDropout':0.0,
 'attentionImplementation':'sdpa','enableThinking':False,'codec':CODEC,'doSample':False,
 'processWallSeconds':2400,'maxResidentMiB':8192,'maxMpsDriverMiB':8192,'threads':1,
 'concurrency':1,'attemptsPerCase':1,'retries':0,'mergeMaxAbsError':0.5,
 'evaluationSplits':['development','test'],'trainingSampling':'task_then_source_full_coverage',
 'loss':'response_tokens_and_eos_only_prompt_labels_masked','logitsSelection':'response_positions_only_full_hidden_context'}
CONFIG['memoryPolicy']='release_unused_MPS_cache_after_each_request_and_optimizer_step; fatal_resource_gate'
CODE=('short_qwen_training.py','short_qwen_codec.py','short_training.py','experiment.py',
      'plan_training.py','lab.py','run_pilot.py','m01_probe.py','fetch_qwen.py','fetch_model.py')
DEPENDENCIES=('torch','transformers','numpy','safetensors','tokenizers','huggingface_hub',
              'pydantic','sentencepiece','optimum','optimum-onnx','onnx','onnxruntime','onnxscript','onnx_ir','ml_dtypes')


def paths(run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}',run_id):raise ValueError('invalid run identity')
    return ART/(run_id+'.plan.json'),ART/(run_id+'.record.json')


def load_rows(path):
    raw=Path(path).read_bytes();raw=gzip.decompress(raw) if str(path).endswith('.gz') else raw
    rows=[json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    validate_rows(rows)
    rows=[r for r in rows if r['kind']=='text']
    if set(r['component'] for r in rows)!=set(TASKS):raise ValueError('all fourteen short-text tasks required')
    return rows


def tokenize_row(tokenizer,row,config):
    prompt=tokenize_prompt(tokenizer,row['component'],row['input'],config['maxInputTokens'])
    target=tokenizer.encode(row['target'],add_special_tokens=False,truncation=False)
    eos=tokenizer.eos_token_id
    if not target or eos is None or eos in target:raise ValueError('empty target or embedded end token')
    target=target+[eos]
    if len(target)>config['maxTargetTokens']:raise ValueError('complete_target_exceeds_frozen_limit')
    vocabulary_size=len(tokenizer)
    if any(type(x) is not int or x<0 or x>=vocabulary_size for x in prompt+target):raise ValueError('invalid token id')
    return {'exampleId':row['exampleId'],'component':row['component'],'sourceGroup':row['sourceGroup'],
            'split':row['split'],'promptIds':prompt,'targetIds':target,
            'inputSha256':digest(row['input']),'targetSha256':digest(row['target'])}


def causal_batch(torch,example,device):
    # Positions prompt[-1], target[0], ... target[-2] predict all target + EOS.
    ids=example['promptIds']+example['targetIds'][:-1]
    return {'input_ids':torch.tensor([ids],dtype=torch.long,device=device),
            'attention_mask':torch.ones((1,len(ids)),dtype=torch.long,device=device)},torch.tensor([example['targetIds']],dtype=torch.long,device=device)


def response_loss(torch,model,example,device):
    tensors,target=causal_batch(torch,example,device)
    output=model(**tensors,use_cache=False,logits_to_keep=target.shape[1])
    if output.logits.shape[:2]!=target.shape:raise ValueError('response logit alignment mismatch')
    return torch.nn.functional.cross_entropy(output.logits.float().reshape(-1,output.logits.shape[-1]),target.reshape(-1))


def tensor_digest(torch,state):
    h=hashlib.sha256()
    for name,value in sorted(state.items()):
        value=value.detach().cpu().contiguous();h.update(name.encode());h.update(str(value.dtype).encode());h.update(str(tuple(value.shape)).encode());h.update(value.view(torch.uint8).numpy().tobytes())
    return h.hexdigest()


def install_lora(torch,model,config):
    """Same low-rank update as shared LoRA, with explicit fp32 optimizer state."""
    for value in model.parameters():value.requires_grad_(False)
    class CausalLoRA(torch.nn.Module):
        def __init__(self,base):
            super().__init__();self.base_layer=base;rank=config['rank'];self.scale=config['alpha']/rank
            self.lora_A=torch.nn.Parameter(torch.empty(rank,base.in_features,device=base.weight.device,dtype=torch.float32))
            self.lora_B=torch.nn.Parameter(torch.zeros(base.out_features,rank,device=base.weight.device,dtype=torch.float32))
            torch.nn.init.kaiming_uniform_(self.lora_A,a=math.sqrt(5))
        def forward(self,x):
            base=self.base_layer(x);delta=(x.float()@self.lora_A.T@self.lora_B.T)*self.scale
            return base+delta.to(base.dtype)
    targets=[(name,module) for name,module in model.named_modules() if isinstance(module,torch.nn.Linear) and name.endswith(('.self_attn.q_proj','.self_attn.v_proj'))]
    if len(targets)!=2*model.config.num_hidden_layers:raise ValueError('Qwen q/v projection coverage mismatch')
    for name,module in targets:
        parent,_,leaf=name.rpartition('.');setattr(model.get_submodule(parent),leaf,CausalLoRA(module))
    return [name for name,_ in targets]


def merge_lora(torch,model):
    targets=[(name,module) for name,module in model.named_modules() if hasattr(module,'lora_A') and hasattr(module,'base_layer')]
    if len(targets)!=2*model.config.num_hidden_layers:raise ValueError('merge adapter coverage mismatch')
    with torch.no_grad():
        for name,module in targets:
            delta=(module.lora_B@module.lora_A)*module.scale
            module.base_layer.weight.add_(delta.to(module.base_layer.weight.dtype))
            parent,_,leaf=name.rpartition('.');setattr(model.get_submodule(parent),leaf,module.base_layer)
    return [name for name,_ in targets]


def source_check(manifest):
    if manifest['modelId']!='Qwen/Qwen3-0.6B' or manifest['license']!='apache-2.0':raise ValueError('unregistered model/license')
    if sha256_file(manifest['registry'])!=manifest['registrySha256']:raise ValueError('source registry changed')
    registry=common.read_json(manifest['registry'])
    if any(manifest[key]!=registry[key] for key in ('modelId','revision','license')):raise ValueError('source registry/manifest identity mismatch')
    if {f['path'] for f in manifest['files']}!={f['path'] for f in registry['files']}:raise ValueError('source file coverage mismatch')
    for item in manifest['files']:
        path=Path(manifest['directory'])/item['path']
        if path.stat().st_size!=item['bytes'] or sha256_file(path)!=item['sha256']:raise ValueError('source model/tokenizer changed:'+item['path'])


def freeze(run_id,*,model_manifest:Path,dataset:Path|None=None):
    from transformers import AutoTokenizer
    plan_path,record=paths(run_id)
    if plan_path.exists() or record.exists():raise FileExistsError('preserve first attempt; new run ID required')
    source=json.loads(Path(model_manifest).read_text());source_check(source)
    dataset=Path(dataset or DATA);rows=load_rows(dataset);config=copy.deepcopy(CONFIG)
    source_metadata=common.read_json(dataset.parent/'manifest.json')
    if source_metadata['files'].get(dataset.name)!=sha256_file(dataset):raise ValueError('dataset/source-manifest mismatch')
    tokenizer=AutoTokenizer.from_pretrained(source['directory'],local_files_only=True,trust_remote_code=False)
    encoded={r['exampleId']:tokenize_row(tokenizer,r,config) for r in rows}
    schedule=training_schedule(rows,config);by_id={r['exampleId']:r for r in rows}
    components={}
    for task in sorted(TASKS):
        subset=[r for r in rows if r['component']==task];selected=[by_id[key] for key in schedule['exampleIds'] if by_id[key]['component']==task]
        actual_sources=sorted({r['sourceGroup'] for r in selected});required_sources=sorted({r['sourceGroup'] for r in subset if r['split']=='train'})
        if actual_sources!=required_sources:raise ValueError('training budget leaves source unexposed:'+task)
        components[task]={'splitRows':dict(__import__('collections').Counter(r['split'] for r in subset)),
          'maxPromptTokens':max(len(encoded[r['exampleId']]['promptIds']) for r in subset),
          'maxTargetTokens':max(len(encoded[r['exampleId']]['targetIds']) for r in subset),
          'scheduledSamples':len(selected),'scheduledSourceGroups':actual_sources}
    directory=ART/'snapshots'/run_id;directory.mkdir(parents=True,exist_ok=False)
    code={}
    for name in CODE:
        destination=directory/'code'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/name,destination);code[name]=sha256_file(destination)
    data_files={}
    for name,path in [('supervision.jsonl.gz',dataset),('manifest.json',dataset.parent/'manifest.json'),('sources.jsonl',dataset.parent/'sources.jsonl')]:
        destination=directory/'data'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,destination);data_files[name]={'path':str(destination),'sha256':sha256_file(destination)}
    manifest_copy=directory/'source-model.json';shutil.copyfile(model_manifest,manifest_copy)
    evaluations=[r['exampleId'] for r in rows if r['split'] in config['evaluationSplits']]
    plan={'schema':'jity-qwen-short-plan-v1','runId':run_id,'preparedAt':timestamp(),'config':config,
      'cases':[{'caseId':'all-fourteen-text-tasks'}],'arms':list(ARMS),'codeSha256':code,
      'codeSnapshot':str(directory/'code'),'data':data_files,'modelManifest':{'path':str(manifest_copy),'sha256':sha256_file(manifest_copy)},
      'model':source,'environment':{'venvExecutableRelativePath':sys.executable,'pythonVersion':sys.version,
         'versions':{name:importlib.metadata.version(name) for name in DEPENDENCIES}},
      'trainingSchedule':schedule,'evaluationExampleIds':evaluations,'workload':{'components':components,
         'fullContext':True,'tokenizerOnly':True,'neuralCalls':0,'baselinePredictions':len(evaluations),'afterPredictions':len(evaluations)},
      'review':{'assistantAuthored':True,'humanReviewed':0,'sourceVerified':0,'sourceGroupsReused':True,
                'formalEvaluationAllowed':False,'holdout':'open reused same-source candidate, not independent generalization'},
      'retryPolicy':{'retries':0,'firstOutputsRetained':True,'truncationTimeoutCancellation':'incomplete'},
      'mergePolicy':{'dtype':'bfloat16','maxAbsLogitError':config['mergeMaxAbsError'],'sameArgmaxRequired':True},
      'exportPreparation':{'tool':'optimum-onnx','task':'text-generation-with-past','opset':18,'dtype':'fp32',
         'targetRuntime':'transformers.js@3.8.1 WebGPU','quantization':'q4f16','blockSize':32,'symmetric':True,
         'webgpuMeasurement':'separate_required_not_MPS','fullRequest500ms':'unmeasured'},
      'paidServices':False,'readiness':'ready_exploratory','formalEvaluationAllowed':False}
    ART.mkdir(parents=True,exist_ok=True);exclusive(plan_path,plan);return plan_path


def verify(plan):
    if plan['config']!=CONFIG or plan['arms']!=list(ARMS):raise ValueError('frozen config drift')
    for name,expected in plan['codeSha256'].items():
        if sha256_file(BASE/name)!=expected or sha256_file(Path(plan['codeSnapshot'])/name)!=expected:raise ValueError('code drift:'+name)
    for item in plan['data'].values():
        if sha256_file(item['path'])!=item['sha256']:raise ValueError('data drift')
    if sha256_file(plan['modelManifest']['path'])!=plan['modelManifest']['sha256']:raise ValueError('source manifest drift')
    source_check(plan['model'])
    if sys.version!=plan['environment']['pythonVersion']:raise ValueError('Python drift')
    for name,expected in plan['environment']['versions'].items():
        if importlib.metadata.version(name)!=expected:raise ValueError('dependency drift:'+name)
    rows=load_rows(plan['data']['supervision.jsonl.gz']['path'])
    if training_schedule(rows,plan['config'])!=plan['trainingSchedule']:raise ValueError('sample schedule drift')
    if [r['exampleId'] for r in rows if r['split'] in CONFIG['evaluationSplits']]!=plan['evaluationExampleIds']:raise ValueError('evaluation denominator drift')
    return rows


def sync(torch):
    if torch.backends.mps.is_available():torch.mps.synchronize()


def memory(torch,config):
    values={'mpsAllocatedBytes':torch.mps.current_allocated_memory(),'mpsDriverBytes':torch.mps.driver_allocated_memory()}
    if values['mpsDriverBytes']>config['maxMpsDriverMiB']*1048576:
        error=MemoryError('frozen_mps_driver_memory_limit');error.metrics=values;raise error
    return values


def legal_eos_ids(model,tokenizer):
    values=getattr(getattr(model,'generation_config',None),'eos_token_id',None)
    if values is None:values=tokenizer.eos_token_id
    values=values if isinstance(values,list) else [values]
    if not values or any(type(x) is not int or x<0 for x in values):raise ValueError('invalid_registered_eos')
    return values


def predictions(torch,model,tokenizer,rows,encoded,config,checkpoint):
    model.eval();outputs=[]
    for row in rows:
        if row['split'] not in config['evaluationSplits']:continue
        x=encoded[row['exampleId']];started=time.perf_counter();event={'exampleId':row['exampleId'],'component':row['component'],
          'sourceGroup':row['sourceGroup'],'split':row['split'],**prompt_packet(row['component'],row['input']),
          'promptIds':x['promptIds'],'status':'running'}
        event['modelGenerateInvoked']=False
        checkpoint('qwen_generation_started',event);fatal=None;out=None;tensors=None
        try:
            memory(torch,config)
            tensors={'input_ids':torch.tensor([x['promptIds']],dtype=torch.long,device=config['device'])}
            tensors['attention_mask']=torch.ones_like(tensors['input_ids'])
            event['modelGenerateInvoked']=True
            forward_started=time.perf_counter()
            with torch.inference_mode():out=model.generate(**tensors,max_new_tokens=config['maxNewTokens'],do_sample=False,
              temperature=None,top_p=None,top_k=None,use_cache=True,pad_token_id=tokenizer.eos_token_id)
            sync(torch);event['modelComputeMs']=(time.perf_counter()-forward_started)*1000
            tokens=out[0,len(x['promptIds']):].tolist();event['rawTokenIds']=tokens
            raw=tokenizer.decode(tokens,skip_special_tokens=True)
            # Preserve the first model output even when the subsequent resource
            # accounting rejects the request. Never evaluate the guard first.
            event.update(rawTokenIds=tokens,rawText=raw)
            event.update(memory(torch,config))
            event['legalEosTokenIds']=legal_eos_ids(model,tokenizer)
            if not tokens or tokens[-1] not in event['legalEosTokenIds']:raise ValueError('truncated_no_eos')
            if not raw.strip():raise ValueError('empty_generation')
            if '<think>' in raw or '</think>' in raw:raise ValueError('unexpected_thinking_output')
            event.update(status='result',output=raw,exactDraftMatch=raw==row['target'])
        except Exception as error:
            event.update(status='incomplete',reason=str(error),exactDraftMatch=False)
            if isinstance(error,MemoryError) or 'out of memory' in str(error).lower():
                fatal=error;event.update(getattr(error,'metrics',{}));event['fatalResourceFailure']=True
        # Cached allocator storage is not semantic context. Drop transient
        # tensors and reclaim only unused allocations between complete calls.
        out=None;tensors=None
        try:
            sync(torch);torch.mps.empty_cache();event['memoryAfterRelease']=memory(torch,config)
        except Exception as error:
            event.update(cacheReleaseError=str(error),status='incomplete',reason='cache_release_failed:'+str(error),exactDraftMatch=False)
            fatal=fatal or error
        event['elapsedMs']=(time.perf_counter()-started)*1000
        reference=checkpoint('qwen_generation_finished',event)
        outputs.append({k:v for k,v in event.items() if k in ('exampleId','component','sourceGroup','split','status','output','reason','exactDraftMatch','elapsedMs')})
        outputs[-1]['rawCheckpoint']=reference
        if fatal is not None:raise fatal
    return outputs


def train(torch,model,encoded,plan,checkpoint,destination):
    from plan_training import adapter_state,base_state
    config=plan['config'];modules=install_lora(torch,model,config);initial=adapter_state(model)
    before=tensor_digest(torch,base_state(model));parameters=[p for p in model.parameters() if p.requires_grad]
    if not parameters or any(p.dtype!=torch.float32 for p in parameters):raise ValueError('float32 adapter optimizer required')
    model.train();model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False});model.enable_input_require_grads()
    model.config.use_cache=False
    for layer in model.modules():
        if isinstance(layer,torch.nn.Dropout):layer.p=0.0
    optimizer=torch.optim.AdamW(parameters,lr=config['learningRate'],weight_decay=config['weightDecay'])
    counts={key:0 for key in TASKS};gradients={key:0 for key in TASKS};losses=[]
    for index,key in enumerate(plan['trainingSchedule']['exampleIds']):
        example=encoded[key];start=time.perf_counter();optimizer.zero_grad(set_to_none=True)
        checkpoint('qwen_optimizer_started',{'step':index+1,'exampleId':key,'component':example['component'],'inputSha256':example['inputSha256'],'promptTokens':len(example['promptIds']),'targetTokens':len(example['targetIds'])})
        loss=response_loss(torch,model,example,config['device'])
        if not torch.isfinite(loss):raise ValueError('nonfinite_loss')
        loss.backward();norm=torch.nn.utils.clip_grad_norm_(parameters,config['maxGradNorm'])
        if not torch.isfinite(norm):raise ValueError('nonfinite_gradient')
        nonzero=bool(float(norm)>0);counts[example['component']]+=1;gradients[example['component']]+=int(nonzero)
        optimizer.step();sync(torch);losses.append(float(loss.detach().cpu()))
        event={'step':index+1,'exampleId':key,'component':example['component'],'loss':losses[-1],
          'gradientNormBeforeClip':float(norm),'nonzeroDataGradient':nonzero,'elapsedMs':(time.perf_counter()-start)*1000}
        try:event.update(memory(torch,config))
        except MemoryError as error:
            event.update(getattr(error,'metrics',{}));event['resourceFailure']=str(error);checkpoint('qwen_optimizer_finished',event);raise
        checkpoint('qwen_optimizer_finished',event)
        del loss;sync(torch);torch.mps.empty_cache()
    model.gradient_checkpointing_disable();model.disable_input_require_grads();model.config.use_cache=True;model.eval()
    final=adapter_state(model);changed={key:not torch.equal(initial[key],value) for key,value in final.items()}
    if not all(gradients.values()) or not any(changed.values()):raise ValueError('untrained_task_or_unchanged_adapter')
    after=tensor_digest(torch,base_state(model))
    if before!=after:raise ValueError('frozen_base_modified')
    destination.mkdir(parents=True,exist_ok=False);path=destination/'adapter.pt'
    with path.open('xb') as stream:torch.save(final,stream);stream.flush();os.fsync(stream.fileno())
    restored=torch.load(path,map_location='cpu',weights_only=True)
    if tensor_digest(torch,restored)!=tensor_digest(torch,final):raise ValueError('adapter_reload_drift')
    return {'steps':len(losses),'losses':losses,'componentGradientExposures':counts,'componentNonzeroDataGradientSteps':gradients,
      'parameterChanged':changed,'targetModules':modules,'baseTensorSha256':before,'baseUnchanged':True,
      'checkpoint':{'path':str(path),'sha256':sha256_file(path),'tensorSha256':tensor_digest(torch,final)}}


def worker(path):
    plan=common.read_json(path);rows=verify(plan);_,out=paths(plan['runId']);slots=common.planned_slots(plan,ARMS)
    record={'schema':'jity-qwen-short-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),'status':'running',
      'attemptSlots':slots,'attempts':[],'activeAttempt':None,'stages':[],'checkpointStorage':common.CHECKPOINT_STORAGE,
      'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequestMeasured':False}
    exclusive(out,record)
    try:
        import torch
        from transformers import AutoTokenizer,AutoModelForCausalLM
        torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(plan['config']['seed'])
        if not torch.backends.mps.is_available():raise ValueError('registered_mps_device_unavailable')
        tokenizer=AutoTokenizer.from_pretrained(plan['model']['directory'],local_files_only=True,trust_remote_code=False)
        encoded={r['exampleId']:tokenize_row(tokenizer,r,plan['config']) for r in rows};model=None
        with common.AppendJournal(out.with_suffix('.journal.jsonl'),record['planSha256']) as journal:
            journal.append('begin',{'runId':plan['runId'],'slots':slots,'checkpointStorage':common.CHECKPOINT_STORAGE})
            for slot in slots:
                attempt={**slot,'status':'started','startedMonotonicNs':time.monotonic_ns(),'checkpoints':[]}
                record['activeAttempt']=attempt;journal.append('attempt_start',attempt)
                def checkpoint(name,payload):
                    event={k:attempt[k] for k in ('arm','caseId','repeat')};event.update(name=name,payload=payload)
                    ref=common.append_checkpoint(journal,event);attempt['checkpoints'].append(ref);return ref
                try:
                    if model is None:
                        start=time.perf_counter();model=AutoModelForCausalLM.from_pretrained(plan['model']['directory'],local_files_only=True,
                          trust_remote_code=False,torch_dtype=torch.bfloat16,attn_implementation='sdpa',weights_only=True).to('mps').eval()
                        sync(torch);checkpoint('qwen_cold_load',{'elapsedMs':(time.perf_counter()-start)*1000,'parameters':sum(p.numel() for p in model.parameters()),**memory(torch,plan['config'])})
                    arm=slot['arm']
                    if arm in ('qwen_baseline','qwen_after'):attempt['predictions']=predictions(torch,model,tokenizer,rows,encoded,plan['config'],checkpoint)
                    elif arm=='qwen_train':attempt['training']=train(torch,model,encoded,plan,checkpoint,LOCAL/'runs'/plan['runId']/'adapter')
                    else:
                        first=encoded[plan['evaluationExampleIds'][0]];inputs,_=causal_batch(torch,first,'mps')
                        with torch.inference_mode():before=model(**inputs,use_cache=False,logits_to_keep=1).logits.float().cpu()
                        modules=merge_lora(torch,model)
                        with torch.inference_mode():after=model(**inputs,use_cache=False,logits_to_keep=1).logits.float().cpu()
                        maximum=float((before-after).abs().max());same=bool(torch.equal(before.argmax(-1),after.argmax(-1)))
                        checkpoint('qwen_merge_validation',{'exampleId':first['exampleId'],'maxAbsError':maximum,'argmaxEqual':same,'beforeLogits':before.flatten().tolist(),'afterLogits':after.flatten().tolist()})
                        if maximum>CONFIG['mergeMaxAbsError'] or not same:raise ValueError('merged_model_numerical_gate_failed')
                        destination=LOCAL/'runs'/plan['runId']/'merged';destination.mkdir(parents=True,exist_ok=False)
                        model.to('cpu');torch.mps.empty_cache();model.save_pretrained(destination,safe_serialization=True,max_shard_size='2GB');tokenizer.save_pretrained(destination)
                        attempt['merged']={'directory':str(destination),'targetModules':modules,'maxAbsLogitError':maximum,'argmaxEqual':same,
                          'files':[{'path':f.name,'sha256':sha256_file(f),'bytes':f.stat().st_size} for f in sorted(destination.iterdir()) if f.is_file()]}
                    attempt['status']='complete'
                except Exception as error:attempt.update(status='failed',completion='incomplete',error={'type':type(error).__name__,'message':str(error)})
                journal.append('attempt_result',attempt);attempt['elapsedThroughResultMs']=(time.monotonic_ns()-attempt['startedMonotonicNs'])/1e6
                journal.append('attempt_settled',{k:attempt[k] for k in ('arm','caseId','repeat','elapsedThroughResultMs')})
                record['attempts'].append(attempt);record['activeAttempt']=None;save(out,record)
                if attempt['status']!='complete':break
        record['status']='diagnostic_completed' if len(record['attempts'])==len(slots) and all(a['status']=='complete' for a in record['attempts']) else 'failed'
        if record['status']=='diagnostic_completed':
            manifest={'schema':'jity-qwen-short-trained-source-v1','runId':plan['runId'],'sourceModel':plan['model'],
              'config':plan['config'],'codec':CODEC,'codeSha256':plan['codeSha256'],'dataset':plan['data'],
              'trainedComponents':sorted(TASKS),'training':record['attempts'][1]['training'],'merged':record['attempts'][3]['merged'],
              'recordPath':str(out),'planPath':str(path),'planSha256':sha256_file(path),'webgpuValidated':False,
              'formalEvaluationAllowed':False,'semanticQualityApproved':False}
            target=ART/(plan['runId']+'.model.json');exclusive(target,manifest);record['modelManifest']={'path':str(target),'sha256':sha256_file(target)}
    except Exception as error:record.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
    finally:save(out,record)
    return 0 if record['status']=='diagnostic_completed' else 1


def execute(plan):
    code=common.execute_plan(Path(plan),paths=paths,verify=verify,worker_script=Path(__file__),
      settle_stages=lambda record,reason:None,arms=ARMS)
    frozen=common.read_json(plan);_,out=paths(frozen['runId']);record=common.read_json(out)
    record['predictionSlots']=prediction_ledger(frozen,record,out.with_suffix('.journal.jsonl'))
    record['unstartedPredictions']=sum(x['status']=='not_started' for x in record['predictionSlots'])
    save(out,record);return code


def prediction_ledger(plan,record,journal_path):
    slots={(arm,key):{'arm':arm,'exampleId':key,'status':'not_started'} for arm in ('qwen_baseline','qwen_after') for key in plan['evaluationExampleIds']}
    if Path(journal_path).exists():
        for event in common.iter_checkpoint_events(record,journal_path):
            if event['name'] not in ('qwen_generation_started','qwen_generation_finished'):continue
            payload=event['payload'];key=(event['arm'],payload['exampleId'])
            if key not in slots:raise ValueError('unregistered prediction event')
            if event['name']=='qwen_generation_started':slots[key].update(status='incomplete',reason='interrupted_before_finished_event')
            else:slots[key].update(status=payload['status'],reason=payload.get('reason'),rawOutputRetained='rawTokenIds' in payload,modelGenerateInvoked=payload.get('modelGenerateInvoked'))
    return list(slots.values())


def report(path):
    plan=common.read_json(path);_,out=paths(plan['runId']);record=common.read_json(out if out.exists() else str(out)+'.gz')
    if record['planSha256']!=sha256_file(path):raise ValueError('report identity drift')
    return {'runId':plan['runId'],'status':record['status'],'modelManifest':record.get('modelManifest'),
      'arms':[{k:v for k,v in a.items() if k not in ('checkpoints','predictions')}|({'predictionCount':len(a['predictions']),
        'completePredictions':sum(p['status']=='result' for p in a['predictions']),'exactDraftMatches':sum(p['exactDraftMatch'] for p in a['predictions'])} if 'predictions' in a else {}) for a in record['attempts']],
      'supervisor':record.get('supervisor'),'webgpuValidated':False,'formalEvaluationAllowed':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=Path,required=True);args=parser.parse_args();raise SystemExit(worker(args.worker))
