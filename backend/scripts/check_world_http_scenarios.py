"""A4 fixed-scenario executor: shared traces over real HTTP on the persistent service.

Replays T01 (both samples) literally from the trace templates and T03 (both
samples) behind its authored preamble, against uvicorn and SQLiteBaselineStore.
Expected projections and digests come only from the trace documents; served
responses are never used to build an expectation. A server restart after the
first sample of each trace checks replay-on-read. No browser and no B code,
so a clean checkout only needs Python and the repository.

Two deliberate divergences from the template literals, both how a real client
speaks: requestIds are freshly chosen per step and sample (a pinned literal
would collide across samples in the idempotency ledger), and narration_submit
carries claimToken/generation/issuedAtEpochMilli from the paired claim receipt
(the persistent authority binds claim identity to its issue time; the
templates predate that and bind the context clock). Every response is
validated against its operation's declared success schema. Authored per-step
assertions are checked: only the six registered T01 s1–s4 control
phase/canCompute VALUE mismatches (authored before creation issued the head
gate) are exempted as assertionDrift — any other assertion failure,
including a missing path on those very steps, fails the run. The T03
preview is additionally verified against the independently computed
time-scan state and digest.

Run from the repository root:
    python backend/scripts/check_world_http_scenarios.py
Full exchanges and the server log stay under ignored .local; the report holds
identities and digests only. Use --output to override the report path.
"""
import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from jsonschema import Draft202012Validator
from app.schemas.world.canonical import canonical_digest
from app.schemas.world.v2.projections import request_projection
from app.schemas.world.v2.registry import OPERATION_BY_NAME
from app.schemas.world.v2.trace import TraceDocument
from world_trace_expected import assertion, expected_digest, instantiate, pointer, validate_trace

BASE = ROOT / 'design/world-protocol/v2'
_WIRE_SCHEMA = json.loads((BASE / 'world-protocol.schema.json').read_text(encoding='utf-8'))
_RESPONSE_VALIDATORS = {}


def validate_response(operation, response):
    """The full wire contract of one response, including required envelope
    fields (operation/requestId are required keys of every success schema)."""
    name = OPERATION_BY_NAME[operation].successSchema
    validator = _RESPONSE_VALIDATORS.get(name)
    if validator is None:
        validator = Draft202012Validator(
            {**_WIRE_SCHEMA, '$ref': f'#/$defs/{name}'})
        _RESPONSE_VALIDATORS[name] = validator
    errors = sorted(validator.iter_errors(response), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        raise AssertionError(f'{operation}: response violates {name} at '
                             f'{list(first.path)}: {first.message}')


# Authored trace assertions that the evolved runtime legitimately answers
# differently: T01 s1–s4 predate "creation issues the head gate" (root
# narration pending keeps phase select_actor; once it is ready canCompute
# turns true). Only these value mismatches are drift — anything else,
# including a missing path on these very steps, fails the run.
REGISTERED_DRIFT = frozenset({
    ('T01', 's1', '/control/phase', 'eq'),
    ('T01', 's2', '/control/phase', 'eq'),
    ('T01', 's3', '/control/phase', 'eq'),
    ('T01', 's3', '/control/canCompute', 'eq'),
    ('T01', 's4', '/control/phase', 'eq'),
    ('T01', 's4', '/control/canCompute', 'eq'),
})

HEADERS = {'X-World-Protocol-Version': '2', 'Content-Type': 'application/json'}
IDENTITY_FILES = ['backend/app/world_app.py', 'backend/app/routers/worlds.py',
                  'backend/scripts/check_world_http_scenarios.py']
IDENTITY_FILES += [str(path.relative_to(ROOT)) for path in sorted(
    (ROOT / 'backend/app/services/world').glob('*.py'))]
IDENTITY_FILES += [str(path.relative_to(ROOT)) for path in sorted(
    (ROOT / 'backend/app/database').glob('world_*.py'))]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def source_identity(head_only=False):
    head = subprocess.check_output(
        ['git', '-c', f'safe.directory={ROOT.as_posix()}', 'rev-parse', 'HEAD'],
        cwd=ROOT, text=True).strip()
    if head_only:
        return {'head': head}
    return {'head': head, 'sourceSha256': {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in IDENTITY_FILES}}


class ScenarioService:
    """One uvicorn subprocess on a fixed SQLite path; start/stop is idempotent."""

    def __init__(self, runtime, db_path):
        self.runtime, self.db_path = runtime, db_path
        self.process, self.port, self.log = None, None, None

    def start(self):
        self.port = free_port()
        self.log = (self.runtime / 'server.log').open('a', encoding='utf-8')
        environment = dict(os.environ, WORLD_SQLITE_PATH=str(self.db_path),
                           WORLD_ALLOWED_ORIGINS='http://127.0.0.1:3170')
        self.process = subprocess.Popen([
            sys.executable, '-X', 'utf8', '-m', 'uvicorn',
            'app.world_app:create_persistent_world_app', '--factory',
            '--host', '127.0.0.1', '--port', str(self.port), '--log-level', 'warning'],
            cwd=ROOT / 'backend', env=environment, stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f'persistent service stopped; see {self.runtime / "server.log"}')
            try:
                with urllib.request.urlopen(
                        f'http://127.0.0.1:{self.port}/openapi.json', timeout=1):
                    return
            except OSError:
                time.sleep(0.1)
        self.stop()
        raise RuntimeError('persistent service startup timed out')

    def stop(self):
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        if self.log is not None:
            self.log.close()
            self.log = None

    def call(self, operation, scope, request):
        spec = OPERATION_BY_NAME[operation]
        path_identities = {key: scope.get(key, request.get(key))
                           for key in re.findall(r'\{(\w+)\}', spec.path)}
        url = f'http://127.0.0.1:{self.port}{spec.path.format(**path_identities)}'
        if spec.method in ('GET', 'DELETE'):
            query = [(key, str(request[key]).lower() if isinstance(request[key], bool)
                      else request[key]) for key in spec.queryBindings if key in request]
            if query:
                url += '?' + urllib.parse.urlencode(query)
            payload = None
        else:
            payload = json.dumps(request, ensure_ascii=False).encode('utf-8')
        http = urllib.request.Request(url, data=payload, method=spec.method, headers=HEADERS)
        try:
            with urllib.request.urlopen(http, timeout=60) as response:
                return response.status, json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode('utf-8'))


