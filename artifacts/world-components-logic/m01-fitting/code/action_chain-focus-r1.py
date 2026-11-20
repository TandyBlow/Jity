"""D offline action decision -> text generation -> targets; no production writes."""
from __future__ import annotations
import argparse
import copy
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import experiment as run
import m01_shared as m01
from lab import build_model_input,guard_case,decode_output,canonical_bytes,sha256_file
from prepare_run_batch import observe_environment
from run_pilot import digest,exclusive,save,timestamp

ROOT=m01.ROOT;BASE=m01.BASE;ART=m01.ART
PROTOCOL=ROOT/'design/world-engine-reports/components-logic/action-focus-probe.md'
CASES=('dev-d02-01','dev-d02-03','dev-d02-05','dev-d02-07')
ARMS=('original','focus','focus_int8')
CONFIG={'device':'cpu','threads':1,'concurrency':1,'attemptsPerCase':3,'trainingSteps':0,
        'processWallSeconds':120,'maxResidentMiB':4096,'seed':42,'threshold':.5,
        'maxInputTokensPerWindow':512,'maxNewTokens':96,'softGenerationSeconds':10,'maxInputTokens':4096,
        'maxActionCharacters':240,'doSample':False,'numBeams':1,'featureCacheForTiming':False,
        'generationEncoding':'causal_full_context','generatorKind':'M03','generatorPrecision':'float32_then_qint8_dynamic','local50msHardGate':False,
        'armBlocks':[['original','focus'],['focus_int8']],'quantizationBackend':'qnnpack',
        'fullNonNarrativeTargetMs':500,'chainScope':'D02_decision_action_text_D03_only'}
CODE=('experiment.py','action_chain.py','m01_shared.py','m01_probe.py','fact_windows.py','pilot_codec.py',
      'lab.py','run_pilot.py','review_io.py','prepare_run_batch.py','fetch_model.py')


def dataset():
    rows,review=m01.old.dataset();by_id={r['case']['caseId']:r for r in rows}
    return [by_id[c]['case'] for c in CASES],review


def prepare(run_id):
    path,out=m01.old.paths(run_id)
    if path.exists() or out.exists():raise FileExistsError('preserve prior evidence; new run id required')
    cases,review=dataset();model=observe_generator();env=observe_environment(ROOT)
    if not model['allFilesFullyRehashedAndVerified'] or not env['registeredVersionsMatch']:raise ValueError('generator/environment identity invalid')
    plan={'schema':'jity-d-action-focus-plan-v1','runId':run_id,'preparedAt':timestamp(),
          'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
          'protocolPath':str(PROTOCOL.relative_to(ROOT)),'protocolSha256':sha256_file(PROTOCOL),
          'code':{'experiments/world-components-logic/'+n:sha256_file(BASE/n) for n in CODE},
          'config':CONFIG.copy(),'configSha256':digest(CONFIG),'cases':cases,'casesSha256':digest(cases),
          'review':review,'baseline':m01.baseline_identity(),'m01Model':m01.old.model_identity(),
          'generatorModel':model,'environment':env,'arms':list(ARMS),
          'authorization':{'instruction':'继续','resourceWindow':'current_turn_D_CPU_single_thread_no_GPU_no_BC',
                           'scope':'offline_three_stage_diagnostic_no_training'},
          'formalEvaluationAllowed':False,'sourceIndependence':'unverified','round1TrainingQuota':0,
          'newIndependentTrainingGroups':0,'retainedDevelopmentPreviouslyObserved':True,
          'performancePolicy':{'effectiveDate':'2026-11-04','localHardLimitMs':None,'localReferenceMs':50,
                               'fullNonNarrativeTargetMs':500,'fullRequestMeasured':False}}
    exclusive(path,plan);return path


