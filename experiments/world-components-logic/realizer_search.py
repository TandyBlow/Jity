"""Bounded D realizer hyperparameter search, using the existing trainer/journal.

Validation labels are exposed drafts, not an independent test set. A continuous
optimizer path supplies fixed-step candidates; validation never backpropagates.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics
import subprocess
import time
import plan_training as t
import realizer_expansion as x

ROOT=t.ROOT;ART=t.ART;SEARCH='m02-realizer-grid-20261105-r2'
PROTOCOL=t.PROTOCOL.with_name('realizer-search-protocol.md')
MANIFEST=ART/'m01-fitting'/f'{SEARCH}.manifest.json'
SELECTION=ART/'m01-fitting'/f'{SEARCH}.selection.json'
REVIEW=ART/'m01-fitting'/f'{SEARCH}.output-review.json'
CONFIRM_REVIEW=ART/'m01-fitting'/f'{SEARCH}.confirmation-review.json'
PAGE='l3-21-realizer-grid'
RATES=(0.0003,0.001,0.003);DECAYS=(0.01,0.1);STEPS=(80,160,320);PROBES=(0,20,40,80,160,320)
CODE=tuple(dict.fromkeys((*t.CODE,'realizer_expansion.py','realizer_search.py')))
INSTRUCTION='检查超参数，是否过拟合了，看一下超参数是不是最适合的，如果不是就要进行网格搜索'


def catalog():
    return [{'runId':f'{SEARCH}-g{i:02}', 'config':{**t.CONFIG,'allowGroupedExamples':True,
        'learningRate':lr,'weightDecay':wd,'steps':320}}
        for i,(lr,wd) in enumerate(itertools.product(RATES,DECAYS),1)]


def data():
    rows=x.rows()
    return [r for r in rows if r['role']=='train_candidate'],[r for r in rows if r['role']=='development_candidate']


def scope():
    return {'instruction':INSTRUCTION,'scope':'one_18_point_draft_grid_and_seed7_confirmation',
        'humanLabelReviews':0,'formalEvaluationAllowed':False,'labelProvenance':'assistant_checked_draft_not_human_gold',
        'sourceIndependence':'unverified'}


def prepare():
    if MANIFEST.exists():raise FileExistsError('preserve original search manifest')
    x.materials();train,dev=data()
    manifest={'schema':'jity-d-realizer-grid-manifest-v1','searchId':SEARCH,'preparedAt':t.timestamp(),
        'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'authorization':scope(),'catalog':catalog(),'generationSteps':list(STEPS),'probeSteps':list(PROBES),
        'confirmationSeed':7,'maximumTrajectories':8,'maximumProcessWindowSeconds':960,
        'dataSha256':t.digest(train+dev),'packetSha256':x.packet(),
        'sourceManifestSha256':t.sha256_file(x.DATA/'source-manifest.json'),
        'protocolSha256':t.sha256_file(PROTOCOL),'model':t.observe_m02(ROOT),'environment':t.observe_environment(ROOT),
        'code':{str((t.BASE/name).relative_to(ROOT)):t.sha256_file(t.BASE/name) for name in CODE}}
    if not manifest['model']['allSixFilesFullyRehashedAndVerified'] or not manifest['environment']['registeredVersionsMatch']:raise ValueError('grid model/environment invalid')
    t.exclusive(MANIFEST,manifest)
    for entry in catalog():prepare_trajectory(manifest,entry)
    return MANIFEST


def prepare_trajectory(manifest,entry,selection_sha=None):
    pp,rp=t.old.paths(entry['runId'])
    if pp.exists() or rp.exists():raise FileExistsError('preserve original grid plan/record')
    config=entry['config'];confirm=selection_sha is not None
    plan={'schema':'jity-d-realizer-grid-plan-v1','runId':entry['runId'],'preparedAt':t.timestamp(),
        'purpose':'draft_grid_seed_confirmation' if confirm else 'draft_grid_continuous_optimizer_trajectory',
        'environment':manifest['environment'],
        'config':config,'cases':[{'caseId':'complete-training-trajectory'}],'arms':['grid'],
        'manifestSha256':t.sha256_file(MANIFEST),'selectionSha256':selection_sha,
        'probeSteps':[i for i in PROBES if i<=config['steps']],
        'generationSteps':[config['steps']] if confirm else list(STEPS),
        'formalEvaluationAllowed':False,'fullRequestMeasured':False}
    t.exclusive(pp,plan);return pp


def verify_manifest(manifest,*,historical=False):
    train,dev=data()
    if (manifest['schema']!='jity-d-realizer-grid-manifest-v1' or manifest['searchId']!=SEARCH
            or manifest['authorization']!=scope() or manifest['catalog']!=catalog()
            or manifest['generationSteps']!=list(STEPS) or manifest['probeSteps']!=list(PROBES)
            or manifest['confirmationSeed']!=7 or manifest['maximumTrajectories']!=8 or manifest['maximumProcessWindowSeconds']!=960
            or manifest['dataSha256']!=t.digest(train+dev) or manifest['packetSha256']!=x.packet()
            or manifest['sourceManifestSha256']!=t.sha256_file(x.DATA/'source-manifest.json')):raise ValueError('grid scope/data/config drift')
    if {r['sourceGroup'] for r in train}&{r['sourceGroup'] for r in dev}:raise ValueError('grid train/development source overlap')
    if (len(train),len(dev))!=(30,18):raise ValueError('grid data count drift')
    for name,h in manifest['code'].items():
        if historical:t.verify_historical_file(ROOT/name,h)
        elif t.sha256_file(ROOT/name)!=h:raise ValueError('grid executed code drift')
    if historical:t.verify_historical_file(PROTOCOL,manifest['protocolSha256'])
    elif t.sha256_file(PROTOCOL)!=manifest['protocolSha256']:raise ValueError('grid protocol drift')


def confirmation_entries(selection):
    configs=[('selected',selection['selected']['config']),('baseline',{**t.CONFIG,'allowGroupedExamples':True,'steps':320})]
    if configs[0][1]==configs[1][1]:configs=configs[:1]
    return [{'runId':f'{SEARCH}-confirm-{name}','config':{**config,'seed':7}} for name,config in configs]


def verify(plan,*,historical=False):
    manifest=t.run.read_json(MANIFEST);verify_manifest(manifest,historical=historical)
    if (plan['manifestSha256']!=t.sha256_file(MANIFEST) or plan.get('environment')!=manifest['environment']
            or plan['formalEvaluationAllowed'] is not False or plan['fullRequestMeasured'] is not False):raise ValueError('grid manifest/environment/scope drift')
    confirm=plan['purpose']=='draft_grid_seed_confirmation'
    entries=confirmation_entries(locked_selection()) if confirm else catalog()
    entry=next((e for e in entries if e['runId']==plan['runId']),None)
    if (entry is None or plan['config']!=entry['config'] or plan['schema']!='jity-d-realizer-grid-plan-v1'
            or plan['purpose']!=('draft_grid_seed_confirmation' if confirm else 'draft_grid_continuous_optimizer_trajectory')
            or plan['arms']!=['grid'] or plan['cases']!=[{'caseId':'complete-training-trajectory'}]
            or plan['probeSteps']!=[i for i in PROBES if i<=entry['config']['steps']]
            or plan['generationSteps']!=([entry['config']['steps']] if confirm else list(STEPS))
            or plan['selectionSha256']!=(t.sha256_file(SELECTION) if confirm else None)):raise ValueError('unregistered grid trajectory')
    if not historical:
        _,record=t.old.paths(plan['runId'])
        if record.with_suffix(record.suffix+'.gz').exists():raise FileExistsError('archived grid record already exists; never rerun')
        if manifest['model']!=t.observe_m02(ROOT) or manifest['environment']!=t.observe_environment(ROOT):raise ValueError('grid runtime model/environment drift')
    return manifest


def aggregate_loss(entries):
    result={}
    for role in ('train_candidate','development_candidate'):
        rows=[e for e in entries if e['role']==role];groups={}
        for row in rows:
            if not math.isfinite(row['meanTokenNll']) or row['meanTokenNll']<0 or row['targetTokens']<=0:raise ValueError('invalid probe loss')
            groups.setdefault(row['sourceGroup'],[]).append(row['meanTokenNll'])
        result[role]={'examples':len(rows),'groups':len(groups),
            'exampleMeanNll':statistics.mean(r['meanTokenNll'] for r in rows),
            'tokenWeightedNll':sum(r['meanTokenNll']*r['targetTokens'] for r in rows)/sum(r['targetTokens'] for r in rows),
            'groupMacroNll':statistics.mean(statistics.mean(values) for values in groups.values())}
    return result


def evaluate_loss(torch,model,encoded,rows,pad_id,step,checkpoint):
    checkpoint('loss_probe_started',{'step':step,'examples':len(rows)})
    start=time.perf_counter();entries=[];model.eval()
    with torch.inference_mode():
        for row,example in zip(rows,encoded):
            checkpoint('loss_forward_started',{'step':step,'annotationId':row['annotationId']})
            output=model(**t.collate(torch,[example],pad_id));value=float(output.loss)
            entry={'annotationId':row['annotationId'],'sourceGroup':row['sourceGroup'],'role':row['role'],
                'meanTokenNll':value,'targetTokens':len(example['labels']),'inputTokenIds':example['inputIds'],
                'targetTokenIds':example['labels'],'inputSha256':example['inputSha256'],'targetSha256':example['targetSha256']}
            checkpoint('loss_forward_settled',{'step':step,**entry});entries.append(entry)
    result={'step':step,'entries':entries,'metrics':aggregate_loss(entries),'elapsedMs':(time.perf_counter()-start)*1000}
    checkpoint('loss_probe',result);return result


def worker(path):
    plan=t.run.read_json(path);config=plan['config'];_,out=t.old.paths(plan['runId']);slots=t.run.planned_slots(plan,('grid',))
    report={'schema':'jity-d-realizer-grid-record-v1','runId':plan['runId'],'planSha256':t.sha256_file(path),
        'status':'running','stages':[],'attempts':[],'attemptSlots':slots,'activeAttempt':None,'forwardAttempts':[],
        'formalEvaluationAllowed':False,'fullRequestMeasured':False}
    t.exclusive(out,report);stage=lambda n,f:t.run.record_stage(report,out,n,f)
    try:
        manifest=stage('verify',lambda:verify(plan));train,dev=data();rows=train+dev
        import torch
        from transformers import T5ForConditionalGeneration,T5Tokenizer
        torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(config['seed'])
        directory=ROOT/manifest['model']['directory']
        tokenizer=stage('tokenizer',lambda:T5Tokenizer.from_pretrained(directory,local_files_only=True,extra_ids=0,legacy=True))
        model=stage('source_model',lambda:T5ForConditionalGeneration.from_pretrained(directory,local_files_only=True,weights_only=True).eval())
        source_hash=t.old.tensor_hash(model.state_dict());t.install_lora(torch,model,config['rank'],config['alpha'])
        encoded=[t.tokenize_example(tokenizer,r,config) for r in rows];train_encoded=encoded[:len(train)]
        phase={'name':'training'};counts={};encoder_counts={}
        def increment(counter):counter[phase['name']]=counter.get(phase['name'],0)+1
        mh=model.register_forward_pre_hook(lambda *_:increment(counts))
        eh=model.get_encoder().register_forward_pre_hook(lambda *_:increment(encoder_counts))
        with t.run.AppendJournal(out.with_suffix('.journal.jsonl'),report['planSha256']) as journal:
            journal.append('begin',{'runId':plan['runId'],'slots':slots})
            a={**slots[0],'status':'started','startedMonotonicNs':time.monotonic_ns(),'checkpoints':[]}
            report['activeAttempt']=a;journal.append('attempt_start',a)
            def checkpoint(name,payload):
                row={k:a[k] for k in ('arm','caseId','repeat')};row.update(name=name,payload=payload)
                journal.append('attempt_checkpoint',row);a['checkpoints'].append(copy.deepcopy(row))
            def inspect(step):
                phase['name']=f'probe{step}'
                evaluate_loss(torch,model,encoded,rows,tokenizer.pad_token_id,step,checkpoint)
                if step in plan['generationSteps']:
                    destination=ROOT/'.local/world-components-logic/realizer-adapters'/plan['runId']/f'step-{step}'
                    identity=t.save_reload_adapter(torch,model,destination,source_hash,checkpoint)
                    phase['name']=f'generate{step}'
                    predictions=t.generate_expressions(torch,model,tokenizer,rows,f's{step:03}',checkpoint,config)
                    checkpoint('grid_candidate',{'step':step,'adapter':identity,'predictions':predictions})
                phase['name']='training'
            def training_checkpoint(name,payload):
                checkpoint(name,payload)
                if name=='training_step_settled' and payload['step'] in plan['probeSteps']:inspect(payload['step'])
            inspect(0)
            a['losses']=t.fit_encoded_adapter(torch,model,train_encoded,tokenizer.pad_token_id,config,training_checkpoint)
            checkpoint('model_forward_accounting',{'modelTopForwardCallsByPhase':counts,'encoderForwardCallsByPhase':encoder_counts})
            if any(p.grad is not None for p in model.parameters() if not p.requires_grad):raise ValueError('frozen backbone acquired gradient')
            if t.old.tensor_hash(t.base_state(model))!=source_hash:raise ValueError('grid changed frozen source')
            a.update(status='complete',settledAt=t.timestamp());journal.append('attempt_result',a)
            timing={k:a[k] for k in ('arm','caseId','repeat')};timing.update(resultJournalMs=0.,snapshotEndMs=0.,elapsedThroughResultMs=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6)
            journal.append('attempt_settled',timing);a.update(timing);report['attempts']=[a];report['activeAttempt']=None
        mh.remove();eh.remove()
        report.update(status='diagnostic_completed',sourceWeightsUnchanged=True,sourceFilesUnchanged=t.observe_m02(ROOT)==manifest['model'],unexecutedAttempts=0)
    except Exception as error:report.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
    finally:t.save(out,report)
    return 0 if report['status']=='diagnostic_completed' else 1


def execute(path):
    return t.run.execute_plan(path,paths=t.old.paths,verify=verify,worker_script=Path(__file__),settle_stages=t.old.settle_stages,arms=('grid',))


def available(path):
    return path if path.exists() else path.with_suffix(path.suffix+'.gz')


def raw_sha(path):
    raw=path.read_bytes()
    return hashlib.sha256(gzip.decompress(raw) if path.suffix=='.gz' else raw).hexdigest()


def archive_file(path):
    """Lossless own-run archival; executed bytes and identity remain unchanged."""
    target=path.with_suffix(path.suffix+'.gz')
    if not path.exists():
        if not target.exists():raise FileNotFoundError(path)
        return
    raw=path.read_bytes();packed=gzip.compress(raw,mtime=0)
    if target.exists() and target.read_bytes()!=packed:raise ValueError('preserve unrelated archive')
    if not target.exists():
        with target.open('xb') as stream:stream.write(packed)
    if gzip.decompress(target.read_bytes())!=raw:raise ValueError('archive roundtrip mismatch')
    path.unlink()


def observed(run_id):
    pp,rp=t.old.paths(run_id);plan=t.run.read_json(pp);record_path=available(rp);record=t.run.read_json(record_path);verify(plan,historical=True)
    if record['planSha256']!=t.sha256_file(pp):raise ValueError('grid plan identity mismatch')
    replay=copy.deepcopy(record);journal=available(rp.with_suffix('.journal.jsonl'));t.run.reconcile_journal(replay,journal,'read_only_grid_check')
    replay['journalRecovery']['sha256']=raw_sha(journal)
    if replay['attempts']!=record['attempts'] or replay['journalRecovery']!=record['journalRecovery']:raise ValueError('grid journal reconstruction differs')
    if (record['status']!='diagnostic_completed' or record['supervisor']['stopReason'] is not None or record['supervisor']['exitCode']!=0
            or not record['sourceWeightsUnchanged'] or not record['sourceFilesUnchanged'] or record['formalEvaluationAllowed'] is not False):raise ValueError('grid incomplete/invalid scope')
    if len(record['attempts'])!=1 or record['attempts']!=record['attemptSlots']:raise ValueError('grid missing trajectory slot')
    events=record['attempts'][0]['checkpoints'];payloads=lambda name:[e['payload'] for e in events if e['name']==name]
    started=payloads('training_step_started');settled=payloads('training_step_settled');train,dev=data();rows=train+dev
    if [e['step'] for e in started]!=list(range(1,plan['config']['steps']+1)) or [e['step'] for e in settled]!=[e['step'] for e in started]:raise ValueError('grid optimizer steps incomplete')
    allowed={(r['annotationId'],r['sourceGroup']) for r in train}
    for event in started:
        if len(event['annotationIds'])!=2 or any(pair not in allowed for pair in zip(event['annotationIds'],event['sourceGroups'])):raise ValueError('development or unknown example reached gradient')
    probes=payloads('loss_probe');candidates=payloads('grid_candidate');generations=payloads('generation_output');timings=payloads('generation_timing')
    if [p['step'] for p in probes]!=plan['probeSteps'] or [c['step'] for c in candidates]!=plan['generationSteps']:raise ValueError('grid probe/checkpoint omitted')
    expected_ids=[r['annotationId'] for r in rows]
    for probe in probes:
        if [e['annotationId'] for e in probe['entries']]!=expected_ids or aggregate_loss(probe['entries'])!=probe['metrics']:raise ValueError('grid probe coverage/aggregation drift')
        for row,entry in zip(rows,probe['entries']):
            if entry['inputSha256']!=t.digest(t.realizer_payload(row)) or entry['targetSha256']!=row['expressionSha256'] or entry['role']!=row['role'] or entry['sourceGroup']!=row['sourceGroup'] or entry['targetTokens']!=len(entry['targetTokenIds']):raise ValueError('grid loss source/role drift')
    if len(generations)!=48*len(candidates) or len(payloads('generation_started'))!=len(generations):raise ValueError('grid dropped generation attempt')
    for candidate in candidates:
        phase=f's{candidate["step"]:03}'
        if candidate['predictions']!=[p for p in generations if p['phase']==phase] or [p['annotationId'] for p in candidate['predictions']]!=expected_ids:raise ValueError('grid generation snapshot differs')
        for row,prediction in zip(rows,candidate['predictions']):
            if prediction['inputText']!=t.input_text(row) or prediction['inputSha256']!=t.digest(t.realizer_payload(row)) or prediction['role']!=row['role'] or prediction['sourceGroup']!=row['sourceGroup'] or prediction['modelTopForwardCalls']!=len(prediction['tokenIds'])-1 or prediction['eos']!=(prediction['tokenIds'][-1]==1):raise ValueError('grid output identity drift')
            timing=next(q for q in timings if q['phase']==phase and q['annotationId']==prediction['annotationId'])
            prediction['elapsedIncludingOutputJournalMs']=timing['elapsedIncludingOutputJournalMs']
        candidate.update(candidateId=f'{run_id}-s{candidate["step"]:03}',config={**plan['config'],'steps':candidate['step']},
            lossProbe=next(p for p in probes if p['step']==candidate['step']))
    counts=payloads('model_forward_accounting')[0];expected_encoder={'training':plan['config']['steps'],**{f'probe{i}':48 for i in plan['probeSteps']},**{f'generate{i}':48 for i in plan['generationSteps']}}
    if counts['encoderForwardCallsByPhase']!=expected_encoder or counts['modelTopForwardCallsByPhase']!={**expected_encoder,**{f'generate{c["step"]}':sum(p['modelTopForwardCalls'] for p in c['predictions']) for c in candidates}}:raise ValueError('grid actual forward count mismatch')
    if len(payloads('loss_forward_started'))!=48*len(probes) or len(payloads('loss_forward_settled'))!=48*len(probes):raise ValueError('grid probe forward attempts incomplete')
    if record['attempts'][0]['losses']!=[e['loss'] for e in settled]:raise ValueError('grid loss snapshot mismatch')
    control=None
    if plan['config']=={**t.CONFIG,'allowGroupedExamples':True,'steps':320}:
        parents={80:t.observed_fit(x.RUN),320:t.observed_fit(t.BUDGET_RUN)}
        control={}
        for step,parent in parents.items():
            candidate=next(c for c in candidates if c['step']==step)
            if candidate['adapter']['tensorSha256']!=parent['checkpoint']['tensorSha256'] or [p['raw'] for p in candidate['predictions']]!=[p['after_fit']['raw'] for p in parent['comparisons']]:raise ValueError('grid original configuration failed historical reproduction')
            control[str(step)]={'adapterTensorExact':True,'outputsExact':True,'lossPrefixExact':[e['loss'] for e in settled[:step]]==parent['losses']}
    return {'runId':run_id,'config':plan['config'],'probes':probes,'candidates':candidates,'supervisor':record['supervisor'],
        'trainingSteps':len(settled),'trainingSampleUses':2*len(started),'generationCalls':len(generations),
        'modelForwardCounts':counts,'historicalControl':control,'recordSha256':raw_sha(record_path),'journalSha256':raw_sha(journal),
        'recordArtifact':str(record_path.relative_to(ART)),'journalArtifact':str(journal.relative_to(ART))}


def reviews(cells,path,record_hashes):
    review=t.run.read_json(path)
    if review.get('schema')!='jity-d-realizer-grid-assistant-review-v1' or review.get('reviewer')!='assistant' or review.get('formalEvaluationAllowed') is not False or review.get('recordHashes')!=record_hashes:raise ValueError('grid review scope/record identity drift')
    expected={(p['annotationId'],t.digest(p['raw'])) for c in cells for p in c['predictions'] if p['role']=='development_candidate'};decisions={}
    for row in review['decisions']:
        key=(row['annotationId'],row['rawOutputSha256'])
        if key in decisions or key not in expected or row['verdict'] not in ('candidate_correct','fail','uncertain') or not row['reason'].strip():raise ValueError('grid review unknown/duplicate output')
        decisions[key]=row
    if set(decisions)!=expected:raise ValueError('grid development outputs not fully reviewed')
    return decisions


def score(candidate,decisions):
    dev=[p for p in candidate['predictions'] if p['role']=='development_candidate'];groups={}
    for p in dev:groups.setdefault(p['sourceGroup'],[]).append(decisions[p['annotationId'],t.digest(p['raw'])]['verdict'])
    verdicts=[v for values in groups.values() for v in values];metrics=candidate['lossProbe']['metrics']
    return {'candidateId':candidate['candidateId'],'config':candidate['config'],
        'allVariantsCorrectGroups':sum(all(v=='candidate_correct' for v in values) for values in groups.values()),'developmentGroups':len(groups),
        'correctExamples':verdicts.count('candidate_correct'),'failedExamples':verdicts.count('fail'),'uncertainExamples':verdicts.count('uncertain'),
        'developmentGroupMacroNll':metrics['development_candidate']['groupMacroNll'],
        'trainGroupMacroNll':metrics['train_candidate']['groupMacroNll'],
        'allOutputsEos':all(p['eos'] for p in candidate['predictions'])}


def ranking(value):
    c=value['config'];return (-value['allVariantsCorrectGroups'],-value['correctExamples'],value['developmentGroupMacroNll'],c['steps'],c['learningRate'],-c['weightDecay'])


def grid_result():
    runs=[observed(e['runId']) for e in catalog()];cells=[c for run in runs for c in run['candidates']]
    hashes={r['runId']:r['recordSha256'] for r in runs};decisions=reviews(cells,REVIEW,hashes)
    scores=sorted((score(c,decisions) for c in cells),key=ranking)
    return runs,cells,decisions,scores


def select():
    if SELECTION.exists():raise FileExistsError('preserve locked grid selection')
    runs,cells,decisions,scores=grid_result()
    result={'schema':'jity-d-realizer-grid-selection-v1','searchId':SEARCH,'selectedAt':t.timestamp(),
        'manifestSha256':t.sha256_file(MANIFEST),'reviewSha256':t.sha256_file(REVIEW),'selected':scores[0],
        'nllMinimum':min(scores,key=lambda s:s['developmentGroupMacroNll']),'rankedCandidates':scores,
        'recordHashes':{r['runId']:r['recordSha256'] for r in runs},'formalEvaluationAllowed':False}
    t.exclusive(SELECTION,result)
    for entry in confirmation_entries(result):prepare_trajectory(t.run.read_json(MANIFEST),entry,t.sha256_file(SELECTION))
    return result


def locked_selection():
    selection=t.run.read_json(SELECTION)
    if selection['manifestSha256']!=t.sha256_file(MANIFEST) or selection['reviewSha256']!=t.sha256_file(REVIEW) or selection['formalEvaluationAllowed'] is not False:raise ValueError('locked selection identity drift')
    return selection


def materials(write=False):
    if write:
        for entry in catalog()+confirmation_entries(locked_selection()):
            _,rp=t.old.paths(entry['runId']);archive_file(rp);archive_file(rp.with_suffix('.journal.jsonl'))
    runs,cells,decisions,scores=grid_result();selection=locked_selection()
    if selection['rankedCandidates']!=scores or selection['selected']!=scores[0] or selection['recordHashes']!={r['runId']:r['recordSha256'] for r in runs}:raise ValueError('selection no longer matches frozen grid')
    confirmations=[observed(e['runId']) for e in confirmation_entries(selection)]
    confirmation_cells=[c for r in confirmations for c in r['candidates']]
    confirmation_decisions=reviews(confirmation_cells,CONFIRM_REVIEW,{r['runId']:r['recordSha256'] for r in confirmations})
    confirmed=[score(c,confirmation_decisions) for c in confirmation_cells]
    summary={'schema':'jity-d-realizer-grid-summary-v1','date':'2026-11-05','batchId':SEARCH,
        'stage':'L3-21 bounded hyperparameter grid and overfitting diagnosis','lastModelRun':confirmations[-1]['runId'],
        'draftSourceGroups':30,'review':{'reviewedGroups':0,'missingReviews':48,'formalEvaluationAllowed':False},
        'realizerTrained':True,'realizerTrainerImplemented':True,'plannerModelImplemented':False,
        'semanticQualityApproved':False,'formalEvaluationAllowed':False,'fullRequest500msStatus':'unverified',
        'newExamples':0,'sourceIndependence':'unverified','gridPoints':18,'selection':selection,
        'supersededPreparation':{'searchId':'m02-realizer-grid-20261105-r1','status':'failed_process_launch',
            'reason':'supervisor environment field absent; fixed in r2','modelCalls':0,'trainingSteps':0,
            'sourceSnapshotCommit':'62391bc','remainingTrajectoriesUnstarted':5},
        'confirmationScores':confirmed,'trajectories':runs+confirmations,
        'trainingSteps':sum(r['trainingSteps'] for r in runs+confirmations),
        'generationAttempts':sum(r['generationCalls'] for r in runs+confirmations),
        'outputReviewSha256':t.sha256_file(REVIEW),'confirmationReviewSha256':t.sha256_file(CONFIRM_REVIEW)}
    document=render(summary,cells+confirmation_cells,{**decisions,**confirmation_decisions})
    files={ART/(PAGE+'-summary.json'):(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),ART/(PAGE+'.html'):document.encode()}
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('preserve original grid report')
        if not write and not path.exists():raise ValueError('grid report missing')
    if write:
        for path,raw in files.items():
            if not path.exists():
                with path.open('xb') as stream:stream.write(raw)
    return summary


def render(summary,cells,decisions):
    import html
    e=lambda value:html.escape(str(value));selection=summary['selection'];winner=selection['selected']
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3-21 超参数与过拟合检查</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui}main{max-width:1200px;margin:auto;padding:24px}section{background:white;padding:22px;border-radius:12px;margin:20px 0}table{border-collapse:collapse;width:100%}td,th{padding:9px;text-align:left;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere}.warn{color:#a7352e}.scroll{overflow:auto}</style><main><p>D / L3-21 · 2026-11-05</p><h1>超参数与过拟合：18组实际对照</h1>'''
    document+=f'<section><h2>怎样理解这次搜索</h2><p>学习率0.0003／0.001／0.003 × 权重衰减0.01／0.1 × 训练80／160／320步，共18组；原配置也在其中。全部使用相同30训练／18开发，rank4、batch2等固定。每条优化轨迹连续训练、固定时点评估，没有重置优化器或让开发题参与梯度。</p><p>本轮排序候选：学习率{winner["config"]["learningRate"]}，衰减{winner["config"]["weightDecay"]}，{winner["config"]["steps"]}步；开发{winner["correctExamples"]}/18条明确合理，{winner["allVariantsCorrectGroups"]}/12组全部变体合理。</p><p class="warn">排序来自助手草稿预检，人审0／来源未核。开发集用于选参数，不能当独立最终考试；这是本轮网格候选，不是全局最优或模型质量通过。自主规划、反应与共同结果、完整500ms、浏览器生产仍未验。</p></section><section><h2>全部候选：按开发质量排序</h2><div class="scroll"><table><tr><th>学习率</th><th>衰减</th><th>步数</th><th>合理组／12</th><th>合理／错／含糊（18题）</th><th>训练损失</th><th>开发损失</th></tr>'
    for item in selection['rankedCandidates']:
        c=item['config'];document+=f'<tr><td>{c["learningRate"]}</td><td>{c["weightDecay"]}</td><td>{c["steps"]}</td><td>{item["allVariantsCorrectGroups"]}</td><td>{item["correctExamples"]}／{item["failedExamples"]}／{item["uncertainExamples"]}</td><td>{item["trainGroupMacroNll"]:.6f}</td><td>{item["developmentGroupMacroNll"]:.6f}</td></tr>'
    document+='</table></div><p>先比较每组所有变体均合理的组数，再比较合理题数，之后比较开发损失；损失为sourceGroup宏平均，不等于自由生成正确率。</p></section><section><h2>训练／开发损失随步数变化</h2><p>每格为训练损失／开发损失。训练下降而开发回升是该轨迹的过拟合迹象，不能只看最后一批训练损失判断。</p>'
    for run in summary['trajectories']:
        c=run['config'];document+=f'<h3>学习率{c["learningRate"]} · 衰减{c["weightDecay"]} · seed{c["seed"]}</h3><div class="scroll"><table><tr><th>步数</th><th>训练</th><th>开发</th></tr>'
        for probe in run['probes']:
            m=probe['metrics'];document+=f'<tr><td>{probe["step"]}</td><td>{m["train_candidate"]["groupMacroNll"]:.6f}</td><td>{m["development_candidate"]["groupMacroNll"]:.6f}</td></tr>'
        document+=f'</table></div><p><a href="m01-fitting/{run["runId"]}.plan.json">冻结计划</a> · <a href="{e(run["recordArtifact"])}">原记录（无损gzip）</a> · <a href="{e(run["journalArtifact"])}">事件（无损gzip）</a></p>'
    document+=f'</section><section><h2>换seed7确认，没有继续调参</h2><pre>{e(json.dumps(summary["confirmationScores"],ensure_ascii=False,indent=2))}</pre><p>全部{len(summary["trajectories"])}条进程，合计训练{summary["trainingSteps"]}步、自由生成{summary["generationAttempts"]}次。每进程限CPU1线程／并发1、120秒／2048MiB；整批进程时间含训练、诊断、生成与存档，不能当作单次游戏等待。每题每模型生成一次，不签正式性能。</p></section>'
    lookup={r['annotationId']:r for r in x.rows()}
    for cell in cells:
        document+=f'<section><details><summary>{e(cell["candidateId"])}：全部48条原文</summary>'
        for p in cell['predictions']:
            decision=decisions.get((p['annotationId'],t.digest(p['raw']))) if p['role']=='development_candidate' else None
            document+=f'<h3>{e(p["annotationId"])} · {e(p["role"])}</h3><p>参考草稿：{e(lookup[p["annotationId"]]["expressionDraft"])}</p><p>原文：{e(p["raw"])}</p>'
            if decision:document+=f'<p>助手{e(decision["verdict"])}：{e(decision["reason"])}</p>'
            document+=f'<p>{p["elapsedIncludingOutputJournalMs"]:.2f}ms · EOS {e(p["eos"])}</p>'
        document+='</details></section>'
    document+=f'<section><h2>证据与方法</h2><p><a href="{PAGE}-summary.json">完整汇总／全部输入token与成本</a> · <a href="m01-fitting/{SEARCH}.manifest.json">冻结搜索清单</a> · <a href="m01-fitting/{SEARCH}.selection.json">锁定选择</a> · <a href="m01-fitting/{SEARCH}.output-review.json">全部开发原文的助手理由</a> · <a href="m01-fitting/{SEARCH}.confirmation-review.json">seed7助手理由</a> · <a href="https://scikit-learn.org/stable/modules/cross_validation.html">验证集与调参方法</a> · <a href="https://docs.pytorch.org/docs/2.7/generated/torch.nn.CrossEntropyLoss.html">有效token损失口径</a></p></section></main></html>'
    return document


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=Path);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    if args.worker:raise SystemExit(worker(args.worker))
    if args.check:
        s=materials();print(json.dumps({'gridPoints':s['gridPoints'],'trainingSteps':s['trainingSteps'],'generations':s['generationAttempts'],'formalEvaluationAllowed':False}));raise SystemExit(0)
    parser.error('use experiment.py realizer-search')
