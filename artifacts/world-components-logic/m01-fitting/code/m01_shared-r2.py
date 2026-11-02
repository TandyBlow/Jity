"""Shared full-fact encoding and learned candidate fusion; development probe only.

No model import at module load. Prior inference code/evidence remains immutable.
"""
from __future__ import annotations

import argparse
import gzip
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

import m01_probe as old
from fact_windows import fact_text, make_windows, restore
from lab import build_model_input, canonical_bytes, guard_case, sha256_file
from run_pilot import digest, exclusive, save, timestamp
from prepare_run_batch import observe_environment

ROOT=old.ROOT
BASE=old.BASE
ART=old.ART
PROTOCOL=ROOT/'design/world-engine-reports/components-logic/m01-shared-probe.md'
OLD_PLAN=ART/'m01-fit-dev42-20261102-r1.plan.json'
OLD_RECORD=ART/'m01-fit-dev42-20261102-r1.record.json.gz'
ARMS=('legacy','shared')
CONFIG={'device':'cpu','threads':1,'concurrency':1,'seed':42,'limit':512,
        'stepsPerHead':200,'learningRate':.01,'weightDecay':.01,'threshold':.5,
        'fusionWidth':32,'attemptsPerCase':5,'processWallSeconds':120,
        'maxResidentMiB':2048,'encoderFrozen':True,'earlyStopping':False,
        'featureCacheForTiming':False,'featureCacheForFitOnly':True}


def read_json(path):
    raw=Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith('.gz') else raw)


def baseline_identity():
    p=read_json(OLD_PLAN);r=read_json(OLD_RECORD)
    if r['planSha256']!=sha256_file(OLD_PLAN) or r['status']!='diagnostic_completed' or not r['encoderUnchanged']:
        raise ValueError('invalid original fit evidence')
    if sha256_file(ROOT/r['checkpoint']['path'])!=r['checkpoint']['sha256']:
        raise ValueError('original checkpoint bytes drift')
    return {'planSha256':sha256_file(OLD_PLAN),'recordSha256':sha256_file(OLD_RECORD),
            'datasetSha256':p['datasetSha256'],'checkpoint':r['checkpoint'],
            'trainedHeadSha256':r['trainedHeadSha256'],'model':p['model']}


def prepare(run_id):
    path,out=old.paths(run_id)
    if path.exists() or out.exists():raise FileExistsError('use a new run id; preserve evidence')
    rows,review=old.dataset();baseline=baseline_identity();model=old.model_identity()
    if baseline['datasetSha256']!=digest(rows) or model!=baseline['model']:raise ValueError('baseline dataset/model drift')
    code=[BASE/name for name in ('m01_shared.py','m01_probe.py','fact_windows.py','pilot_codec.py','lab.py','run_pilot.py','review_io.py','prepare_run_batch.py')]
    plan={'schema':'jity-d-m01-shared-probe-plan-v1','runId':run_id,'preparedAt':timestamp(),
          'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
          'protocolSha256':sha256_file(PROTOCOL),'code':{str(p.relative_to(ROOT)):sha256_file(p) for p in code},
          'config':CONFIG.copy(),'configSha256':digest(CONFIG),'dataset':rows,'datasetSha256':digest(rows),
          'cases':[r['case'] for r in rows if r['role']=='retained_development'],
          'review':review,'model':model,'baseline':baseline,'environment':observe_environment(ROOT),
          'authorization':{'instruction':'好继续工作','scope':'bounded_D_single_thread_shared_encoder_development_probe'},
          'arms':list(ARMS),'formalEvaluationAllowed':False,'sourceIndependence':'unverified',
          'retainedDevelopmentPreviouslyObserved':True,'newIndependentTrainingGroups':0,'round1TrainingQuota':0}
    exclusive(path,plan)
    return path


