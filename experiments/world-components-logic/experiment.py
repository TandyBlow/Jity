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


def execute_plan(path,*,paths,verify,worker_script,settle_stages,arms):
    """Bounded child process; callbacks supply only experiment-specific facts."""
    plan=read_json(path);_,out=paths(plan['runId'])
    if out.exists():raise FileExistsError('preserve original record; use a new run id')
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
    settle_events(report,out.with_suffix('.windows.jsonl'),reason or 'worker_exit');save(out,report)
    print(json.dumps({'status':report['status'],'attempts':len(report['attempts']),'record':str(out)},ensure_ascii=False))
    return 0 if report['status']=='diagnostic_completed' else 1


def status():
    summary=read_json(ART/'l3-6-m01-shared-summary.json');latest=summary['runs'][-1]
    result={'stage':'L3 exploratory offline validation','entrypoint':'experiments/world-components-logic/experiment.py',
            'implementation':'experiments/world-components-logic/m01_shared.py','latestRun':latest['runId'],
            'resultPage':'artifacts/world-components-logic/l3-6-m01-shared-results.html','quality':latest['quality'],
            'formalEvaluationAllowed':summary['formalEvaluationAllowed'],'fullRequest500msStatus':summary['fullRequest500msStatus'],
            'modelExecutionPerformed':False}
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


def check():
    commands=[['-m','unittest','discover','-s',str(BASE/'tests'),'-p','test_*.py'],
              *[[str(BASE/name),'--check'] for name in ('pilot_report.py','m01_report.py','m01_shared_report.py')]]
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
    sub.add_parser('execute',help='actually train and infer a frozen current batch').add_argument('plan',type=Path)
    args=parser.parse_args(argv)
    if args.command in (None,'status'):return status()
    if args.command=='check':return check()
    import m01_shared
    if args.command=='prepare':print(m01_shared.prepare(args.run_id));return 0
    return m01_shared.execute(args.plan)


if __name__=='__main__':raise SystemExit(main())
