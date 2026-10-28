"""A-side real-time TTL evidence: no clock injection, no advancing.

The service is the documented persistent entry (store default real-time
clock), and this script never supplies a clock. Three independent worlds
run one shared wall-clock window, each walking the three agreed paths in
order:

  renew+reacquire while alive  -> lease_renew extends the TTL and a
                                  matching narration_claim re-acquire
                                  returns the same claim identity;
  expired claim refused        -> narration_submit with the expired
                                  claim's receipt identity is refused
                                  claim_expired while the lease is still
                                  alive (a second renewal keeps it so);
  takeover after real expiry   -> lease_acquire succeeds only after the
                                  renewed lease has genuinely expired,
                                  fenceEpoch moves monotonically, a write
                                  with the stale lease is refused
                                  stale_epoch, and the expired claim
                                  turns claim_fenced once the epoch has
                                  moved.

Deadlines come from server-issued expiresAtEpochMilli values plus a fixed
margin; the script only sleeps and records wall-clock deltas. Repetitions
share the wait window, so the whole run costs roughly one lease lifetime
plus one claim lifetime of real time.

Run from the repository root:
    python backend/scripts/check_world_ttl_realtime.py
Report default: artifacts/world-ttl-realtime.json (identities and wall
times only; server log and exchanges stay under ignored .local).
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend/scripts'))
import check_world_http_scenarios as base

MARGIN_MILLI = 3_000
REPETITIONS = 3
IDENTITY_FILES = [*base.IDENTITY_FILES,
                  'backend/scripts/check_world_ttl_realtime.py']


def now_milli():
    return int(time.time_ns() // 1_000_000)


def source_identity():
    head = subprocess.check_output(
        ['git', '-c', f'safe.directory={ROOT.as_posix()}', 'rev-parse', 'HEAD'],
        cwd=ROOT, text=True).strip()
    return {'head': head, 'sourceSha256': {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in IDENTITY_FILES}}


class Repetition:
    """One world walking the three paths against real deadlines."""

    def __init__(self, index, service, create_request):
        self.index = index
        self.service = service
        self.counter = 0
        self.world_id = None
        self.scope = None
        self.root = None
        self.lease = None
        self.claim = None
        self.claim_expired = None
        self.lease_renewals = []
        self.events = []
        self.outcome = None
        self.step_index = 0
        self.create_request = dict(create_request)
        self.steps = [
            ('create', self._create, lambda: True),
            ('claim', self._claim, lambda: self.world_id is not None),
            ('renew_and_reacquire', self._renew_and_reacquire,
             lambda: self.claim is not None),
            ('renew_again', self._renew_again,
             lambda: self.claim is not None
             and now_milli() >= self.lease['expiresAtEpochMilli'] - 6_000),
            ('expired_claim_refused', self._expired_claim,
             lambda: len(self.lease_renewals) >= 2
             and now_milli() >= self.claim['expiresAtEpochMilli'] + MARGIN_MILLI),
            ('takeover', self._takeover,
             lambda: self.claim_expired is not None
             and now_milli() >= self.lease['expiresAtEpochMilli'] + MARGIN_MILLI),
        ]

    def request_id_next(self):
        self.counter += 1
        return f'req_ttl_{self.index}_{self.counter}'

    def call(self, operation, scope, request):
        status, response = self.service.call(operation, scope, request)
        self.events.append({
            'requestId': request.get('requestId'), 'operation': operation,
            'clientAtEpochMilli': now_milli(),
            'serverTimeEpochMilli': response.get('serverTimeEpochMilli'),
            'httpStatus': status,
            'refusalCode': (response.get('error') or {}).get('code'),
        })
        return status, response

    def due(self):
        if self.outcome is not None or self.step_index >= len(self.steps):
            return None
        name, action, condition = self.steps[self.step_index]
        return (name, action) if condition() else None

    def run_due(self):
        name, action = self.due()
        action()
        self.step_index += 1
        return name

    # --- steps -----------------------------------------------------------
    def _create(self):
        self.create_request['requestId'] = self.request_id_next()
        status, response = self.call('create_world', {}, self.create_request)
        assert status == 201, response
        self.world_id = response['data']['worldId']
        self.root = response['data']['rootPointId']
        self.lease = response['data']['lease']
        self.scope = {'worldId': self.world_id}

    def _claim(self):
        status, response = self.call('narration_claim', {
            'worldId': self.world_id, 'pointId': self.root}, {
            'protocolVersion': 2, 'requestId': self.request_id_next(),
            'worldId': self.world_id, 'pointId': self.root,
            'mode': 'head', 'currentClaim': None,
            'leaseToken': self.lease['leaseToken'],
            'fenceEpoch': self.lease['fenceEpoch']})
        assert status == 200, response
        self.claim = {key: response['data'][key] for key in
                      ('claimToken', 'generation', 'issuedAtEpochMilli',
                       'fenceEpoch', 'expiresAtEpochMilli')}

    def _renew_and_reacquire(self):
        status, renewed = self.call('lease_renew', self.scope, {
            'protocolVersion': 2, 'requestId': self.request_id_next(),
            'worldId': self.world_id,
            'leaseToken': self.lease['leaseToken'],
            'fenceEpoch': self.lease['fenceEpoch']})
        assert status == 200, renewed
        self.lease_renewals.append({
            'phase': 'alive', 'renewedAtEpochMilli': now_milli(),
            'expiresBefore': self.lease['expiresAtEpochMilli'],
            'expiresAfter': renewed['data']['expiresAtEpochMilli']})
        self.lease = {**self.lease,
                      'expiresAtEpochMilli': renewed['data']['expiresAtEpochMilli']}
        status, reacquired = self.call('narration_claim', {
            'worldId': self.world_id, 'pointId': self.root}, {
            'protocolVersion': 2, 'requestId': self.request_id_next(),
            'worldId': self.world_id, 'pointId': self.root,
            'mode': 'head', 'currentClaim': {
                'claimToken': self.claim['claimToken'],
                'generation': self.claim['generation'],
                'issuedAtEpochMilli': self.claim['issuedAtEpochMilli']},
            'leaseToken': self.lease['leaseToken'],
            'fenceEpoch': self.lease['fenceEpoch']})
        assert status == 200, reacquired
        assert all(reacquired['data'][key] == self.claim[key]
                   for key in ('claimToken', 'generation', 'issuedAtEpochMilli')), \
            're-acquire returned a different claim identity'
        status, allocated = self.call('allocate_ids', self.scope, {
            'protocolVersion': 2, 'requestId': self.request_id_next(),
            'worldId': self.world_id,
            'leaseToken': self.lease['leaseToken'],
            'fenceEpoch': self.lease['fenceEpoch'],
            'allocationKey': f'ttl_{self.index}',
            'slots': [{'slotKey': 'probe', 'kind': 'point', 'scope': None}]})
        assert status == 200, allocated

    def _renew_again(self):
        status, renewed = self.call('lease_renew', self.scope, {
            'protocolVersion': 2, 'requestId': self.request_id_next(),
            'worldId': self.world_id,
            'leaseToken': self.lease['leaseToken'],
            'fenceEpoch': self.lease['fenceEpoch']})
        assert status == 200, renewed
        self.lease_renewals.append({
            'phase': 'pre-claim-expiry', 'renewedAtEpochMilli': now_milli(),
            'expiresBefore': self.lease['expiresAtEpochMilli'],
            'expiresAfter': renewed['data']['expiresAtEpochMilli']})
        self.lease = {**self.lease,
                      'expiresAtEpochMilli': renewed['data']['expiresAtEpochMilli']}

    def _expired_claim(self):
        status, response = self.call('narration_submit', {
            'worldId': self.world_id, 'pointId': self.root}, {
            'protocolVersion': 2, 'requestId': self.request_id_next(),
            'worldId': self.world_id, 'pointId': self.root,
            'mode': 'head', **{key: self.claim[key] for key in
                               ('claimToken', 'generation', 'issuedAtEpochMilli')},
            'outcome': 'ready', 'text': '过期凭证不得提交。',
            'failureReason': None,
            'leaseToken': self.lease['leaseToken'],
            'fenceEpoch': self.lease['fenceEpoch']})
        assert status == 409 and response['error']['code'] == 'claim_expired', response
        self.claim_expired = {
            'code': response['error']['code'],
            'clientAction': response['error']['clientAction'],
            'submittedAtEpochMilli': now_milli(),
            'claimExpiredAtEpochMilli': self.claim['expiresAtEpochMilli'],
            'leaseStillValidUntil': self.lease['expiresAtEpochMilli'],
        }

    def _takeover(self):
        expired_lease = self.lease
        status, acquired = self.call('lease_acquire', self.scope, {
            'protocolVersion': 2, 'requestId': self.request_id_next(),
            'worldId': self.world_id, 'holderId': f'holder_ttl_{self.index}'})
        assert status == 200, acquired
        self.lease = acquired['data']
        assert self.lease['fenceEpoch'] == expired_lease['fenceEpoch'] + 1, acquired
        status, fenced = self.call('allocate_ids', self.scope, {
            'protocolVersion': 2, 'requestId': self.request_id_next(),
            'worldId': self.world_id,
            'leaseToken': expired_lease['leaseToken'],
            'fenceEpoch': expired_lease['fenceEpoch'],
            'allocationKey': f'ttl_stale_{self.index}',
            'slots': [{'slotKey': 'probe', 'kind': 'point', 'scope': None}]})
        assert status == 409 and fenced['error']['code'] == 'stale_epoch', fenced
        stale_write_code = fenced['error']['code']
        status, allocated = self.call('allocate_ids', self.scope, {
            'protocolVersion': 2, 'requestId': self.request_id_next(),
            'worldId': self.world_id,
            'leaseToken': self.lease['leaseToken'],
            'fenceEpoch': self.lease['fenceEpoch'],
            'allocationKey': f'ttl_new_{self.index}',
            'slots': [{'slotKey': 'probe', 'kind': 'point', 'scope': None}]})
        assert status == 200, allocated
        new_write_status = status
        status, fenced_claim = self.call('narration_submit', {
            'worldId': self.world_id, 'pointId': self.root}, {
            'protocolVersion': 2, 'requestId': self.request_id_next(),
            'worldId': self.world_id, 'pointId': self.root,
            'mode': 'head', **{key: self.claim[key] for key in
                               ('claimToken', 'generation', 'issuedAtEpochMilli')},
            'outcome': 'ready', 'text': '接管后旧凭证被围栏。',
            'failureReason': None,
            'leaseToken': self.lease['leaseToken'],
            'fenceEpoch': self.lease['fenceEpoch']})
        assert status == 409 and fenced_claim['error']['code'] == 'claim_fenced', fenced_claim
        self.outcome = {
            'worldId': self.world_id,
            'claimIssued': self.claim,
            'leaseRenewals': self.lease_renewals,
            'expiredClaimRefusal': self.claim_expired,
            'takeover': {
                'fenceEpoch': self.lease['fenceEpoch'],
                'acquiredAtEpochMilli': now_milli(),
                'leaseExpiredAtEpochMilli': expired_lease['expiresAtEpochMilli'],
                'staleLeaseWriteCode': stale_write_code,
                'newLeaseWriteOk': new_write_status == 200,
                'expiredClaimAfterTakeover': fenced_claim['error']['code'],
            },
            'events': self.events,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'artifacts/world-ttl-realtime.json')
    args = parser.parse_args()
    identity_before = source_identity()
    runtime = ROOT / '.local/world-ttl-realtime' / uuid.uuid4().hex
    runtime.mkdir(parents=True)
    create_request = json.loads(
        (base.BASE / 'fixtures/api/create_world/request.json').read_text(encoding='utf-8'))
    service = base.ScenarioService(runtime, runtime / 'world.sqlite3')
    repetitions = []
    started = now_milli()
    try:
        service.start()
        repetitions = [Repetition(index, service, create_request)
                       for index in range(1, REPETITIONS + 1)]
        while any(rep.outcome is None for rep in repetitions):
            progressed = False
            for rep in repetitions:
                if rep.due() is not None:
                    name = rep.run_due()
                    progressed = True
            if not progressed:
                time.sleep(0.5)
    finally:
        service.stop()
    assert source_identity() == identity_before, 'A source changed during the run'
    finished = now_milli()
    report = {
        'status': 'PASS',
        'layer': 'real wall-clock waits; service clock is the store default, never injected',
        'service': 'create_persistent_world_app; SQLiteBaselineStore; one worker',
        'repetitions': REPETITIONS,
        'waitMarginMilli': MARGIN_MILLI,
        'window': {'startedAtEpochMilli': started, 'finishedAtEpochMilli': finished,
                   'wallSeconds': round((finished - started) / 1000, 1)},
        'paths': ['renew+reacquire while alive', 'expired claim refused (claim_expired)',
                  'takeover after real expiry (fenceEpoch monotonic, stale write fenced, '
                  'expired claim claim_fenced)'],
        'repetitions_detail': [rep.outcome for rep in repetitions],
        'A': identity_before,
        'sourceUnchangedDuringRun': True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                           encoding='utf-8')
    print(f"PASS: {REPETITIONS} repetitions x 3 TTL paths over real wall-clock "
          f"({report['window']['wallSeconds']}s window, no clock injection); {args.output}")


if __name__ == '__main__':
    main()
