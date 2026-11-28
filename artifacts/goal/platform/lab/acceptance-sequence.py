#!/usr/bin/env python3
"""Wait for the shared lease, then run the platform acceptance sequence.

Stages: 4-turn new-input holdout -> 2-turn mobile simulation -> 10-turn soak
with resource sampling. Uses the product server on 3177 when it is up; starts
its own server on 3180 only if 3177 is down. Stops only its own server/driver
pids, never another lane's browser or server.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[4]
FRONTEND = ROOT / 'frontend'
LAB = ROOT / 'artifacts/goal/platform/lab'
EVID = ROOT / 'results/product/evidence'
EVAL = ROOT / 'artifacts/goal/platform/eval'
LOCK = ROOT / 'resources/local-inference.lock'
sys.path.insert(0, str(ROOT))
from tools.experiment_platform.verify_run import check  # noqa: E402

WAIT_LIMIT_SEC = 40 * 60
MEM_FLOOR_MB = 2500
QUERY = 'semanticCtx=4096&narrationModel=semantic'


def lease_state() -> tuple[str, dict | None]:
    if not LOCK.exists():
        return 'free', None
    try:
        record = json.loads(LOCK.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return 'stale', None
    holder = record.get('holderPid')
    if holder and psutil.pid_exists(int(holder)):
        return 'held', record
    return 'stale', record


def server_ok(base: str) -> bool:
    try:
        with urllib.request.urlopen(base + '/world-local', timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def start_server() -> tuple[subprocess.Popen, str, Path]:
    log = LAB / 'server-3180.log'
    proc = subprocess.Popen(
        ['node', 'node_modules/next/dist/bin/next', 'start', '-p', '3180'],
        cwd=FRONTEND, stdout=log.open('wb'), stderr=subprocess.STDOUT)
    return proc, 'http://127.0.0.1:3180', log


def stop_pid(pid: int) -> None:
    subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True)


def run_driver(name: str, turns: Path, expect: int, extra: list[str], query: str) -> dict:
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    out = EVID / f'platform-{name}-{stamp}.json'
    profile = LAB / f'profile-{name}'
    log_path = LAB / f'platform-{name}.log'
    cmd = ['node', 'scripts/product-acceptance/accept-world-local.mjs',
           '--base', BASE, '--turns', str(turns), '--profile', str(profile), '--fresh',
           '--query', query, '--out', str(out), '--turn-timeout-ms', '600000', *extra]
    log = log_path.open('wb')
    proc = subprocess.Popen(cmd, cwd=FRONTEND, stdout=log, stderr=subprocess.STDOUT)
    monitor = None
    if name == 'soak-10':
        monitor = subprocess.Popen(
            [sys.executable, '-X', 'utf8', '-m', 'tools.experiment_platform.resource_monitor',
             '--pid', str(proc.pid), '--interval', '2', '--duration', '3600',
             '--out', str(LAB / 'soak-memory.csv')],
            cwd=ROOT, env={**os.environ, 'PYTHONUTF8': '1'},
            stdout=(LAB / 'soak-monitor.log').open('wb'), stderr=subprocess.STDOUT)
    started = time.time()
    timed_out = False
    stalled = False
    while proc.poll() is None:
        elapsed = time.time() - started
        if elapsed > 45 * 60:
            timed_out = True
            stop_pid(proc.pid)
            break
        if elapsed > 420 and out.exists():
            try:
                turns = len(json.loads(out.read_text(encoding='utf-8-sig')).get('turns') or [])
            except (OSError, json.JSONDecodeError):
                turns = 0
            if turns == 0:
                stalled = True
                stop_pid(proc.pid)
                break
        time.sleep(10)
    proc.wait()
    log.close()
    if monitor:
        try:
            monitor.wait(timeout=30)
        except subprocess.TimeoutExpired:
            monitor.terminate()
    report: dict = {'stage': name, 'evidence': str(out.relative_to(ROOT)).replace('\\', '/'),
                    'exitCode': proc.returncode, 'timedOut': timed_out}
    if out.exists():
        try:
            doc = json.loads(out.read_text(encoding='utf-8-sig'))
            verdict = check(doc, None, None, None, False, False, expect)
            report.update({'status': doc.get('status'), 'turns': len(doc.get('turns') or []),
                           'verifyPass': verdict['pass'], 'verifyFailures': verdict['failures']})
        except (OSError, json.JSONDecodeError) as exc:
            report['verifyFailures'] = [f'unreadable evidence: {exc}']
    else:
        report['verifyFailures'] = ['evidence missing']
    print(json.dumps(report, ensure_ascii=False))
    return report


_parser = argparse.ArgumentParser()
_parser.add_argument('--base', default='http://127.0.0.1:3177')
BASE = _parser.parse_args().base.rstrip('/')
own_server = None
reports = []
try:
    deadline = time.time() + WAIT_LIMIT_SEC
    while time.time() < deadline:
        state, holder = lease_state()
        free_mb = round(psutil.virtual_memory().available / 1048576)
        up = server_ok(BASE)
        print(f"{datetime.now().isoformat()} lease={state} freeMB={free_mb} server3177={up}")
        if state in ('free', 'stale') and free_mb >= MEM_FLOOR_MB and up:
            break
        if state in ('free', 'stale') and free_mb >= MEM_FLOOR_MB and not up and BASE.endswith(':3177'):
            if own_server is None:
                own_server, BASE, _ = start_server()
                for _ in range(45):
                    if server_ok(BASE):
                        break
                    time.sleep(2)
                print('started own server', BASE)
        time.sleep(20)
    else:
        raise SystemExit('no lease/memory/server window within 40 minutes')

    reports.append(run_driver('holdout-4', EVAL / 'turns-holdout-v1.json', 4, [], QUERY))
    if reports[-1].get('turns', 0) >= 1:
        reports.append(run_driver('mobile-2', EVAL / 'turns-mobile-2.json', 2,
                                  ['--cpu-throttle', '4', '--gpu-lite'], QUERY))
        reports.append(run_driver('soak-10', EVAL / 'turns-soak-10.json', 10, [], QUERY))
finally:
    (LAB / 'acceptance-sequence-report.json').write_text(
        json.dumps({'generatedAt': datetime.now().isoformat(), 'base': BASE, 'runs': reports},
                   ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    if own_server:
        stop_pid(own_server.pid)
