"""Full H2 acceptance on ONE pinned checkout (A and B from the same tree).

Adapted from artifacts/h2-full-6b809dc-0cb1951/run-recorded.py for the joint
integration commit: instead of a B worktree plus a separate A worktree, both
the browser harness and the SQLite service run out of the checkout that
contains this script's parent directory. The pin, the contract digest and the
dirty state are asserted before any phase runs, and the source identity is
captured again at the end.

Place at <checkout>/.local/run_integration_h2.py and run from anywhere:

    python -X utf8 <checkout>/.local/run_integration_h2.py

Phases (each a separate node invocation so the service can be restarted or a
row damaged in between): main, successor, build-frozen-case, post-restart,
expect-frozen x3 (missing / corrupt / group).
"""

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

PIN = 'd1d2de0cf2805d0f3ce1d182cde57821800d3bef'
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.local/h2-integration-run'
PORT = 18793
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


def git(*args):
    return subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}',
                                   '-C', str(ROOT), *args], text=True).strip()


def source_identity():
    files = {
        'browser': ['frontend/src/lib/world-engine/recovery.ts', 'frontend/src/lib/world-engine/controller.ts',
                    'frontend/src/lib/world-engine/schedule.ts', 'frontend/scripts/review-world-h2-full.mjs'],
        'server': ['backend/app/services/world/control.py', 'backend/app/services/world/authority.py',
                   'backend/app/database/world_frozen_repository.py'],
    }
    return {side: {relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() for relative in paths}
            for side, paths in files.items()}


def start(db):
    global process, log, generation
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', PORT))
    generation += 1
    log = (OUT / f'server-{generation}.log').open('wb')
    env = dict(os.environ, WORLD_SQLITE_PATH=str(db), PYTHONUTF8='1', PYTHONUNBUFFERED='1')
    process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'uvicorn',
        'app.world_app:create_persistent_world_app', '--factory', '--host', '127.0.0.1',
        '--port', str(PORT), '--workers', '1'], cwd=ROOT / 'backend', env=env,
        stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(200):
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
    args = ['node', 'scripts/review-world-h2-full.mjs', URL, name, str(report), str(ROOT)]
    if state:
        args += ['--state', str(state)]
    if kind:
        args += ['--kind', kind]
    with (OUT / f'phase-{label}.log').open('wb') as phase_log:
        result = subprocess.run(args, cwd=ROOT / 'frontend', stdout=phase_log,
                                stderr=subprocess.STDOUT, timeout=180)
    data = json.loads(report.read_text(encoding='utf8')) if report.exists() else {}
    event('phase', phase=name, label=label, exitCode=result.returncode, status=data.get('status'))
    assert result.returncode == 0, f'{label} failed; inspect private report/log'
    assert data.get('browser', {}).get('head') == PIN, f'{label}: browser head is not the pin'
    assert data.get('server', {}).get('head') == PIN, f'{label}: server head is not the pin'
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


