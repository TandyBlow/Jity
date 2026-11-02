"""Shared full-fact encoding and learned candidate fusion; development probe only.

No model import at module load. Prior inference code/evidence remains immutable.
"""
from __future__ import annotations

import argparse
import copy
from functools import partial
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import m01_probe as old
from fact_windows import fact_text, make_windows, restore
from lab import build_model_input, canonical_bytes, guard_case, sha256_file
from run_pilot import digest, exclusive, save, timestamp
from prepare_run_batch import observe_environment
import experiment
from experiment import read_json,settle_attempts,settle_events

ROOT=old.ROOT
BASE=old.BASE
ART=old.ART
PROTOCOL=ROOT/'design/world-engine-reports/components-logic/m01-event-depth-probe.md'
OLD_PLAN=ART/'m01-fit-dev42-20261102-r1.plan.json'
OLD_RECORD=ART/'m01-fit-dev42-20261102-r1.record.json.gz'
BASELINE_PLAN=ART/'m01-shared-dev42-20261102-r3.plan.json'
BASELINE_RECORD=ART/'m01-shared-dev42-20261102-r3.record.json.gz'
ARMS=('baseline','event','event2')
CONFIG={'device':'cpu','threads':1,'concurrency':1,'seed':42,'limit':512,
        'stepsPerHead':200,'learningRate':.0003,'weightDecay':.01,'threshold':.5,
        'fusionWidth':32,'attemptsPerCase':5,'processWallSeconds':120,
        'maxResidentMiB':2048,'encoderFrozen':True,'earlyStopping':False,
        'featureCacheForTiming':False,'featureCacheForFitOnly':True,
        'reducedEncoderLayerIndices':[0,1],'eventAnchor':'D03_source_actionText_only'}
planned_slots=partial(experiment.planned_slots,arms=ARMS)
unstarted_record=partial(experiment.unstarted_record,arms=ARMS)


def baseline_identity():
    p=read_json(BASELINE_PLAN);r=read_json(BASELINE_RECORD)
    if r['planSha256']!=sha256_file(BASELINE_PLAN) or r['status']!='diagnostic_completed' or not r['encoderUnchanged']:
        raise ValueError('invalid original fit evidence')
    if sha256_file(ROOT/r['checkpoint']['path'])!=r['checkpoint']['sha256']:
        raise ValueError('original checkpoint bytes drift')
    return {'planSha256':sha256_file(BASELINE_PLAN),'recordSha256':sha256_file(BASELINE_RECORD),
            'planPath':str(BASELINE_PLAN.relative_to(ROOT)),'recordPath':str(BASELINE_RECORD.relative_to(ROOT)),
            'datasetSha256':p['datasetSha256'],'checkpoint':r['checkpoint'],
            'trainedHeadSha256':r['trainedHeadSha256'],'model':p['model']}


