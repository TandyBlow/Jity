"""Short-semantics data/plan/model execution via the existing D supervisor."""
from __future__ import annotations
import argparse
import copy
import gzip
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

import experiment as common
from lab import canonical_bytes, sha256_file
from run_pilot import digest, exclusive, save, timestamp
from short_training import validate_rows, task_specs, training_schedule

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
ART=ROOT/'artifacts/world-components-logic/short-semantics'
DATA=BASE/'data/short-semantics'
LOCAL=ROOT/'.local/world-components-logic'
REGISTRY=ROOT/'artifacts/world-components-logic/l2-model-sources-20261029.json'
MODEL_IDS={'encoder':'hfl/minirbt-h256','generator':'IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese'}
TRAIN_ARMS=('encoder_train','generator_train')
CONFIG={'device':'cpu','threads':1,'concurrency':1,'precision':'float32','seed':42,
        'steps':160,'batchSize':2,'learningRate':0.001,'weightDecay':0.01,'maxGradNorm':1.0,
        'rank':4,'alpha':8,'encoderLayers':[0,1],'encoderPooling':False,'promptCodec':'complete_json_executor_binding_v2','trainingSampling':'task_then_observed_label_then_source_round_robin_v1','generatorTokenizer':{'extra_ids':0,'legacy':True},'encoderTokenLimit':512,'maxInputTokens':8192,
        'maxTargetTokens':128,'maxNewTokens':128,'processWallSeconds':1800,
        'gradientCheckpointing':True,'gradientCheckpointingReentrant':False,'trainingDropout':0.0,'microbatchSize':1,
        'maxResidentMiB':4096,'attemptsPerCase':1,'earlyStopping':False,
        'retries':0,'doSample':False,'numBeams':1}
# Limits are resource admission checks, never a context shortening instruction.
CODE=('short_experiment.py','short_training.py','short_contracts.py','short_intent.py',
      'short_settlement.py','short_lifecycle.py','short_heads_updates.py','short_heads_lifecycle.py','short_handoff.py','short_preview.py','experiment.py','plan_training.py',
      'fact_windows.py','pilot_codec.py','lab.py','run_pilot.py','m01_probe.py',
      'prepare_run_batch.py','action_plan.py','generate_dev_drafts.py','data/short-semantics/author_packet.py','data/short-semantics/project_primitives.py')


def paths(run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}',run_id): raise ValueError('invalid run id')
    return ART/(run_id+'.plan.json'),ART/(run_id+'.record.json')


