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
REPAIR_COMPONENTS=('D01.4.parent','D02.1','D05.2.label')
TIME_REPAIR_COMPONENTS=('D08.1.unit','D08.2.time.unit')
REPAIR_PROFILES=('encoder_repair','encoder_time_repair')
CONFIG={'device':'cpu','threads':1,'concurrency':1,'precision':'float32','seed':42,
        'steps':160,'batchSize':2,'learningRate':0.001,'weightDecay':0.01,'maxGradNorm':1.0,
        'rank':4,'alpha':8,'encoderLayers':[0,1],'encoderPooling':False,'promptCodec':'complete_json_executor_binding_v2','trainingSampling':'task_then_label_or_reference_choice_then_source_v2','generatorTokenizer':{'extra_ids':0,'legacy':True},'encoderTokenLimit':512,'maxInputTokens':8192,
        'maxTargetTokens':128,'maxNewTokens':128,'processWallSeconds':1800,
        'gradientCheckpointing':True,'gradientCheckpointingReentrant':False,'trainingDropout':0.0,'microbatchSize':1,
        'maxResidentMiB':4096,'attemptsPerCase':1,'earlyStopping':False,
        'retries':0,'doSample':False,'numBeams':1}
# Limits are resource admission checks, never a context shortening instruction.
CODE=('short_experiment.py','short_training.py','short_contracts.py','short_intent.py',
      'short_settlement.py','short_data_migration.py','short_lifecycle.py','short_heads_updates.py','short_heads_lifecycle.py','short_handoff.py','short_preview.py','experiment.py','plan_training.py',
      'fact_windows.py','pilot_codec.py','lab.py','run_pilot.py','m01_probe.py',
      'prepare_run_batch.py','action_plan.py','generate_dev_drafts.py','data/short-semantics/author_packet.py','data/short-semantics/project_primitives.py','data/short-semantics/abstention_packet.py','data/short-semantics/partial_packet.py')


def paths(run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}',run_id): raise ValueError('invalid run id')
    return ART/(run_id+'.plan.json'),ART/(run_id+'.record.json')


def model_output(run_id,config):
    if config['profile']=='encoder_time_repair':return Path.home()/'.cache/jity-d-short-semantics-20261109/encoder'/run_id
    return LOCAL/'short-semantic-models'/run_id


