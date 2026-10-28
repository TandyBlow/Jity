import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / '.local/world-server-worktree'
OUT = ROOT / '.local/h2-fixed-20261027'
OUT.mkdir(exist_ok=False)
PORT = 18783
URL = f'http://127.0.0.1:{PORT}'
events = []
process = None
log = None
generation = 0


def event(action, **fields):
    item = dict(at=datetime.now(timezone.utc).isoformat(), action=action, **fields)
    events.append(item)
    (OUT / 'lifecycle.json').write_text(json.dumps(events, indent=2) + '\n', encoding='utf8')
    print(json.dumps(item), flush=True)


def git(checkout, *args):
    return subprocess.check_output(['git', '-c', f'safe.directory={checkout.as_posix()}',
                                   '-C', str(checkout), *args], text=True).strip()


def start(db):
    global process, log, generation
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', PORT))
    generation += 1
    log = (OUT / f'server-{generation}.log').open('wb')
    env = dict(os.environ, WORLD_SQLITE_PATH=str(db), PYTHONUTF8='1', PYTHONUNBUFFERED='1')
    process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'uvicorn',
        'app.world_app:create_persistent_world_app', '--factory', '--host', '127.0.0.1',
        '--port', str(PORT), '--workers', '1'], cwd=A / 'backend', env=env,
        stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(150):
        if process.poll() is not None:
            raise RuntimeError(f'service exited; see server-{generation}.log')
        try:
            with urlopen(URL + '/openapi.json', timeout=1) as response:
                assert response.status == 200
            event('service_start', generation=generation, pid=process.pid, database=db.name,
                  factory='app.world_app:create_persistent_world_app', ready=True)
            return
        except OSError:
            time.sleep(.1)
    raise RuntimeError('service readiness timeout')


def stop():
    global process, log
    if process is None:
        return
    pid = process.pid
    process.terminate()
    process.wait(timeout=15)
    log.close()
    event('service_stop', generation=generation, pid=pid, exitCode=process.returncode)
    process = log = None


def phase(name, label=None, state=None, kind=None):
    label = label or name
    report = OUT / f'report-{label}.json'
    args = ['node', 'scripts/review-world-h2-full.mjs', URL, name, str(report), str(A)]
    if state:
        args += ['--state', str(state)]
    if kind:
        args += ['--kind', kind]
    with (OUT / f'phase-{label}.log').open('wb') as phase_log:
        result = subprocess.run(args, cwd=ROOT / 'frontend', stdout=phase_log,
                                stderr=subprocess.STDOUT, timeout=90)
    data = json.loads(report.read_text(encoding='utf8')) if report.exists() else {}
    event('phase', phase=name, label=label, exitCode=result.returncode, status=data.get('status'))
    assert result.returncode == 0, f'{label} failed; inspect private report/log'
    assert data.get('browser', {}).get('head') == '6b809dca846b407ae24f545adeef7ae068fcf5b5'
    assert data.get('server', {}).get('head') == '0cb1951cd1b0181f6a0505026cdd9939dd668de9'
    return data


def damage(db, state, mode):
    assert process is None
    identity = json.loads(state.read_text(encoding='utf8'))
    keys = (identity['worldId'], identity['pointId'], identity['groupId'])
    with sqlite3.connect(db) as connection:
        if mode == 'missing':
            connection.execute('DROP TRIGGER active_frozen_payload_retained')
            sql = '''DELETE FROM world_frozen_work WHERE (world_id,point_id,group_id,member_id,epoch,attempt)
                IN (SELECT world_id,point_id,group_id,member_id,epoch,attempt FROM world_work_refs
                    WHERE world_id=? AND point_id=? AND group_id=?)'''
            affected = connection.execute(sql, keys).rowcount
        elif mode == 'corrupt':
            connection.execute('DROP TRIGGER frozen_work_immutable')
            sql = '''UPDATE world_frozen_work SET action_bytes=?
                WHERE (world_id,point_id,group_id,member_id,epoch,attempt)
                IN (SELECT world_id,point_id,group_id,member_id,epoch,attempt FROM world_work_refs
                    WHERE world_id=? AND point_id=? AND group_id=?)'''
            affected = connection.execute(sql, (b'H2 deliberately damaged bytes', *keys)).rowcount
        elif mode == 'group':
            raw = connection.execute('SELECT group_json FROM world_group_payloads '
                'WHERE world_id=? AND point_id=? AND group_id=?', keys).fetchone()[0]
            payload = json.loads(raw)
            payload['actionTexts']['person_a'] = 'H2 deliberately damaged active group'
            sql = 'UPDATE world_group_payloads SET group_json=? WHERE world_id=? AND point_id=? AND group_id=?'
            affected = connection.execute(sql, (json.dumps(payload, ensure_ascii=False), *keys)).rowcount
        else:
            raise ValueError(mode)
        assert affected == 1, (mode, affected)
    event('damage_injection', mode=mode, database=db.name, affectedRows=affected,
          worldId=keys[0], pointId=keys[1], groupId=keys[2], serviceStopped=True)


try:
    assert git(ROOT, 'rev-parse', 'HEAD') == '6b809dca846b407ae24f545adeef7ae068fcf5b5'
    assert git(A, 'rev-parse', 'HEAD') == '0cb1951cd1b0181f6a0505026cdd9939dd668de9'
    assert not git(ROOT, 'diff', 'HEAD', '--name-only')
    assert not git(A, 'diff', 'HEAD', '--name-only')
    shared = git(ROOT, 'ls-files', 'design/world-protocol/v2',
                 'frontend/src/lib/world-engine/contract-digest.json').splitlines()
    for relative in shared:
        assert (ROOT / relative).read_bytes() == (A / relative).read_bytes(), relative
    event('baseline', browser=git(ROOT, 'rev-parse', 'HEAD'), server=git(A, 'rev-parse', 'HEAD'),
          browserStatus=git(ROOT, 'status', '--short'), serverStatus=git(A, 'status', '--short'),
          sharedFilesCompared=len(shared), contractDigest=json.loads(
              (ROOT / 'design/world-protocol/v2/manifest.json').read_text())['contractDigest'])
    database = OUT / 'positive.db'
    start(database)
    phase('main')
    phase('successor')
    state = OUT / 'positive-state.json'
    phase('build-frozen-case', state=state)
    stop()
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    start(database)
    phase('post-restart', state=state)
    stop()
    event('restart_evidence', sameDatabase='positive.db', databaseBeforeRestartSha256=before,
          persistedState='positive-state.json', restartFromGeneration=1, restartToGeneration=2)
    for mode in ['missing', 'corrupt', 'group']:
        database = OUT / f'{mode}.db'
        state = OUT / f'{mode}-state.json'
        start(database)
        phase('build-frozen-case', label=f'build-{mode}', state=state)
        stop()
        damage(database, state, mode)
        start(database)
        phase('expect-frozen', label=f'frozen-{mode}', state=state,
              kind='missing' if mode == 'missing' else 'corrupt')
        stop()
    event('complete', status='PASS_FIXED_H2')
finally:
    stop()