def verify(plan):
    if (plan['formalEvaluationAllowed'] is not False or plan['round1TrainingQuota']!=0
            or plan['newIndependentTrainingGroups']!=0 or plan['retainedDevelopmentPreviouslyObserved'] is not True):
        raise ValueError('probe scope drift')
    if plan['config']!=CONFIG or plan['configSha256']!=digest(CONFIG):raise ValueError('fixed policy drift')
    if plan['protocolSha256']!=sha256_file(PROTOCOL):raise ValueError('protocol drift')
    expected={'experiments/world-components-logic/'+n for n in ('m01_shared.py','m01_probe.py','fact_windows.py','pilot_codec.py','lab.py','run_pilot.py','review_io.py','prepare_run_batch.py')}
    if set(plan['code'])!=expected:raise ValueError('incomplete code identity')
    for name,h in plan['code'].items():
        if sha256_file(ROOT/name)!=h:raise ValueError('code drift: '+name)
    rows,review=old.dataset()
    if rows!=plan['dataset'] or digest(rows)!=plan['datasetSha256'] or review!=plan['review']:raise ValueError('dataset/review drift')
    if plan['cases']!=[r['case'] for r in rows if r['role']=='retained_development'] or plan['arms']!=list(ARMS):
        raise ValueError('comparison cases/arms drift')
    if baseline_identity()!=plan['baseline']:raise ValueError('baseline identity drift')
    if (old.model_identity()!=plan['model'] or plan['model']!=plan['baseline']['model']
            or plan['datasetSha256']!=plan['baseline']['datasetSha256'] or observe_environment(ROOT)!=plan['environment']):
        raise ValueError('model/environment drift')


def shared_prefix(case):
    v=case['input']
    return ('行动选择判断；当前人物='+v['actorId'] if case['task']=='D02' else
            '牵连关系判断；冻结源='+v['source']['memberId'])+'。全部窗口共同提供完整场景，逐人判断。'


def pack(case,tokenizer,limit=512):
    if not guard_case(case)['shouldCall']:raise ValueError('guarded input')
    value=build_model_input(case);prefix=shared_prefix(case)
    facts,windows=make_windows(value,tokenizer,prefix,limit)
    # Reconstruct the exact BERT pair payload, so fact pools cannot point at
    # a prefix, separator, another fact or a silently dropped token.
    prefix_ids=tokenizer.encode(prefix,add_special_tokens=False)
    for w in windows:
        start=len(prefix_ids)+2;spans=[]
        for i in w['factIds']:
            ids=tokenizer.encode(fact_text(facts[i]),add_special_tokens=False)
            if not ids or w['inputIds'][start:start+len(ids)]!=ids:raise ValueError('fact token span mismatch')
            spans.append({'factIndex':i,'start':start,'end':start+len(ids)});start+=len(ids)
        if start!=len(w['inputIds'])-1:raise ValueError('uncovered payload tokens')
        w['factSpans']=spans
    return value,facts,windows


def pool_indices(case,facts):
    v=case['input'];people=v['world']['characters']
    by_id={p['id']:i for i,p in enumerate(people)}
    if len(by_id)!=len(people):raise ValueError('duplicate character IDs')
    targets=[v['actorId']] if case['task']=='D02' else v['candidateIds']
    if len(set(targets))!=len(targets) or any(t not in by_id for t in targets):raise ValueError('invalid candidate roster')
    def person(pid):return [i for i,f in enumerate(facts) if f['path'][:3]==['world','characters',by_id[pid]]]
    source=v['actorId'] if case['task']=='D02' else v['source']['memberId']
    if source not in by_id:raise ValueError('missing source character')
    anchor=person(source)+[i for i,f in enumerate(facts) if f['path'] and f['path'][0]==('advance' if case['task']=='D02' else 'source')]
    candidates=[person(t) for t in targets]
    if not anchor or any(not c for c in candidates):raise ValueError('empty source/candidate facts')
    return targets,anchor,candidates