def load_rows(path=DATA/'supervision.jsonl.gz'):
    raw=Path(path).read_bytes()
    if str(path).endswith('.gz'):raw=gzip.decompress(raw)
    rows=[json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    validate_rows(rows)
    return rows


def audit_resources(model_root=None, *, roles=None):
    """Exact local payload checks. No download, shared-cache mutation, or inference."""
    model_root=Path(model_root) if model_root else LOCAL/'models'
    registry=json.loads(REGISTRY.read_text()); models={}; blockers=[]
    for role,model_id in MODEL_IDS.items():
        if roles is not None and role not in roles:continue
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
    if profile not in ('intent','all',*REPAIR_PROFILES):raise ValueError('unknown frozen task profile')
    value={**copy.deepcopy(CONFIG),'profile':profile}
    if profile in REPAIR_PROFILES:value.update(steps=48 if profile=='encoder_repair' else 32,processWallSeconds=300,repairComponents=list(REPAIR_COMPONENTS if profile=='encoder_repair' else TIME_REPAIR_COMPONENTS))
    return value


def training_arms(profile):
    return ('encoder_train',) if profile in REPAIR_PROFILES else TRAIN_ARMS


def select_rows(rows,profile):
    if profile in REPAIR_PROFILES:return [r for r in rows if r['component'] in configuration(profile)['repairComponents']]
    return [r for r in rows if profile=='all' or r['component'].startswith(('D02.','D03.','D04.'))]


def registered_schedules(rows,config):
    return {role:training_schedule([r for r in rows if r['kind'] in kinds],config)
            for role,kinds in (('encoder',('label','reference','number')),('generator',('text',))) if any(r['kind'] in kinds for r in rows)}


def representation_function_hashes(path):
    import ast
    names={'input_text','complete_tokens','encode_complete','build_heads','head_logits','load_neural'}
    tree=ast.parse(Path(path).read_text())
    found={node.name:digest(ast.dump(node,include_attributes=False)) for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names}
    if set(found)!=names:raise ValueError('representation implementation incomplete')
    return found


def source_model_identity(spec):
    return {**{key:spec[key] for key in ('modelId','revision','registrySha256')},
            'files':sorted([{'path':item['path'],'bytes':item['expectedBytes'],'sha256':item['observedSha256']}
                            for item in spec['files']],key=lambda item:item['path'])}


def token_statistics(rows,models,config,schedules=None):
    """Actual complete tokenizer workload, no model load/forward or truncation."""
    from transformers import AutoTokenizer,T5Tokenizer
    from fact_windows import make_windows
    from short_training import input_text
    generator=T5Tokenizer.from_pretrained(models['generator']['directory'],local_files_only=True,**config['generatorTokenizer']) if any(r['kind']=='text' for r in rows) else None
    encoder=AutoTokenizer.from_pretrained(models['encoder']['directory'],local_files_only=True,trust_remote_code=False)
    components={};errors=[];started=time.perf_counter()
    schedules=schedules or registered_schedules(rows,config)
    scheduled=set(schedules['encoder']['exampleIds']);generator_ids=schedules.get('generator',{}).get('exampleIds',[])
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


def freeze(run_id, *, model_root=None, dataset=None, profile='intent', inherit_provider=None):
    if 'generator_train' in training_arms(profile):
        raise ValueError('Randeng training retired; use the frozen Qwen/WebGPU experiment entry')
    path,out=paths(run_id)
    if path.exists() or out.exists(): raise FileExistsError('new run identity required; preserve evidence')
    dataset=Path(dataset) if dataset else DATA/'supervision.jsonl.gz'; rows=select_rows(load_rows(dataset),profile)
    source_manifest=common.read_json(dataset.parent/'manifest.json')
    if source_manifest['files'].get(dataset.name)!=sha256_file(dataset):raise ValueError('source manifest does not identify this supervision packet')
    inherited=None;migration=None
    if profile in REPAIR_PROFILES:
        if not inherit_provider:raise ValueError('encoder repair requires its frozen parent provider')
        parent_path=Path(inherit_provider).resolve();parent=common.read_json(parent_path)
        from short_training import LocalSemanticProvider
        LocalSemanticProvider(parent)
        parent_plan_path,parent_record_path=paths(parent['runId'])
        if profile=='encoder_time_repair' and Path(str(parent_record_path)+'.gz').exists():parent_record_path=Path(str(parent_record_path)+'.gz')
        parent_plan=common.read_json(parent_plan_path);parent_record=common.read_json(parent_record_path)
        if (parent_record['status']!='diagnostic_completed' or parent_record['planSha256']!=sha256_file(parent_plan_path)
            or parent_record['providerManifest']['sha256']!=sha256_file(parent_path)):
            raise ValueError('parent training completion/manifest identity mismatch')
        prior_functions=representation_function_hashes(Path(parent_plan['codeSnapshot']['directory'])/'short_training.py')
        if representation_function_hashes(BASE/'short_training.py')!=prior_functions:raise ValueError('repair changed the feature or inference implementation')
        for name in ('fact_windows.py','pilot_codec.py','lab.py'):
            if sha256_file(BASE/name)!=parent['codeSha256'][name]:raise ValueError('repair changed representation dependency:'+name)
        all_specs=task_specs(load_rows(dataset))
        if set(all_specs)!=set(parent['tasks']):raise ValueError('repair cannot add or remove unrelated runtime task definitions')
        if any(spec!=parent['tasks'][key] for key,spec in all_specs.items() if key not in configuration(profile)['repairComponents']):raise ValueError('repair changed an unrelated task definition')
        for key in ('encoderLayers','encoderPooling','precision','promptCodec','generatorTokenizer','encoderTokenLimit'):
            if parent['config'][key]!=configuration(profile)[key]:raise ValueError('repair would change the representation basis:'+key)
        snapshot=ART/'providers'/(run_id+'.inherited.json');snapshot.parent.mkdir(parents=True,exist_ok=True)
        with snapshot.open('xb') as stream:stream.write(parent_path.read_bytes())
        inherited={'path':str(parent_path),'snapshotPath':str(snapshot),'sha256':sha256_file(parent_path),'runId':parent['runId'],
          'parentPlanPath':str(parent_plan_path),'parentPlanSha256':sha256_file(parent_plan_path),
          'parentRecordPath':str(parent_record_path),'parentRecordSha256':sha256_file(parent_record_path),
          'representationFunctionHashes':prior_functions}
        if profile=='encoder_time_repair':
            from short_data_migration import verify_migration
            proof=dataset.parent/'migration-proof.json'
            verify_migration(proof,source_sha=parent['datasetSha256'],target_sha=sha256_file(dataset))
            migration={'path':str(proof.resolve()),'sha256':sha256_file(proof),
                       'sourceDatasetSha256':parent['datasetSha256'],'targetDatasetSha256':sha256_file(dataset)}
            original=parent['models']['encoder']['checkpoint']
            relocated=Path(model_root)/parent['runId']/Path(original['path']).name if model_root else Path(original['path'])
            if not relocated.is_absolute():relocated=ROOT/relocated
            if sha256_file(relocated)!=original['sha256']:raise ValueError('relocated inherited head checkpoint mismatch')
            inherited['checkpointLoad']={'path':str(relocated),'sha256':original['sha256'],'originalPath':original['path']}
    elif inherit_provider:raise ValueError('parent provider is only allowed for encoder repair')
    resource=audit_resources(model_root,roles=('encoder',) if profile=='encoder_time_repair' else None);code={name:sha256_file(BASE/name) for name in CODE if (BASE/name).exists()}
    if inherited and (resource['versions']!=parent_plan['environment']['versions'] or sys.version!=parent_plan['environment']['pythonVersion']):raise ValueError('repair representation environment drift')
    if inherited and source_model_identity(resource['models']['encoder'])!=source_model_identity(parent['models']['encoder']):raise ValueError('repair training/inherited encoder byte identity mismatch')
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
      'trainingArms':list(training_arms(profile)),'trainingSchedules':schedules,'inheritedProvider':inherited,'readiness':'blocked' if blockers else 'ready_exploratory',
      'dataMigration':migration,
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
    if 'generator_train' in plan.get('trainingArms',[]):
        raise ValueError('Randeng execution retired; historical reports remain read-only')
    if plan['config']!=configuration(plan['config']['profile']): raise ValueError('configuration drift; freeze a new run')
    if plan['trainingArms']!=list(training_arms(plan['config']['profile'])): raise ValueError('training arm drift')
    path=Path(plan['dataset']['path'])
    if sha256_file(path)!=plan['dataset']['sha256']: raise ValueError('dataset drift')
    rows=select_rows(load_rows(path),plan['config']['profile'])
    if validate_rows(rows)!=plan['dataset']['inventory']: raise ValueError('dataset inventory drift')
    if task_specs(rows)!=plan['dataset']['tasks'] or {r['sourceGroup']:r['split'] for r in rows}!=plan['dataset']['sourceGroups']:raise ValueError('task vocabulary/codec/source split drift')
    if registered_schedules(rows,plan['config'])!=plan['trainingSchedules']:raise ValueError('training schedule drift')
    if plan['config']['profile'] in REPAIR_PROFILES:
        inherited=plan['inheritedProvider']
        if any(sha256_file(inherited[key])!=inherited['sha256'] for key in ('path','snapshotPath')):raise ValueError('inherited provider drift')
        for key in ('parentPlan','parentRecord'):
            if sha256_file(inherited[key+'Path'])!=inherited[key+'Sha256']:raise ValueError('inherited training evidence drift')
        if representation_function_hashes(BASE/'short_training.py')!=inherited['representationFunctionHashes']:raise ValueError('repair representation code drift')
        parent=common.read_json(inherited['snapshotPath'])
        if source_model_identity(plan['models']['encoder'])!=source_model_identity(parent['models']['encoder']):raise ValueError('repair encoder representation identity mismatch')
        for role,spec in parent['models'].items():
            if plan['config']['profile']=='encoder_time_repair' and role!='encoder':continue
            checkpoint=Path(inherited.get('checkpointLoad',spec['checkpoint'])['path']);checkpoint=checkpoint if checkpoint.is_absolute() else ROOT/checkpoint
            if sha256_file(checkpoint)!=spec['checkpoint']['sha256']:raise ValueError('inherited trained checkpoint drift:'+role)
            for item in spec['files']:
                directory=plan['models'][role]['directory'] if plan['config']['profile']=='encoder_time_repair' else spec['directory']
                if sha256_file(Path(directory)/item['path'])!=item['observedSha256']:raise ValueError('inherited base/tokenizer byte drift:'+role)
        if task_specs(load_rows(path))!={**parent['tasks'],**plan['dataset']['tasks']}:raise ValueError('repair task registry drift')
        if plan['config']['profile']=='encoder_time_repair':
            from short_data_migration import verify_migration
            migration=plan['dataMigration']
            if sha256_file(migration['path'])!=migration['sha256']:raise ValueError('data migration proof drift')
            verify_migration(migration['path'],source_sha=parent['datasetSha256'],target_sha=plan['dataset']['sha256'])
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


def merge_repaired_head_states(torch,original,replacement,components):
    """Storage assembly only: replace trained heads, preserve every other tensor."""
    from m01_probe import tensor_hash
    if set(replacement)!=set(components) or not set(components)<=set(original):raise ValueError('repair checkpoint task coverage mismatch')
    merged=dict(original);unchanged={}
    for key,value in original.items():
        if key in components:merged[key]=replacement[key]
        else:
            if tensor_hash(value)!=tensor_hash(merged[key]):raise ValueError('unrelated head tensor changed')
            unchanged[key]=tensor_hash(value)
    return merged,unchanged


def head_collection_hashes(heads):
    """The checkpoint is task -> named tensors; tensor_hash expects one task."""
    from m01_probe import tensor_hash
    return {component:tensor_hash(state) for component,state in heads.items()}


def repaired_manifest(plan,report,torch):
    from m01_probe import tensor_hash
    inherited=plan['inheritedProvider'];parent=common.read_json(inherited['snapshotPath'])
    trained=copy.deepcopy(report['attempts'][0]['training']);components=plan['config']['repairComponents']
    if set(trained['trainedHeadComponents'])!=set(components):raise ValueError('not all repair heads had real changed parameters and nonzero gradients')
    for component in ('D02.1','D05.2.label') if plan['config']['profile']=='encoder_repair' else ():
        if any(trained['componentLabelDataGradientExposures'][component].get(label,0)<1 for label in trained['specs'][component]['labels']):
            raise ValueError('repair class received no actual positive-label data gradient:'+component)
    if plan['config']['profile']=='encoder_time_repair':
        trained['componentLabelDataGradientExposures']=validate_observed_label_training(trained,select_rows(load_rows(plan['dataset']['path']),plan['config']['profile']),components)
    original_path=Path(inherited.get('checkpointLoad',parent['models']['encoder']['checkpoint'])['path'])
    if not original_path.is_absolute():original_path=ROOT/original_path
    original=torch.load(original_path,map_location='cpu',weights_only=True)
    replacement=torch.load(trained['checkpoint']['path'],map_location='cpu',weights_only=True)
    merged,unchanged=merge_repaired_head_states(torch,original,replacement,components)
    destination=model_output(plan['runId'],plan['config'])/'encoder'/'merged-heads.pt'
    with destination.open('xb') as stream:torch.save(merged,stream);stream.flush();os.fsync(stream.fileno())
    restored=torch.load(destination,map_location='cpu',weights_only=True)
    if head_collection_hashes(restored)!=head_collection_hashes(merged):raise ValueError('merged checkpoint reload mismatch')
    manifest=copy.deepcopy(parent);manifest.update(runId=plan['runId'],datasetSha256=plan['dataset']['sha256'],
       codeSha256=plan['codeSha256'],recordPath=str(paths(plan['runId'])[1]),tasks=task_specs(load_rows(plan['dataset']['path'])),
       inheritedProvider=inherited,inferenceConfigSource=parent['runId'],repairTrainingConfig=plan['config'],
       trainingEvidence='actual_selected_head_repair_with_per_component_gradient_and_unchanged_tensor_proofs')
    if plan.get('dataMigration'):manifest['dataMigration']=plan['dataMigration']
    # Inference retains the same full-input codec, tokenizer, precision and
    # representation basis. The distinct optimizer config lives in this plan.
    encoder=manifest['models']['encoder'];encoder['checkpoint']={'path':str(destination),'sha256':sha256_file(destination)}
    if plan['config']['profile']=='encoder_time_repair':encoder['directory']=plan['models']['encoder']['directory']
    encoder['trainingSteps']=parent['models']['encoder']['trainingSteps']+trained['steps']
    encoder['trainingStepMeaning']='sum across lineage; per-head provenance identifies which optimizer run trained each tensor'
    encoder['trainedComponents']=sorted(set(encoder['trainedComponents'])|set(components))
    encoder['taskSpecs'].update(trained['specs'])
    for key in ('componentGradientExposures','componentNonzeroDataGradientSteps','componentLabelDataGradientExposures'):
        current=encoder.get(key) or {};current.update(trained[key]);encoder[key]=current
    encoder['componentTrainingRuns']={component:(plan['runId'] if component in components else parent['models']['encoder'].get('componentTrainingRuns',{}).get(component,parent['runId'])) for component in encoder['taskSpecs']}
    training_datasets={run:common.read_json(paths(run)[0])['dataset']['sha256'] for run in set(encoder['componentTrainingRuns'].values())}
    encoder['componentTrainingDatasetSha256']={component:training_datasets[run] for component,run in encoder['componentTrainingRuns'].items()}
    encoder['supportedLabels']={component:[label for label,count in encoder['componentLabelDataGradientExposures'].get(component,{}).items() if count>0] for component in components}
    manifest['repairProof']={'replacedComponents':list(components),'unchangedHeadTensorHashes':unchanged,
      'unmodifiedHeadCount':len(unchanged),'newHeadsCheckpoint':trained['checkpoint'],'generatorExactInheritedEntry':True,
      'generatorCheckpointSha256':parent['models']['generator']['checkpoint']['sha256'],
      'representationBasis':'same source encoder weights/layers/tokenizer/float32/complete fact-window codec; no cached features imported'}
    if manifest['models']['generator']!=parent['models']['generator']:raise ValueError('repair changed inherited generator')
    report['repairProof']=manifest['repairProof']
    return manifest


def validate_observed_label_training(trained,rows,components):
    """Unsupported labels stay explicit zeroes and are refused by the provider."""
    normalized={}
    for component in components:
        counts=trained['componentLabelDataGradientExposures'][component]
        labels=trained['specs'][component]['labels']
        if not set(counts)<=set(labels):raise ValueError('unregistered per-label gradient qualification')
        observed={r['target'] for r in rows if r['component']==component and r['split']=='train'}
        if not observed or any(counts.get(label,0)<1 for label in observed):raise ValueError('observed repair class lacks positive-label gradient:'+component)
        normalized[component]={label:counts.get(label,0) for label in labels}
    return normalized


def worker(path):
    plan=common.read_json(path);rows=verify(plan);_,out=paths(plan['runId'])
    slots=common.planned_slots(plan,plan['trainingArms'])
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
                    destination=model_output(plan['runId'],plan['config'])/role
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
                  'componentLabelDataGradientExposures':trained.get('componentLabelDataGradientExposures'),
                  'taskSpecs':trained.get('specs',{c:plan['dataset']['tasks'][c] for c in components})}
            if plan['config']['profile'] in REPAIR_PROFILES:manifest=repaired_manifest(plan,report,torch)
            destination=model_output(plan['runId'],plan['config'])/'provider.json'
            exclusive(destination,manifest);report['providerManifest']={'path':str(destination),'sha256':sha256_file(destination)}
    except Exception as error:
        report.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
    finally: save(out,report)
    return 0 if report['status']=='diagnostic_completed' else 1