def prepare(run_id):
    path,out=old.paths(run_id)
    if path.exists() or out.exists():raise FileExistsError('use a new run id; preserve evidence')
    rows,review=old.dataset();baseline=baseline_identity();model=old.model_identity()
    if baseline['datasetSha256']!=digest(rows) or model!=baseline['model']:raise ValueError('baseline dataset/model drift')
    code=[BASE/name for name in ('experiment.py','m01_shared.py','m01_probe.py','fact_windows.py','pilot_codec.py','lab.py','run_pilot.py','review_io.py','prepare_run_batch.py')]
    plan={'schema':'jity-d-m01-event-depth-plan-v1','runId':run_id,'preparedAt':timestamp(),
          'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
          'protocolPath':str(PROTOCOL.relative_to(ROOT)),'protocolSha256':sha256_file(PROTOCOL),
          'inheritedProtocolSha256':sha256_file(PROTOCOL.with_name('m01-shared-probe.md')),
          'code':{str(p.relative_to(ROOT)):sha256_file(p) for p in code},
          'config':CONFIG.copy(),'configSha256':digest(CONFIG),'dataset':rows,'datasetSha256':digest(rows),
          'cases':[r['case'] for r in rows if r['role']=='retained_development'],
          'review':review,'model':model,'baseline':baseline,'environment':observe_environment(ROOT),
          'authorization':{'instruction':'继续','scope':'bounded_D_single_thread_event_anchor_depth_probe',
                           'resourceWindow':'current_user_requested_turn_single_CPU_thread_no_GPU_no_BC'},
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
    if (plan['protocolPath']!=str(PROTOCOL.relative_to(ROOT))
            or plan['inheritedProtocolSha256']!=sha256_file(PROTOCOL.with_name('m01-shared-probe.md'))):raise ValueError('inherited protocol drift')
    expected={'experiments/world-components-logic/'+n for n in ('experiment.py','m01_shared.py','m01_probe.py','fact_windows.py','pilot_codec.py','lab.py','run_pilot.py','review_io.py','prepare_run_batch.py')}
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


def event_indices(case,facts):
    """Separate the frozen action, without filtering any facts or candidates."""
    if case['task']!='D03':return None
    indices=[i for i,f in enumerate(facts) if f['path']==['source','actionText']]
    if len(indices)!=1:raise ValueError('missing or duplicate frozen action fact')
    return indices


def features(case,tokenizer,encoder,torch,on_window=None,event_anchor=False):
    t=time.perf_counter();value,facts,windows=pack(case,tokenizer)
    targets,anchor,candidates=pool_indices(case,facts);pack_ms=(time.perf_counter()-t)*1000
    vectors=[None]*len(facts);weighted=None;total=0
    timing={'packMs':pack_ms,'tensorMs':0.,'encoderMs':0.,'poolAndDigestMs':0.,'windowJournalMs':0.}
    def emit(event):
        t=time.perf_counter()
        if on_window:on_window(event)
        timing['windowJournalMs']+=(time.perf_counter()-t)*1000
    for i,w in enumerate(windows):
        start=time.perf_counter();event={'caseId':case['caseId'],'targetId':None,'windowIndex':i,
            **w,'status':'running','startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns()}
        emit(event)
        try:
            t=time.perf_counter()
            tensors={'input_ids':torch.tensor([w['inputIds']],dtype=torch.long),
                     'token_type_ids':torch.tensor([w['tokenTypeIds']],dtype=torch.long),
                     'attention_mask':torch.ones((1,w['totalTokens']),dtype=torch.long)}
            timing['tensorMs']+=(time.perf_counter()-t)*1000;t=time.perf_counter()
            with torch.inference_mode():hidden=encoder(**tensors).last_hidden_state[0]
            timing['encoderMs']+=(time.perf_counter()-t)*1000;t=time.perf_counter()
            for span in w['factSpans']:
                vectors[span['factIndex']]=hidden[span['start']:span['end']].mean(dim=0).clone()
            payload=hidden[w['factSpans'][0]['start']:w['factSpans'][-1]['end']].sum(dim=0)
            weighted=payload.clone() if weighted is None else weighted+payload;total+=w['payloadTokens']
            event.update(status='complete',factVectorSha256=old.tensor_hash({str(s['factIndex']):vectors[s['factIndex']] for s in w['factSpans']}))
            timing['poolAndDigestMs']+=(time.perf_counter()-t)*1000
        except Exception as error:
            event.update(status='failed',error={'type':type(error).__name__,'message':str(error)});raise
        finally:
            event.update(elapsedMs=(time.perf_counter()-start)*1000,settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns())
            emit(event)
        w['forwardMs']=(time.perf_counter()-start)*1000
    if any(x is None for x in vectors):raise ValueError('missing encoded fact')
    memory=torch.stack(vectors).detach().clone()
    # clone exits inference_mode: the small learned heads need ordinary frozen
    # feature tensors for autograd, never gradients through the encoder.
    selected=event_indices(case,facts) if event_anchor else None
    data={'memory':memory,'anchor':memory[selected if selected is not None else anchor].mean(dim=0),
          'candidates':torch.stack([memory[c].mean(dim=0) for c in candidates]),
          'global':(weighted/total).detach().clone()}
    coverage={'factRecords':facts,'factSha256':digest(facts),'fullFactsRestored':canonical_bytes(restore(facts))==canonical_bytes(value),
              'targets':targets,'anchorFactIds':anchor,'candidateFactIds':candidates,'encodeAndPackMs':pack_ms,'windows':windows,
              'eventAnchorFactIds':selected,'timing':timing}
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


def worker(path):
    plan=read_json(path);_,out=old.paths(plan['runId']);events=out.with_suffix('.windows.jsonl')
    slots=planned_slots(plan)
    report={'schema':'jity-d-m01-event-depth-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),
            'status':'running','stages':[],'attempts':[],'attemptSlots':slots,'activeAttempt':None,
            'forwardAttempts':[],'activeForward':None,'featureCoverage':[],'fitLosses':{},
            'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequestMeasured':False,
            'sourceIndependence':'unverified'}
    exclusive(out,report)
    def stage(name,fn):
        return experiment.record_stage(report,out,name,fn)
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
        baseline_state=stage('baseline_checkpoint_load',lambda:torch.load(ROOT/plan['baseline']['checkpoint']['path'],map_location='cpu',weights_only=True))
        heads={'baseline':{t:make_head(torch,encoder.config.hidden_size) for t in ('D02','D03')}}
        for task,head in heads['baseline'].items():
            head.load_state_dict(baseline_state[task]);head.eval()
            if old.tensor_hash(head.state_dict())!=plan['baseline']['trainedHeadSha256'][task]:raise ValueError('baseline head identity drift')
        reduced=copy.deepcopy(encoder)
        reduced.encoder.layer=torch.nn.ModuleList([reduced.encoder.layer[i] for i in plan['config']['reducedEncoderLayerIndices']])
        reduced.config.num_hidden_layers=len(reduced.encoder.layer);reduced.eval()
        encoders={'baseline':encoder,'event':encoder,'event2':reduced}
        encoder_hashes={a:old.tensor_hash(e.state_dict()) for a,e in encoders.items()}
        report['encoderVariants']={a:{'layers':len(e.encoder.layer),'parameters':sum(p.numel() for p in e.parameters()),
            'tensorSha256':encoder_hashes[a]} for a,e in encoders.items()}
        for arm in ARMS[1:]:
            torch.manual_seed(plan['config']['seed'])
            heads[arm]={t:make_head(torch,encoder.config.hidden_size,plan['config']['fusionWidth']) for t in ('D02','D03')}
        report['headParametersPerArm']={a:sum(p.numel() for h in hs.values() for p in h.parameters()) for a,hs in heads.items()}
        cache={}
        with events.open('x',encoding='utf-8') as log:
            context={'phase':'feature_fit','arm':None}
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
                for arm in ARMS[1:]:
                    context['arm']=arm;cache[arm]={}
                    for row in plan['dataset']:
                        data,cov=features(row['case'],tokenizer,encoders[arm],torch,journal,event_anchor=True)
                        cache[arm][row['case']['caseId']]=data
                        report['featureCoverage'].append({'arm':arm,'caseId':row['case']['caseId'],'role':row['role'],'coverage':cov})
            stage('shared_feature_extraction',encode_fit)
            def fit_heads():
                for arm in ARMS[1:]:
                    report['fitLosses'][arm]={}
                    for task,head in heads[arm].items():
                        rows=[r for r in plan['dataset'] if r['case']['task']==task and r['role']=='fit']
                        y=torch.tensor([v for r in rows for v in old.labels(r)],dtype=torch.float32)
                        positives=int(y.sum());negatives=len(y)-positives
                        if not positives or not negatives:raise ValueError('missing fitting class')
                        loss_fn=torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(negatives/positives))
                        opt=torch.optim.AdamW(head.parameters(),lr=plan['config']['learningRate'],weight_decay=plan['config']['weightDecay'])
                        report['fitLosses'][arm][task]=[]
                        for step in range(plan['config']['stepsPerHead']):
                            opt.zero_grad();logits=torch.cat([head(cache[arm][r['case']['caseId']]) for r in rows]);loss=loss_fn(logits,y)
                            if not torch.isfinite(loss):raise ValueError('nonfinite fitting loss')
                            loss.backward();opt.step();report['fitLosses'][arm][task].append(float(loss.detach()))
                        head.eval()
            stage('fit_shared_heads',fit_heads)
            report['encoderUnchanged']=all(encoder_hashes[a]==old.tensor_hash(e.state_dict()) for a,e in encoders.items())
            if not report['encoderUnchanged']:raise ValueError('encoder was changed')
            report['encoderTensorSha256']=before
            report['trainedHeadSha256']={a:{t:old.tensor_hash(h.state_dict()) for t,h in hs.items()} for a,hs in heads.items()}
            checkpoint=old.LOCAL/'checkpoints'/f"{plan['runId']}.pt";checkpoint.parent.mkdir(parents=True,exist_ok=True)
            with checkpoint.open('xb') as f:torch.save({a:{t:h.state_dict() for t,h in heads[a].items()} for a in ARMS[1:]},f)
            report['checkpoint']={'path':str(checkpoint.relative_to(ROOT)),'sha256':sha256_file(checkpoint),'contains':'four_event_anchor_heads_only'}
            state=stage('shared_checkpoint_reload',lambda:torch.load(checkpoint,map_location='cpu',weights_only=True))
            for arm in ARMS[1:]:
                for task,head in heads[arm].items():
                    head.load_state_dict(state[arm][task]);head.eval()
                    if old.tensor_hash(head.state_dict())!=report['trainedHeadSha256'][arm][task]:raise ValueError('shared checkpoint tensor drift')
            report['fitAndDevelopmentPredictions']=[]
            for arm in ARMS[1:]:
                for row in plan['dataset']:
                    probabilities,decoded=predict(row['case'],cache[arm][row['case']['caseId']],heads[arm][row['case']['task']],torch)
                    report['fitAndDevelopmentPredictions'].append({'arm':arm,'caseId':row['case']['caseId'],'task':row['case']['task'],
                        'role':row['role'],'label':row['label'],'probabilities':probabilities,'decoded':decoded})
            cases={c['caseId']:c for c in plan['cases']}
            for index,slot in enumerate(slots):
                case=cases[slot['caseId']];context.update(phase='inference',arm=slot['arm'],repeat=slot['repeat'])
                a={**slot,'status':'started','startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns(),
                   'featureCacheUsed':False,'generationStarted':False,'fullRequestMeasured':False}
                report['activeAttempt']=a;report['attemptSlots'][index]=a
                jt=time.perf_counter();save(out,report);a['startJournalMs']=(time.perf_counter()-jt)*1000
                try:
                    data,cov=features(case,tokenizer,encoders[slot['arm']],torch,journal,event_anchor=slot['arm']!='baseline')
                    t=time.perf_counter()
                    probabilities,decoded=predict(case,data,heads[slot['arm']][case['task']],torch)
                    a.update(status='complete',inputSha256=digest(case['input']),coverage=cov,
                             probabilities=probabilities,decoded=decoded,headMs=(time.perf_counter()-t)*1000)
                except Exception as e:a.update(status='failed',error={'type':type(e).__name__,'message':str(e)})
                finally:
                    a.update(elapsedMs=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6,settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns())
                report['attempts'].append(a);report['activeAttempt']=None
                jt=time.perf_counter();save(out,report);a['endJournalMs']=(time.perf_counter()-jt)*1000
                a['elapsedIncludingEndJournalMs']=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6
        report['status']='diagnostic_completed' if all(a['status']=='complete' for a in report['attempts']) else 'failed'
    except Exception as e:report.update(status='failed',error={'type':type(e).__name__,'message':str(e)})
    finally:
        if report['activeAttempt'] is not None:settle_attempts(report,'worker_exception')
        report['unexecutedAttempts']=sum(x['status']=='not_started' for x in report['attemptSlots'])
        if events.exists():report['windowEventsSha256']=sha256_file(events)
        report['finishedAt']=timestamp();save(out,report)
    return 0 if report['status']=='diagnostic_completed' else 1


def execute(path):
    return experiment.execute_plan(path,paths=old.paths,verify=verify,worker_script=Path(__file__),
                                   settle_stages=old.settle_stages,arms=ARMS)


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--prepare');m.add_argument('--execute',type=Path);m.add_argument('--worker',type=Path);a=p.parse_args()
    if a.prepare:print(prepare(a.prepare));return 0
    return execute(a.execute) if a.execute else worker(a.worker)


if __name__=='__main__':raise SystemExit(main())
