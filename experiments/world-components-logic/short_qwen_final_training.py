"""One explicitly authorized final continuation; never a deployment provider.

Uses the unchanged full-context training and inference recipes. A permanent
claim is created before any model execution; failed runs cannot silently retry.
"""
from __future__ import annotations
import argparse
import copy
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import short_qwen_training as q

RUN = 'qwen-short-final-20261110-r6'
DIRECTORY = q.ART / RUN
PARENT = q.ART / 'qwen-short-time-20261109-r5.model.json'
CLAIM = q.ART / 'final-training-20261110.claim.json'


def configuration():
    return {**q.configuration('all'), 'steps':224, 'profile':'final_once',
            'optimizerInitialization':'inherit_r5_AdamW_and_RNG',
            'automaticAdditionalTraining':False}


def normalized_parent_state(state, cumulative):
    """Separate a parent's batch-local cursor from its cumulative AdamW step."""
    actual={int(v['step']) for v in state['optimizer']['state'].values()}
    if state['optimizerCumulativeSteps'] != cumulative or actual != {cumulative}:
        raise ValueError('parent cumulative optimizer history mismatch')
    value=dict(state)
    # train_chunk's existing first-unit check expects the cumulative cursor.
    # Adapter, optimizer, RNG and the persisted parent file remain unchanged.
    value['nextSchedulePosition']=cumulative
    return value


def freeze():
    from transformers import AutoTokenizer
    if CLAIM.exists() or DIRECTORY.exists():
        raise FileExistsError('final attempt already registered; no automatic retry')
    parent=q.common.read_json(PARENT)
    record=q.common.read_json(parent['recordPath'])
    if record['status']!='diagnostic_completed':raise ValueError('parent incomplete')
    if record['modelManifest']['sha256']!=q.sha256_file(PARENT):raise ValueError('parent manifest drift')
    q.source_check(parent['sourceModel'])
    prior=q.common.read_json(parent['planPath'])
    if q.sha256_file(parent['planPath'])!=parent['planSha256']:raise ValueError('parent plan drift')
    versions={n:importlib.metadata.version(n) for n in q.DEPENDENCIES}
    if versions!=prior['environment']['versions']:raise ValueError('dependency drift')
    config=configuration()
    for key in ('rank','alpha','learningRate','weightDecay','maxGradNorm','basePrecision','adapterPrecision','attentionImplementation','codec'):
        if parent['config'][key]!=config[key]:raise ValueError('parent recipe mismatch:'+key)
    source=Path(parent['dataset']['supervision.jsonl.gz']['path'])
    if q.sha256_file(source)!=parent['dataset']['supervision.jsonl.gz']['sha256']:raise ValueError('parent data drift')
    rows=q.load_rows(source)
    tokenizer=AutoTokenizer.from_pretrained(parent['sourceModel']['directory'],local_files_only=True,trust_remote_code=False)
    encoded={r['exampleId']:q.tokenize_row(tokenizer,r,config) for r in rows}
    schedule=q.training_schedule(rows,config)
    evaluations=[r['exampleId'] for r in rows if r['split'] in config['evaluationSplits']]
    if evaluations!=prior['evaluationExampleIds']:raise ValueError('regression coverage changed')
    by_id={r['exampleId']:r for r in rows}
    for task in q.TASKS:
        expected={r['sourceGroup'] for r in rows if r['component']==task and r['split']=='train'}
        actual={by_id[k]['sourceGroup'] for k in schedule['exampleIds'] if by_id[k]['component']==task}
        if actual!=expected:raise ValueError('training source coverage missing:'+task)
    resume=parent['training']['resumeState']
    if q.sha256_file(resume['path'])!=resume['sha256']:raise ValueError('parent checkpoint drift')
    DIRECTORY.mkdir(parents=True)
    data=DIRECTORY/'supervision.jsonl.gz';shutil.copyfile(source,data)
    code={}
    for name in (*q.CODE,Path(__file__).name):
        dst=DIRECTORY/'code'/name;dst.parent.mkdir(exist_ok=True)
        shutil.copyfile(q.BASE/name,dst);code[name]=q.sha256_file(dst)
    units=q.execution_units(evaluations,schedule['exampleIds'],config)
    units=[u for u in units if u['arm']!='qwen_merge']
    plan={'schema':'jity-qwen-final-once-v1','runId':RUN,'preparedAt':q.timestamp(),
          'authorization':'user: 最后再训练一次，训练效果不好就停止',
          'config':config,'model':parent['sourceModel'],'modelManifest':{'path':str(PARENT),'sha256':q.sha256_file(PARENT)},
          'data':{'path':str(data),'sha256':q.sha256_file(data)},'codeSha256':code,
          'environment':{'python':sys.version,'versions':versions},
          'inheritedModel':{'parentOptimizerSteps':parent['training']['optimizerCumulativeSteps'],
                            'parentSchedulePosition':resume['nextSchedulePosition'],'resumeState':resume},
          'trainingSchedule':schedule,'evaluationExampleIds':evaluations,'executionUnits':units,
          'encodedInputsSha256':q.digest(encoded),'sourceGroups':{
              split:sorted({r['sourceGroup'] for r in rows if r['split']==split}) for split in ('train','development','test')},
          'acceptance':{'completeFirstOutputsRequired':128,'minimumSemanticAcceptableFraction':0.8,
                        'criticalRoleDirectionConditionCoverageErrorsAllowed':0,
                        'newCriticalSemanticErrorsAllowed':0,'semanticAcceptableCountMustNotDecrease':True,
                        'semanticReview':'paired assistant review from full input, not exact draft match',
                        'unknownReviewCountsAsPass':False,'poorResultAction':'stop_training_no_new_schedule',
                        'resourceOrExecutionFailureAction':'stop_no_automatic_retry'},
          'review':{'assistantDraftData':True,'independentGeneralization':False,'humanSigned':False},
          'conversionStatus':'转换未合格','formalDEligible':False,'worldWritesAllowed':False,
          'browserAdmissionAllowed':False,'automaticMergeOrExport':False,'paidServices':False}
    path=DIRECTORY/'plan.json';q.exclusive(path,plan)
    q.exclusive(CLAIM,{'runId':RUN,'planPath':str(path),'planSha256':q.sha256_file(path),
                       'maximumTrainingRuns':1,'retries':0})
    return path