def execute(path):
    plan=common.read_json(path)
    if plan['readiness']=='blocked':
        verify(plan,require_resources=False)
        _,out=paths(plan['runId'])
        report=common.unstarted_record(plan,path,plan.get('trainingArms',TRAIN_ARMS))
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
                               settle_stages=settle_stages,arms=plan['trainingArms'])
    _,out=paths(plan['runId']);report=common.read_json(out)
    if report['status']=='failed_preflight':return code
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


def active_selection():
    path=DATA/'active-selection.json'
    value=common.read_json(path)
    if value.get('schema')!='jity-short-active-selection-v1':raise ValueError('unknown_active_selection')
    return value


def _active_reference_path(selection,name):
    """Reject changed registered bytes before a current-default consumer reads them."""
    entry=selection['references'][name];path=Path(entry['path'])
    if not path.is_file() or sha256_file(path)!=entry['sha256']:
        raise ValueError('active_reference_identity_mismatch:'+name)
    return path


def active_data_path():
    return _active_reference_path(active_selection(),'dataset')


def active_audit():
    """Current candidate metadata/identity only; never load or qualify a model."""
    selection=active_selection();references={};blockers=[]
    for name,entry in selection['references'].items():
        path=Path(entry['path']);observed=sha256_file(path) if path.is_file() else None
        valid=observed==entry['sha256']
        references[name]={**entry,'exists':path.is_file(),'observedSha256':observed,'identityMatches':valid}
        if not valid:blockers.append('missing_or_changed_reference:'+name)
    browser=selection.get('browserProvider')
    if browser:
        path=Path(browser['path'])
        if not path.is_file() or sha256_file(path)!=browser['sha256']:
            blockers.append('missing_or_changed_browser_provider')
        else:
            try:
                from short_mixed_provider import verify_backend_artifacts
                verify_backend_artifacts(common.read_json(path))
            except Exception as error:blockers.append('browser_provider_rejected:'+str(error))
    else:blockers.append('qualified_browser_provider_not_selected')
    return {'scope':'current_candidate_identity_audit_not_inference_or_semantic_approval',
        'references':references,'browserProvider':browser,'blockers':blockers,
        'modelCalls':0,'trainingSteps':0,'randeng':'retired_no_fallback',
        'semanticQualityApproved':False,'productionIntegration':False}