def replay(service, trace, sample, bindings, steps, label, rid_prefix):
    """Replay trace steps verbatim; returns digests, responses and assertion drift.

    Hard failures: HTTP status, operation/requestId echo, requestHash, capture
    paths, served projections and digests — the integrated results the interface
    baseline agrees on. Authored per-step assertions are also checked, but a
    mismatch is recorded as drift instead of failing: the trace documents an
    S1-era scenario expectation while the runtime legitimately evolved (root
    gate at creation, control TTL), which H1/H2 never asserted live. A
    requestId is client-chosen identity, so each replayed step sends a fresh
    one under rid_prefix instead of the template's pinned literal.
    """
    declarations = {variable.name: variable for variable in trace.variables}
    digests, responses, drift = {}, {}, []
    claim_receipt = None
    for step in steps:
        request = instantiate(step.request, bindings)
        scope = instantiate(step.scope, bindings)
        if 'requestId' in request:
            request['requestId'] = f'{rid_prefix}_{step.id}'
        if step.operation == 'narration_submit':
            # The persistent authority binds a claim to its issue time
            # (token + generation + issuedAtEpochMilli), so a submit carries
            # the paired claim receipt's identity — as every real client does.
            # The trace templates predate that and bind the context clock.
            if claim_receipt is None:
                raise AssertionError(f'{label}/{step.id}: submit without a replayed claim')
            for key in ('claimToken', 'generation', 'issuedAtEpochMilli'):
                request[key] = claim_receipt[key]
        if step.operation == 'narration_claim':
            claim_receipt = None
        status, response = service.call(step.operation, scope, request)
        if status != step.httpStatus:
            raise AssertionError(f'{label}/{step.id}: HTTP {status} != {step.httpStatus}; '
                                 f'body {json.dumps(response, ensure_ascii=False)[:600]}')
        validate_response(step.operation, response)
        if response.get('operation') is not None and response['operation'] != step.operation:
            raise AssertionError(f'{label}/{step.id}: response operation mismatch')
        if request.get('requestId') is not None and response.get('requestId') is not None \
                and response['requestId'] != request['requestId']:
            raise AssertionError(f'{label}/{step.id}: response requestId mismatch')
        if step.responseKind != 'success':
            raise AssertionError(f'{label}/{step.id}: executor handles success steps only')
        if 'requestHash' in response:
            if response['requestHash'] != canonical_digest(request_projection(step.operation, request)):
                raise AssertionError(f'{label}/{step.id}: served requestHash differs from the '
                                     'instantiated normalized request')
        for capture in step.captures:
            bindings[capture.variable] = pointer(response, capture.path)
        if step.operation == 'narration_claim':
            data = response.get('data') or {}
            claim_receipt = {key: data[key] for key in
                             ('claimToken', 'generation', 'issuedAtEpochMilli')}
        for item in step.assertions:
            try:
                assertion(response, item, bindings)
            except (ValueError, KeyError) as error:
                registered = ((trace.scenario, step.id, item.path, item.op)
                              in REGISTERED_DRIFT)
                value_mismatch = str(error) == f'{item.op} assertion failed: {item.path}'
                if not (registered and value_mismatch):
                    raise AssertionError(
                        f'{label}/{step.id}: assertion {item.op} {item.path} failed '
                        f'(registered exemption: {registered}): {error}') from error
                drift.append({'step': step.id, 'operation': step.operation,
                              'assertion': item.op, 'path': item.path,
                              'detail': str(error)})
        if step.expectedProjection is not None:
            expected, digest = expected_digest(step.expectedProjection, declarations, bindings)
            served_state = pointer(response, step.projectionPath)
            served_digest = pointer(response, step.digestPath)
            if served_state != expected:
                raise AssertionError(f'{label}/{step.id}: served state differs from the '
                                     'independent expected projection')
            if served_digest != digest:
                raise AssertionError(f'{label}/{step.id}: served state digest differs from the '
                                     f'independent expected digest ({served_digest} != {digest})')
            # The trace's own golden digests pin the authored placeholder
            # bindings and stay an offline validate_trace concern; live
            # identities differ by design.
            digests[step.id] = digest
        responses[step.id] = response
    return digests, responses, drift