def verify(plan):
    if plan['config']!=CONFIG or plan['configSha256']!=digest(CONFIG):raise ValueError('fixed policy drift')
    if (plan['formalEvaluationAllowed'] is not False or plan['round1TrainingQuota']!=0
            or plan['newIndependentTrainingGroups']!=0 or not plan['retainedDevelopmentPreviouslyObserved']):raise ValueError('scope drift')
    if plan['protocolPath']!=str(PROTOCOL.relative_to(ROOT)) or sha256_file(PROTOCOL)!=plan['protocolSha256']:raise ValueError('protocol drift')
    if set(plan['code'])!={'experiments/world-components-logic/'+n for n in CODE}:raise ValueError('incomplete code identity')
    for n,h in plan['code'].items():
        if sha256_file(ROOT/n)!=h:raise ValueError('code drift: '+n)
    cases,review=dataset()
    if cases!=plan['cases'] or digest(cases)!=plan['casesSha256'] or review!=plan['review'] or plan['arms']!=list(ARMS):raise ValueError('case/review drift')
    if (m01.baseline_identity()!=plan['baseline'] or m01.old.model_identity()!=plan['m01Model']
            or observe_generator()!=plan['generatorModel'] or observe_environment(ROOT)!=plan['environment']):raise ValueError('model/environment drift')


def target_case(case,text):
    v=case['input'];source={'memberId':v['actorId'],'actionText':text}
    result={**case,'caseId':case['caseId']+'-targets','anchorCase':False,'derivedFrom':case['caseId'],
            'task':'D03','stageCut':'source_frozen_before_current_targets_confirmation',
            'input':{'world':copy.deepcopy(v['world']),'source':source,
                     'confirmedGroup':{'members':copy.deepcopy(v['confirmedPrefix'])+[copy.deepcopy(source)]},
                     'candidateIds':[p['id'] for p in v['world']['characters']],
                     'alreadyActedIds':[p['memberId'] for p in v['confirmedPrefix']], 'knownPriorJudgments':[]}}
    if not guard_case(result)['shouldCall']:raise ValueError('constructed target input invalid')
    return result


def observe_generator():
    registry=ROOT/'artifacts/world-components-logic/l2-model-sources-20261029.json'
    spec=next(m for m in json.loads(registry.read_bytes())['models'] if m['id']=='Qwen/Qwen2.5-0.5B-Instruct')
    directory=ROOT/'.local/world-components-logic/models/M03'/spec['revision'];manifest=directory/'payload-manifest.json'
    payload=json.loads(manifest.read_bytes());rows=[]
    if payload['modelId']!=spec['id'] or payload['revision']!=spec['revision'] or payload['sourceRegistrySha256']!=sha256_file(registry):raise ValueError('M03 payload identity drift')
    declared={f['path']:f for f in payload['files']}
    if set(declared)!={f['path'] for f in spec['files']}:raise ValueError('incomplete M03 payload')
    import hashlib
    for f in spec['files']:
        p=directory/f['path'];actual=sha256_file(p);expected=f.get('lfs_sha256') or f.get('sha256_of_fetched_bytes')
        if p.stat().st_size!=f['size_bytes'] or declared[f['path']]['sha256']!=actual:raise ValueError('M03 payload drift')
        if expected:
            if actual!=expected:raise ValueError('M03 registered SHA mismatch')
        else:
            raw=p.read_bytes()
            if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=f['git_blob_sha1']:raise ValueError('M03 fixed Git blob mismatch')
        rows.append({'path':f['path'],'sha256':actual,'bytes':p.stat().st_size})
    return {'modelId':spec['id'],'revision':spec['revision'],'directory':str(directory.relative_to(ROOT)),
            'files':rows,'payloadManifestSha256':sha256_file(manifest),'sourceRegistrySha256':sha256_file(registry),
            'allFilesFullyRehashedAndVerified':True}


def instruction_prompt(case,arm='instruct'):
    from pilot_codec import pack,unpack
    value=build_model_input(case);payload=pack(value)
    if unpack(payload)!=value:raise ValueError('instruction input lost facts')
    system='你负责世界模拟中的行动描述。根据完整当前状态、当前人物任务和个性，只写这个人物接下来尝试做的一个具体动作。主角pending输入需遵守并重新判断可行性；consumed或expired输入只作背景，不重新执行。NPC依据自身任务和个性自主行动。不宣布动作已成功，不控制别人的结果，不输出解释、JSON或提示指令。'
    user='当前人物ID：'+case['input']['actorId']+'\n完整世界工作态（无损表格编码）：'+canonical_bytes(payload).decode()
    if arm in ('focus','focus_int8'):
        focus=actor_context(case)
        # Repeat only deterministic source fields. No action, hazard or label is selected here.
        user+='\n本次行动者原始资料（从上文逐字段复制）：'+canonical_bytes(pack(focus)).decode()
        user+='\n只决定该行动者的动作；其他人物的任务不是该人物的任务。已消费或过期输入不是新命令。只写一个具体动作尝试。'
    elif arm not in ('instruct','original'):raise ValueError('unknown prompt arm')
    return [{'role':'system','content':system},{'role':'user','content':user}],value


