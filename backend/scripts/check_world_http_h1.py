"""Real Chromium/B-controller/HTTP T01 check with independent Python answers.

Run from any directory. Requires B's checkout, its installed frontend packages
and an installed Playwright browser/channel. Child servers are local, isolated
and stopped in finally. Full exchange logs stay under ignored .local; the
shareable report contains identities/digests and source hashes, no credentials.
"""
import argparse
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
from app.schemas.world.contracts import TimelinePoint, WorldState
from app.schemas.world.v2.trace import TraceDocument
from world_trace_expected import expected_digest, instantiate, pointer, validate_trace


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def source_identity(root, files):
    def git(*args):
        return subprocess.check_output(
            ['git', '-c', f'safe.directory={root.as_posix()}', *args], cwd=root,
            text=True, encoding='utf-8').strip()
    return {'head': git('rev-parse', 'HEAD'), 'status': git('status', '--short'),
            'sourceSha256': {path: hashlib.sha256((root / path).read_bytes()).hexdigest()
                             for path in files}}


def verify(trace, actual):
    sample = next(sample for sample in trace.samples if sample.id == actual['id'])
    exchanges = [entry for entry in actual['exchanges'] if not entry.get('repeat')]
    nonpreview = [entry for entry in exchanges if entry['operation'] != 'preview_point']
    steps = [step for step in trace.steps if step.operation != 'preview_point']
    assert [entry['operation'] for entry in nonpreview] == [step.operation for step in steps]
    served = {step.id: entry['response'] for step, entry in zip(steps, nonpreview)}
    previews = [entry['response'] for entry in exchanges if entry['operation'] == 'preview_point']
    assert len(previews) >= 2
    served['s16'] = previews[-1]
    bindings = dict(sample.values)
    for step in trace.steps:
        for capture in step.captures:
            bindings[capture.variable] = pointer(served[step.id], capture.path)
    declarations = {variable.name: variable for variable in trace.variables}
    final_step = next(step for step in trace.steps if step.id == 's21')
    expected_state, digest = expected_digest(final_step.expectedProjection, declarations, bindings)
    # The answers come from the hand-authored projection and captured identities,
    # never from an actual response state/digest or the apply implementation.
    assert served['s21']['data']['state'] == expected_state
    assert served['s21']['data']['stateDigest'] == digest
    assert served['s18']['data']['stateDigest'] == digest
    assert previews[-1]['data']['workingState'] == expected_state
    assert previews[-1]['data']['workingStateDigest'] == digest
    expected_point = instantiate(next(step for step in trace.steps if step.id == 's18').request, bindings)['point']
    expected_point = TimelinePoint.model_validate(expected_point).model_dump(mode='json')
    assert previews[-1]['data']['pointProjection'] == expected_point
    assert previews[-1]['data']['pointProjectionDigest'] == canonical_digest(expected_point)
    begin_expected = json.loads(json.dumps(expected_state))
    for entity_id in expected_point['entityDeltas']:
        begin_expected['characters'][entity_id]['position'] = begin_expected['initial']['characters'][entity_id]['initialPosition']
    assert previews[0]['data']['workingState'] == begin_expected
    assert previews[0]['data']['workingStateDigest'] == canonical_digest(
        WorldState.model_validate(begin_expected).model_dump(mode='json'))
    for call in actual['modelCalls']:
        if call['task'] in ('action', 'targets', 'results', 'updates'):
            assert call['input']['workingState'] == begin_expected
    assert actual['context']['control']['revision'] == 13
    assert actual['context']['world']['round']['cursor'] == 6
    assert [(entry['operation'], entry['code']) for entry in actual['errorChecks']] == [
        ('checkpoint_restore_group_work', 'frozen_work_missing'),
        ('narration_get', 'version_mismatch')]
    return {'sample': sample.id, 'worldId': served['s1']['data']['worldId'],
            'rootPointId': served['s1']['data']['rootPointId'],
            'pointId': served['s18']['data']['pointId'], 'version': 1,
            'checkpointRevision': 13, 'stateDigest': digest,
            'pointProjectionDigest': canonical_digest(expected_point),
            'httpExchanges': len(actual['exchanges']),
            'modelCalls': [call['task'] for call in actual['modelCalls']],
            'browserErrorChecks': actual['errorChecks'],
            'repeatedPreviewCount': sum(bool(entry.get('repeat')) for entry in actual['exchanges'])}


