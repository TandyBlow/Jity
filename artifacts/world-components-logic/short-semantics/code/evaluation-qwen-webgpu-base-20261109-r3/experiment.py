"""Current D experiment entry point and shared execution bookkeeping.

status/check never import a model or prepare/execute a model batch. Model-specific
collaboration belongs to action_chain and its M01 helpers, loaded on demand.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from lab import sha256_file
from run_pilot import exclusive,save,timestamp

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
ART=ROOT/'artifacts/world-components-logic'
CHECKPOINT_STORAGE='journal_refs_v1'


def read_json(path):
    raw=Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith('.gz') else raw)


def record_stage(report,out,name,fn):
    stage={'stage':name,'status':'running','startedAt':timestamp(),'startedMonotonicNs':time.monotonic_ns()}
    report['stages'].append(stage);save(out,report)
    try:
        result=fn();stage['status']='complete';return result
    except Exception as error:
        stage.update(status='failed',error={'type':type(error).__name__,'message':str(error)});raise
    finally:
        stage.update(elapsedMs=(time.monotonic_ns()-stage['startedMonotonicNs'])/1e6,settledAt=timestamp());save(out,report)


def planned_slots(plan,arms):
    blocks=plan['config'].get('armBlocks',[list(arms)])
    if not blocks or any(not b for b in blocks) or [a for b in blocks for a in b]!=list(arms):raise ValueError('invalid registered arm blocks')
    return [{'arm':arm,'caseId':case['caseId'],'repeat':repeat,'status':'not_started'}
            for block in blocks for repeat in range(plan['config']['attemptsPerCase']) for case in plan['cases']
            for arm in (block if repeat%2==0 else block[::-1])]


def unstarted_record(plan,path,arms):
    slots=planned_slots(plan,arms)
    return {'status':'failed_before_journal','planSha256':sha256_file(path),'attempts':[],
            'attemptSlots':slots,'unexecutedAttempts':len(slots),'activeAttempt':None,'stages':[],
            'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequestMeasured':False}


def settle_attempts(report,reason):
    active=report.get('activeAttempt')
    if active is not None:
        active=dict(active)
        active.update(status='interrupted',stopReason=reason,settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns())
        active['elapsedMs']=(active['settledMonotonicNs']-active['startedMonotonicNs'])/1e6
        key=lambda row:(row['arm'],row['caseId'],row['repeat'])
        if key(active) not in {key(row) for row in report['attempts']}:report['attempts'].append(active)
        for index,slot in enumerate(report['attemptSlots']):
            if key(slot)==key(active):report['attemptSlots'][index]=active
        report['activeAttempt']=None
    report['unexecutedAttempts']=sum(row['status']=='not_started' for row in report['attemptSlots'])


def settle_events(report,event_path,reason):
    if not event_path.exists():return
    active={};malformed=[]
    for index,line in enumerate(event_path.read_text(encoding='utf-8').splitlines()):
        if not line.strip():continue
        try:event=json.loads(line)
        except ValueError:malformed.append(index);continue
        if event['status']=='running':active[event['eventId']]=event
        else:active.pop(event['eventId'],None)
    with event_path.open('a',encoding='utf-8') as stream:
        for event in active.values():
            event.update(status='interrupted',stopReason=reason,settledAt=timestamp(),settledMonotonicNs=time.monotonic_ns())
            event['elapsedMs']=(event['settledMonotonicNs']-event['startedMonotonicNs'])/1e6
            stream.write('\n'+json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n')
    report['windowEventsSha256']=sha256_file(event_path);report['windowEventMalformedLines']=malformed


class AppendJournal:
    """D experiment evidence only: exclusive append stream, never a game store."""
    def __init__(self,path,plan_sha):
        self.stream=Path(path).open('xb');self.plan_sha=plan_sha;self.seq=0;self.previous=None

    def append(self,kind,data):
        from run_pilot import digest
        row={'sequence':self.seq,'planSha256':self.plan_sha,'previousSha256':self.previous,'kind':kind,'data':data}
        row['sha256']=digest(row)
        self.stream.write((json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8'))
        self.stream.flush()
        # Attempt boundaries persist preceding window evidence too. In-flight
        # window events are flushed for process-exit recovery, not power-loss QA.
        if kind!='window':os.fsync(self.stream.fileno())
        self.previous=row['sha256'];self.seq+=1
        return {'sequence':row['sequence'],'sha256':row['sha256']}

    def close(self):self.stream.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def append_checkpoint(journal,event):
    """Persist every raw byte first; retain only a verified event reference."""
    reference=journal.append('attempt_checkpoint',event)
    return {'checkpointRef':reference,'name':event['name']}


class JournalStream:
    """Verified streaming reader: memory is bounded by one journal event.

    A final unterminated line is retained as partial-tail evidence, never parsed
    as a completion. gzip is streamed as well. Callers must not accumulate rows.
    """
    def __init__(self,path,plan_sha):
        self.path=Path(path);self.plan_sha=plan_sha
        self.events=0;self.partial_tail_bytes=0;self.previous=None

    def __iter__(self):
        from run_pilot import digest
        self.events=0;self.partial_tail_bytes=0;self.previous=None
        opener=gzip.open if str(self.path).endswith('.gz') else open
        with opener(self.path,'rb') as stream:
            for index,line in enumerate(stream):
                if not line.endswith(b'\n'):
                    self.partial_tail_bytes=len(line);break
                row=json.loads(line)
                if set(row)!={'sequence','planSha256','previousSha256','kind','data','sha256'}:raise ValueError('journal envelope invalid')
                if (row['sequence']!=index or row['planSha256']!=self.plan_sha or row['previousSha256']!=self.previous
                        or digest({k:v for k,v in row.items() if k!='sha256'})!=row['sha256']):
                    raise ValueError('journal identity/sequence/hash mismatch')
                self.previous=row['sha256'];self.events+=1
                yield row


def read_journal(path,plan_sha):
    """Legacy materialized API. New execution/recovery uses JournalStream."""
    stream=JournalStream(path,plan_sha)
    entries=list(stream)
    return entries,stream.partial_tail_bytes


def _checkpoint_reference(row):
    return {'checkpointRef':{'sequence':row['sequence'],'sha256':row['sha256']},'name':row['data']['name']}


def iter_checkpoint_events(report,path):
    """Resolve v1 raw or v2 referenced checkpoints without accumulating payloads.

    Every referenced event must match sequence/hash/name and attempt identity.
    All checkpoint entries must be covered exactly once. Consumers interested
    in predictions may filter by event name after verification, without keeping
    encoder token arrays. Exhaust the iterator to validate trailing events.
    """
    path=Path(path)
    if not path.exists() and path.with_suffix(path.suffix+'.gz').exists():path=path.with_suffix(path.suffix+'.gz')
    key=lambda value:(value['arm'],value['caseId'],value['repeat'])
    expected={};counts={}
    for attempt in report['attempts']:
        identity=key(attempt)
        if identity in expected:raise ValueError('duplicate attempt identity in checkpoint index')
        expected[identity]=attempt.get('checkpoints',[]);counts[identity]=0
    stream=JournalStream(path,report['planSha256']);first=True
    for row in stream:
        if first:
            if row['kind']!='begin' or row['data']['runId']!=report['runId']:raise ValueError('journal header mismatch')
            first=False
        if row['kind']!='attempt_checkpoint':continue
        event=row['data'];identity=key(event)
        if identity not in expected or counts[identity]>=len(expected[identity]):raise ValueError('checkpoint missing from record index')
        registered=expected[identity][counts[identity]]
        if 'checkpointRef' in registered:
            if registered!=_checkpoint_reference(row):raise ValueError('checkpoint reference mismatch')
        elif registered!=event:raise ValueError('legacy checkpoint bytes differ from journal')
        counts[identity]+=1
        yield event
    if any(counts[k]!=len(rows) for k,rows in expected.items()):raise ValueError('unresolved checkpoint references')


def reconcile_journal(report,path,reason,*,bounded=None):
    """Read only: reconstruct evidence after exit; never infer/retry a model."""
    import copy
    stream=JournalStream(path,report['planSha256']);entries=iter(stream)
    first=next(entries,None)
    if first is None:
        report['journalRecovery']={'events':0,'partialTailBytes':stream.partial_tail_bytes,'sha256':sha256_file(path),
                                   'readOnlyReplay':True,'modelCallsDuringReplay':0}
        report['status']='stopped_incomplete'
        report['unexecutedAttempts']=sum(slot['status']=='not_started' for slot in report['attemptSlots'])
        return
    key=lambda a:(a['arm'],a['caseId'],a['repeat'])
    if first['kind']!='begin' or first['data']['runId']!=report['runId']:raise ValueError('journal header mismatch')
    storage=first['data'].get('checkpointStorage')
    if storage not in (None,CHECKPOINT_STORAGE):raise ValueError('unknown checkpoint storage')
    referenced=storage==CHECKPOINT_STORAGE
    if bounded is None:bounded=referenced
    if referenced and not bounded:raise ValueError('referenced journal requires bounded recovery')
    planned=first['data']['slots'];ids=[key(s) for s in planned]
    if len(set(ids))!=len(ids) or ids!=[key(s) for s in report['attemptSlots']]:raise ValueError('journal slot mismatch')
    slots={key(s):dict(s) for s in planned};attempts=[];active=None;result=None;windows=[];active_window=None
    snapshots={key(a):a for a in report['attempts']};checkpoint_hashes=[]
    from run_pilot import digest
    def window_summary(data,row):
        return {**{k:data[k] for k in ('eventId','arm','caseId','repeat','status','windowIndex') if k in data},
                'journalRef':{'sequence':row['sequence'],'sha256':row['sha256']}}
    for row in entries:
        kind=row['kind'];data=row['data']
        if kind=='attempt_start':
            k=key(data)
            if active is not None or k not in slots or slots[k]['status']!='not_started' or data['status']!='started':raise ValueError('duplicate/unknown/overlapping attempt start')
            if data.get('checkpoints'):raise ValueError('attempt starts with unlogged checkpoints')
            active=copy.deepcopy(data);slots[k]=active;result=None;checkpoint_hashes=[]
        elif kind=='window':
            if active is None or result is not None or key(data)!=key(active):raise ValueError('window outside active attempt')
            index=data['eventId']
            if data['status']=='running':
                if active_window is not None or index!=len(windows):raise ValueError('duplicate/overlapping window start')
                active_window=copy.deepcopy(data);windows.append(window_summary(data,row) if bounded else active_window)
            else:
                if (active_window is None or index!=active_window['eventId'] or data['status'] not in ('complete','failed')
                        or any(data[k]!=active_window[k] for k in ('caseId','arm','repeat','windowIndex','inputIds','tokenTypeIds','factSpans'))):
                    raise ValueError('unmatched window settlement')
                windows[index]=window_summary(data,row) if bounded else copy.deepcopy(data);active_window=None
        elif kind=='attempt_result':
            if active is None or result is not None or key(data)!=key(active) or active_window is not None:raise ValueError('unmatched/duplicate attempt result')
            if data['status'] not in ('complete','failed'):raise ValueError('invalid attempt result status')
            if bounded and not referenced:
                if [digest(event) for event in data.get('checkpoints',[])]!=checkpoint_hashes:raise ValueError('attempt checkpoint history mismatch')
            elif data.get('checkpoints',[])!=active.get('checkpoints',[]):raise ValueError('attempt checkpoint history mismatch')
            result={**data,'checkpoints':active.get('checkpoints',[])} if bounded else copy.deepcopy(data)
        elif kind=='attempt_checkpoint':
            if active is None or result is not None or key(data)!=key(active):raise ValueError('checkpoint outside active attempt')
            if (set(data)!={'arm','caseId','repeat','name','payload'} or not isinstance(data['name'],str)
                    or not isinstance(data['payload'],dict)):raise ValueError('invalid checkpoint envelope')
            active.setdefault('checkpoints',[]).append(_checkpoint_reference(row) if bounded else copy.deepcopy(data))
            if bounded and not referenced:checkpoint_hashes.append(digest(data))
        elif kind=='attempt_settled':
            if active is None or result is None or key(data)!=key(active):raise ValueError('timing without result')
            if set(data)!={'arm','caseId','repeat','resultJournalMs','snapshotEndMs','elapsedThroughResultMs'}:raise ValueError('invalid timing fields')
            item={**result,**copy.deepcopy(data)}
            # Final batch snapshots can retain exact cost of writing this timing
            # event. A killed worker cannot invent that final timestamp.
            prior=snapshots.get(key(item),{})
            if all(prior.get(k)==v for k,v in item.items()) and 'elapsedIncludingTelemetryMs' in prior:
                item.update({k:prior[k] for k in ('elapsedIncludingTelemetryMs','telemetryJournalMs')})
            else:item['exactTelemetryTimingAvailable']=False
            attempts.append(item);slots[key(item)]=item;active=None;result=None
        else:raise ValueError('unknown journal event kind')
    if active_window is not None:
        active_window.update(status='interrupted',stopReason=reason,settledAt=timestamp())
        if bounded:windows[active_window['eventId']].update(status='interrupted',stopReason=reason,settledAt=timestamp())
    if active is not None:
        item=result if result is not None else active
        item.update(status='result_saved_timing_incomplete' if result is not None else 'interrupted',stopReason=reason,
                    settledAt=timestamp(),exactTelemetryTimingAvailable=False)
        attempts.append(item);slots[key(item)]=item
    report.update(attempts=attempts,attemptSlots=[slots[k] for k in ids],activeAttempt=None,
                  forwardAttempts=windows,activeForward=None,
                  unexecutedAttempts=sum(s['status']=='not_started' for s in slots.values()),
                  journalRecovery={'events':stream.events,'partialTailBytes':stream.partial_tail_bytes,'sha256':sha256_file(path),
                                   'readOnlyReplay':True,'modelCallsDuringReplay':0})
    if bounded:
        report['checkpointStorage']=CHECKPOINT_STORAGE
        report['journalRecovery']['boundedReferences']=True
    else:report.pop('checkpointStorage',None)
    if stream.partial_tail_bytes or active is not None or active_window is not None or (report.get('status')=='diagnostic_completed' and report['unexecutedAttempts']):report['status']='stopped_incomplete'



def execute_plan(path,*,paths,verify,worker_script,settle_stages,arms):
    """Bounded child process; callbacks supply only experiment-specific facts."""
    plan=read_json(path);_,out=paths(plan['runId'])
    if any(p.exists() for p in (out,out.with_suffix(out.suffix+'.gz'),out.with_suffix('.journal.jsonl'),out.with_suffix('.journal.jsonl.gz'))):
        raise FileExistsError('preserve original record/journal; use a new run id')
    try:verify(plan)
    except Exception as error:
        report=unstarted_record(plan,path,arms)
        report.update(status='failed_preflight',error=str(error),formalEvaluationAllowed=False)
        exclusive(out,report);raise
    config=plan['config']
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',
             TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
             HF_HOME=str(ROOT/'.local/world-components-logic/hf-cache'))
    start=time.monotonic();reason=None;peak=0.;error=None
    with out.with_suffix('.process.log').open('x',encoding='utf-8') as log:
        try:
            child=subprocess.Popen([str(ROOT/plan['environment']['venvExecutableRelativePath']),str(worker_script),
                                    '--worker',str(path)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        except Exception as launch_error:
            report=unstarted_record(plan,path,arms);report.update(status='failed_process_launch',error=str(launch_error))
            exclusive(out,report);return 1
        try:
            while child.poll() is None:
                rss=subprocess.run(['ps','-o','rss=','-p',str(child.pid)],capture_output=True,text=True)
                if rss.returncode or not rss.stdout.strip():
                    if child.poll() is not None:break
                    raise RuntimeError('RSS monitor unavailable')
                peak=max(peak,float(rss.stdout)/1024)
                if peak>config['maxResidentMiB']:reason='resident_memory_limit'
                if time.monotonic()-start>config['processWallSeconds']:reason='process_wall_limit'
                if reason:break
                time.sleep(.25)
        except Exception as monitor_error:reason='supervisor_failure';error=str(monitor_error)
        finally:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
    report=read_json(out) if out.exists() else unstarted_record(plan,path,arms)
    report['supervisor']={'exitCode':child.returncode,'stopReason':reason,'error':error,'wallMs':(time.monotonic()-start)*1000,
                          'observedPeakResidentMiB':peak,'measurement':'ps_rss_every250ms'}
    if reason or child.returncode:
        settle_stages(report,reason or 'worker_exit');settle_attempts(report,reason or 'worker_exit')
        report['status']='stopped_incomplete' if reason else 'failed'
    journal=out.with_suffix('.journal.jsonl')
    if journal.exists():
        report.setdefault('runId',plan['runId'])
        try:reconcile_journal(report,journal,reason or 'worker_exit')
        except Exception as replay_error:
            report.update(status='invalid_journal',journalRecoveryError=str(replay_error))
    else:settle_events(report,out.with_suffix('.windows.jsonl'),reason or 'worker_exit')
    save(out,report)
    print(json.dumps({'status':report['status'],'attempts':len(report['attempts']),'record':str(out)},ensure_ascii=False))
    return 0 if report['status']=='diagnostic_completed' else 1


def historical_status():
    slots=(ART/'l3-22-realizer-slots-summary.json').exists()
    search=(ART/'l3-21-realizer-grid-summary.json').exists()
    budget=(ART/'l3-20-realizer-budget320-summary.json').exists()
    steps=(ART/'l3-19-realizer-steps-summary.json').exists()
    expanded=(ART/'l3-18-realizer-expanded-summary.json').exists()
    fit=(ART/'l3-17-realizer-fit-summary.json').exists()
    audit=(ART/'l3-16-label-audit-summary.json').exists()
    smoke=(ART/'l3-15-realizer-smoke-summary.json').exists()
    summary=read_json(ART/('l3-22-realizer-slots-summary.json' if slots else 'l3-21-realizer-grid-summary.json' if search else 'l3-20-realizer-budget320-summary.json' if budget else 'l3-19-realizer-steps-summary.json' if steps else 'l3-18-realizer-expanded-summary.json' if expanded else 'l3-17-realizer-fit-summary.json' if fit else 'l3-16-label-audit-summary.json' if audit else 'l3-15-realizer-smoke-summary.json' if smoke else 'l3-14-realizer-training-readiness-summary.json'))
    result={'stage':summary['stage'],'entrypoint':'experiments/world-components-logic/experiment.py',
            'implementation':'experiments/world-components-logic/'+('realizer_slots.py' if slots else 'realizer_search.py' if search else 'plan_training.py'),'latestBatch':summary['batchId'],
            'lastModelRun':summary['lastModelRun'],'resultPage':'artifacts/world-components-logic/'+('l3-22-realizer-slots.html' if slots else 'l3-21-realizer-grid.html' if search else 'l3-20-realizer-budget320.html' if budget else 'l3-19-realizer-steps.html' if steps else 'l3-18-realizer-expanded.html' if expanded else 'l3-17-realizer-fit.html' if fit else 'l3-16-label-audit.html' if audit else 'l3-15-realizer-smoke.html' if smoke else 'l3-14-realizer-training-readiness.html'),
            'draftSourceGroups':summary['draftSourceGroups'],'review':summary['review'],
            'realizerTrainerImplemented':summary.get('realizerTrainerImplemented',False),'inspection':summary.get('inspection'),
            'syntheticTrainingCheck':summary.get('realModelSyntheticCheck'),
            'assistantLabelCheck':{k:summary.get(k) for k in ('reviewKind','checkedAnnotations','correctedSourceInputs','sourceRisks')},
            'trainingOutcomes':{k:summary.get(k) for k in ('runStatus','trainingSteps','generationAttempts','assistantQualityCounts')},
            'plannerModelImplemented':summary['plannerModelImplemented'],'realizerTrained':summary['realizerTrained'],
            'formalEvaluationAllowed':summary['formalEvaluationAllowed'],'fullRequest500msStatus':summary['fullRequest500msStatus'],
            'modelExecutionPerformed':False}
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


def status():
    import short_experiment
    return short_experiment.active_status()


def historical_check():
    """Read archived evidence only; retired model-dependent tests stay at d80a031."""
    commands=[*[[str(BASE/name),'--check'] for name in ('pilot_report.py','m01_report.py','m01_shared_report.py')],
              [str(BASE/'m01_shared_report.py'),'--event','--check'],
              [str(BASE/'m01_shared_report.py'),'--journal','--check'],
              [str(BASE/'m01_shared_report.py'),'--input','--check'],
              [str(BASE/'m01_shared_report.py'),'--compiled','--check'],
              [str(BASE/'m01_shared_report.py'),'--chain','--check'],
              [str(BASE/'m01_shared_report.py'),'--focus','--check'],
              [str(BASE/'action_plan.py'),'--check'],
              [str(BASE/'plan_training.py'),'--check-materials'],
              [str(BASE/'plan_training.py'),'--check-smoke'],
              [str(BASE/'plan_training.py'),'--check-audit'],
              [str(BASE/'plan_training.py'),'--check-fit'],[str(BASE/'plan_training.py'),'--check-expanded'],
              [str(BASE/'realizer_steps.py'),'--check'],[str(BASE/'plan_training.py'),'--check-budget'],
              [str(BASE/'realizer_search.py'),'--check'],[str(BASE/'realizer_slots.py'),'--check']]
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for args in commands:
        result=subprocess.run([sys.executable,*args],cwd=ROOT,env=env)
        if result.returncode:return result.returncode
    print('PASS: archived evidence checks; no training or inference executed.')
    return 0


def check():
    """Active architecture checks, including tiny numerical training fixtures.

    No production model weights, game inference, services or old experiments
    are executed. Archive validation is explicitly available separately.
    """
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
             OPENBLAS_NUM_THREADS='1',TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    for pattern in ('test_short_*.py','test_experiment_journal*.py'):
        answer=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(BASE/'tests'),'-p',pattern],cwd=ROOT,env=env)
        if answer.returncode:return answer.returncode
    print('PASS: new-architecture engineering and numerical fixtures; no game-model capability claim.')
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description='D current entry: status/check do not execute models; prepare freezes a new batch; execute runs it.')
    sub=parser.add_subparsers(dest='command')
    sub.add_parser('status',help='new short-semantics status, no model execution')
    sub.add_parser('history-status',help='read archived pre-short-semantics status')
    sub.add_parser('history-check',help='read-only archived evidence validation; no legacy model execution')
    sub.add_parser('short-data',help='check new authored supervision and group isolation')
    audit=sub.add_parser('short-audit',help='inspect local model/dependency availability only')
    audit.add_argument('--model-root',type=Path)
    prep=sub.add_parser('short-prepare',help='freeze new short semantic training plan; no model execution')
    prep.add_argument('run_id');prep.add_argument('--model-root',type=Path);prep.add_argument('--dataset',type=Path);prep.add_argument('--profile',choices=('intent','all','encoder_repair'),default='intent')
    prep.add_argument('--inherit-provider',type=Path,help='required for encoder_repair; all other heads and generator retain this exact identity')
    qp=sub.add_parser('short-qwen-prepare',help='freeze complete-context Qwen short-text training; no inference')
    qp.add_argument('run_id');qp.add_argument('--model-manifest',type=Path,required=True);qp.add_argument('--dataset',type=Path)
    sub.add_parser('short-qwen-execute',help='execute frozen local Qwen training using shared supervisor').add_argument('plan',type=Path)
    sub.add_parser('short-qwen-report',help='read Qwen training evidence').add_argument('plan',type=Path)
    fp=sub.add_parser('short-encoder-focus-prepare',help='freeze full-context versus query-focus encoder comparison')
    fp.add_argument('run_id');fp.add_argument('--source-provider',type=Path,required=True);fp.add_argument('--dataset',type=Path)
    sub.add_parser('short-encoder-focus-execute',help='execute frozen encoder comparison using shared supervisor').add_argument('plan',type=Path)
    sub.add_parser('short-encoder-focus-report',help='read first-output encoder comparison evidence').add_argument('plan',type=Path)
    ep=sub.add_parser('short-eval-prepare',help='freeze diagnostic and actual-upstream model comparison')
    ep.add_argument('run_id');ep.add_argument('--provider',type=Path,required=True);ep.add_argument('--dataset',type=Path)
    ep.add_argument('--scope',choices=('contracts','all','webgpu','webgpu_text'),default='contracts')
    sub.add_parser('short-eval-execute',help='execute frozen new-chain comparison').add_argument('plan',type=Path)
    sub.add_parser('short-eval-report',help='read original new-chain comparison evidence').add_argument('plan',type=Path)
    sub.add_parser('short-execute',help='execute frozen new training plan using shared supervisor').add_argument('plan',type=Path)
    sub.add_parser('short-report',help='read new frozen preparation or training record').add_argument('plan',type=Path)
    sub.add_parser('check',help='new-architecture engineering and tiny numerical fixtures; no game inference')
    plan_data=sub.add_parser('plan-data',help='check/write current action-plan preparation; no models')
    plan_data.add_argument('--write-new',action='store_true')
    training_data=sub.add_parser('train-data',help='current new-source candidate and training-readiness materials; no models')
    training_data.add_argument('--write-new',action='store_true')
    label_audit=sub.add_parser('train-audit',help='twelve-label assistant precheck and corrected r2 candidates; no models')
    label_audit.add_argument('--write-new',action='store_true')
    expansion=sub.add_parser('train-expand',help='expanded grouped draft supervision data; no model execution')
    expansion.add_argument('--write-new',action='store_true')
    inspection=sub.add_parser('train-inspect',help='prepare or execute no-business M02 adapter inspection')
    inspection_group=inspection.add_mutually_exclusive_group(required=True)
    inspection_group.add_argument('--prepare');inspection_group.add_argument('--execute',type=Path)
    smoke=sub.add_parser('train-smoke',help='real M02 synthetic numeric training and disk reload; no business labels')
    smoke_group=smoke.add_mutually_exclusive_group(required=True)
    smoke_group.add_argument('--prepare');smoke_group.add_argument('--execute',type=Path);smoke_group.add_argument('--report',action='store_true')
    training=sub.add_parser('train-prepare',help='freeze a reviewed-source adapter training batch')
    training.add_argument('run_id');admission=training.add_mutually_exclusive_group(required=True)
    admission.add_argument('--reviews',type=Path);admission.add_argument('--authorization',type=Path)
    sub.add_parser('train-execute',help='execute a previously frozen reviewed training batch').add_argument('plan',type=Path)
    fit_report=sub.add_parser('train-report',help='read-only first fit outputs and assistant review report')
    fit_report.add_argument('--write-new',action='store_true')
    fit_report.add_argument('--run-id',default='m02-realizer-fit-20261104-r1')
    steps=sub.add_parser('realizer-steps',help='frozen whole versus ordered step expression diagnostic')
    step_mode=steps.add_mutually_exclusive_group(required=True)
    step_mode.add_argument('--prepare');step_mode.add_argument('--execute',type=Path)
    step_mode.add_argument('--report',action='store_true')
    search=sub.add_parser('realizer-search',help='bounded draft hyperparameter grid and seed confirmation')
    search_mode=search.add_mutually_exclusive_group(required=True)
    search_mode.add_argument('--prepare',action='store_true');search_mode.add_argument('--execute',type=Path)
    search_mode.add_argument('--select',action='store_true');search_mode.add_argument('--report',action='store_true')
    slots=sub.add_parser('realizer-slots',help='controlled references with source-ID name/literal restoration')
    slot_mode=slots.add_mutually_exclusive_group(required=True)
    slot_mode.add_argument('--data',action='store_true');slot_mode.add_argument('--tokenize',action='store_true')
    slot_mode.add_argument('--prepare',action='store_true');slot_mode.add_argument('--execute',type=Path)
    slot_mode.add_argument('--report',action='store_true')
    sub.add_parser('prepare',help='freeze the historical L3-12 diagnostic; current work uses plan-data').add_argument('run_id')
    sub.add_parser('execute',help='run inference on a frozen current batch; no training').add_argument('plan',type=Path)
    args=parser.parse_args(argv)
    if args.command in (None,'status'):return status()
    if args.command=='history-status':return historical_status()
    if args.command=='history-check':return historical_check()
    if args.command and args.command.startswith('short-'):
        import short_experiment as short
        if args.command.startswith('short-qwen-'):
            import short_qwen_training as qwen
            if args.command=='short-qwen-prepare':print(qwen.freeze(args.run_id,model_manifest=args.model_manifest,dataset=args.dataset));return 0
            if args.command=='short-qwen-execute':return qwen.execute(args.plan)
            print(json.dumps(qwen.report(args.plan),ensure_ascii=False,indent=2));return 0
        if args.command.startswith('short-encoder-focus-'):
            import short_encoder_repair as focus
            if args.command=='short-encoder-focus-prepare':print(focus.freeze(args.run_id,source_provider=args.source_provider,dataset=args.dataset or short.DATA/'supervision.jsonl.gz'));return 0
            if args.command=='short-encoder-focus-execute':return focus.execute(args.plan)
            print(json.dumps(focus.report(args.plan),ensure_ascii=False,indent=2));return 0
        if args.command.startswith('short-eval-'):
            import short_evaluation as evaluation
            if args.command=='short-eval-prepare':print(evaluation.freeze(args.run_id,args.provider,dataset=args.dataset,scope=args.scope));return 0
            if args.command=='short-eval-execute':return evaluation.execute(args.plan)
            print(json.dumps(evaluation.report(args.plan),ensure_ascii=False,indent=2));return 0
        if args.command=='short-data':print(json.dumps(short.validate_rows(short.load_rows()),ensure_ascii=False));return 0
        if args.command=='short-audit':print(json.dumps(short.audit_resources(args.model_root),ensure_ascii=False,indent=2));return 0
        if args.command=='short-prepare':print(short.freeze(args.run_id,model_root=args.model_root,dataset=args.dataset,profile=args.profile,inherit_provider=args.inherit_provider));return 0
        if args.command=='short-execute':return short.execute(args.plan)
        if args.command=='short-report':print(json.dumps(short.readiness_report(args.plan),ensure_ascii=False,indent=2));return 0
    retired=args.command in ('prepare','execute','train-prepare','train-execute')
    retired=retired or (args.command in ('train-inspect','train-smoke','realizer-steps','realizer-search','realizer-slots') and not getattr(args,'report',False))
    retired=retired or (args.command in ('plan-data','train-data','train-audit','train-expand','train-report') and getattr(args,'write_new',False))
    if retired:
        parser.error('legacy execution retired on this branch; use short-* for the new architecture; d80a031 remains the historical reproduction reference')
    if args.command=='check':return check()
    if args.command=='realizer-slots':
        import realizer_slots
        if args.data:print(json.dumps(realizer_slots.source_materials(write=True),ensure_ascii=False));return 0
        if args.tokenize:
            value=realizer_slots.tokenizer_materials(write=True);print(json.dumps({k:value[k] for k in ('maxNaturalInputTokens','maxSlotInputTokens','maxSlotTargetTokens','neuralForwardCalls')}));return 0
        if args.prepare:print(realizer_slots.prepare());return 0
        if args.execute:return realizer_slots.execute(args.execute)
        value=realizer_slots.materials(write=True);print(json.dumps({'trainingSteps':value['trainingSteps'],'generations':value['generationAttempts'],'promotion':value['promotionStatus']}));return 0
    if args.command=='realizer-search':
        import realizer_search
        if args.prepare:print(realizer_search.prepare());return 0
        if args.execute:return realizer_search.execute(args.execute)
        if args.select:print(json.dumps(realizer_search.select()['selected'],ensure_ascii=False));return 0
        s=realizer_search.materials(write=True);print(json.dumps({'gridPoints':s['gridPoints'],'trainingSteps':s['trainingSteps'],'generations':s['generationAttempts']}));return 0
    if args.command=='realizer-steps':
        import realizer_steps
        if args.prepare:print(realizer_steps.prepare(args.prepare));return 0
        if args.execute:return realizer_steps.execute(args.execute)
        s=realizer_steps.materials(write=True);print(json.dumps({'attempts':s['attemptCount'],'generationCalls':s['generationCalls'],'trainingSteps':0}));return 0
    if args.command=='train-expand':
        import realizer_expansion
        print(json.dumps(realizer_expansion.materials(write=args.write_new),ensure_ascii=False));return 0
    if args.command=='plan-data':
        import action_plan
        s=action_plan.prepare_materials(write=args.write_new)
        print(json.dumps({'batchId':s['batchId'],'newPlanLabelsReviewed':s['review']['newPlanLabelsReviewed'],'trainingSteps':0,'modelInferenceCalls':0},ensure_ascii=False))
        return 0
    if args.command in ('train-data','train-audit','train-inspect','train-smoke','train-prepare','train-execute','train-report'):
        import plan_training
        if args.command=='train-data':
            print(json.dumps(plan_training.prepare_materials(write=args.write_new),ensure_ascii=False,indent=2));return 0
        if args.command=='train-audit':
            s=plan_training.label_audit_materials(write=args.write_new)
            print(json.dumps({'batchId':s['batchId'],'checkedAnnotations':s['checkedAnnotations'],'correctedSourceInputs':s['correctedSourceInputs'],'humanReviewedGroups':s['review']['reviewedGroups']},ensure_ascii=False));return 0
        if args.command=='train-inspect':
            if args.prepare:print(plan_training.inspection_plan(args.prepare));return 0
            return plan_training.execute_inspection(args.execute)
        if args.command=='train-smoke':
            if args.prepare:print(plan_training.inspection_plan(args.prepare,smoke=True));return 0
            if args.report:
                s=plan_training.smoke_materials(write=True);print(json.dumps({'batchId':s['batchId'],'businessTrainingSteps':0,'syntheticOptimizerSteps':s['realModelSyntheticCheck']['syntheticOptimizerSteps']}));return 0
            return plan_training.execute_inspection(args.execute)
        if args.command=='train-prepare':print(plan_training.training_plan(args.run_id,args.reviews,authorization_path=args.authorization));return 0
        if args.command=='train-report':
            s=plan_training.fit_materials(write=args.write_new,run_id=args.run_id);print(json.dumps({'batchId':s['batchId'],'trainingSteps':s['trainingSteps'],'generationAttempts':s['generationAttempts']},ensure_ascii=False));return 0
        return plan_training.execute_training(args.plan)
    import action_chain
    if args.command=='prepare':print(action_chain.prepare(args.run_id));return 0
    return action_chain.execute(args.plan)


if __name__=='__main__':raise SystemExit(main())