def database_evidence():
    """Read-only byte/hash and binding evidence. No action text is copied out."""
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.schemas.world.canonical import canonical_digest  # pinned checkout's own code

    def dump(db, label):
        with sqlite3.connect(db) as connection:
            connection.row_factory = sqlite3.Row
            worlds = {}
            for world in connection.execute('SELECT id FROM worlds ORDER BY id'):
                wid = world['id']
                row = {'submissions': {}, 'points': [], 'work': [], 'copies': [], 'rolls': {},
                       'narrations': 0, 'lease': None, 'groups': {}, 'settledUnits': []}
                for submission in connection.execute(
                        'SELECT operation,request_id,request_hash,result_json FROM world_submissions WHERE world_id=?',
                        (wid,)):
                    row['submissions'][submission['operation']] = row['submissions'].get(submission['operation'], 0) + 1
                    assert submission['request_id'] not in row.setdefault('requestIds', []), 'duplicate request binding'
                    row['requestIds'].append(submission['request_id'])
                    result = json.loads(submission['result_json'])
                    assert 'inputText' not in submission['result_json'] and 'claimToken' not in submission['result_json'], \
                        'idempotency row leaked a private payload'
                    assert result.get('world', {}).get('worldId', wid) == wid, 'idempotency result crossed worlds'
                row['pointRows'] = [dict(point) for point in connection.execute(
                    'SELECT id,sequence,kind,previous_point_id,state_digest FROM world_points WHERE world_id=? ORDER BY sequence', (wid,))]
                row['nonRootCommits'] = len([p for p in row['pointRows'] if p['previous_point_id'] is not None])
                for work in connection.execute(
                        '''SELECT w.point_id,w.group_id,w.member_id,w.epoch,w.attempt,w.action_bytes,
                                  w.candidates_json,w.targets_json,w.result_bytes,a.hashes_json
                           FROM world_frozen_work w JOIN world_accepted_work a
                             ON a.world_id=w.world_id AND a.point_id=w.point_id AND a.group_id=w.group_id
                            AND a.member_id=w.member_id AND a.epoch=w.epoch AND a.attempt=w.attempt
                           WHERE w.world_id=?''', (wid,)):
                    hashes = json.loads(work['hashes_json'])
                    action_hash = hashlib.sha256(work['action_bytes']).hexdigest()
                    entry = {'pointId': work['point_id'], 'groupId': work['group_id'], 'memberId': work['member_id'],
                             'epoch': work['epoch'], 'attempt': work['attempt'],
                             'actionBytes': len(work['action_bytes']), 'actionSha256': action_hash,
                             'acceptedActionSha256': hashes['actionContentHash'],
                             'actionBytesMatchAccepted': action_hash == hashes['actionContentHash'],
                             'targetsSha256': hashes['targetsContentHash'],
                             'resultSha256': hashes['resultContentHash']}
                    if work['candidates_json'] is not None:
                        candidates = json.loads(work['candidates_json'])
                        digest = canonical_digest(candidates)
                        entry['candidatesSha256'] = digest
                        entry['acceptedCandidatesSha256'] = hashes['candidatesContentHash']
                        entry['candidatesMatchAccepted'] = digest == hashes['candidatesContentHash']
                    row['work'].append(entry)
                for copy in connection.execute(
                        'SELECT point_id,group_id,target_epoch,source_epoch,source_attempt,manifest_hash,attempt '
                        'FROM world_copy_results WHERE world_id=?', (wid,)):
                    row['copies'].append(dict(copy))
                for roll in connection.execute(
                        'SELECT rule_version,COUNT(*) AS n,SUM(admitted) AS admitted FROM world_rolls WHERE world_id=? GROUP BY rule_version',
                        (wid,)):
                    row['rolls'][roll['rule_version']] = {'count': roll['n'], 'admitted': roll['admitted']}
                row['narrations'] = connection.execute(
                    'SELECT COUNT(*) FROM world_narrations WHERE world_id=?', (wid,)).fetchone()[0]
                lease = connection.execute('SELECT epoch,holder_id,expires_at FROM world_leases WHERE world_id=?', (wid,)).fetchone()
                row['lease'] = dict(lease) if lease else None
                for group in connection.execute('SELECT id,status FROM world_groups WHERE world_id=?', (wid,)):
                    row['groups'][group['id']] = group['status']
                for unit in connection.execute(
                        'SELECT point_id,group_id,ordinal,unit_id,candidates_json,content_hash FROM world_settled_units WHERE world_id=?',
                        (wid,)):
                    row['settledUnits'].append({'pointId': unit['point_id'], 'groupId': unit['group_id'],
                                                'ordinal': unit['ordinal'], 'unitId': unit['unit_id'],
                                                'contentHash': unit['content_hash'],
                                                'recomputedContentHash': canonical_digest(json.loads(unit['candidates_json'])),
                                                'matches': canonical_digest(json.loads(unit['candidates_json'])) == unit['content_hash']})
                worlds[wid] = row
            creations = connection.execute('SELECT COUNT(*),COUNT(DISTINCT world_id) FROM world_creations').fetchone()
        return {'label': label, 'database': db.name, 'worlds': worlds,
                'creations': {'rows': creations[0], 'distinctWorlds': creations[1]}}

    evidence = {'recordedAt': datetime.now(timezone.utc).isoformat(),
                'databases': [dump(OUT / 'positive.db', 'positive'),
                              dump(OUT / 'missing.db', 'missing'),
                              dump(OUT / 'corrupt.db', 'corrupt'),
                              dump(OUT / 'group.db', 'group')]}
    (OUT / 'database-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf8')
    event('database_evidence', databases=len(evidence['databases']),
          worlds=sum(len(d['worlds']) for d in evidence['databases']))
    return evidence


try:
    OUT.mkdir(exist_ok=False)
    assert git('rev-parse', 'HEAD') == PIN, f'checkout is not the pinned commit: {git("rev-parse", "HEAD")}'
    assert not git('status', '--short'), 'worktree must be clean before the run'
    manifest = json.loads((ROOT / 'design/world-protocol/v2/manifest.json').read_text(encoding='utf8'))
    baseline_identity = source_identity()
    event('baseline', head=git('rev-parse', 'HEAD'), pin=PIN, status=git('status', '--short'),
          contractDigest=manifest['contractDigest'], artifacts=len(manifest['artifacts']),
          identity=baseline_identity, python=sys.version.split()[0],
          node=subprocess.check_output(['node', '--version'], text=True).strip())
    database = OUT / 'positive.db'
    start(database)
    phase('main')
    phase('successor')
    state = OUT / 'positive-state.json'
    phase('build-frozen-case', state=state)
    stop()
    stoppedGeneration = generation
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    start(database)
    phase('post-restart', state=state)
    stop()
    event('restart_evidence', sameDatabase='positive.db', databaseBeforeRestartSha256=before,
          persistedState='positive-state.json', restartFromGeneration=stoppedGeneration,
          restartToGeneration=stoppedGeneration + 1)
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
    stop()
    after = source_identity()
    assert not git('status', '--short'), 'worktree changed during the run'
    event('source_unchanged_during_run', identity=after, matchesBaseline=after == baseline_identity)
    database_evidence()
    event('complete', status='PASS_INTEGRATION_H2')
finally:
    stop()