def active_status():
    audit=active_audit();selection=active_selection()
    dataset=_active_reference_path(selection,'dataset')
    training_path=_active_reference_path(selection,'trainedQwen')
    rows=load_rows(dataset)
    training=common.read_json(training_path)
    value={'activeArchitecture':'short_semantics_only','entrypoint':'experiment.py short-*',
      'legacyExecution':'retired; archived reports remain read-only',
      'naturalLanguageBackend':{'selected':'Qwen3-0.6B','runtime':'WebGPU','thinking':False,
                               'randeng':'retired_no_fallback','quality':'not_approved'},
      'data':{'path':str(dataset),'sha256':sha256_file(dataset),'inventory':validate_rows(rows)},
      'realQwenTraining':{'manifest':selection['references']['trainedQwen'],
          'currentBatchSteps':training['training']['steps'],
          'optimizerCumulativeSteps':training['training'].get('optimizerCumulativeSteps'),
          'components':training['trainedComponents'],'semanticQualityApproved':False},
      'candidateAudit':audit,'primitiveBackend':'implemented; rejects untrained heads and missing model output',
      'formalQuality':'not_approved','fullRequest500ms':'unmeasured_with_AB_C_and_ready',
      'statusCommandModelExecutions':0}
    print(json.dumps(value,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=Path,required=True)
    raise SystemExit(worker(parser.parse_args().worker))
