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
from fact_windows import flatten,restore,fact_text
from lab import build_model_input,guard_case,decode_output,canonical_bytes,sha256_file
from prepare_run_batch import observe_environment,observe_m02
from run_pilot import digest,exclusive,save,timestamp

ROOT=m01.ROOT;BASE=m01.BASE;ART=m01.ART
PROTOCOL=ROOT/'design/world-engine-reports/components-logic/action-chain-probe-r2.md'
CASES=('dev-d02-01','dev-d02-03','dev-d02-05','dev-d02-07')
ARMS=('qa','summary')
CONFIG={'device':'cpu','threads':1,'concurrency':1,'attemptsPerCase':3,'trainingSteps':0,
        'processWallSeconds':120,'maxResidentMiB':2048,'seed':42,'threshold':.5,
        'maxInputTokensPerWindow':512,'maxNewTokens':64,'softGenerationSeconds':3,
        'maxActionCharacters':240,'doSample':False,'numBeams':1,'featureCacheForTiming':False,
        'generationEncoding':'all_atomic_facts_fused_in_decoder','local50msHardGate':False,
        'fullNonNarrativeTargetMs':500,'chainScope':'D02_decision_action_text_D03_only'}
CODE=('experiment.py','action_chain.py','m01_shared.py','m01_probe.py','fact_windows.py','pilot_codec.py',
      'lab.py','run_pilot.py','review_io.py','prepare_run_batch.py')


def dataset():
    rows,review=m01.old.dataset();by_id={r['case']['caseId']:r for r in rows}
    return [by_id[c]['case'] for c in CASES],review


def prepare(run_id):
    path,out=m01.old.paths(run_id)
    if path.exists() or out.exists():raise FileExistsError('preserve prior evidence; new run id required')
    cases,review=dataset();model=observe_m02(ROOT);env=observe_environment(ROOT)
    if not model['allSixFilesFullyRehashedAndVerified'] or not env['registeredVersionsMatch']:raise ValueError('M02/environment identity invalid')
    plan={'schema':'jity-d-action-chain-plan-v1','runId':run_id,'preparedAt':timestamp(),
          'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
          'protocolPath':str(PROTOCOL.relative_to(ROOT)),'protocolSha256':sha256_file(PROTOCOL),
          'code':{'experiments/world-components-logic/'+n:sha256_file(BASE/n) for n in CODE},
          'config':CONFIG.copy(),'configSha256':digest(CONFIG),'cases':cases,'casesSha256':digest(cases),
          'review':review,'baseline':m01.baseline_identity(),'m01Model':m01.old.model_identity(),
          'm02Model':model,'environment':env,'arms':list(ARMS),
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
            or observe_m02(ROOT)!=plan['m02Model'] or observe_environment(ROOT)!=plan['environment']):raise ValueError('model/environment drift')