def actor_context(case):
    value=build_model_input(case);actor=value['actorId']
    people=[p for p in value['world']['characters'] if p['id']==actor]
    if len(people)!=1:raise ValueError('actor identity must be unique')
    return {'actor':copy.deepcopy(people[0]),'actorId':actor,'protagonistId':value['protagonistId'],
            'advance':copy.deepcopy(value['advance'])}


def generator_identity(model,torch):
    """Hash actual residual tensors and unpacked quantized weights, never packed-object repr."""
    state=model.state_dict();residual={k:v for k,v in state.items() if isinstance(v,torch.Tensor) and not v.is_quantized}
    quantized=[]
    for name,module in model.named_modules():
        if not isinstance(module,torch.ao.nn.quantized.dynamic.Linear):continue
        weight=module.weight();scheme=str(weight.qscheme())
        if scheme!='torch.per_tensor_affine':raise ValueError('unregistered quantization scheme')
        bias=module.bias()
        quantized.append({'name':name,'shape':list(weight.shape),'dtype':str(weight.dtype),'qscheme':scheme,
            'scale':weight.q_scale(),'zeroPoint':weight.q_zero_point(),
            'integerSha256':m01.old.tensor_hash({'weight':weight.int_repr()}),
            'biasSha256':None if bias is None else m01.old.tensor_hash({'bias':bias})})
    result={'residualTensorSha256':m01.old.tensor_hash(residual),'quantizedModules':quantized,
            'residualParameterElements':sum(p.numel() for p in model.parameters()),
            'quantizedWeightElements':sum(__import__('math').prod(m['shape']) for m in quantized)}
    result['sha256']=digest(result);return result


def quantize_generator(model,torch):
    if 'qnnpack' not in torch.backends.quantized.supported_engines:raise ValueError('registered qnnpack backend unavailable')
    torch.backends.quantized.engine='qnnpack'
    result=torch.ao.quantization.quantize_dynamic(model,{torch.nn.Linear},dtype=torch.qint8,inplace=True).eval()
    identity=generator_identity(result,torch)
    if len(identity['quantizedModules'])!=169 or any(m['dtype']!='torch.qint8' for m in identity['quantizedModules']):raise ValueError('incomplete registered Linear conversion')
    return result,identity