def verify_time(trace, actual):
    sample = next(sample for sample in trace.samples if sample.id == actual['id'])
    served = actual['served']
    bindings = dict(sample.values)
    for step in trace.steps:
        for capture in step.captures:
            bindings[capture.variable] = pointer(served[step.id], capture.path)
    identities = dict(actual['identityBindings'])
    for variable in trace.variables:
        if variable.origin == 'input' and variable.kind == 'identity':
            bindings[variable.name] = identities.get(bindings[variable.name], bindings[variable.name])
    expected_state, digest = expected_digest(
        next(step for step in trace.steps if step.id == 's8').expectedProjection,
        {variable.name: variable for variable in trace.variables}, bindings)
    assert served['s8']['data']['state'] == expected_state
    assert served['s8']['data']['stateDigest'] == digest
    assert served['s5']['data']['stateDigest'] == digest
    assert served['preview']['data']['workingState'] == expected_state
    assert served['preview']['data']['workingStateDigest'] == digest
    assert served['s5']['world']['advance']['intentStatus'] == 'pending'
    return {'sample': sample.id, 'worldId': served['s8']['world']['worldId'],
            'pointId': served['s8']['data']['pointId'], 'stateDigest': digest,
            'validatedFields': ['task status', 'personality sourcePointId', 'sanity', 'time'],
            'layer': 'browser HTTP transport; direct fixed-candidate harness'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-worktree', type=Path, required=True)
    parser.add_argument('--browser-channel', default='msedge')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/world-http-h1.json')
    args = parser.parse_args()
    browser_root = args.browser_worktree.resolve()
    a_files = ['backend/app/routers/worlds.py', 'backend/app/world_app.py',
               'backend/app/services/world/control.py',
               'backend/scripts/check_world_http_h1.py', 'backend/scripts/world_http_h1_browser.mjs']
    b_files = [f'frontend/src/lib/world-engine/{name}.ts'
               for name in ('controller', 'schedule', 'http-transport', 'protocol')]
    a_source, b_source = source_identity(ROOT, a_files), source_identity(browser_root, b_files)
    api_port, browser_port = port(), port()
    runtime = ROOT / '.local/world-http-h1' / uuid.uuid4().hex
    runtime.mkdir(parents=True)
    config_path, result_path = runtime / 'config.json', runtime / 'browser-result.json'
    raw = json.loads((ROOT / 'design/world-protocol/v2/traces/T01.json').read_text(encoding='utf-8'))
    validate_trace(raw)
    trace = TraceDocument.model_validate(raw)
    time_raw = json.loads((ROOT / 'design/world-protocol/v2/traces/T03.json').read_text(encoding='utf-8'))
    validate_trace(time_raw)
    time_trace = TraceDocument.model_validate(time_raw)
    config_path.write_text(json.dumps({
        'apiUrl': f'http://127.0.0.1:{api_port}', 'browserPort': browser_port,
        'browserChannel': args.browser_channel,
        'samples': [{'id': sample.id, 'requests': {
            step.id: instantiate(step.request, sample.values) for step in trace.steps}}
                    for sample in trace.samples],
        'timeSamples': [{'id': sample.id, 'requests': {
            step.id: instantiate(step.request, sample.values) for step in time_trace.steps}}
                        for sample in time_trace.samples],
    }, ensure_ascii=False), encoding='utf-8')
    environment = dict(os.environ, WORLD_ALLOWED_ORIGINS=f'http://127.0.0.1:{browser_port}')
    server = None
    with (runtime / 'server.log').open('w', encoding='utf-8') as log:
        try:
            server = subprocess.Popen([
                sys.executable, '-X', 'utf8', '-m', 'uvicorn',
                'app.world_app:create_world_app', '--factory', '--host', '127.0.0.1',
                '--port', str(api_port), '--log-level', 'warning'], cwd=ROOT / 'backend',
                env=environment, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            deadline = time.monotonic() + 30
            while True:
                if server.poll() is not None:
                    raise RuntimeError(f'fixture service stopped; see {runtime / "server.log"}')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{api_port}/openapi.json', timeout=1):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        raise RuntimeError('fixture service startup timed out')
                    time.sleep(0.1)
            subprocess.run([shutil.which('node'), str(ROOT / 'backend/scripts/world_http_h1_browser.mjs'),
                            str(browser_root), str(config_path), str(result_path), str(runtime / 'vite-cache')],
                           cwd=ROOT, check=True, timeout=180)
        finally:
            if server is not None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
    result = json.loads(result_path.read_text(encoding='utf-8'))
    checks = [verify(trace, actual) for actual in result['results']['normal']]
    time_checks = [verify_time(time_trace, actual) for actual in result['results']['time']]
    assert source_identity(ROOT, a_files)['sourceSha256'] == a_source['sourceSha256']
    assert source_identity(browser_root, b_files)['sourceSha256'] == b_source['sourceSha256']
    report = {'status': 'PASS', 'layer': 'local browser/controller/HTTP; review pending',
              'contractDigest': trace.contractDigest, 'browser': result['browser'],
              'apiUrl': f'http://127.0.0.1:{api_port}',
              'browserOrigin': f'http://127.0.0.1:{browser_port}',
              'store': 'FixtureBaselineStore; one worker; no SQLite',
              'fetchConfiguration': 'native window.fetch.bind(window); B default receiver bug remains',
              'A': a_source, 'B': b_source, 'sourceUnchangedDuringRun': True,
              'checks': checks, 'timeScanChecks': time_checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {len(checks)} browser H1 flows + {len(time_checks)} time-scan HTTP flows; '
          f'independent state/point digests; {args.output}')


if __name__ == '__main__':
    main()
