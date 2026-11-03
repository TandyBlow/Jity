"""Current D experiment entry point and shared execution bookkeeping.

status/check never import a model or prepare/execute a model batch. Model-specific
packing, heads, fitting and predictions belong to m01_shared, loaded on demand.
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
    return [{'arm':arm,'caseId':case['caseId'],'repeat':repeat,'status':'not_started'}
            for repeat in range(plan['config']['attemptsPerCase']) for case in plan['cases']
            for arm in (arms if repeat%2==0 else arms[::-1])]


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

    def close(self):self.stream.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def read_journal(path,plan_sha):
    from run_pilot import digest
    raw=Path(path).read_bytes()
    if str(path).endswith('.gz'):raw=gzip.decompress(raw)
    lines=raw.splitlines(keepends=True);entries=[];previous=None;partial=0
    for i,line in enumerate(lines):
        if not line.endswith(b'\n'):
            if i!=len(lines)-1:raise ValueError('journal has an interior partial line')
            partial=len(line);break
        row=json.loads(line)
        if set(row)!={'sequence','planSha256','previousSha256','kind','data','sha256'}:raise ValueError('journal envelope invalid')
        if (row['sequence']!=i or row['planSha256']!=plan_sha or row['previousSha256']!=previous
                or digest({k:v for k,v in row.items() if k!='sha256'})!=row['sha256']):raise ValueError('journal identity/sequence/hash mismatch')
        entries.append(row);previous=row['sha256']
    return entries,partial


def reconcile_journal(report,path,reason):
    """Read only: reconstruct evidence after exit; never infer/retry a model."""
    import copy
    entries,partial=read_journal(path,report['planSha256'])
    if not entries:
        report['journalRecovery']={'events':0,'partialTailBytes':partial,'sha256':sha256_file(path)}
        return
    key=lambda a:(a['arm'],a['caseId'],a['repeat'])
    first=entries[0]
    if first['kind']!='begin' or first['data']['runId']!=report['runId']:raise ValueError('journal header mismatch')
    planned=first['data']['slots'];ids=[key(s) for s in planned]
    if len(set(ids))!=len(ids) or ids!=[key(s) for s in report['attemptSlots']]:raise ValueError('journal slot mismatch')
    slots={key(s):dict(s) for s in planned};attempts=[];active=None;result=None;windows=[];active_window=None
    snapshots={key(a):a for a in report['attempts']}
    for row in entries[1:]:
        kind=row['kind'];data=row['data']
        if kind=='attempt_start':
            k=key(data)
            if active is not None or k not in slots or slots[k]['status']!='not_started' or data['status']!='started':raise ValueError('duplicate/unknown/overlapping attempt start')
            active=copy.deepcopy(data);slots[k]=active;result=None
        elif kind=='window':
            if active is None or result is not None or key(data)!=key(active):raise ValueError('window outside active attempt')
            index=data['eventId']
            if data['status']=='running':
                if active_window is not None or index!=len(windows):raise ValueError('duplicate/overlapping window start')
                active_window=copy.deepcopy(data);windows.append(active_window)
            else:
                if (active_window is None or index!=active_window['eventId'] or data['status'] not in ('complete','failed')
                        or any(data[k]!=active_window[k] for k in ('caseId','arm','repeat','windowIndex','inputIds','tokenTypeIds','factSpans'))):
                    raise ValueError('unmatched window settlement')
                windows[index]=copy.deepcopy(data);active_window=None
        elif kind=='attempt_result':
            if active is None or result is not None or key(data)!=key(active) or active_window is not None:raise ValueError('unmatched/duplicate attempt result')
            if data['status'] not in ('complete','failed'):raise ValueError('invalid attempt result status')
            result=copy.deepcopy(data)
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
    if active is not None:
        item=result if result is not None else active
        item.update(status='result_saved_timing_incomplete' if result is not None else 'interrupted',stopReason=reason,
                    settledAt=timestamp(),exactTelemetryTimingAvailable=False)
        attempts.append(item);slots[key(item)]=item
    report.update(attempts=attempts,attemptSlots=[slots[k] for k in ids],activeAttempt=None,
                  forwardAttempts=windows,activeForward=None,
                  unexecutedAttempts=sum(s['status']=='not_started' for s in slots.values()),
                  journalRecovery={'events':len(entries),'partialTailBytes':partial,'sha256':sha256_file(path),
                                   'readOnlyReplay':True,'modelCallsDuringReplay':0})
    if partial or active is not None or active_window is not None or (report.get('status')=='diagnostic_completed' and report['unexecutedAttempts']):report['status']='stopped_incomplete'



def execute_plan(path,*,paths,verify,worker_script,settle_stages,arms):
    """Bounded child process; callbacks supply only experiment-specific facts."""
    plan=read_json(path);_,out=paths(plan['runId'])
    if any(p.exists() for p in (out,out.with_suffix(out.suffix+'.gz'),out.with_suffix('.journal.jsonl'),out.with_suffix('.journal.jsonl.gz'))):
        raise FileExistsError('preserve original record/journal; use a new run id')
    try:verify(plan)
    except Exception as error:
        exclusive(out,{'status':'failed_preflight','planSha256':sha256_file(path),'attempts':[],
                      'error':str(error),'formalEvaluationAllowed':False});raise
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


def status():
    summary=read_json(ART/'l3-8-m01-journal-summary.json');latest=summary['runs'][-1]
    result={'stage':'L3 exploratory offline validation','entrypoint':'experiments/world-components-logic/experiment.py',
            'implementation':'experiments/world-components-logic/m01_shared.py','latestRun':latest['runId'],
            'resultPage':'artifacts/world-components-logic/l3-8-m01-journal-results.html','quality':latest['quality'],
            'formalEvaluationAllowed':summary['formalEvaluationAllowed'],'fullRequest500msStatus':summary['fullRequest500msStatus'],
            'modelExecutionPerformed':False}
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


def check():
    commands=[['-m','unittest','discover','-s',str(BASE/'tests'),'-p','test_*.py'],
              *[[str(BASE/name),'--check'] for name in ('pilot_report.py','m01_report.py','m01_shared_report.py')],
              [str(BASE/'m01_shared_report.py'),'--event','--check'],
              [str(BASE/'m01_shared_report.py'),'--journal','--check']]
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for args in commands:
        result=subprocess.run([sys.executable,*args],cwd=ROOT,env=env)
        if result.returncode:return result.returncode
    print('PASS: engineering tests and archived reports; no training or inference executed.')
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description='D current entry: status/check do not execute models; prepare freezes a new batch; execute runs it.')
    sub=parser.add_subparsers(dest='command')
    sub.add_parser('status',help='read current status only (default)')
    sub.add_parser('check',help='run lightweight tests and verify archived reports; no models')
    sub.add_parser('prepare',help='freeze a new shared-encoder batch; requires local model files').add_argument('run_id')
    sub.add_parser('execute',help='run inference on a frozen current batch; no training').add_argument('plan',type=Path)
    args=parser.parse_args(argv)
    if args.command in (None,'status'):return status()
    if args.command=='check':return check()
    import m01_shared
    if args.command=='prepare':print(m01_shared.prepare(args.run_id));return 0
    return m01_shared.execute(args.plan)


if __name__=='__main__':raise SystemExit(main())