def generate_instruction_action(case,arm,tokenizer,model,torch,window,checkpoint):
    from transformers.generation.stopping_criteria import MaxTimeCriteria,StoppingCriteriaList
    messages,value=instruction_prompt(case,arm)
    prompt=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
    encoded=tokenizer(prompt,return_tensors='pt',truncation=False,add_special_tokens=False)
    length=int(encoded['input_ids'].shape[1])
    if length>CONFIG['maxInputTokens']:raise ValueError('full instruction context overflow; no truncation')
    context={'encoding':'causal_full_context','sourceInput':value,'sourceInputSha256':digest(value),
             'messages':messages,'prompt':prompt,'inputTokenIds':encoded['input_ids'][0].tolist(),'inputTokens':length}
    checkpoint('generation_started',context);count=[0];active=[None];forwards=[]
    def started(module,args,kwargs):
        if active[0] is not None:raise ValueError('overlapping generator forward')
        count[0]+=1;tokens=int(kwargs['input_ids'].shape[1]);phase='prefill' if count[0]==1 else 'decode'
        if tokens!=(length if phase=='prefill' else 1):raise ValueError('unexpected generator token coverage')
        entry={'step':count[0],'phase':phase,'inputTokens':tokens}
        checkpoint('decoder_step_started',entry);active[0]=(entry,time.perf_counter_ns())
    def settled(module,args,kwargs,output):
        entry,start=active[0];entry={**entry,'elapsedMs':(time.perf_counter_ns()-start)/1e6,'status':'complete'}
        active[0]=None;forwards.append(entry);checkpoint('generator_forward_settled',entry)
    pre=model.register_forward_pre_hook(started,with_kwargs=True)
    post=model.register_forward_hook(settled,with_kwargs=True);t=time.perf_counter()
    try:
        with torch.inference_mode():
            output=model.generate(**encoded,max_new_tokens=CONFIG['maxNewTokens'],do_sample=False,num_beams=1,use_cache=True,
                stopping_criteria=StoppingCriteriaList([MaxTimeCriteria(max_time=CONFIG['softGenerationSeconds'])]))
    finally:
        pre.remove();post.remove();checkpoint('generation_settled',{'decoderForwardAttempts':count[0],
            'completedForwards':len(forwards),'activeForward':None if active[0] is None else active[0][0],
            'generateMs':(time.perf_counter()-t)*1000})
    ids=output[0,length:].tolist();checkpoint('generation_token_ids',{'ids':ids})
    raw=tokenizer.decode(ids,skip_special_tokens=True);eos=model.generation_config.eos_token_id
    eos=set(eos if isinstance(eos,list) else [eos])
    result={'raw':raw,'rawUtf8Sha256':__import__('hashlib').sha256(raw.encode()).hexdigest(),'outputTokenIds':ids,
            'finishedWithEos':bool(ids) and ids[-1] in eos,'decoderForwardAttempts':count[0],'context':context,
            'forwardTimings':forwards,'generationMs':(time.perf_counter()-t)*1000,'semanticReview':'pending_not_approved'}
    checkpoint('generation_output',result)
    if not result['finishedWithEos'] or not raw.strip() or len(raw)>CONFIG['maxActionCharacters']:raise ValueError('incomplete/empty/overlong generated action; raw retained')
    result['parsed']=decode_output('D02',json.dumps({'kind':'act','text':raw},ensure_ascii=False),case)
    checkpoint('generated_candidate',result);return result