def verify(path):
    plan=q.common.read_json(path)
    if plan['config']!=configuration():raise ValueError('final configuration drift')
    claim=q.common.read_json(CLAIM)
    if claim['runId']!=RUN or claim['planSha256']!=q.sha256_file(path):raise ValueError('one-run claim drift')
    for name,sha in plan['codeSha256'].items():
        if q.sha256_file(q.BASE/name)!=sha or q.sha256_file(DIRECTORY/'code'/name)!=sha:raise ValueError('code drift:'+name)
    for item in (plan['data'],plan['modelManifest'],plan['inheritedModel']['resumeState']):
        if q.sha256_file(item['path'])!=item['sha256']:raise ValueError('frozen identity drift')
    if sys.version!=plan['environment']['python']:raise ValueError('Python drift')
    if {n:importlib.metadata.version(n) for n in q.DEPENDENCIES}!=plan['environment']['versions']:raise ValueError('dependency drift')
    rows=q.load_rows(plan['data']['path'])
    if q.training_schedule(rows,plan['config'])!=plan['trainingSchedule']:raise ValueError('schedule drift')
    return plan,rows


def unit(path,index,resume_path,resume_sha):
    plan,rows=verify(path);u=plan['executionUnits'][index];cfg=plan['config']
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(cfg['seed'])
    if not torch.backends.mps.is_available():raise ValueError('MPS unavailable')
    selected=[r for r in rows if r['exampleId'] in u['exampleIds']]
    if len(selected)!=len(set(u['exampleIds'])):raise ValueError('missing complete row')
    tok=AutoTokenizer.from_pretrained(plan['model']['directory'],local_files_only=True,trust_remote_code=False)
    enc={r['exampleId']:q.tokenize_row(tok,r,cfg) for r in selected}
    model=AutoModelForCausalLM.from_pretrained(plan['model']['directory'],local_files_only=True,trust_remote_code=False,
                                             torch_dtype=torch.bfloat16,attn_implementation='sdpa',weights_only=True).to('mps').eval()
    if q.sha256_file(resume_path)!=resume_sha:raise ValueError('resume file drift')
    state=torch.load(resume_path,map_location='cpu',weights_only=True)
    event_path=DIRECTORY/(u['unitId']+'.events.jsonl')
    with event_path.open('x') as stream:
        def checkpoint(name,payload):
            stream.write(json.dumps({'name':name,'payload':payload},ensure_ascii=False)+'\n');stream.flush()
            if name in ('qwen_optimizer_finished','qwen_generation_finished'):
                print(name,payload.get('step',payload.get('exampleId')),payload.get('loss',payload.get('status')),flush=True)
            return {'file':str(event_path),'name':name,'sha256Payload':q.digest(payload)}
        checkpoint('loaded',{'unit':u,**q.memory(torch,cfg)})
        if u['arm']=='qwen_train':
            if u['offset']==0:
                checkpoint('parent_cursor_normalization',{'original':state['nextSchedulePosition'],'cumulative':plan['inheritedModel']['parentOptimizerSteps']})
                state=normalized_parent_state(state,plan['inheritedModel']['parentOptimizerSteps'])
            result={'training':q.train_chunk(torch,model,enc,plan,u,checkpoint,q.LOCAL/'runs'/RUN/u['unitId'],state)}
        else:
            expected=plan['inheritedModel']['parentSchedulePosition'] if u['arm']=='qwen_baseline' else cfg['steps']
            if state['nextSchedulePosition']!=expected:raise ValueError('incomplete checkpoint')
            q.install_lora(torch,model,cfg);q.restore_adapter(torch,model,state['adapter'])
            result={'predictions':q.predictions(torch,model,tok,selected,enc,cfg,checkpoint)}
    q.exclusive(DIRECTORY/(u['unitId']+'.result.json'),result)