def features(case,tokenizer,encoder,torch,on_window=None):
    t=time.perf_counter();value,facts,windows=pack(case,tokenizer)
    targets,anchor,candidates=pool_indices(case,facts);pack_ms=(time.perf_counter()-t)*1000
    vectors=[None]*len(facts);weighted=None;total=0
    for i,w in enumerate(windows):
        start=time.perf_counter();event={'caseId':case['caseId'],'targetId':None,'windowIndex':i,
            **w,'status':'running','startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns()}
        if on_window:on_window(event)
        try:
            tensors={'input_ids':torch.tensor([w['inputIds']],dtype=torch.long),
                     'token_type_ids':torch.tensor([w['tokenTypeIds']],dtype=torch.long),
                     'attention_mask':torch.ones((1,w['totalTokens']),dtype=torch.long)}
            with torch.inference_mode():hidden=encoder(**tensors).last_hidden_state[0]
            for span in w['factSpans']:
                vectors[span['factIndex']]=hidden[span['start']:span['end']].mean(dim=0).clone()
            payload=hidden[w['factSpans'][0]['start']:w['factSpans'][-1]['end']].sum(dim=0)
            weighted=payload.clone() if weighted is None else weighted+payload;total+=w['payloadTokens']
            event.update(status='complete',factVectorSha256=old.tensor_hash({str(s['factIndex']):vectors[s['factIndex']] for s in w['factSpans']}))
        except Exception as error:
            event.update(status='failed',error={'type':type(error).__name__,'message':str(error)});raise
        finally:
            event.update(elapsedMs=(time.perf_counter()-start)*1000,settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns())
            if on_window:on_window(event)
        w['forwardMs']=(time.perf_counter()-start)*1000
    if any(x is None for x in vectors):raise ValueError('missing encoded fact')
    memory=torch.stack(vectors).detach().clone()
    # clone exits inference_mode: the small learned heads need ordinary frozen
    # feature tensors for autograd, never gradients through the encoder.
    data={'memory':memory,'anchor':memory[anchor].mean(dim=0),
          'candidates':torch.stack([memory[c].mean(dim=0) for c in candidates]),
          'global':(weighted/total).detach().clone()}
    coverage={'factRecords':facts,'factSha256':digest(facts),'fullFactsRestored':canonical_bytes(restore(facts))==canonical_bytes(value),
              'targets':targets,'anchorFactIds':anchor,'candidateFactIds':candidates,'encodeAndPackMs':pack_ms,'windows':windows}
    return data,coverage


def make_head(torch,hidden,width=32):
    class FusionHead(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.query=torch.nn.Linear(hidden*4,width)
            self.key=torch.nn.Linear(hidden,width,bias=False)
            self.output=torch.nn.Sequential(torch.nn.Linear(hidden*6,width),torch.nn.Tanh(),torch.nn.Linear(width,1))
        def forward(self,data):
            norm=lambda x:torch.nn.functional.layer_norm(x,(hidden,))
            memory=norm(data['memory']);target=norm(data['candidates'])
            source=norm(data['anchor']).expand_as(target);global_=norm(data['global']).expand_as(target)
            product=source*target;delta=(source-target).abs()
            query=torch.tanh(self.query(torch.cat([source,target,product,delta],dim=-1)))
            weights=torch.softmax(query@self.key(memory).T/(width**.5),dim=-1)
            context=weights@memory
            return self.output(torch.cat([source,target,context,global_,product,delta],dim=-1)).flatten()
    return FusionHead()


def predict(case,data,head,torch):
    with torch.inference_mode():values=torch.sigmoid(head(data)).tolist()
    decoded=({'kind':'act' if values[0]>=.5 else 'skip'} if case['task']=='D02' else
             {'targets':[{'targetId':t} for t,p in zip(case['input']['candidateIds'],values) if p>=.5]})
    return values,decoded


def settle_events(report,event_path,reason):
    if not event_path.exists():return
    active={}
    malformed=[]
    for index,line in enumerate(event_path.read_text(encoding='utf-8').splitlines()):
        if not line.strip():continue
        try:e=json.loads(line)
        except ValueError:malformed.append(index);continue
        if e['status']=='running':active[e['eventId']]=e
        else:active.pop(e['eventId'],None)
    with event_path.open('a',encoding='utf-8') as f:
        for e in active.values():
            e.update(status='interrupted',stopReason=reason,settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns())
            e['elapsedMs']=(e['settledMonotonicNs']-e['startedMonotonicNs'])/1e6
            f.write('\n'+json.dumps(e,ensure_ascii=False,separators=(',',':'))+'\n')
    report['windowEventsSha256']=sha256_file(event_path)
    report['windowEventMalformedLines']=malformed


def settle_attempts(report,reason):
    active=report.get('activeAttempt')
    if active is not None:
        active=dict(active)
        active.update(status='interrupted',stopReason=reason,settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns())
        active['elapsedMs']=(active['settledMonotonicNs']-active['startedMonotonicNs'])/1e6
        key=lambda a:(a['arm'],a['caseId'],a['repeat'])
        if key(active) not in {key(a) for a in report['attempts']}:report['attempts'].append(active)
        for i,slot in enumerate(report['attemptSlots']):
            if key(slot)==key(active):report['attemptSlots'][i]=active
        report['activeAttempt']=None
    report['unexecutedAttempts']=sum(a['status']=='not_started' for a in report['attemptSlots'])


def planned_slots(plan):
    return [{'arm':arm,'caseId':c['caseId'],'repeat':rep,'status':'not_started'}
            for rep in range(plan['config']['attemptsPerCase']) for c in plan['cases']
            for arm in (ARMS if rep%2==0 else ARMS[::-1])]


def unstarted_record(plan,path):
    slots=planned_slots(plan)
    return {'status':'failed_before_journal','planSha256':sha256_file(path),'attempts':[],
            'attemptSlots':slots,'unexecutedAttempts':len(slots),'activeAttempt':None,'stages':[],
            'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequestMeasured':False}


def worker(path):
    plan=read_json(path);_,out=old.paths(plan['runId']);events=out.with_suffix('.windows.jsonl')
    slots=planned_slots(plan)
    report={'schema':'jity-d-m01-shared-probe-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),
            'status':'running','stages':[],'attempts':[],'attemptSlots':slots,'activeAttempt':None,
            'forwardAttempts':[],'activeForward':None,'featureCoverage':[],'fitLosses':{},
            'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequestMeasured':False,
            'sourceIndependence':'unverified'}
    exclusive(out,report)
    def stage(name,fn):
        s={'stage':name,'status':'running','startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns()};report['stages'].append(s);save(out,report)
        try:r=fn();s['status']='complete';return r
        except Exception as e:s.update(status='failed',error={'type':type(e).__name__,'message':str(e)});raise
        finally:s.update(elapsedMs=(time.monotonic_ns()-s['startedMonotonicNs'])/1e6,settledAt=timestamp());save(out,report)
    try:
        stage('verify_plan',lambda:verify(plan))
        def stack():
            import torch
            from transformers import BertModel,BertTokenizer
            torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(42)
            return torch,BertModel,BertTokenizer
        torch,BertModel,BertTokenizer=stage('dependency_import',stack)
        report['actualRuntime']={'python':sys.executable,'pythonVersion':platform.python_version(),'device':'cpu',
             'threads':torch.get_num_threads(),'interopThreads':torch.get_num_interop_threads(),
             'dependencies':{n:importlib.metadata.version(n) for n in ('torch','transformers','tokenizers','numpy')}}
        directory=ROOT/plan['model']['directory']
        tokenizer=stage('tokenizer_load',lambda:BertTokenizer.from_pretrained(directory,local_files_only=True))
        encoder,info=stage('encoder_load',lambda:BertModel.from_pretrained(directory,local_files_only=True,trust_remote_code=False,
                         weights_only=True,add_pooling_layer=False,output_loading_info=True))
        if info['missing_keys'] or info.get('mismatched_keys') or any(not k.startswith('cls.') for k in info['unexpected_keys']):raise ValueError('uninitialized encoder')
        encoder.eval()
        for p in encoder.parameters():p.requires_grad_(False)
        before=old.tensor_hash(encoder.state_dict());report['encoderParameters']=sum(p.numel() for p in encoder.parameters())
        legacy_state=stage('legacy_checkpoint_load',lambda:torch.load(ROOT/plan['baseline']['checkpoint']['path'],map_location='cpu',weights_only=True))
        legacy={t:torch.nn.Linear(encoder.config.hidden_size,1) for t in ('D02','D03')}
        for task,head in legacy.items():
            head.load_state_dict(legacy_state[task]);head.eval()
            if old.tensor_hash(head.state_dict())!=plan['baseline']['trainedHeadSha256'][task]:raise ValueError('legacy head identity drift')
        # Reset after legacy head allocation, so shared initialization is stable.
        torch.manual_seed(42)
        heads={t:make_head(torch,encoder.config.hidden_size,plan['config']['fusionWidth']) for t in ('D02','D03')}
        report['headParameters']=sum(p.numel() for h in heads.values() for p in h.parameters())
        cache={}
        with events.open('x',encoding='utf-8') as log:
            context={'phase':'feature_fit','arm':'shared'}
            def journal(e):
                e.update(context)
                if e['status']=='running':
                    e['eventId']=len(report['forwardAttempts']);e['forwardIndex']=e['eventId']
                    report['forwardAttempts'].append({k:v for k,v in e.items() if k not in ('inputIds','tokenTypeIds','factSpans')})
                    report['activeForward']=report['forwardAttempts'][-1]
                else:
                    report['forwardAttempts'][e['eventId']]={k:v for k,v in e.items() if k not in ('inputIds','tokenTypeIds','factSpans')}
                    report['activeForward']=None
                log.write(json.dumps(e,ensure_ascii=False,separators=(',',':'))+'\n');log.flush()
            def encode_fit():
                for row in plan['dataset']:
                    data,cov=features(row['case'],tokenizer,encoder,torch,journal)
                    cache[row['case']['caseId']]=data
                    report['featureCoverage'].append({'caseId':row['case']['caseId'],'role':row['role'],'coverage':cov})
            stage('shared_feature_extraction',encode_fit)
            def fit_heads():
                for task,head in heads.items():
                    rows=[r for r in plan['dataset'] if r['case']['task']==task and r['role']=='fit']
                    y=torch.tensor([v for r in rows for v in old.labels(r)],dtype=torch.float32)
                    positives=int(y.sum());negatives=len(y)-positives
                    if not positives or not negatives:raise ValueError('missing fitting class')
                    loss_fn=torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(negatives/positives))
                    opt=torch.optim.AdamW(head.parameters(),lr=.01,weight_decay=.01);report['fitLosses'][task]=[]
                    for step in range(200):
                        opt.zero_grad();logits=torch.cat([head(cache[r['case']['caseId']]) for r in rows]);loss=loss_fn(logits,y)
                        if not torch.isfinite(loss):raise ValueError('nonfinite fitting loss')
                        loss.backward();opt.step();report['fitLosses'][task].append(float(loss.detach()))
                    head.eval()
            stage('fit_shared_heads',fit_heads)
            report['encoderUnchanged']=before==old.tensor_hash(encoder.state_dict())
            if not report['encoderUnchanged']:raise ValueError('encoder was changed')
            report['encoderTensorSha256']=before
            report['trainedHeadSha256']={t:old.tensor_hash(h.state_dict()) for t,h in heads.items()}
            checkpoint=old.LOCAL/'checkpoints'/f"{plan['runId']}.pt";checkpoint.parent.mkdir(parents=True,exist_ok=True)
            with checkpoint.open('xb') as f:torch.save({t:h.state_dict() for t,h in heads.items()},f)
            report['checkpoint']={'path':str(checkpoint.relative_to(ROOT)),'sha256':sha256_file(checkpoint),'contains':'two_shared_fusion_heads_only'}
            state=stage('shared_checkpoint_reload',lambda:torch.load(checkpoint,map_location='cpu',weights_only=True))
            for task,head in heads.items():
                head.load_state_dict(state[task]);head.eval()
                if old.tensor_hash(head.state_dict())!=report['trainedHeadSha256'][task]:raise ValueError('shared checkpoint tensor drift')
            report['fitAndDevelopmentPredictions']=[]
            for row in plan['dataset']:
                probabilities,decoded=predict(row['case'],cache[row['case']['caseId']],heads[row['case']['task']],torch)
                report['fitAndDevelopmentPredictions'].append({'caseId':row['case']['caseId'],'task':row['case']['task'],
                    'role':row['role'],'label':row['label'],'probabilities':probabilities,'decoded':decoded})
            cases={c['caseId']:c for c in plan['cases']}
            for index,slot in enumerate(slots):
                case=cases[slot['caseId']];context.update(phase='inference',arm=slot['arm'],repeat=slot['repeat'])
                a={**slot,'status':'started','startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns(),
                   'featureCacheUsed':False,'generationStarted':False,'fullRequestMeasured':False}
                report['activeAttempt']=a;report['attemptSlots'][index]=a;save(out,report)
                try:
                    if slot['arm']=='shared':data,cov=features(case,tokenizer,encoder,torch,journal)
                    else:data,cov=old.features(case,tokenizer,encoder,torch,on_window=journal)
                    t=time.perf_counter()
                    if slot['arm']=='shared':probabilities,decoded=predict(case,data,heads[case['task']],torch)
                    else:probabilities,decoded=old.score(case,data,legacy[case['task']],torch,.5)
                    a.update(status='complete',inputSha256=digest(case['input']),coverage=cov,
                             probabilities=probabilities,decoded=decoded,headMs=(time.perf_counter()-t)*1000)
                except Exception as e:a.update(status='failed',error={'type':type(e).__name__,'message':str(e)})
                finally:
                    a.update(elapsedMs=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6,settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns())
                report['attempts'].append(a);report['activeAttempt']=None;save(out,report)
        report['status']='diagnostic_completed'
    except Exception as e:report.update(status='failed',error={'type':type(e).__name__,'message':str(e)})
    finally:
        if report['activeAttempt'] is not None:settle_attempts(report,'worker_exception')
        report['unexecutedAttempts']=sum(x['status']=='not_started' for x in report['attemptSlots'])
        if events.exists():report['windowEventsSha256']=sha256_file(events)
        report['finishedAt']=timestamp();save(out,report)
    return 0 if report['status']=='diagnostic_completed' else 1


def execute(path):
    plan=read_json(path);_,out=old.paths(plan['runId'])
    if out.exists():raise FileExistsError('preserve original record; use a new run id')
    try:verify(plan)
    except Exception as error:
        exclusive(out,{'status':'failed_preflight','planSha256':sha256_file(path),'attempts':[],
                      'error':str(error),'formalEvaluationAllowed':False});raise
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',
             TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HOME=str(old.LOCAL/'hf-cache'))
    start=time.monotonic();reason=None;peak=0.;error=None
    with out.with_suffix('.process.log').open('x',encoding='utf-8') as log:
        try:
            child=subprocess.Popen([str(ROOT/plan['environment']['venvExecutableRelativePath']),str(Path(__file__)),
                                    '--worker',str(path)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        except Exception as e:
            r=unstarted_record(plan,path);r.update(status='failed_process_launch',error=str(e));exclusive(out,r)
            return 1
        try:
            while child.poll() is None:
                rss=subprocess.run(['ps','-o','rss=','-p',str(child.pid)],capture_output=True,text=True)
                if rss.returncode or not rss.stdout.strip():
                    if child.poll() is not None:break
                    raise RuntimeError('RSS monitor unavailable')
                peak=max(peak,float(rss.stdout)/1024)
                if peak>CONFIG['maxResidentMiB']:reason='resident_memory_limit'
                if time.monotonic()-start>CONFIG['processWallSeconds']:reason='process_wall_limit'
                if reason:break
                time.sleep(.25)
        except Exception as e:reason='supervisor_failure';error=str(e)
        finally:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
    report=read_json(out) if out.exists() else unstarted_record(plan,path)
    report['supervisor']={'exitCode':child.returncode,'stopReason':reason,'error':error,'wallMs':(time.monotonic()-start)*1000,
                          'observedPeakResidentMiB':peak,'measurement':'ps_rss_every250ms'}
    if reason or child.returncode:
        old.settle_stages(report,reason or 'worker_exit');settle_attempts(report,reason or 'worker_exit')
        report['status']='stopped_incomplete' if reason else 'failed'
    settle_events(report,out.with_suffix('.windows.jsonl'),reason or 'worker_exit')
    save(out,report)
    print(json.dumps({'status':report['status'],'attempts':len(report['attempts']),'record':str(out)},ensure_ascii=False))
    return 0 if report['status']=='diagnostic_completed' else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--prepare');m.add_argument('--execute',type=Path);m.add_argument('--worker',type=Path);a=p.parse_args()
    if a.prepare:print(prepare(a.prepare));return 0
    return execute(a.execute) if a.execute else worker(a.worker)


if __name__=='__main__':raise SystemExit(main())