def worker(path):
    plan=run.read_json(path);_,out=m01.old.paths(plan['runId']);slots=run.planned_slots(plan,ARMS)
    report={'schema':'jity-d-action-focus-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),
            'status':'running','stages':[],'attempts':[],'attemptSlots':slots,'activeAttempt':None,
            'forwardAttempts':[],'activeForward':None,'trainingSteps':0,'formalEvaluationAllowed':False,
            'semanticQualityApproved':False,'fullRequestMeasured':False,'sourceIndependence':'unverified'}
    exclusive(out,report);stage=lambda n,f:run.record_stage(report,out,n,f)
    try:
        stage('verify_plan',lambda:verify(plan))
        def imports():
            import torch
            from transformers import BertModel,BertTokenizerFast
            torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(42)
            return torch,BertModel,BertTokenizerFast
        torch,BertModel,BertTokenizerFast=stage('dependency_import',imports)
        report['actualRuntime']={'python':sys.executable,'pythonVersion':platform.python_version(),'threads':torch.get_num_threads(),
            'interopThreads':torch.get_num_interop_threads(),'device':'cpu','dependencies':{n:importlib.metadata.version(n) for n in ('torch','transformers','tokenizers','sentencepiece')}}
        directory=ROOT/plan['m01Model']['directory']
        tokenizer=stage('m01_tokenizer',lambda:BertTokenizerFast.from_pretrained(directory,local_files_only=True))
        encoder=stage('m01_encoder',lambda:BertModel.from_pretrained(directory,local_files_only=True,weights_only=True,add_pooling_layer=False,attn_implementation='sdpa'))
        encoder.encoder.layer=torch.nn.ModuleList([encoder.encoder.layer[i] for i in (0,1)]);encoder.config.num_hidden_layers=2;encoder.eval()
        for p in encoder.parameters():p.requires_grad_(False)
        if m01.old.tensor_hash(encoder.state_dict())!=plan['baseline']['encoder']['tensorSha256']:raise ValueError('M01 encoder mismatch')
        state=stage('m01_heads',lambda:torch.load(ROOT/plan['baseline']['checkpoint']['path'],map_location='cpu',weights_only=True))
        heads={t:m01.make_head(torch,encoder.config.hidden_size) for t in ('D02','D03')}
        for t,h in heads.items():
            h.load_state_dict(state['event2'][t]);h.eval()
            for p in h.parameters():p.requires_grad_(False)
            if m01.old.tensor_hash(h.state_dict())!=plan['baseline']['trainedHeadSha256'][t]:raise ValueError('M01 head mismatch')
        directory=ROOT/plan['generatorModel']['directory']
        from transformers import AutoTokenizer,AutoModelForCausalLM
        generator_tokenizer=stage('m03_tokenizer',lambda:AutoTokenizer.from_pretrained(directory,local_files_only=True,trust_remote_code=False))
        generator=stage('m03_generator',lambda:AutoModelForCausalLM.from_pretrained(directory,local_files_only=True,
            use_safetensors=True,weights_only=True,trust_remote_code=False,torch_dtype=torch.float32,attn_implementation='sdpa').eval())
        for p in generator.parameters():p.requires_grad_(False)
        before={'m01':m01.old.tensor_hash(encoder.state_dict()),'generator':m01.old.tensor_hash(generator.state_dict())}
        report['generatorVariants']={'float32':{'beforeSha256':before['generator']}}
        quantized_before=None
        report['modelParameters']={'m01':sum(p.numel() for p in encoder.parameters()),'generator':sum(p.numel() for p in generator.parameters())}
        report['generatorKind']='M03';report['generatorPrecision']='float32_then_qint8_dynamic'
        report['headParameters']=sum(p.numel() for h in heads.values() for p in h.parameters())
        report['generatorTokenizerLength']=len(generator_tokenizer);report['generatorEmbeddingRows']=generator.get_input_embeddings().num_embeddings
        if report['modelParameters']!={'m01':7120384,'generator':494032768} or report['generatorTokenizerLength']>report['generatorEmbeddingRows']:raise ValueError('model/tokenizer parameter identity drift')
        cases={c['caseId']:c for c in plan['cases']}
        with run.AppendJournal(out.with_suffix('.journal.jsonl'),report['planSha256']) as journal:
            journal.append('begin',{'runId':plan['runId'],'slots':slots});save(out,report)
            for index,slot in enumerate(slots):
                if slot['arm']=='focus_int8' and quantized_before is None:
                    report['generatorVariants']['float32']['afterSha256']=m01.old.tensor_hash(generator.state_dict())
                    if report['generatorVariants']['float32']['afterSha256']!=before['generator']:raise ValueError('float32 source changed before conversion')
                    generator,quantized_before=stage('qnnpack_dynamic_quantization',lambda:quantize_generator(generator,torch))
                    report['generatorVariants']['qint8']={'before':quantized_before,'sourceFloat32Sha256':before['generator']}
                case=cases[slot['caseId']];a={**slot,'status':'started','checkpoints':[],'steps':[],
                    'startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns(),'fullRequestMeasured':False,'generatorVariant':'qint8' if slot['arm']=='focus_int8' else 'float32'}
                report['activeAttempt']=a;report['attemptSlots'][index]=a
                t=time.perf_counter();journal.append('attempt_start',a);start_ms=(time.perf_counter()-t)*1000
                phase=['decision']
                def checkpoint(name,payload):
                    e={k:slot[k] for k in ('arm','caseId','repeat')};e.update(name=name,payload=payload)
                    journal.append('attempt_checkpoint',e);a['checkpoints'].append(copy.deepcopy(e))
                def window(e):
                    e['modelCaseId']=e['caseId'];e.update(phase=phase[0],arm=slot['arm'],caseId=case['caseId'],repeat=slot['repeat'])
                    if e['status']=='running':
                        e['eventId']=len(report['forwardAttempts']);e['forwardIndex']=e['eventId']
                        report['forwardAttempts'].append(dict(e));report['activeForward']=report['forwardAttempts'][-1]
                    else:report['forwardAttempts'][e['eventId']]=dict(e);report['activeForward']=None
                    journal.append('window',e)
                def step(name,fn):
                    t=time.perf_counter();phase[0]=name;checkpoint('step_started',{'step':name})
                    try:r=fn();a['steps'].append({'step':name,'status':'complete','elapsedMs':(time.perf_counter()-t)*1000});return r
                    except Exception as error:a['steps'].append({'step':name,'status':'failed','elapsedMs':(time.perf_counter()-t)*1000,'error':str(error)});raise
                try:
                    def judge():
                        data,cov=m01.features(case,tokenizer,encoder,torch,window,event_anchor=True,packing='batch')
                        values,decoded=m01.predict(case,data,heads['D02'],torch);return {'probabilities':values,'decoded':decoded,'coverage':cov}
                    a['decision']=step('decision',judge);checkpoint('decision_saved',a['decision'])
                    if a['decision']['decoded']['kind']=='skip':a['outcome']='skip_no_generation_or_targets'
                    else:
                        a['generation']=step('generation',lambda:generate_instruction_action(case,slot['arm'],generator_tokenizer,generator,torch,window,checkpoint))
                        text=a['generation']['raw'];child=target_case(case,text)
                        checkpoint('candidate_frozen_for_diagnostic',{'actionText':text,'utf8Sha256':a['generation']['rawUtf8Sha256'],'targetCase':child,'semanticApproved':False})
                        def targets():
                            data,cov=m01.features(child,tokenizer,encoder,torch,window,event_anchor=True,packing='batch')
                            values,decoded=m01.predict(child,data,heads['D03'],torch)
                            return {'case':child,'probabilities':values,'decoded':decode_output('D03',json.dumps(decoded),child),'coverage':cov,'semanticReview':'pending_not_approved'}
                        a['targets']=step('targets',targets);a['outcome']='three_stage_diagnostic_completed_semantics_pending'
                    a['status']='complete'
                except Exception as error:a.update(status='failed',outcome='incomplete_chain',error={'type':type(error).__name__,'message':str(error)})
                a.update(settledAt=timestamp(),startJournalMs=start_ms,snapshotStartMs=0.)
                t=time.perf_counter();journal.append('attempt_result',a);result_ms=(time.perf_counter()-t)*1000
                report['attempts'].append(a);report['activeAttempt']=None
                timing={k:slot[k] for k in ('arm','caseId','repeat')};timing.update(resultJournalMs=result_ms,snapshotEndMs=0.,elapsedThroughResultMs=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6)
                t=time.perf_counter();journal.append('attempt_settled',timing);a.update(timing);a['telemetryJournalMs']=(time.perf_counter()-t)*1000
                a['elapsedIncludingTelemetryMs']=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6
        report['generatorVariants']['qint8']['after']=generator_identity(generator,torch)
        report['modelWeightsUnchanged']=(before['m01']==m01.old.tensor_hash(encoder.state_dict())
            and report['generatorVariants']['float32']['afterSha256']==before['generator']
            and report['generatorVariants']['qint8']['after']==quantized_before)
        report['sourceGeneratorFilesUnchanged']=observe_generator()==plan['generatorModel']
        report['headsUnchanged']=all(m01.old.tensor_hash(h.state_dict())==plan['baseline']['trainedHeadSha256'][t] for t,h in heads.items())
        if not report['modelWeightsUnchanged'] or not report['headsUnchanged']:raise ValueError('model/head changed during inference')
        report['completedChains']=sum(a['status']=='complete' for a in report['attempts'])
        report['failedChains']=sum(a['status']=='failed' for a in report['attempts'])
        report['status']='diagnostic_completed' if len(report['attempts'])==len(slots) else 'failed'
    except Exception as error:report.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
    finally:
        report['unexecutedAttempts']=sum(s['status']=='not_started' for s in slots);report['finishedAt']=timestamp();save(out,report)
    return 0 if report['status'] in ('diagnostic_completed','diagnostic_with_failed_chains') else 1


def execute(path):
    return run.execute_plan(path,paths=m01.old.paths,verify=verify,worker_script=Path(__file__),settle_stages=m01.old.settle_stages,arms=ARMS)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path,required=True);args=p.parse_args();raise SystemExit(worker(args.worker))