def run(path):
    plan,_=verify(path);q.source_check(plan['model'])
    record={'schema':'jity-qwen-final-once-record-v1','runId':RUN,'planSha256':q.sha256_file(path),
            'status':'running','units':[],'formalDEligible':False,'worldWritesAllowed':False,
            'conversionStatus':'转换未合格','semanticQualityApproved':False,'automaticAdditionalTraining':False}
    out=DIRECTORY/'record.json';q.exclusive(out,record)
    resume=plan['inheritedModel']['resumeState']
    try:
        for index,u in enumerate(plan['executionUnits']):
            entry={'unitId':u['unitId'],'arm':u['arm'],'startedAt':q.timestamp(),'status':'running'}
            record['units'].append(entry);q.save(out,record)
            log=DIRECTORY/(u['unitId']+'.log');start=time.monotonic();peak=0
            with log.open('x') as stream:
                command=[sys.executable,str(Path(__file__)),'unit',str(path),'--index',str(index),
                         '--resume',resume['path'],'--resume-sha',resume['sha256']]
                process=subprocess.Popen(command,cwd=q.ROOT,stdout=stream,stderr=subprocess.STDOUT)
                try:
                    while process.poll() is None:
                        if time.monotonic()-start>plan['config']['processWallSeconds']:raise TimeoutError('frozen process wall limit')
                        rss=subprocess.run(['/bin/ps','-o','rss=','-p',str(process.pid)],capture_output=True,text=True).stdout.strip()
                        if rss:
                            peak=max(peak,int(rss))
                            if peak>plan['config']['maxResidentMiB']*1024:raise MemoryError('frozen resident limit')
                        time.sleep(1)
                    if process.returncode:raise RuntimeError('unit failed; preserve log:'+str(log))
                finally:
                    if process.poll() is None:process.terminate();process.wait(timeout=10)
            result_path=DIRECTORY/(u['unitId']+'.result.json');result=q.common.read_json(result_path)
            if 'training' in result:resume=result['training']['resumeState'];record['training']=result['training']
            entry.update(status='complete',elapsedSeconds=time.monotonic()-start,peakResidentKiB=peak,
                         resultPath=str(result_path),sha256=q.sha256_file(result_path))
            q.save(out,record);print('COMPLETE',u['unitId'],u['arm'],flush=True)
        record['status']='completed_pending_semantic_review'
    except BaseException as error:
        record.update(status='failed_stopped',error={'type':type(error).__name__,'message':str(error)})
        if record['units']:record['units'][-1]['status']='failed'
        raise
    finally:q.save(out,record)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['freeze','run','unit'])
    parser.add_argument('plan',nargs='?',type=Path);parser.add_argument('--index',type=int)
    parser.add_argument('--resume');parser.add_argument('--resume-sha');a=parser.parse_args()
    if a.command=='freeze':print(freeze())
    elif a.command=='run':run(a.plan)
    else:unit(a.plan,a.index,a.resume,a.resume_sha)
