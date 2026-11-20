"""Reviewed-development fitting probe, never a formal training/evaluation set.

Fixed M01 encoder, complete atomic-fact windows and two learned scalar heads.
All training labels come from the original user-reviewed D02/D03 drafts; the
20 source groups are explicitly consumed for fitting/development, not new data.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

from lab import canonical_bytes, sha256_file, build_model_input, guard_case
from fact_windows import make_windows, restore
from run_pilot import exclusive, save, timestamp, digest, peak_rss_mib, settle_interrupted
from prepare_run_batch import observe_environment
import review_io

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
ART=ROOT/'artifacts/world-components-logic/m01-fitting'
LOCAL=ROOT/'.local/world-components-logic'
REGISTRY=ROOT/'artifacts/world-components-logic/l2-model-sources-20261029.json'
PROTOCOL=ROOT/'design/world-engine-reports/components-logic/m01-fitting-probe.md'
CLAIMS=ROOT/'artifacts/world-components-logic/reviews/l3-review-5db17d61-2026-10-30T19-04-59-780Z.json'
CONFIG={'device':'cpu','threads':1,'concurrency':1,'seed':42,'limit':512,
        'stepsPerHead':200,'learningRate':0.01,'weightDecay':0.01,'threshold':0.5,
        'attemptsPerCase':5,'processWallSeconds':120,'maxResidentMiB':2048,
        'encoderFrozen':True,'pooling':'attention_mean_each_window_then_payload_token_weighted_mean',
        'earlyStopping':False,'featureCacheForFitOnly':True,'featureCacheForTiming':False}


def paths(run_id):
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',run_id):raise ValueError('invalid run id')
    return ART/f'{run_id}.plan.json',ART/f'{run_id}.record.json'


def dataset():
    packet=review_io.build_packet();claims=review_io._parse_json(CLAIMS.read_text(encoding='utf-8'))
    review_io.reconcile_claims(claims,packet)
    approved={r['caseId'] for r in claims['decisions'] if r['decision']=='agree'}
    rows=[]
    for c in packet['cases']:
        if c['task'] not in ('D02','D03'):continue
        case={k:c[k] for k in ('caseId','sourceGroup','anchorCase','derivedFrom','split','purpose','task','stageCut','input')}
        if c['caseId'] not in approved or c['split']!='development' or not guard_case(case)['shouldCall']:raise ValueError('unreviewed/non-development/guarded case')
        expected=c['review']['draftExpected']
        label=expected['kind'] if c['task']=='D02' else expected['targetIds']
        rows.append({'case':case,'label':label,'reviewDraftSha256':c['reviewSha256'],
                     'labelStatus':'existing_user_initial_review_only_not_double_blind',
                     'sourcePurpose':'consumed_reviewed_development_fitting_probe'})
    if len(rows)!=20 or len({r['case']['sourceGroup'] for r in rows})!=20:raise ValueError('expected twenty original source groups')
    for task in ('D02','D03'):
        for positive in (False,True):
            bucket=[r for r in rows if r['case']['task']==task and (r['label']=='act' if task=='D02' else bool(r['label']))==positive]
            bucket.sort(key=lambda r:hashlib.sha256(('42:'+r['case']['sourceGroup']).encode()).hexdigest())
            if len(bucket)<2:raise ValueError('stratified split lacks independent groups')
            for i,row in enumerate(bucket):row['role']='retained_development' if i==0 else 'fit'
    return rows,{'claimsSha256':sha256_file(CLAIMS),'inputSha256':packet['inputSha256'],
                'reviewSha256':packet['reviewDraftSha256'],'provenanceSha256':packet['provenanceSha256']}


def model_identity():
    m=next(m for m in json.loads(REGISTRY.read_text(encoding='utf-8'))['models'] if m['id']=='hfl/minirbt-h256')
    directory=LOCAL/'models/M01'/m['revision'];files=[]
    for f in m['files']:
        p=directory/f['path'];expected=f.get('lfs_sha256') or f['sha256_of_fetched_bytes']
        if p.stat().st_size!=f['size_bytes'] or sha256_file(p)!=expected:raise ValueError('M01 identity mismatch: '+f['path'])
        files.append({'path':f['path'],'sha256':expected,'bytes':p.stat().st_size})
    return {'modelId':m['id'],'revision':m['revision'],'directory':str(directory.relative_to(ROOT)),
            'files':files,'registrySha256':sha256_file(REGISTRY)}


def prepare(run_id):
    path,out=paths(run_id)
    if path.exists() or out.exists():raise FileExistsError('preserve prior evidence; use new run id')
    rows,review=dataset()
    config=dict(CONFIG)
    code=[BASE/'m01_probe.py',BASE/'fact_windows.py',BASE/'pilot_codec.py',BASE/'lab.py',BASE/'run_pilot.py',BASE/'review_io.py',BASE/'prepare_run_batch.py']
    plan={'schema':'jity-d-m01-fitting-probe-plan-v1','runId':run_id,'preparedAt':timestamp(),
          'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
          'protocolSha256':sha256_file(PROTOCOL),'code':{str(p.relative_to(ROOT)):sha256_file(p) for p in code},
          'config':config,'configSha256':digest(config),'dataset':rows,'datasetSha256':digest(rows),
          'cases':[r['case'] for r in rows if r['role']=='retained_development'],
          'review':review,'model':model_identity(),'environment':observe_environment(ROOT),
          'authorization':{'instruction':'继续工作至下一个提交','recordedAt':timestamp(),
              'scope':'bounded_local_CPU_fitting_probe_on_existing_reviewed_development_labels',
              'resourceWindow':'current_user_requested_turn_single_CPU_thread_no_GPU_no_BC'},
          'newIndependentTrainingGroups':0,'round1TrainingQuota':0,'formalEvaluationAllowed':False,
          'sourceIndependence':'unverified','crossWindowSemanticsValidated':False}
    exclusive(path,plan);return path


def verify(plan):
    if plan['formalEvaluationAllowed'] is not False or plan['round1TrainingQuota']!=0:raise ValueError('invalid experiment scope')
    if plan['configSha256']!=digest(plan['config']) or plan['protocolSha256']!=sha256_file(PROTOCOL):raise ValueError('configuration/protocol drift')
    if canonical_bytes(plan['config'])!=canonical_bytes(CONFIG):raise ValueError('probe policy drift')
    for name,h in plan['code'].items():
        if sha256_file(ROOT/name)!=h:raise ValueError('code changed: '+name)
    rows,review=dataset()
    if rows!=plan['dataset'] or digest(rows)!=plan['datasetSha256'] or review!=plan['review']:raise ValueError('data/label/split drift')
    if plan['cases']!=[r['case'] for r in rows if r['role']=='retained_development']:raise ValueError('retained development case binding drift')
    if observe_environment(ROOT)!=plan['environment'] or model_identity()!=plan['model']:raise ValueError('environment/model drift')


def prefix(case,target=None):
    value=case['input']
    if case['task']=='D02':return '行动选择判断。当前人物='+value['actorId']+'。下列各窗共同包含完整当前输入。'
    name=next(p['name'] for p in value['world']['characters'] if p['id']==target)
    return '牵连关系判断。冻结源='+value['source']['memberId']+'；当前候选='+target+' '+name+'。下列各窗共同包含完整当前输入。'


def features(case,tokenizer,encoder,torch,limit=512,on_window=None):
    if not guard_case(case)['shouldCall']:raise ValueError('guarded input cannot enter model')
    value=build_model_input(case);targets=[None] if case['task']=='D02' else value['candidateIds']
    vectors=[];coverage=[]
    for target in targets:
        started=time.perf_counter();facts,windows=make_windows(value,tokenizer,prefix(case,target),limit)
        encode_ms=(time.perf_counter()-started)*1000;weighted=None;total=0;window_rows=[]
        for index,w in enumerate(windows):
            t=time.perf_counter();forward={'caseId':case['caseId'],'targetId':target,'windowIndex':index,
                **w,'status':'running','startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns()}
            if on_window:on_window(forward)
            tensors={'input_ids':torch.tensor([w['inputIds']],dtype=torch.long),
                     'token_type_ids':torch.tensor([w['tokenTypeIds']],dtype=torch.long),
                     'attention_mask':torch.ones((1,w['totalTokens']),dtype=torch.long)}
            try:
                with torch.inference_mode():vector=encoder(**tensors).last_hidden_state.mean(dim=1)[0]
                forward.update(status='complete',pooledVectorSha256=tensor_hash({'vector':vector}))
            except Exception as error:
                forward.update(status='failed',error={'type':type(error).__name__,'message':str(error)});raise
            finally:
                forward.update(settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns(),elapsedMs=(time.perf_counter()-t)*1000)
                if on_window:on_window(forward)
            weighted=vector*w['payloadTokens'] if weighted is None else weighted+vector*w['payloadTokens']
            total+=w['payloadTokens'];window_rows.append({**w,'forwardMs':(time.perf_counter()-t)*1000})
        vectors.append(weighted/total)
        coverage.append({'targetId':target,'inputSha256':digest(value),'prefix':prefix(case,target),
                         'factRecords':facts,'factSha256':digest(facts),
                         'fullFactsRestored':canonical_bytes(restore(facts))==canonical_bytes(value),
                         'encodeAndPackMs':encode_ms,'windows':window_rows,'payloadTokens':total})
    return torch.stack(vectors),coverage


def settle_stages(report,reason):
    """Only the supervisor calls this after it has confirmed process exit."""
    for entry in report.get('stages',[]):
        if entry['status']=='running':
            entry.update(status='interrupted',stopReason=reason,settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns())
            entry['elapsedMs']=(entry['settledMonotonicNs']-entry['startedMonotonicNs'])/1e6
    active=report.get('activeForward')
    if active is not None:
        active.update(status='interrupted',stopReason=reason,settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns())
        active['elapsedMs']=(active['settledMonotonicNs']-active['startedMonotonicNs'])/1e6
        report['forwardAttempts'][active['forwardIndex']]=active
        report['activeForward']=None


def labels(row):
    if row['case']['task']=='D02':return [int(row['label']=='act')]
    return [int(target in row['label']) for target in row['case']['input']['candidateIds']]


def tensor_hash(state):
    h=hashlib.sha256()
    for name,value in sorted(state.items()):
        h.update(name.encode());h.update(str(tuple(value.shape)).encode());h.update(value.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def score(case,vectors,head,torch,threshold):
    with torch.inference_mode():values=torch.sigmoid(head(vectors).flatten()).tolist()
    bits=[v>=threshold for v in values]
    decoded={'kind':'act' if bits[0] else 'skip'} if case['task']=='D02' else {'targets':[{'targetId':p} for p,b in zip(case['input']['candidateIds'],bits) if b]}
    return values,decoded


def worker(path):
    plan=json.loads(path.read_text(encoding='utf-8'));_,out=paths(plan['runId'])
    report={'schema':'jity-d-m01-fitting-probe-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),
            'status':'running','stages':[],'featureCoverage':[],'fitLosses':{},'attempts':[],
            'attemptSlots':[{'caseId':c['caseId'],'repeat':i,'status':'not_started'} for i in range(5) for c in plan['cases']],
            'activeAttempt':None,'forwardAttempts':[],'activeForward':None,'formalEvaluationAllowed':False,'fullRequestMeasured':False,
            'sourceIndependence':'unverified','semanticQualityApproved':False}
    exclusive(out,report)
    def stage(name,fn):
        t=time.perf_counter();entry={'stage':name,'status':'running','startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns()};report['stages'].append(entry);save(out,report)
        try:value=fn();entry['status']='complete';return value
        except Exception as e:entry.update(status='failed',error={'type':type(e).__name__,'message':str(e)});raise
        finally:entry.update(elapsedMs=(time.perf_counter()-t)*1000,settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns());save(out,report)
    def journal_forward(value):
        if value['status']=='running':
            value['forwardIndex']=len(report['forwardAttempts']);report['forwardAttempts'].append(value);report['activeForward']=value
        else:
            report['forwardAttempts'][value['forwardIndex']]=value;report['activeForward']=None
        save(out,report)
    try:
        stage('verify_plan',lambda:verify(plan))
        def stack():
            import torch
            from transformers import BertModel,BertTokenizer
            torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(42)
            return torch,BertModel,BertTokenizer
        torch,BertModel,BertTokenizer=stage('dependency_import',stack)
        report['actualRuntime']={'python':sys.executable,'pythonVersion':platform.python_version(),
            'dependencies':{n:importlib.metadata.version(n) for n in ('torch','transformers','tokenizers','numpy')},
            'threads':torch.get_num_threads(),'interopThreads':torch.get_num_interop_threads(),'device':'cpu'}
        directory=ROOT/plan['model']['directory']
        tokenizer=stage('tokenizer_load',lambda:BertTokenizer.from_pretrained(directory,local_files_only=True))
        encoder,info=stage('encoder_load',lambda:BertModel.from_pretrained(directory,local_files_only=True,
                    trust_remote_code=False,weights_only=True,add_pooling_layer=False,output_loading_info=True))
        if info['missing_keys'] or info.get('mismatched_keys'):raise ValueError('encoder contains uninitialized weights')
        if any(not k.startswith('cls.') for k in info['unexpected_keys']):raise ValueError('unexpected checkpoint namespace')
        encoder.eval()
        for p in encoder.parameters():p.requires_grad_(False)
        before=tensor_hash(encoder.state_dict());report['encoderLoadInfo']=info
        report['encoderParameters']=sum(p.numel() for p in encoder.parameters())
        heads={task:torch.nn.Linear(encoder.config.hidden_size,1) for task in ('D02','D03')}
        report['headParameters']=sum(p.numel() for h in heads.values() for p in h.parameters())
        report['initialHeadSha256']={k:tensor_hash(h.state_dict()) for k,h in heads.items()}
        cache={}
        def cache_features():
            for row in plan['dataset']:
                vectors,coverage=features(row['case'],tokenizer,encoder,torch,on_window=journal_forward)
                cache[row['case']['caseId']]=vectors.detach().clone()
                report['featureCoverage'].append({'caseId':row['case']['caseId'],'role':row['role'],'coverage':coverage})
                save(out,report)
        stage('frozen_feature_extraction',cache_features)
        def fit():
            for task,head in heads.items():
                rows=[r for r in plan['dataset'] if r['case']['task']==task and r['role']=='fit']
                x=torch.cat([cache[r['case']['caseId']] for r in rows]);y=torch.tensor([v for r in rows for v in labels(r)],dtype=torch.float32)
                positives=int(y.sum());negatives=len(y)-positives
                if not positives or not negatives:raise ValueError('fitting labels lack both classes')
                loss_fn=torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(negatives/positives))
                opt=torch.optim.AdamW(head.parameters(),lr=plan['config']['learningRate'],weight_decay=plan['config']['weightDecay'])
                report['fitLosses'][task]=[]
                for step in range(plan['config']['stepsPerHead']):
                    opt.zero_grad();loss=loss_fn(head(x).flatten(),y)
                    if not torch.isfinite(loss):raise ValueError('nonfinite fit loss')
                    loss.backward();opt.step();report['fitLosses'][task].append(float(loss.detach()))
                    if step%20==0:save(out,report)
                head.eval()
        stage('fit_only_two_linear_heads',fit)
        report['encoderUnchanged']=before==tensor_hash(encoder.state_dict())
        if not report['encoderUnchanged']:raise ValueError('frozen encoder changed')
        report['trainedHeadSha256']={k:tensor_hash(h.state_dict()) for k,h in heads.items()}
        checkpoint=LOCAL/'checkpoints'/f"{plan['runId']}.pt";checkpoint.parent.mkdir(parents=True,exist_ok=True)
        with checkpoint.open('xb') as f:torch.save({k:h.state_dict() for k,h in heads.items()},f)
        report['checkpoint']={'path':str(checkpoint.relative_to(ROOT)),'sha256':sha256_file(checkpoint),'contains':'two_linear_heads_only'}
        report['fitAndDevelopmentPredictions']=[]
        for row in plan['dataset']:
            probabilities,decoded=score(row['case'],cache[row['case']['caseId']],heads[row['case']['task']],torch,.5)
            report['fitAndDevelopmentPredictions'].append({'caseId':row['case']['caseId'],'task':row['case']['task'],
                    'role':row['role'],'label':row['label'],'probabilities':probabilities,'decoded':decoded})
        for repeat in range(5):
            for offset,case in enumerate(plan['cases']):
                index=repeat*len(plan['cases'])+offset;start=time.perf_counter()
                attempt={'caseId':case['caseId'],'task':case['task'],'repeat':repeat,'status':'started',
                         'startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns(),'activeStage':'full_window_inference',
                         'generationStarted':False,'fullRequestMeasured':False,'featureCacheUsed':False}
                report['activeAttempt']=attempt;report['attemptSlots'][index]=attempt;save(out,report)
                try:
                    vectors,coverage=features(case,tokenizer,encoder,torch,on_window=journal_forward)
                    h=time.perf_counter();probabilities,decoded=score(case,vectors,heads[case['task']],torch,.5)
                    attempt.update(status='complete',inputSha256=digest(case['input']),coverage=coverage,
                                   probabilities=probabilities,decoded=decoded,headMs=(time.perf_counter()-h)*1000)
                except Exception as e:attempt.update(status='failed',error={'type':type(e).__name__,'message':str(e)})
                finally:attempt.update(elapsedMs=(time.perf_counter()-start)*1000,settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns())
                report['attempts'].append(attempt);report['activeAttempt']=None;save(out,report)
        report['status']='diagnostic_completed'
    except Exception as e:report.update(status='failed',error={'type':type(e).__name__,'message':str(e)})
    finally:
        report['peakResidentMiB']=peak_rss_mib();report['finishedAt']=timestamp()
        if report['activeAttempt'] is not None:settle_interrupted(report,plan,'worker_exception')
        report['unexecutedAttempts']=sum(s['status']=='not_started' for s in report['attemptSlots']);save(out,report)
    return 0 if report['status']=='diagnostic_completed' else 1


def execute(path,verify_fn=None,worker_script=None):
    plan=json.loads(path.read_text(encoding='utf-8'));_,out=paths(plan['runId'])
    if out.exists():raise FileExistsError('record already exists')
    try:(verify_fn or verify)(plan)
    except Exception as e:
        exclusive(out,{'status':'failed_preflight','attempts':[],'error':str(e)});raise
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',
             TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HOME=str(LOCAL/'hf-cache'))
    start=time.monotonic();reason=None;peak=0.;error=None;logpath=out.with_suffix('.process.log')
    with logpath.open('x',encoding='utf-8') as log:
        p=subprocess.Popen([str(ROOT/plan['environment']['venvExecutableRelativePath']),str(worker_script or Path(__file__)),'--worker',str(path)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while p.poll() is None:
                rss=subprocess.run(['ps','-o','rss=','-p',str(p.pid)],capture_output=True,text=True)
                if rss.returncode or not rss.stdout.strip():
                    if p.poll() is not None:break
                    raise RuntimeError('RSS monitor unavailable')
                peak=max(peak,float(rss.stdout)/1024)
                if peak>plan['config']['maxResidentMiB']:reason='resident_memory_limit'
                if time.monotonic()-start>plan['config']['processWallSeconds']:reason='process_wall_limit'
                if reason:
                    os.killpg(p.pid,signal.SIGTERM)
                    try:p.wait(timeout=3)
                    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
                    break
                time.sleep(.25)
        except Exception as e:reason='supervisor_failure';error=str(e)
        finally:
            if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait()
    report=json.loads(out.read_text(encoding='utf-8')) if out.exists() else {'status':'failed_before_journal','attempts':[],'activeAttempt':None}
    report['supervisor']={'exitCode':p.returncode,'stopReason':reason,'error':error,'wallMs':(time.monotonic()-start)*1000,'observedPeakResidentMiB':peak,'measurement':'ps_rss_every250ms'}
    if reason or p.returncode:
        settle_stages(report,reason or 'worker_exit');settle_interrupted(report,plan,reason or 'worker_exit');report['status']='stopped_incomplete' if reason else 'failed'
    if out.exists():save(out,report)
    else:exclusive(out,report)
    print(json.dumps({'status':report['status'],'attempts':len(report['attempts']),'record':str(out)},ensure_ascii=False))
    return 0 if report['status']=='diagnostic_completed' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__);m=parser.add_mutually_exclusive_group(required=True)
    m.add_argument('--prepare');m.add_argument('--execute',type=Path);m.add_argument('--worker',type=Path);args=parser.parse_args()
    if args.prepare:print(prepare(args.prepare));return 0
    return execute(args.execute) if args.execute else worker(args.worker)


if __name__=='__main__':raise SystemExit(main())