def replay_read(service, bindings, read_step, golden_digest, label):
    """After a restart, one read must return the identical committed digest."""
    request = instantiate(read_step.request, bindings)
    scope = instantiate(read_step.scope, bindings)
    status, response = service.call(read_step.operation, scope, request)
    if status != read_step.httpStatus:
        raise AssertionError(f'{label}: HTTP {status} after restart')
    served_digest = pointer(response, read_step.digestPath)
    if served_digest != golden_digest:
        raise AssertionError(f'{label}: state digest changed across restart '
                             f'({served_digest} != {golden_digest})')
    return served_digest


def load_trace(name):
    raw = json.loads((BASE / 'traces' / f'{name}.json').read_text(encoding='utf-8'))
    validate_trace(raw)
    return raw, TraceDocument.model_validate(raw)


def run_t01(service, trace, sample):
    bindings = {name: value for name, value in sample.values.items()
                if {variable.name: variable for variable in trace.variables}[name].origin == 'input'}
    digests, responses, drift = replay(service, trace, sample, bindings, trace.steps,
                                       f'T01/{sample.id}', f'req_A4_T01_{sample.id}')
    return {'sample': sample.id, 'worldId': responses['s1']['data']['worldId'],
            'steps': len(trace.steps), 'stateDigests': digests,
            'finalDigest': digests['s21'], 'bindings': bindings, 'drift': drift}


