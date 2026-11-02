"""Separate inference batch: fixed trained-head identity, append-only trace.

No optimization step, cached features or label-dependent routing occurs here.
The same retained-development cases are observations, never fresh holdout data.
"""
from __future__ import annotations

import argparse
import gzip
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time

import m01_probe as fit
from lab import canonical_bytes,sha256_file
from run_pilot import exclusive,save,timestamp,digest,peak_rss_mib,settle_interrupted
from prepare_run_batch import observe_environment

ROOT,BASE,ART=fit.ROOT,fit.BASE,fit.ART
CONFIG={'device':'cpu','threads':1,'concurrency':1,'seed':42,'limit':512,'threshold':.5,
        'attemptsPerCase':5,'processWallSeconds':120,'maxResidentMiB':2048,'featureCacheForTiming':False,
        'windowJournal':'append_only_start_and_settle','trainingPerformed':False}


def read_record(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)


def prepare(run_id,fit_record):
    path,out=fit.paths(run_id)
    if path.exists() or out.exists():raise FileExistsError('use a new run id')
    record=read_record(fit_record)
    if record['status']!='diagnostic_completed' or not record['encoderUnchanged']:raise ValueError('fit did not complete with frozen encoder')
    checkpoint=record['checkpoint']
    if sha256_file(ROOT/checkpoint['path'])!=checkpoint['sha256']:raise ValueError('trained checkpoint mismatch')
    fit_plan=ART/f"{record['runId']}.plan.json"
    if sha256_file(fit_plan)!=record['planSha256']:raise ValueError('fit plan mismatch')
    original=json.loads(fit_plan.read_text(encoding='utf-8'));rows,review=fit.dataset()
    if rows!=original['dataset'] or review!=original['review']:raise ValueError('fitting data provenance changed')
    code=[BASE/'m01_infer.py',BASE/'m01_probe.py',BASE/'fact_windows.py',BASE/'pilot_codec.py',BASE/'run_pilot.py',BASE/'lab.py',BASE/'prepare_run_batch.py',BASE/'review_io.py']
    plan={'schema':'jity-d-m01-inference-probe-plan-v1','runId':run_id,'preparedAt':timestamp(),
          'config':dict(CONFIG),'configSha256':digest(CONFIG),'cases':original['cases'],'review':review,
          'fitRecord':{'path':str(fit_record.relative_to(ROOT)),'sha256':sha256_file(fit_record)},
          'fitPlanSha256':sha256_file(fit_plan),'fitDatasetSha256':original['datasetSha256'],
          'checkpoint':checkpoint,'trainedHeadSha256':record['trainedHeadSha256'],
          'model':fit.model_identity(),'environment':observe_environment(ROOT),
          'code':{str(p.relative_to(ROOT)):sha256_file(p) for p in code},
          'protocolSha256':sha256_file(fit.PROTOCOL),'authorization':{'instruction':'继续工作至下一个提交','scope':'bounded_single_thread_inference_on_fixed_fitting_probe_checkpoint'},
          'formalEvaluationAllowed':False,'round1TrainingQuota':0,'sourceIndependence':'unverified',
          'selectionChangedSinceFit':False,'learningConfigurationChanged':False}
    exclusive(path,plan);return path


def verify(plan):
    if canonical_bytes(plan['config'])!=canonical_bytes(CONFIG) or plan['configSha256']!=digest(CONFIG):raise ValueError('inference policy drift')
    if plan['formalEvaluationAllowed'] is not False or plan['round1TrainingQuota']!=0:raise ValueError('invalid scope')
    for name,h in plan['code'].items():
        if sha256_file(ROOT/name)!=h:raise ValueError('code drift: '+name)
    if sha256_file(fit.PROTOCOL)!=plan['protocolSha256'] or observe_environment(ROOT)!=plan['environment'] or fit.model_identity()!=plan['model']:raise ValueError('protocol/environment/model drift')
    record=read_record(ROOT/plan['fitRecord']['path'])
    if sha256_file(ROOT/plan['fitRecord']['path'])!=plan['fitRecord']['sha256']:raise ValueError('fit evidence drift')
    original=json.loads((ART/f"{record['runId']}.plan.json").read_text(encoding='utf-8'))
    rows,review=fit.dataset()
    expected=[r['case'] for r in rows if r['role']=='retained_development']
    if plan['cases']!=expected or plan['cases']!=original['cases'] or rows!=original['dataset'] or plan['review']!=review:raise ValueError('retained-case/data binding drift')
    if sha256_file(ROOT/plan['checkpoint']['path'])!=plan['checkpoint']['sha256'] or plan['checkpoint']!=record['checkpoint'] or plan['trainedHeadSha256']!=record['trainedHeadSha256']:raise ValueError('checkpoint binding drift')