def generation_frames(case,tokenizer,arm,limit=512):
    if not guard_case(case)['shouldCall']:raise ValueError('guarded source input')
    value=build_model_input(case);facts=flatten(value)
    if canonical_bytes(restore(facts))!=canonical_bytes(value):raise ValueError('incomplete generation facts')
    actor_id=case['input']['actorId']
    actor=next(p for p in case['input']['world']['characters'] if p['id']==actor_id)
    from pilot_codec import pack as compact
    anchor=canonical_bytes(compact(actor)).decode('utf-8')
    status={'pending':'待判断的新命令','consumed':'已消费的历史命令','expired':'已过期的历史命令'}[case['input']['advance']['intentStatus']]
    article='当前人物资料：'+anchor+'；输入性质：'+status+'；完整世界工作态：'
    if arm=='qa':
        prefix='抽取式阅读理解任务：阅读文章【'+article
        suffix='】问题【'+actor['name']+'接下来打算怎样完成眼前的任务？】的答案是什么？'
    elif arm=='summary':
        prefix='生成式摘要任务：【'+article
        suffix='】这篇文章的摘要是什么？'
    else:raise ValueError('unknown generation arm')
    pre=tokenizer.encode(prefix,add_special_tokens=False);post=tokenizer.encode(suffix,add_special_tokens=False)
    budget=limit-len(pre)-len(post)-tokenizer.num_special_tokens_to_add(pair=False)
    if budget<=0:raise ValueError('generation prompt exceeds window')
    windows=[];ids=[];indices=[];spans=[]
    def emit():
        if not indices:return
        full=tokenizer.build_inputs_with_special_tokens(pre+ids+post)
        if len(full)>limit:raise ValueError('generation window overflow')
        windows.append({'inputIds':full,'tokenTypeIds':[0]*len(full),'factIds':indices.copy(),
            'factSpans':[{'factIndex':i,'start':len(pre)+a,'end':len(pre)+b} for i,a,b in spans],
            'payloadTokens':len(ids),'totalTokens':len(full)})
    for i,f in enumerate(facts):
        part=tokenizer.encode(fact_text(f),add_special_tokens=False)
        if not part or len(part)>budget:raise ValueError('atomic generation fact overflow/empty; no truncation')
        if len(ids)+len(part)>budget:emit();ids=[];indices=[];spans=[]
        spans.append((i,len(ids),len(ids)+len(part)));ids.extend(part);indices.append(i)
    emit()
    if [i for w in windows for i in w['factIds']]!=list(range(len(facts))):raise ValueError('missing generation facts')
    return {'prefix':prefix,'suffix':suffix,'factRecords':facts,'factSha256':digest(facts),
            'fullFactsRestored':True,'inputSha256':digest(value),'windows':windows}


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