def load_rows(path=DATA/'supervision.jsonl.gz'):
    raw=Path(path).read_bytes()
    if str(path).endswith('.gz'):raw=gzip.decompress(raw)
    rows=[json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    validate_rows(rows)
    return rows


def audit_resources(model_root=None):
    """Exact local payload checks. No download, shared-cache mutation, or inference."""
    model_root=Path(model_root) if model_root else LOCAL/'models'
    registry=json.loads(REGISTRY.read_text()); models={}; blockers=[]
    for role,model_id in MODEL_IDS.items():
        spec=next(m for m in registry['models'] if m['id']==model_id)
        directory=model_root/('M01' if role=='encoder' else 'M02')/spec['revision']
        files=[]
        for f in spec['files']:
            # M02 has duplicate serialization; use its existing safetensors path.
            if role=='generator' and f['path']=='pytorch_model.bin': continue
            p=directory/f['path']; observed=sha256_file(p) if p.is_file() else None
            expected=f.get('lfs_sha256') or f.get('sha256_of_fetched_bytes')
            valid=bool(p.is_file() and p.stat().st_size==f['size_bytes'] and (not expected or observed==expected))
            if valid and not expected:
                import hashlib
                raw=p.read_bytes();valid=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==f.get('git_blob_sha1')
            files.append({'path':f['path'],'expectedSha256':expected,'observedSha256':observed,
                          'expectedBytes':f['size_bytes'],'valid':valid})
            if not valid: blockers.append('missing_or_mismatched_model_file:'+role+':'+f['path'])
        models[role]={'modelId':model_id,'revision':spec['revision'],'directory':str(directory),
                      'registrySha256':sha256_file(REGISTRY),'files':files,'available':all(f['valid'] for f in files)}
    dependencies={name:importlib.util.find_spec(name) is not None for name in ('torch','transformers','sentencepiece','numpy','pydantic')}
    blockers += ['missing_dependency:'+key for key,value in dependencies.items() if not value]
    versions={}
    for key,value in dependencies.items():
        if value:
            try: versions[key]=importlib.metadata.version(key)
            except importlib.metadata.PackageNotFoundError: versions[key]='unregistered'
    return {'models':models,'dependencies':dependencies,'versions':versions,'blockers':blockers,
            'pythonExecutable':sys.executable,'pythonVersion':sys.version,'platform':platform.platform(),
            'modelCalls':0,'trainingSteps':0,'scope':'local_presence_identity_only'}


def snapshot_code(run_id,names=None):
    """Retain the exact executed source bytes, independent of future edits."""
    names=tuple(CODE if names is None else names);paths(run_id)
    directory=ART/'code'/run_id
    files={}
    for name in names:
        source=BASE/name
        if not source.is_file():raise ValueError('snapshot source missing:'+name)
        destination=directory/name;destination.parent.mkdir(parents=True,exist_ok=True)
        raw=source.read_bytes()
        if destination.exists():
            if destination.read_bytes()!=raw:raise FileExistsError('source snapshot identity already used')
        else:
            with destination.open('xb') as stream:stream.write(raw)
        files[name]=sha256_file(destination)
    return {'directory':str(directory),'files':files}


def snapshot_data(run_id,dataset):
    directory=ART/'data'/run_id;directory.mkdir(parents=True,exist_ok=False)
    files={}
    source_directory=Path(dataset).parent
    for name,source in (('supervision.jsonl.gz',Path(dataset)),('manifest.json',source_directory/'manifest.json'),('sources.jsonl',source_directory/'sources.jsonl')):
        destination=directory/name
        with destination.open('xb') as stream:stream.write(source.read_bytes())
        files[name]={'path':str(destination),'sha256':sha256_file(destination)}
    return files


def configuration(profile='intent'):
    if profile not in ('intent','all'):raise ValueError('unknown frozen task profile')
    return {**copy.deepcopy(CONFIG),'profile':profile}


def select_rows(rows,profile):
    return [r for r in rows if profile=='all' or r['component'].startswith(('D02.','D03.','D04.'))]


def registered_schedules(rows,config):
    return {role:training_schedule([r for r in rows if r['kind'] in kinds],config)
            for role,kinds in (('encoder',('label','reference','number')),('generator',('text',)))}


def token_statistics(rows,models,config,schedules=None):
    """Actual complete tokenizer workload, no model load/forward or truncation."""
    from transformers import AutoTokenizer,T5Tokenizer
    from fact_windows import make_windows
    from short_training import input_text
    generator=T5Tokenizer.from_pretrained(models['generator']['directory'],local_files_only=True,**config['generatorTokenizer'])
    encoder=AutoTokenizer.from_pretrained(models['encoder']['directory'],local_files_only=True,trust_remote_code=False)
    components={};errors=[];started=time.perf_counter()
    schedules=schedules or registered_schedules(rows,config)
    scheduled=set(schedules['encoder']['exampleIds']);generator_ids=schedules['generator']['exampleIds']
    generator_counts={key:generator_ids.count(key) for key in set(generator_ids)}
    scheduled_generator_max=0;long_scheduled_generator=0
    for row in rows:
        if row['kind']=='annotation_only':continue
        out=components.setdefault(row['component'],{'kind':row['kind'],'trainRows':0,'evaluationRows':0,
             'maxInputTokens':0,'maxTargetTokens':0,'trainEncoderWindows':0,'scheduledTrainEncoderWindows':0,'evaluationEncoderWindows':0})
        training=row['split']=='train';out['trainRows' if training else 'evaluationRows']+=1
        try:
            if row['kind']=='text':
                x=generator.encode(input_text(row['component'],row['input']),add_special_tokens=True,truncation=False)
                y=generator.encode(row['target'],add_special_tokens=True,truncation=False)
                out['maxInputTokens']=max(out['maxInputTokens'],len(x));out['maxTargetTokens']=max(out['maxTargetTokens'],len(y))
                if row['exampleId'] in generator_counts:
                    scheduled_generator_max=max(scheduled_generator_max,len(x))
                    if len(x)>2500:long_scheduled_generator+=generator_counts[row['exampleId']]
                if len(x)>config['maxInputTokens'] or len(y)>config['maxTargetTokens']:raise ValueError('complete token budget exceeded')
            else:
                _,windows=make_windows(row['input'],encoder,row['component'],config['encoderTokenLimit'])
                total=len(windows);out['maxInputTokens']=max(out['maxInputTokens'],sum(w['totalTokens'] for w in windows))
                if row['kind']=='reference':
                    for candidate in row['input']['candidates']:
                        _,cw=make_windows(candidate,encoder,row['component']+':candidate',config['encoderTokenLimit']);total+=len(cw)
                out['trainEncoderWindows' if training else 'evaluationEncoderWindows']+=total
                if row['exampleId'] in scheduled:out['scheduledTrainEncoderWindows']+=total
        except Exception as error:errors.append({'exampleId':row['exampleId'],'error':str(error)})
    return {'status':'complete' if not errors else 'blocked','components':components,'errors':errors,
      'elapsedMs':(time.perf_counter()-started)*1000,'neuralCalls':0,'trainingSteps':0,
      'generatorScheduledSamples':len(generator_ids),'generatorScheduledUniqueSamples':len(generator_counts),
      'maxScheduledGeneratorInputTokens':scheduled_generator_max,'scheduledGeneratorSamplesOver2500Tokens':long_scheduled_generator,
      'tokenizersOnly':True,'allInputsComplete':not errors,'scope':config['profile']}


def freeze(run_id, *, model_root=None, dataset=None, profile='intent'):
    path,out=paths(run_id)
    if path.exists() or out.exists(): raise FileExistsError('new run identity required; preserve evidence')
    dataset=Path(dataset) if dataset else DATA/'supervision.jsonl.gz'; rows=select_rows(load_rows(dataset),profile)
    source_manifest=common.read_json(dataset.parent/'manifest.json')
    if source_manifest['files'].get(dataset.name)!=sha256_file(dataset):raise ValueError('source manifest does not identify this supervision packet')
    resource=audit_resources(model_root);code={name:sha256_file(BASE/name) for name in CODE if (BASE/name).exists()}
    missing=[name for name in CODE if not (BASE/name).exists()]
    blockers=resource['blockers']+['missing_code:'+name for name in missing]
    schedules=registered_schedules(rows,configuration(profile))
    token_work=token_statistics(rows,resource['models'],configuration(profile),schedules) if not blockers else {'status':'blocked','errors':[],'neuralCalls':0}
    blockers += ['tokenization:'+e['exampleId']+':'+e['error'] for e in token_work.get('errors',[])]
    packet=validate_rows(rows);source_snapshot=snapshot_code(run_id);data_snapshot=snapshot_data(run_id,dataset)
    plan={'schema':'jity-d-short-semantics-plan-v1','runId':run_id,'preparedAt':timestamp(),
      'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
      'activeArchitecture':'short_semantics_only_no_legacy_fallback',
      'purpose':'assistant_draft_training_and_validation_preparation','config':configuration(profile),
      'dataset':{'path':data_snapshot['supervision.jsonl.gz']['path'],'sha256':sha256_file(dataset),'inventory':packet,
                 'sourceGroups':{r['sourceGroup']:r['split'] for r in rows},'tasks':task_specs(rows),
                 'sourceManifestSha256':data_snapshot['manifest.json']['sha256'],'sourcesSha256':data_snapshot['sources.jsonl']['sha256'],
                 'sourceManifestPath':data_snapshot['manifest.json']['path'],'sourcesPath':data_snapshot['sources.jsonl']['path'],
                 'previousExposure':source_manifest.get('previousExposure'),'holdoutStatus':source_manifest.get('holdoutStatus'),
                 'runtimeCatalog':source_manifest.get('runtimeCatalog'),'authoredPreview':source_manifest.get('authoredPreview')},
      'models':resource['models'],'environment':{'venvExecutableRelativePath':sys.executable,
             'pythonVersion':sys.version,'dependencies':resource['dependencies'],'versions':resource['versions']},
      'codeSha256':code,'codeSnapshot':source_snapshot,'dataSnapshot':data_snapshot,'cases':[{'caseId':'new-draft-training'}],
      'trainingArms':list(TRAIN_ARMS),'trainingSchedules':schedules,'readiness':'blocked' if blockers else 'ready_exploratory',
      'blockers':blockers,'authorization':{'source':'current_user_request_2026-11-09',
        'scope':'author_new_data_and_train_local_models_for_exploration','paidServices':False,
        'humanReviewDelegatedToAssistant':False},
      'review':{'assistantAuthored':True,'human':'pending','sourceVerification':'pending',
                'exploratoryDraftUseAuthorized':True,'formalEvaluationAllowed':False},
      'comparisonArms':[
        {'id':'diagnostic_correct_intermediate','input':'same frozen full worlds with authored intermediate candidates','claim':'isolated downstream diagnostic, not autonomous planning'},
        {'id':'live_upstream','input':'same full worlds, actual preceding model outputs only','claim':'new chain; all first outputs and failures included'}],
      'representationSubarms':['natural','references'],'referenceDefaultPromoted':False,
      'legacyComparison':{'execution':'not_scheduled','evidence':'existing archived reports only','comparability':'historical_different_machine_scope_not_a_new_control_arm'},
      'thresholds':{'structure':1.0,'referenceCoverage':1.0,'requiredCoverage':1.0,
        'criticalSemanticErrors':0,'fullRequestWallMs':500,'semanticHumanReviewRequiredForPromotion':True},
      'retryPolicy':{'maxRetries':0,'changedFrozenActionOrRollAllowed':False,'firstOutputRetained':True,
                     'budgetExhaustion':'incomplete','modelFailure':'incomplete'},
      'workload':{'registrationStatus':'training_and_local_component_only','tokenization':token_work,
        'fullRequestIncludes':['D_models','program','service_roundtrips','reaction_chain','six_stages',
           'associated_segments','automatic_followups','retries','C_generation','ready_wait'],
        'fullRequestMeasurement':'not_available_until_AB_and_real_C_connected',
        'timingBuckets':['cold_load','request_load','D_compute','program_service','C_generation','ready_wait','request_total'],
        'inferenceSplits':['development','test'],'trainingFitQualityClaim':False,'testGroupsSealed':False,'testReason':'assistant-authored open candidate holdout; no formal independence claim'},
      'formalEvaluationAllowed':False,'fullRequest500msStatus':'unmeasured'}
    ART.mkdir(parents=True,exist_ok=True);exclusive(path,plan)
    return path


def verify(plan, *, require_resources=True):
    if plan['schema']!='jity-d-short-semantics-plan-v1': raise ValueError('wrong plan schema')
    if plan['config']!=configuration(plan['config']['profile']): raise ValueError('configuration drift; freeze a new run')
    if plan['trainingArms']!=list(TRAIN_ARMS): raise ValueError('training arm drift')
    path=Path(plan['dataset']['path'])
    if sha256_file(path)!=plan['dataset']['sha256']: raise ValueError('dataset drift')
    rows=select_rows(load_rows(path),plan['config']['profile'])
    if validate_rows(rows)!=plan['dataset']['inventory']: raise ValueError('dataset inventory drift')
    if task_specs(rows)!=plan['dataset']['tasks'] or {r['sourceGroup']:r['split'] for r in rows}!=plan['dataset']['sourceGroups']:raise ValueError('task vocabulary/codec/source split drift')
    if registered_schedules(rows,plan['config'])!=plan['trainingSchedules']:raise ValueError('training schedule drift')
    if set(plan['codeSha256'])!=set(CODE):raise ValueError('incomplete code identity manifest')
    if sha256_file(plan['dataset']['sourceManifestPath'])!=plan['dataset']['sourceManifestSha256'] or sha256_file(plan['dataset']['sourcesPath'])!=plan['dataset']['sourcesSha256']:raise ValueError('source manifest drift')
    for name,expected in plan['codeSha256'].items():
        if sha256_file(Path(plan['codeSnapshot']['directory'])/name)!=expected:raise ValueError('executed source snapshot drift:'+name)
        if sha256_file(BASE/name)!=expected: raise ValueError('execution code drift:'+name)
    if require_resources:
        for role,model in plan['models'].items():
            if not model['available']: raise ValueError('missing local '+role+' payload')
            for f in model['files']:
                if sha256_file(Path(model['directory'])/f['path'])!=f['observedSha256']: raise ValueError('model byte drift')
        if not all(plan['environment']['dependencies'].values()): raise ValueError('missing neural dependencies')
        if sys.version!=plan['environment']['pythonVersion']:raise ValueError('Python environment drift')
        for name,version in plan['environment']['versions'].items():
            if importlib.metadata.version(name)!=version:raise ValueError('dependency version drift:'+name)
    return rows


def worker(path):
    plan=common.read_json(path);rows=verify(plan);_,out=paths(plan['runId'])
    slots=common.planned_slots(plan,TRAIN_ARMS)
    report={'schema':'jity-d-short-training-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),
            'status':'running','stages':[],'attempts':[],'attemptSlots':slots,'activeAttempt':None,
            'checkpointStorage':common.CHECKPOINT_STORAGE,
            'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequestMeasured':False}
    exclusive(out,report)
    try:
        import torch
        from transformers import AutoModel,AutoTokenizer,T5ForConditionalGeneration,T5Tokenizer
        from short_training import train_heads,train_generator,load_neural
        torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(plan['config']['seed'])
        with common.AppendJournal(out.with_suffix('.journal.jsonl'),report['planSha256']) as journal:
            journal.append('begin',{'runId':plan['runId'],'slots':slots,'checkpointStorage':common.CHECKPOINT_STORAGE})
            for slot in slots:
                attempt={**slot,'status':'started','startedMonotonicNs':time.monotonic_ns(),'checkpoints':[]}
                report['activeAttempt']=attempt;journal.append('attempt_start',attempt)
                def checkpoint(name,payload):
                    event={k:attempt[k] for k in ('arm','caseId','repeat')};event.update(name=name,payload=payload)
                    reference=common.append_checkpoint(journal,event)
                    attempt['checkpoints'].append(reference);return reference
                try:
                    role='encoder' if slot['arm']=='encoder_train' else 'generator'
                    directory=plan['models'][role]['directory'];begin=time.perf_counter()
                    model,tokenizer=load_neural(torch,role,directory,plan['config'])
                    checkpoint('cold_model_load',{'role':role,'elapsedMs':(time.perf_counter()-begin)*1000,
                                                 'parameters':sum(p.numel() for p in model.parameters())})
                    destination=LOCAL/'short-semantic-models'/plan['runId']/role
                    result=(train_heads if role=='encoder' else train_generator)(torch,model,tokenizer,rows,plan['config'],destination,checkpoint)
                    attempt.update(status='complete',training=result);del model,tokenizer
                except Exception as error:
                    attempt.update(status='failed',completion='incomplete',error={'type':type(error).__name__,'message':str(error)})
                journal.append('attempt_result',attempt)
                timing={k:attempt[k] for k in ('arm','caseId','repeat')}
                timing.update(resultJournalMs=0.,snapshotEndMs=0.,elapsedThroughResultMs=(time.monotonic_ns()-attempt['startedMonotonicNs'])/1e6)
                journal.append('attempt_settled',timing);attempt.update(timing)
                report['attempts'].append(attempt);report['activeAttempt']=None;save(out,report)
        report['status']='diagnostic_completed' if all(a['status']=='complete' for a in report['attempts']) else 'failed'
        report['unexecutedAttempts']=0
        if report['status']=='diagnostic_completed':
            manifest={'schema':'jity-d-short-trained-provider-v1','runId':plan['runId'],
              'datasetSha256':plan['dataset']['sha256'],'codeSha256':plan['codeSha256'],
              'config':plan['config'],'tasks':plan['dataset']['tasks'],'models':{},
              'recordPath':str(out),'trainingEvidence':'actual_optimizer_steps_with_component_exposures',
              'formalEvaluationAllowed':False,'semanticQualityApproved':False}
            for attempt in report['attempts']:
                role='encoder' if attempt['arm']=='encoder_train' else 'generator';trained=attempt['training']
                components=trained.get('trainedHeadComponents',trained.get('trainedComponents',[]))
                manifest['models'][role]={**plan['models'][role],'checkpoint':trained['checkpoint'],
                  'trainingSteps':trained['steps'],'trainedComponents':components,
                  'componentGradientExposures':trained['componentGradientExposures'],
                  'componentNonzeroDataGradientSteps':trained.get('componentNonzeroDataGradientSteps'),
                  'taskSpecs':trained.get('specs',{c:plan['dataset']['tasks'][c] for c in components})}
            destination=LOCAL/'short-semantic-models'/plan['runId']/'provider.json'
            exclusive(destination,manifest);report['providerManifest']={'path':str(destination),'sha256':sha256_file(destination)}
    except Exception as error:
        report.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
    finally: save(out,report)
    return 0 if report['status']=='diagnostic_completed' else 1


def execute(path):
    plan=common.read_json(path);verify(plan,require_resources=False)
    if plan['readiness']=='blocked':
        _,out=paths(plan['runId'])
        report=common.unstarted_record(plan,path,TRAIN_ARMS)
        report.update(status='blocked_preflight',runId=plan['runId'],completion='incomplete',
            blockers=plan['blockers'],trainingSteps=0,modelCalls=0,formalEvaluationAllowed=False,
            firstOutputCount=0,allPlannedAttemptsRetained=True)
        exclusive(out,report)
        print(json.dumps({'status':report['status'],'unstartedAttempts':report['unexecutedAttempts'],'record':str(out)}))
        return 2
    def settle_stages(report,reason):
        for stage in report.get('stages',[]):
            if stage['status']=='running':stage.update(status='interrupted',stopReason=reason)
    code=common.execute_plan(path,paths=paths,verify=verify,worker_script=Path(__file__),
                               settle_stages=settle_stages,arms=TRAIN_ARMS)
    _,out=paths(plan['runId']);report=common.read_json(out)
    rows=select_rows(load_rows(plan['dataset']['path']),plan['config']['profile'])
    slots={r['exampleId']:{'exampleId':r['exampleId'],'component':r['component'],'split':r['split'],
          'status':'not_started','arm':'generator_train' if r['kind']=='text' else 'encoder_train'}
          for r in rows if r['kind']!='annotation_only' and r['split']!='train'}
    journal_path=out.with_suffix('.journal.jsonl')
    events=common.iter_checkpoint_events(report,journal_path) if journal_path.exists() or journal_path.with_name(journal_path.name+'.gz').exists() else ()
    for event in events:
        body=event['payload'];identity=body.get('exampleId')
        if identity in slots:
            if event['name'] in ('generation_started','head_prediction_started'):slots[identity]['status']='started'
            elif event['name'] in ('generation_output','head_prediction'):
                slots[identity].update(status='complete' if body.get('completion','result')=='result' else 'incomplete',
                                      completion=body.get('completion','result'))
    trained=set(next((a.get('training',{}).get('trainedHeadComponents',[]) for a in report.get('attempts',[]) if a['arm']=='encoder_train'),[]))
    for slot in slots.values():
        if slot['status']=='started':slot.update(status='incomplete',reason='interrupted_or_failed_after_start')
        elif slot['status']=='not_started' and slot['arm']=='encoder_train' and slot['component'] not in trained:
            slot['reason']='untrained_or_no_nonzero_data_gradient'
    report['predictionSlots']=list(slots.values());report['unstartedPredictions']=sum(s['status']=='not_started' for s in slots.values())
    save(out,report);return code


def readiness_report(plan_path):
    plan_path=Path(plan_path);plan=common.read_json(plan_path)
    # Historical reading verifies retained evidence, not today's runnable code.
    for name,expected in plan['codeSha256'].items():
        if sha256_file(Path(plan['codeSnapshot']['directory'])/name)!=expected:raise ValueError('historical source snapshot drift:'+name)
    for snapshot in plan['dataSnapshot'].values():
        if sha256_file(snapshot['path'])!=snapshot['sha256']:raise ValueError('historical data snapshot drift')
    _,record_path=paths(plan['runId'])
    if not record_path.exists() and record_path.with_name(record_path.name+'.gz').exists():record_path=record_path.with_name(record_path.name+'.gz')
    record=common.read_json(record_path) if record_path.exists() else None
    if record is not None and record.get('planSha256')!=sha256_file(plan_path):raise ValueError('historical plan/record identity mismatch')
    drift=[name for name,expected in plan['codeSha256'].items() if not (BASE/name).is_file() or sha256_file(BASE/name)!=expected]
    return {'runId':plan['runId'],'readiness':plan['readiness'],'blockers':plan['blockers'],
      'dataset':plan['dataset']['inventory'],'modelTrainingStatus':'not_run' if not record else record['status'],
      'trainingSteps':0 if not record else sum(a.get('training',{}).get('steps',0) for a in record.get('attempts',[])),
      'frozenEvidenceVerified':True,'currentSourceDrift':drift,'rerunStatus':'new_freeze_required' if drift or record else 'original_identity_current',
      'recordOutcomeReason':record.get('reason') if record else None,
      'supervisor':record.get('supervisor') if record else None,
      'semanticQuality':'pending_review_not_inferred_from_structure_or_exact_match','coverageQuality':'see_per_component_records','fullRequest500ms':'unmeasured',
      'comparison':'separate_evaluation_plan_and_record_required',
      'humanReview':'pending','sourceVerification':'pending'}


def active_status():
    available=(DATA/'supervision.jsonl.gz').exists()
    rows=load_rows() if available else []
    providers=[]
    for path in sorted((LOCAL/'short-semantic-models').glob('*/provider.json')):
        value=common.read_json(path)
        if value.get('schema')=='jity-d-short-trained-provider-v1' and all(m.get('trainingSteps',0)>0 for m in value.get('models',{}).values()):
            providers.append({'runId':value['runId'],'path':str(path),'formalQualityApproved':value['semanticQualityApproved']})
    value={'activeArchitecture':'short_semantics_only','entrypoint':'experiment.py short-*',
      'legacyExecution':'retired; archived reports remain read-only','data':validate_rows(rows) if rows else 'not_prepared',
      'realModelTraining':'see_registered_local_runs' if providers else 'not_run_until_a_new_frozen_plan_passes_resource_preflight','trainedProviderRuns':providers,
      'primitiveBackend':'implemented; no untrained or JSON fallback',
      'formalQuality':'unverified','fullRequest500ms':'unmeasured','modelExecutionPerformed':bool(providers)}
    print(json.dumps(value,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=Path,required=True)
    raise SystemExit(worker(parser.parse_args().worker))