def worker(path):
    plan=json.loads(path.read_text(encoding='utf-8'));_,out=fit.paths(plan['runId']);events=out.with_suffix('.windows.jsonl')
    report={'schema':'jity-d-m01-inference-probe-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),
            'status':'running','stages':[],'attempts':[],'activeAttempt':None,
            'attemptSlots':[{'caseId':c['caseId'],'repeat':i,'status':'not_started'} for i in range(5) for c in plan['cases']],
            'formalEvaluationAllowed':False,'fullRequestMeasured':False,'trainingPerformed':False,
            'windowEventsPath':str(events.relative_to(ROOT)),'sourceIndependence':'unverified'}
    exclusive(out,report)
    def stage(name,fn):
        s={'stage':name,'status':'running','startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns()};report['stages'].append(s);save(out,report)
        try:value=fn();s['status']='complete';return value
        except Exception as e:s.update(status='failed',error=str(e));raise
        finally:s.update(settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns());s['elapsedMs']=(s['settledMonotonicNs']-s['startedMonotonicNs'])/1e6;save(out,report)
    try:
        stage('verify_frozen_inference_batch',lambda:verify(plan))
        def stack():
            import torch
            from transformers import BertModel,BertTokenizer
            torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(42)
            return torch,BertModel,BertTokenizer
        torch,BertModel,BertTokenizer=stage('dependency_import',stack)
        report['actualRuntime']={'python':sys.executable,'pythonVersion':platform.python_version(),'device':'cpu',
             'threads':torch.get_num_threads(),'interopThreads':torch.get_num_interop_threads(),
             'dependencies':{n:importlib.metadata.version(n) for n in ('torch','transformers','tokenizers','numpy')}}
        directory=ROOT/plan['model']['directory'];tokenizer=stage('tokenizer_load',lambda:BertTokenizer.from_pretrained(directory,local_files_only=True))
        encoder,info=stage('encoder_load',lambda:BertModel.from_pretrained(directory,local_files_only=True,trust_remote_code=False,weights_only=True,add_pooling_layer=False,output_loading_info=True))
        if info['missing_keys'] or info.get('mismatched_keys') or any(not k.startswith('cls.') for k in info['unexpected_keys']):raise ValueError('incomplete encoder')
        encoder.eval()
        for p in encoder.parameters():p.requires_grad_(False)
        states=stage('verified_trained_heads_load',lambda:torch.load(ROOT/plan['checkpoint']['path'],map_location='cpu',weights_only=True))
        heads={t:torch.nn.Linear(encoder.config.hidden_size,1) for t in ('D02','D03')}
        for task,head in heads.items():
            head.load_state_dict(states[task],strict=True);head.eval()
            if fit.tensor_hash(head.state_dict())!=plan['trainedHeadSha256'][task]:raise ValueError('head tensor identity mismatch')
        report['encoderParameters']=sum(p.numel() for p in encoder.parameters());report['headParameters']=sum(p.numel() for h in heads.values() for p in h.parameters())
        with events.open('x',encoding='utf-8') as eventlog:
            sequence=0
            def journal(value):
                nonlocal sequence
                if value['status']=='running':value['eventId']=sequence;sequence+=1
                eventlog.write(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n');eventlog.flush()
            for repeat in range(5):
                for offset,case in enumerate(plan['cases']):
                    i=repeat*len(plan['cases'])+offset;t=time.perf_counter()
                    a={'caseId':case['caseId'],'task':case['task'],'repeat':repeat,'status':'started','activeStage':'full_window_inference',
                       'startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns(),'featureCacheUsed':False,'generationStarted':False,'fullRequestMeasured':False}
                    report['activeAttempt']=a;report['attemptSlots'][i]=a;save(out,report)
                    try:
                        vectors,coverage=fit.features(case,tokenizer,encoder,torch,on_window=journal)
                        h=time.perf_counter();probabilities,decoded=fit.score(case,vectors,heads[case['task']],torch,.5)
                        a.update(status='complete',inputSha256=digest(case['input']),probabilities=probabilities,decoded=decoded,
                                 coverage=coverage,headMs=(time.perf_counter()-h)*1000)
                    except Exception as e:a.update(status='failed',error={'type':type(e).__name__,'message':str(e)})
                    finally:a.update(settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns(),elapsedMs=(time.perf_counter()-t)*1000)
                    report['attempts'].append(a);report['activeAttempt']=None;save(out,report)
        report['status']='diagnostic_completed'
    except Exception as e:report.update(status='failed',error={'type':type(e).__name__,'message':str(e)})
    finally:
        report['peakResidentMiB']=peak_rss_mib();report['finishedAt']=timestamp()
        if report['activeAttempt'] is not None:settle_interrupted(report,plan,'worker_exception')
        report['unexecutedAttempts']=sum(a['status']=='not_started' for a in report['attemptSlots'])
        if events.exists():report['windowEventsSha256']=sha256_file(events)
        save(out,report)
    return 0 if report['status']=='diagnostic_completed' else 1


def execute(path):
    result=fit.execute(path,verify_fn=verify,worker_script=Path(__file__))
    plan=json.loads(path.read_text(encoding='utf-8'));_,out=fit.paths(plan['runId']);report=json.loads(out.read_text(encoding='utf-8'))
    events=out.with_suffix('.windows.jsonl')
    if events.exists():
        active={};malformed=[]
        for i,line in enumerate(events.read_text(encoding='utf-8').splitlines()):
            try:v=json.loads(line)
            except ValueError:malformed.append(i);continue
            if v['status']=='running':active[v['eventId']]=v
            else:active.pop(v['eventId'],None)
        with events.open('a',encoding='utf-8') as stream:
            for v in active.values():
                v.update(status='interrupted',stopReason=report['supervisor']['stopReason'] or 'worker_exit',settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns())
                v['elapsedMs']=(v['settledMonotonicNs']-v['startedMonotonicNs'])/1e6
                stream.write('\n'+json.dumps(v,ensure_ascii=False,separators=(',',':'))+'\n')
        report['windowEventsSha256']=sha256_file(events);report['windowEventMalformedLines']=malformed;save(out,report)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--prepare');m.add_argument('--execute',type=Path);m.add_argument('--worker',type=Path)
    p.add_argument('--from-fit-record',type=Path);a=p.parse_args()
    if a.prepare:
        if a.from_fit_record is None:p.error('--from-fit-record required')
        print(prepare(a.prepare,a.from_fit_record.resolve()));return 0
    return execute(a.execute) if a.execute else worker(a.worker)


if __name__=='__main__':raise SystemExit(main())