def t03_preamble(service, t01_raw, trace, sample):
    """The authored T03 preamble: world, root narration, ids, advance start.

    Mirrors the canonical driver: the world is the T01 school scenario, the
    root narration is ready, five ids are allocated and start_advance opens
    the round that the trace's get_context then observes.
    """
    counter = 0

    def request_id():
        nonlocal counter
        counter += 1
        return f'req_A4_T03_{sample.id}_{counter}'

    create_step = next(step for step in t01_raw['steps'] if step['id'] == 's1')
    order_step = next(step for step in t01_raw['steps'] if step['id'] == 's5')
    # The school scenario is a shared literal; only the client-chosen
    # requestId distinguishes one sample's world from another's.
    status, created = service.call('create_world', {}, dict(
        create_step['request'], requestId=request_id()))
    assert status == 201, created
    world, root = created['data']['worldId'], created['data']['rootPointId']
    lease = created['data']['lease']
    lease_bind = {'worldId': world, 'leaseToken': lease['leaseToken'],
                  'fenceEpoch': lease['fenceEpoch']}
    scope = {'worldId': world}

    def ready(point_id, text):
        status, claim = service.call('narration_claim', {'worldId': world, 'pointId': point_id}, {
            'protocolVersion': 2, 'requestId': request_id(), **lease_bind,
            'pointId': point_id, 'mode': 'head', 'currentClaim': None})
        assert status == 200, claim
        status, response = service.call('narration_submit', {'worldId': world, 'pointId': point_id}, {
            'protocolVersion': 2, 'requestId': request_id(), **lease_bind, 'pointId': point_id,
            'mode': 'head', 'claimToken': claim['data']['claimToken'],
            'generation': claim['data']['generation'],
            'issuedAtEpochMilli': claim['data']['issuedAtEpochMilli'],
            'outcome': 'ready', 'text': text, 'failureReason': None})
        assert status == 200, response

    ready(root, '纯时间场景的根点。')
    status, allocation = service.call('allocate_ids', scope, {
        'protocolVersion': 2, 'requestId': request_id(), **lease_bind,
        'allocationKey': f'a4_time_{sample.id}',
        'slots': [{'slotKey': kind, 'kind': kind, 'scope': None}
                  for kind in ('advance', 'input', 'round', 'point', 'change')]})
    assert status == 200, allocation
    ids = {entry['slotKey']: entry['id'] for entry in allocation['data']['allocations']}
    status, _ = service.call('checkpoint_start_advance', scope, {
        'protocolVersion': 2, 'requestId': request_id(), **lease_bind,
        'operation': 'start_advance', 'expectedPointId': root, 'expectedVersion': 0,
        'expectedCheckpointRevision': 0, 'advanceId': ids['advance'],
        'inputId': ids['input'], 'roundId': ids['round'],
        'inputText': '等待到中午。', 'order': order_step['request']['order']})
    assert status == 200
    origins = {variable.name: variable.origin for variable in trace.variables}
    bindings = {name: value for name, value in sample.values.items()
                if origins[name] == 'input'}
    bindings.update({'v1': world, 'v10': lease['leaseToken'],
                     'v11': ids['point'], 'v13': ids['change']})
    return bindings


def preview_time_scan(service, trace, bindings, revision, label):
    """The T03 driver's extra preview: stage result before sealing, twice.

    Idempotence only here; the independent correctness check runs in
    run_t03 once the full replay has assembled the bindings.
    """
    begin = next(step for step in trace.steps if step.id == 's2')
    stage = next(step for step in trace.steps if step.id == 's3')
    request = {
        'protocolVersion': 2, 'worldId': bindings['v1'],
        'advanceId': bindings['v5'], 'roundId': bindings['v7'],
        'pointId': bindings['v11'], 'expectedPointId': bindings['v3'],
        'expectedVersion': 0, 'expectedCheckpointRevision': revision,
        'timeAdvance': instantiate(begin.request['timeAdvance'], bindings),
        'settlementGroups': [instantiate(stage.request['candidates'], bindings)],
    }
    status, first = service.call('preview_point', {'worldId': bindings['v1']}, request)
    assert status == 200, first
    status, second = service.call('preview_point', {'worldId': bindings['v1']}, request)
    assert status == 200, second
    if first['data'] != second['data']:
        raise AssertionError(f'{label}: repeated time-scan preview changed')
    return first


def verify_time_scan_preview(trace, sample, bindings, preview, label):
    """The preview must already show the committed time-scan state.

    Independent expectation: the s8 get_state projection instantiated from
    the completed bindings — never from the preview response itself. The
    committed head equals the preview working state because sealing does not
    change state and the narration does not either.
    """
    declarations = {variable.name: variable for variable in trace.variables}
    commit = next(step for step in trace.steps if step.id == 's8')
    expected_state, digest = expected_digest(commit.expectedProjection,
                                             declarations, bindings)
    data = preview['data']
    if data['workingState'] != expected_state:
        raise AssertionError(f'{label}: preview workingState differs from the independent '
                             'expected time-scan state')
    if data['workingStateDigest'] != digest:
        raise AssertionError(f'{label}: preview workingStateDigest differs from the '
                            f'independent expected digest ({data["workingStateDigest"]} '
                            f'!= {digest})')
    return digest


