"""A3 authority over actual SQLite transactions and the HTTP error surface."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.database.world_store import SQLiteBaselineStore
from app.services.world.control import ServiceRefusal, WorldService
from app.world_app import create_world_app
from tests.test_world_control_service import TIME_ADVANCE, begin_work, initial_template, run_t01_flow
from tests.test_world_http import HttpService


class Clock:
    now = 1_792_617_600_000

    def __call__(self):
        return self.now


def test_missing_head_cache_is_read_only_and_reclaims_a_new_generation(runtime):
    service, clock, path = runtime
    flow = begin_work(service)
    world, point = flow['world_id'], flow['root_id']
    before = service.store.world(world)
    old_claim = before['narrations'][point]['claim']
    with sqlite3.connect(path) as connection:
        connection.execute('DELETE FROM world_narrations WHERE point_id=?', (point,))
    context = service.execute('get_context', {'worldId': world})
    assert context['world']['head']['narrationStatus'] == 'missing'
    assert 'cache_missing' in context['control']['blockedReasons']
    assert not context['control']['canCompute']
    read = service.execute('narration_get', {'worldId': world, 'pointId': point})
    assert read['data']['narrationStatus'] == 'missing' and read['data']['text'] is None
    state = service.execute('get_state', {'worldId': world})['data']
    assert state['stateDigest'] == before['pointStates'][point]['stateDigest']
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT narration_status,generation FROM world_points').fetchone() == ('ready', 1)
        assert connection.execute('SELECT count(*) FROM world_narrations').fetchone() == (0,)
    claim_request = {'protocolVersion': 2, 'requestId': 'repair_cache_claim', 'worldId': world,
        'pointId': point, 'mode': 'head', 'currentClaim': None,
        'leaseToken': flow['lease']['leaseToken'], 'fenceEpoch': flow['lease']['fenceEpoch']}
    reclaimed = service.execute('narration_claim', claim_request)['data']
    assert reclaimed['generation'] == old_claim['generation'] + 1
    old_write = {**claim_request, 'requestId': 'late_missing_cache_submit',
        'claimToken': old_claim['claimToken'], 'generation': old_claim['generation'],
        'issuedAtEpochMilli': old_claim['issuedAtEpochMilli'], 'outcome': 'ready',
        'text': '开学第一天。', 'failureReason': None}
    old_write.pop('currentClaim')
    refusal(service, 'narration_submit', old_write, 'claim_fenced')
    new_write = {**old_write, 'requestId': 'new_cache_submit', 'claimToken': reclaimed['claimToken'],
        'generation': reclaimed['generation'], 'issuedAtEpochMilli': reclaimed['issuedAtEpochMilli']}
    service.execute('narration_submit', new_write)
    after = service.store.world(world)
    assert after['state'] == before['state'] and after['work'] == before['work']
    assert after['control']['revision'] == before['control']['revision']
    assert service.execute('get_context', {'worldId': world})['control']['canCompute']


@pytest.fixture()
def runtime(tmp_path):
    clock = Clock()
    path = tmp_path / 'authority.sqlite'
    store = SQLiteBaselineStore(path, clock=clock)
    service = WorldService(store)
    return service, clock, path


def create(service, request_id='create_authority'):
    return service.execute('create_world', {
        'protocolVersion': 2, 'requestId': request_id, 'initial': initial_template()})


def body(created, request_id, **extra):
    return {'protocolVersion': 2, 'requestId': request_id,
            'worldId': created['data']['worldId'],
            'leaseToken': created['data']['lease']['leaseToken'],
            'fenceEpoch': created['data']['lease']['fenceEpoch'], **extra}


def checkpoint(created, request_id, operation, revision=0, **extra):
    return body(created, request_id, operation=operation,
                expectedPointId=created['data']['rootPointId'], expectedVersion=0,
                expectedCheckpointRevision=revision, **extra)


def claim_body(created, claim, request_id, **extra):
    return body(created, request_id, pointId=created['data']['rootPointId'], mode='head',
                claimToken=claim['claimToken'], generation=claim['generation'],
                issuedAtEpochMilli=claim['issuedAtEpochMilli'], **extra)


def refusal(service, operation, request, expected):
    with pytest.raises(ServiceRefusal) as caught:
        service.execute(operation, request)
    assert caught.value.code == expected


def test_root_transaction_persists_claim_gate_and_random_lease_before_any_claim_call(runtime):
    service, clock, path = runtime
    created = create(service)
    record = service.store.world(created['data']['worldId'])
    claim = record['narrations'][created['data']['rootPointId']]['claim']
    assert claim is not None and claim['generation'] == claim['fenceEpoch'] == 1
    assert created['data']['lease']['expiresAtEpochMilli'] == clock.now + 120_000
    assert claim['expiresAtEpochMilli'] == clock.now + 180_000
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT claim_token,claim_epoch FROM world_points').fetchone() == (
            claim['claimToken'], 1)
        assert db.execute('SELECT token,epoch FROM world_gates').fetchone() == (claim['claimToken'], 1)
    assert 'claimToken' not in str(created)


def test_expired_old_write_refuses_without_changes_but_takeover_and_old_replay_work(runtime):
    service, clock, path = runtime
    created = create(service)
    pause = checkpoint(created, 'pause_before_expiry', 'pause')
    paused = service.execute('checkpoint_pause', pause)
    clock.now += 120_000
    before = service.store.world(created['data']['worldId'])
    refusal(service, 'checkpoint_resume', checkpoint(
        created, 'expired_resume', 'resume', revision=1), 'lease_invalid')
    assert service.store.world(created['data']['worldId']) == before
    takeover = service.execute('lease_acquire', {
        'protocolVersion': 2, 'requestId': 'takeover', 'worldId': created['data']['worldId'],
        'holderId': 'second_tab'})
    assert takeover['data']['fenceEpoch'] == 2
    refusal(service, 'checkpoint_resume', checkpoint(
        created, 'old_resume_after_takeover', 'resume', revision=1), 'stale_epoch')
    replay = service.execute('checkpoint_pause', pause)
    assert replay['replayed'] is True and replay['data'] == paused['data']
    assert replay['world']['lease']['fenceEpoch'] == 2


def test_release_restart_and_reacquire_preserve_strict_epoch_monotonicity(runtime):
    service, clock, path = runtime
    created = create(service)
    current = created['data']['lease']
    for epoch in (2, 3, 4):
        service.execute('lease_release', {**body(created, f'release_{epoch}'), **{key: current[key] for key in ('leaseToken', 'fenceEpoch')}})
        service = WorldService(SQLiteBaselineStore(path, clock=clock))
        grant = service.execute('lease_acquire', {
            'protocolVersion': 2, 'requestId': f'acquire_{epoch}',
            'worldId': created['data']['worldId'], 'holderId': 'next_tab'})['data']
        assert grant['fenceEpoch'] == epoch
        current = {key: grant[key] for key in ('leaseToken', 'fenceEpoch')}


def test_resume_commits_pause_change_and_expired_gate_without_advancing_world(runtime):
    service, clock, path = runtime
    service.store.claim_ttl_milli = 5_000
    created = create(service)
    service.execute('checkpoint_pause', checkpoint(created, 'pause_pending', 'pause'))
    clock.now += 5_000
    resumed = service.execute('checkpoint_resume', checkpoint(
        created, 'resume_expired', 'resume', revision=1))
    assert resumed['control']['paused'] is False
    assert resumed['control']['revision'] == 2
    assert resumed['control']['gate']['status'] == 'none'
    assert resumed['control']['blockedReasons'] == ['claim_expired']
    assert resumed['control']['canCompute'] is False
    record = WorldService(SQLiteBaselineStore(path, clock=clock)).store.world(created['data']['worldId'])
    assert record['version'] == 0 and record['round'] is None
    assert record['control']['revision'] == 2 and record['_gateBlockedReason'] == 'claim_expired'
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM world_gates').fetchone()[0] == 0


def test_compute_refusal_commits_only_valid_gate_cleanup_not_business_or_success_id(runtime):
    service, clock, path = runtime
    service.store.claim_ttl_milli = 5_000
    created = create(service)
    clock.now += 5_000
    request = checkpoint(created, 'start_after_claim_expiry', 'start_advance',
                         advanceId='advance_1', inputId='input_1', roundId='round_1',
                         inputText='不要推进。', order=['person_a'])
    refusal(service, 'checkpoint_start_advance', request, 'narration_blocked')
    record = service.store.world(created['data']['worldId'])
    assert record['control']['gate']['status'] == 'none'
    assert record['control']['revision'] == 0
    assert record['_gateBlockedReason'] == 'claim_expired'
    assert record['round'] is record['advance'] is None
    assert 'start_after_claim_expiry' not in record['idempotency']
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM world_rounds').fetchone()[0] == 0


@pytest.mark.parametrize('fault,code', [('binding', 'version_mismatch'), ('lease', 'lease_invalid')])
def test_invalid_binding_or_lease_does_not_commit_gate_cleanup(runtime, fault, code):
    service, clock, path = runtime
    service.store.claim_ttl_milli = 5_000
    created = create(service)
    clock.now += 5_000
    request = checkpoint(created, f'invalid_{fault}', 'resume')
    request['expectedVersion' if fault == 'binding' else 'leaseToken'] = (
        1 if fault == 'binding' else 'unknown_token')
    before = service.store.world(created['data']['worldId'])
    refusal(service, 'checkpoint_resume', request, code)
    assert service.store.world(created['data']['worldId']) == before
    assert before['control']['gate']['status'] == 'pending'


def test_claim_identity_and_independent_renewal_are_enforced_in_sql_transaction(runtime):
    service, clock, path = runtime
    created = create(service)
    claim = service.execute('narration_claim', body(created, 'get_root_claim',
        pointId=created['data']['rootPointId'], mode='head', currentClaim=None))['data']
    clock.now += 20_000
    bad = claim_body(created, claim, 'wrong_issue_time')
    bad['issuedAtEpochMilli'] += 1
    before = service.store.world(created['data']['worldId'])
    refusal(service, 'narration_claim_renew', bad, 'claim_fenced')
    assert service.store.world(created['data']['worldId']) == before
    renewed = service.execute('narration_claim_renew', claim_body(created, claim, 'renew_claim'))
    assert renewed['data']['generation'] == claim['generation']
    assert renewed['data']['expiresAtEpochMilli'] == clock.now + 180_000
    assert service.store.world(created['data']['worldId'])['lease']['expiresAtEpochMilli'] == (
        created['data']['lease']['expiresAtEpochMilli'])
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT expires_at FROM world_gates').fetchone()[0] == clock.now + 180_000


def test_claim_response_replay_never_returns_secret_and_late_failure_cannot_mutate(runtime):
    service, clock, path = runtime
    service.store.claim_ttl_milli = 5_000
    created = create(service)
    claim_request = body(created, 'claim_original', pointId=created['data']['rootPointId'],
                         mode='head', currentClaim=None)
    claim = service.execute('narration_claim', claim_request)['data']
    clock.now += 5_000
    replay = service.execute('narration_claim', claim_request)
    assert replay['replayed'] and 'claimToken' not in replay['data']
    next_claim = service.execute('narration_claim', {**claim_request, 'requestId': 'claim_next'})['data']
    assert next_claim['generation'] == 2
    before = service.store.world(created['data']['worldId'])
    refusal(service, 'narration_submit', claim_body(
        created, claim, 'late_failure', outcome='failed', text=None, failureReason='late'), 'claim_fenced')
    assert service.store.world(created['data']['worldId']) == before


def test_head_cache_delete_atomically_installs_next_generation_claim_and_gate(runtime):
    service, clock, path = runtime
    created = create(service)
    claim = service.execute('narration_claim', body(created, 'delete_claim',
        pointId=created['data']['rootPointId'], mode='head', currentClaim=None))['data']
    service.execute('narration_submit', claim_body(
        created, claim, 'ready_before_delete', outcome='ready', text='缓存', failureReason=None))
    deleted = service.execute('narration_delete', claim_body(created, claim, 'delete_cache'))
    assert deleted['data']['narrationStatus'] == 'missing'
    record = service.store.world(created['data']['worldId'])
    next_claim = record['narrations'][created['data']['rootPointId']]['claim']
    assert next_claim['generation'] == 2 and next_claim['claimToken'] != claim['claimToken']
    assert record['control']['gate']['generation'] == 2
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM world_narrations').fetchone()[0] == 0
        assert db.execute('SELECT token,generation FROM world_gates').fetchone() == (
            next_claim['claimToken'], 2)


def test_http_claim_expiry_resume_reports_actionable_state_with_success_status(runtime):
    service, clock, path = runtime
    service.store.claim_ttl_milli = 5_000
    with TestClient(create_world_app(store=service.store)) as client:
        http = HttpService(client)
        created = create(http)
        http.execute('checkpoint_pause', checkpoint(created, 'http_pause', 'pause'))
        clock.now += 5_000
        resumed = http.execute('checkpoint_resume', checkpoint(created, 'http_resume', 'resume', revision=1))
        assert resumed['control']['paused'] is False
        assert resumed['control']['canCompute'] is False
        assert 'claim_expired' in resumed['control']['blockedReasons']


def test_commit_already_issues_the_new_head_claim_and_gate(runtime):
    service, clock, path = runtime
    flow = run_t01_flow(service)
    record = service.store.world(flow['world_id'])
    entry = record['narrations'][flow['point_id']]
    assert entry['claim']['generation'] == entry['claim']['fenceEpoch'] == 1
    assert record['control']['gate']['generation'] == 1
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT point_id,token FROM world_gates').fetchone() == (
            flow['point_id'], entry['claim']['claimToken'])


def test_recovery_refuses_expired_lease_before_reading_protected_payload(runtime, monkeypatch):
    service, clock, path = runtime
    created = create(service)
    clock.now = created['data']['lease']['expiresAtEpochMilli']

    def must_not_read(*args):
        pytest.fail('expired authority reached the protected recovery payload')

    monkeypatch.setattr(service.store, 'recovery_view', must_not_read)
    refusal(service, 'get_context', {
        'worldId': created['data']['worldId'], 'includeRecovery': True,
        **created['data']['lease']}, 'lease_invalid')


def test_recovery_reads_authority_and_payload_inside_one_sql_transaction(runtime, monkeypatch):
    service, clock, path = runtime
    created = create(service)
    original = service.store.recovery_view

    def require_same_snapshot(record, work_view):
        assert service.store._local.connection.in_transaction
        assert record.clock_milli() == clock.now
        return original(record, work_view)

    monkeypatch.setattr(service.store, 'recovery_view', require_same_snapshot)
    response = service.execute('get_context', {
        'worldId': created['data']['worldId'], 'includeRecovery': True,
        'leaseToken': created['data']['lease']['leaseToken'],
        'fenceEpoch': created['data']['lease']['fenceEpoch']})
    assert response['recovery']['fenceEpoch'] == 1
    assert response['recovery']['current'] is response['recovery']['successor'] is None


def test_preview_ready_cache_survives_old_claim_and_lease_expiry(runtime):
    service, clock, path = runtime
    flow = begin_work(service)
    clock.now += 180_000
    response = service.execute('preview_point', {
        'protocolVersion': 2, 'worldId': flow['world_id'], 'advanceId': flow['advance_id'],
        'roundId': flow['round_id'], 'pointId': flow['point_id'],
        'expectedPointId': flow['root_id'], 'expectedVersion': 0,
        'expectedCheckpointRevision': flow['revision'], 'timeAdvance': TIME_ADVANCE,
        'settlementGroups': []})
    assert response['operation'] == 'preview_point'
    assert response['control']['canCompute'] is False
    assert response['control']['blockedReasons'] == ['lease_invalid']


def test_preview_refuses_expired_missing_head_without_mutating_anything(runtime):
    service, clock, path = runtime
    service.store.claim_ttl_milli = 5_000
    flow = begin_work(service)
    record = service.store.world(flow['world_id'])
    claim = record['narrations'][flow['root_id']]['claim']
    service.execute('narration_delete', {
        'protocolVersion': 2, 'requestId': 'delete_before_preview', 'worldId': flow['world_id'],
        'pointId': flow['root_id'], 'mode': 'head', **{key: flow['lease'][key] for key in ('leaseToken', 'fenceEpoch')},
        'claimToken': claim['claimToken'], 'generation': claim['generation'],
        'issuedAtEpochMilli': claim['issuedAtEpochMilli']})
    clock.now += 5_000
    before = service.store.world(flow['world_id'])
    refusal(service, 'preview_point', {
        'protocolVersion': 2, 'worldId': flow['world_id'], 'advanceId': flow['advance_id'],
        'roundId': flow['round_id'], 'pointId': flow['point_id'],
        'expectedPointId': flow['root_id'], 'expectedVersion': 0,
        'expectedCheckpointRevision': flow['revision'], 'timeAdvance': TIME_ADVANCE,
        'settlementGroups': []}, 'narration_blocked')
    assert service.store.world(flow['world_id']) == before