def generate_action(case,arm,tokenizer,model,torch,window,checkpoint):
    frames=generation_frames(case,tokenizer,arm);hidden=[];encoder_ms=0.
    for index,w in enumerate(frames['windows']):
        e={'caseId':case['caseId'],'targetId':None,'windowIndex':index,**w,'status':'running',
           'startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns()};window(e)
        start=time.perf_counter()
        try:
            ids=torch.tensor([w['inputIds']],dtype=torch.long)
            with torch.inference_mode():h=model.encoder(input_ids=ids,attention_mask=torch.ones_like(ids),return_dict=True).last_hidden_state
            hidden.append(h);e.update(status='complete',hiddenSha256=m01.old.tensor_hash({'hidden':h}))
        except Exception as error:e.update(status='failed',error=str(error));raise
        finally:
            ms=(time.perf_counter()-start)*1000;encoder_ms+=ms;e.update(elapsedMs=ms,settledAt=timestamp());window(e)
    from transformers.modeling_outputs import BaseModelOutput
    from transformers.generation.stopping_criteria import MaxTimeCriteria,StoppingCriteriaList
    memory=torch.cat(hidden,dim=1);count=[0]
    def started(module,args,kwargs):
        count[0]+=1;checkpoint('decoder_step_started',{'step':count[0]})
    hook=model.decoder.register_forward_pre_hook(started,with_kwargs=True)
    checkpoint('generation_started',{'frames':frames,'encoderMs':encoder_ms,'memoryTokens':int(memory.shape[1])})
    t=time.perf_counter()
    try:
        with torch.inference_mode():
            output=model.generate(encoder_outputs=BaseModelOutput(last_hidden_state=memory),
                attention_mask=torch.ones(memory.shape[:2],dtype=torch.long),max_new_tokens=CONFIG['maxNewTokens'],
                do_sample=False,num_beams=1,use_cache=True,
                stopping_criteria=StoppingCriteriaList([MaxTimeCriteria(max_time=CONFIG['softGenerationSeconds'])]))
    finally:
        hook.remove();checkpoint('generation_settled',{'decoderForwardAttempts':count[0], 'generateMs':(time.perf_counter()-t)*1000})
    ids=output[0].tolist();checkpoint('generation_token_ids',{'ids':ids})
    raw=tokenizer.decode(output[0],skip_special_tokens=True)
    result={'raw':raw,'rawUtf8Sha256':__import__('hashlib').sha256(raw.encode()).hexdigest(),
            'outputTokenIds':ids,'finishedWithEos':bool(ids) and ids[-1]==model.generation_config.eos_token_id,
            'decoderForwardAttempts':count[0],'frames':frames,'encoderMs':encoder_ms,
            'memoryTokens':int(memory.shape[1]),'generationMs':(time.perf_counter()-t)*1000,
            'semanticReview':'pending_not_approved'}
    checkpoint('generation_output',result)
    if not result['finishedWithEos']:raise ValueError('generation incomplete; raw output retained in checkpoint: '+str(ids))
    if len(raw)>CONFIG['maxActionCharacters'] or not raw.strip():raise ValueError('empty/overlong generated action')
    result['parsed']=decode_output('D02',json.dumps({'kind':'act','text':raw},ensure_ascii=False),case)
    checkpoint('generated_candidate',result)
    return result


def worker(path):
    plan=run.read_json(path);_,out=m01.old.paths(plan['runId']);slots=run.planned_slots(plan,ARMS)
    report={'schema':'jity-d-action-chain-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),
            'status':'running','stages':[],'attempts':[],'attemptSlots':slots,'activeAttempt':None,
            'forwardAttempts':[],'activeForward':None,'trainingSteps':0,'formalEvaluationAllowed':False,
            'semanticQualityApproved':False,'fullRequestMeasured':False,'sourceIndependence':'unverified'}
    exclusive(out,report);stage=lambda n,f:run.record_stage(report,out,n,f)
    try:
        stage('verify_plan',lambda:verify(plan))
        def imports():
            import torch
            from transformers import BertModel,BertTokenizerFast,T5ForConditionalGeneration,T5Tokenizer
            torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(42)
            return torch,BertModel,BertTokenizerFast,T5ForConditionalGeneration,T5Tokenizer
        torch,BertModel,BertTokenizerFast,T5Model,T5Tokenizer=stage('dependency_import',imports)
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
        directory=ROOT/plan['m02Model']['directory']
        generator_tokenizer=stage('m02_tokenizer',lambda:T5Tokenizer.from_pretrained(directory,local_files_only=True,extra_ids=0,legacy=True))
        generator=stage('m02_generator',lambda:T5Model.from_pretrained(directory,local_files_only=True,use_safetensors=True,weights_only=True).eval())
        for p in generator.parameters():p.requires_grad_(False)
        before={'m01':m01.old.tensor_hash(encoder.state_dict()),'m02':m01.old.tensor_hash(generator.state_dict())}
        report['modelParameters']={'m01':sum(p.numel() for p in encoder.parameters()),'m02':sum(p.numel() for p in generator.parameters())}
        report['headParameters']=sum(p.numel() for h in heads.values() for p in h.parameters())
        report['m02TokenizerLength']=len(generator_tokenizer);report['m02EmbeddingRows']=generator.get_input_embeddings().num_embeddings
        if report['modelParameters']!={'m01':7120384,'m02':77440384} or report['m02TokenizerLength']!=report['m02EmbeddingRows']:raise ValueError('model/tokenizer parameter identity drift')
        cases={c['caseId']:c for c in plan['cases']}
        with run.AppendJournal(out.with_suffix('.journal.jsonl'),report['planSha256']) as journal:
            journal.append('begin',{'runId':plan['runId'],'slots':slots});save(out,report)
            for index,slot in enumerate(slots):
                case=cases[slot['caseId']];a={**slot,'status':'started','checkpoints':[],'steps':[],
                    'startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns(),'fullRequestMeasured':False}
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
                        a['generation']=step('generation',lambda:generate_action(case,slot['arm'],generator_tokenizer,generator,torch,window,checkpoint))
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
        report['modelWeightsUnchanged']=before=={'m01':m01.old.tensor_hash(encoder.state_dict()),'m02':m01.old.tensor_hash(generator.state_dict())}
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