def run_t03(service, t01_raw, trace, sample):
    bindings = t03_preamble(service, t01_raw, trace, sample)
    steps = {step.id: index for index, step in enumerate(trace.steps)}
    split = steps['s3'] + 1
    _, responses, drift_a = replay(service, trace, sample, bindings, trace.steps[:split],
                                   f'T03/{sample.id}', f'req_A4_T03_{sample.id}')
    preview = preview_time_scan(
        service, trace, bindings, responses['s3']['control']['revision'], f'T03/{sample.id}')
    digests, _, drift_b = replay(service, trace, sample, bindings, trace.steps[split:],
                                 f'T03/{sample.id}', f'req_A4_T03_{sample.id}')
    preview_digest = verify_time_scan_preview(trace, sample, bindings, preview,
                                              f'T03/{sample.id}')
    return {'sample': sample.id, 'worldId': bindings['v1'],
            'steps': len(trace.steps), 'stateDigests': digests,
            'finalDigest': digests['s8'], 'previewDigest': preview_digest,
            'bindings': bindings, 'drift': drift_a + drift_b}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'artifacts/world-http-scenarios.json')
    args = parser.parse_args()
    identity_before = source_identity()
    runtime = ROOT / '.local/world-http-scenarios' / uuid.uuid4().hex
    runtime.mkdir(parents=True)
    t01_raw, t01 = load_trace('T01')
    t03_raw, t03 = load_trace('T03')
    service = ScenarioService(runtime, runtime / 'world.sqlite3')
    report_traces = []
    try:
        service.start()
        runs = {}
        for sample in t01.samples:
            runs[f'T01/{sample.id}'] = run_t01(service, t01, sample)
        first_t01 = runs['T01/sample_1']
        service.stop()
        service.start()
        replay_read(service, dict(first_t01['bindings']), t01.steps[-3],
                    first_t01['finalDigest'], 'T01/sample_1 after restart')
        for sample in t03.samples:
            runs[f'T03/{sample.id}'] = run_t03(service, t01_raw, t03, sample)
        first_t03 = runs['T03/sample_1']
        service.stop()
        service.start()
        replay_read(service, dict(first_t03['bindings']),
                    next(step for step in t03.steps if step.id == 's8'),
                    first_t03['finalDigest'], 'T03/sample_1 after restart')
        report_traces = [
            {'trace': name, 'sample': values['sample'], 'worldId': values['worldId'],
             'steps': values['steps'], 'stateDigests': values['stateDigests'],
             'finalStateDigest': values['finalDigest'],
             'assertionDrift': values['drift'],
             **({'previewWorkingStateDigest': values['previewDigest']}
                if 'previewDigest' in values else {})}
            for name, values in runs.items()]
    finally:
        service.stop()
    assert source_identity() == identity_before, 'A source changed during the run'
    drift_count = sum(len(entry['assertionDrift']) for entry in report_traces)
    report = {
        'status': 'PASS',
        'layer': 'real HTTP + SQLite persistent service; no browser, no B code',
        'contractDigest': t01.contractDigest,
        'service': 'create_persistent_world_app; SQLiteBaselineStore; one worker',
        'restarts': 2,
        'restartReplayChecks': ['T01/sample_1 get_state digest unchanged',
                                'T03/sample_1 get_state digest unchanged'],
        'assertionDriftCount': drift_count,
        'assertionDriftNote': 'registered exemptions only: T01 s1-s4 control '
                              'phase/canCompute value mismatches authored before creation '
                              'issued the head gate; every response schema-validated; '
                              'hard checks all passed',
        'traces': report_traces,
        'A': identity_before,
        'sourceUnchangedDuringRun': True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                           encoding='utf-8')
    print(f'PASS: {len(report_traces)} fixed-scenario replays over real HTTP/SQLite '
          f'({len(t01.samples)} T01 + {len(t03.samples)} T03 samples, 2 restarts, '
          f'independent digests matched, {drift_count} authored-assertion drift '
          f'entries reported); {args.output}')


if __name__ == '__main__':
    main()
