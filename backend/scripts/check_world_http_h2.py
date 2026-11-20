"""A-owned H2 prerequisite: real B HTTP transport, reload and SQLite restart.

This deliberately does not certify B's refresh/takeover controller or close
H2. It uses a fixed trace driver, B's unmodified HTTP transport, Chromium and
the real persistent service. A complete B recovery client is a separate gate.
Full responses and credentials stay under ignored .local; the console prints
only a concise verdict. No standalone report is produced.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.schemas.world.canonical import canonical_digest
from app.schemas.world.v2.trace import TraceDocument
from world_trace_expected import expected_digest, instantiate, validate_trace


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def stop(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def source_identity(root, files):
    head = subprocess.check_output(
        ['git', '-c', f'safe.directory={root.as_posix()}', 'rev-parse', 'HEAD'],
        cwd=root, text=True).strip()
    return {'head': head, 'sourceSha256': {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}}


def verify(trace, result):
    """Independent hand-authored T01 answers; never apply the served deltas."""
    declarations = {variable.name: variable for variable in trace.variables}
    for actual in result['samples']:
        bindings = actual['bindings']
        served = actual['served']
        projection = next(step.expectedProjection for step in trace.steps if step.id == 's21')
        expected_state, digest = expected_digest(projection, declarations, bindings)
        assert served['s21']['data']['state'] == expected_state
        assert served['s21']['data']['stateDigest'] == digest
        assert served['s18']['data']['stateDigest'] == digest
        assert served['s16']['data']['workingState'] == expected_state
        assert served['s16']['data']['workingStateDigest'] == digest
        point = instantiate(next(step.request for step in trace.steps if step.id == 's18'), bindings)['point']
        assert served['s16']['data']['pointProjection'] == point
        assert served['s16']['data']['pointProjectionDigest'] == canonical_digest(point)
        before, after = actual['frozenBefore'], actual['frozenAfter']
        action = instantiate(next(step.request for step in trace.steps if step.id == 's7'), bindings)['actionText']
        staged = instantiate(next(step.request for step in trace.steps if step.id == 's10'), bindings)
        assert before['members'][0]['actionText'].encode('utf-8') == action.encode('utf-8')
        assert before['members'][0]['resultText'] == staged['results']['person_a']
        assert before['members'][0]['targets'] == []
        assert before['candidates'] == staged['candidates']
        # Accepted source ownership moves on copy; business bytes and hashes do not.
        for field in ('members', 'candidates', 'inputProjectionHash'):
            assert after[field] == before[field], field
        for a, b in zip(before['acceptedSources'], after['acceptedSources']):
            for field in ('actionContentHash', 'targetsContentHash', 'resultContentHash',
                          'candidatesContentHash'):
                assert a[field] == b[field], field
        assert actual['newFenceEpoch'] > actual['oldFenceEpoch']
        assert actual['oldWriteError'] in ('stale_epoch', 'lease_invalid')
        assert actual['replayAfterRestart']
        assert actual['reloadLostJavascriptHeap']
        assert actual['restoredSourceCount'] > 0
        assert actual['finalContext']['world']['head']['version'] == 1
        assert actual['finalContext']['work'] is None
        assert actual['finalContext']['control']['gate']['status'] == 'none'
        assert actual['generationCallsAfterRecovery'] == 0
    return len(result['samples'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-worktree', type=Path, required=True)
    parser.add_argument('--browser-channel', default='chrome')
    args = parser.parse_args()
    browser_root = args.browser_worktree.resolve()
    runtime = ROOT / '.local/world-http-h2' / uuid.uuid4().hex
    runtime.mkdir(parents=True)
    config_path, result_path = runtime / 'config.json', runtime / 'browser-result.json'
    raw = json.loads((ROOT / 'design/world-protocol/v2/traces/T01.json').read_text(encoding='utf-8'))
    validate_trace(raw)
    trace = TraceDocument.model_validate(raw)
    # The page receives requests and capture declarations, never expected
    # response specimens or the independently authored final state projection.
    steps = [{key: step[key] for key in ('id', 'operation', 'scope', 'request', 'captures')}
             for step in raw['steps']]
    a_files = ['backend/app/world_app.py', 'backend/app/routers/worlds.py',
               'backend/app/database/world_storage_v2.sql',
               'backend/scripts/check_world_http_h2.py', 'backend/scripts/world_http_h2_browser.mjs']
    a_files += [str(path.relative_to(ROOT)) for path in sorted(
        (ROOT / 'backend/app/services/world').glob('*.py'))]
    a_files += [str(path.relative_to(ROOT)) for path in sorted(
        (ROOT / 'backend/app/database').glob('world_*.py'))]
    b_files = [f'frontend/src/lib/world-engine/{name}.ts'
               for name in ('http-transport', 'transport', 'protocol', 'types')]
    identities = {'A': source_identity(ROOT, a_files), 'B': source_identity(browser_root, b_files)}
    api_port, browser_port = free_port(), free_port()
    environment = dict(os.environ, WORLD_SQLITE_PATH=str(runtime / 'world.sqlite3'),
                       WORLD_ALLOWED_ORIGINS=f'http://127.0.0.1:{browser_port}')
    config_path.write_text(json.dumps({
        'apiUrl': f'http://127.0.0.1:{api_port}', 'browserPort': browser_port,
        'browserChannel': args.browser_channel, 'steps': steps,
        'samples': [{'id': sample.id, 'values': copy.deepcopy(sample.values)} for sample in trace.samples],
        'runtime': str(runtime),
    }, ensure_ascii=False), encoding='utf-8')
    server = browser = None
    restarts = 0
    with (runtime / 'server.log').open('w', encoding='utf-8') as server_log, \
            (runtime / 'browser.log').open('w', encoding='utf-8') as browser_log:
        def start_server():
            process = subprocess.Popen([
                sys.executable, '-X', 'utf8', '-m', 'uvicorn',
                'app.world_app:create_persistent_world_app', '--factory',
                '--host', '127.0.0.1', '--port', str(api_port), '--log-level', 'warning'],
                cwd=ROOT / 'backend', env=environment, stdout=server_log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f'persistent service stopped; see {runtime / "server.log"}')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{api_port}/openapi.json', timeout=1):
                        return process
                except OSError:
                    time.sleep(0.1)
            stop(process)
            raise RuntimeError('persistent service startup timed out')

        try:
            server = start_server()
            browser = subprocess.Popen([
                shutil.which('node'), str(ROOT / 'backend/scripts/world_http_h2_browser.mjs'),
                str(browser_root), str(config_path), str(result_path), str(runtime / 'vite-cache')],
                cwd=ROOT, stdout=browser_log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 180
            while browser.poll() is None:
                if time.monotonic() > deadline:
                    raise RuntimeError(f'browser probe timed out; see {runtime / "browser.log"}')
                marker = runtime / f'restart-{restarts}.request'
                if marker.exists():
                    stop(server)
                    server = start_server()
                    (runtime / f'restart-{restarts}.ready').write_text('ready', encoding='utf-8')
                    restarts += 1
                time.sleep(0.05)
            if browser.returncode:
                raise RuntimeError(f'browser probe failed; see {runtime / "browser.log"}')
        finally:
            stop(browser)
            stop(server)
    result = json.loads(result_path.read_text(encoding='utf-8'))
    count = verify(trace, result)
    assert restarts == count
    assert source_identity(ROOT, a_files) == identities['A'], 'A source changed during the run'
    assert source_identity(browser_root, b_files) == identities['B'], 'B source changed during the run'
    # Private reproducibility evidence is local only, consistent with server.md.
    (runtime / 'identity.json').write_text(json.dumps(identities, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {count} B-transport/Chromium/SQLite prerequisite flows; '
          f'{restarts} actual server restarts; browser {result["browser"]}; '
          f'B={identities["B"]["head"]}; H2 controller recovery remains a separate gate')


if __name__ == '__main__':
    main()
