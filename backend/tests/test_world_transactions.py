"""Runtime SQLite counterparts of the frozen FC01–FC32 transaction matrix.

Expected refusals and SQL counts are authored here, independently of the
business implementation. Faults abort real statements, not mocked commits.
"""
import copy
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.database.world_store import SQLiteBaselineStore
from app.schemas.world.canonical import canonical_digest
from app.services.world.control import ServiceRefusal, WorldService
from app.world_app import create_world_app
from tests.test_world_authority_integration import (
    Clock, body, checkpoint, claim_body, create, refusal, runtime,
)
from tests.test_world_control_service import (
    ORDER, TIME_ADVANCE, _claim_and_submit, _payload, begin_work,
    initial_template, run_t01_flow, single_group,
)
from tests.test_world_http import HEADERS, HttpService
from tests.test_world_work_store import discover, staged


def _reopen(path, clock):
    return WorldService(SQLiteBaselineStore(path, clock=clock))


def _root_claim(service, created, request_id='get_claim'):
    return service.execute('narration_claim', body(created, request_id,
        pointId=created['data']['rootPointId'], mode='head', currentClaim=None))['data']


def _start(service, created, request_id='start', **overrides):
    allocation = service.execute('allocate_ids', body(created, 'allocate_fc_start',
        allocationKey='fc_start', slots=[{'slotKey': kind, 'kind': kind, 'scope': None}
            for kind in ('advance', 'input', 'round')]))
    ids = {item['slotKey']: item['id'] for item in allocation['data']['allocations']}
    return checkpoint(created, request_id, 'start_advance',
        advanceId=ids['advance'], inputId=ids['input'], roundId=ids['round'],
        inputText='测试输入。', order=ORDER, **overrides)


def _point_request(flow, request_id, operation, **fields):
    return _payload(request_id, flow['world_id'], flow['lease'], operation=operation,
        pointId=flow['point_id'], expectedPointId=flow['root_id'], expectedVersion=0,
        expectedCheckpointRevision=flow['revision'], **fields)


def test_root_creation_atomic(runtime):
    service, clock, path = runtime
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER fc01 BEFORE INSERT ON world_leases BEGIN SELECT RAISE(ABORT,'FC01 after root'); END")
    with pytest.raises(sqlite3.IntegrityError, match='FC01 after root'):
        create(service)
    with sqlite3.connect(path) as db:
        for table in ('worlds', 'world_points', 'world_leases', 'world_gates',
                      'world_snapshots', 'world_creations', 'world_creation_replays'):
            assert db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
        assert db.execute('SELECT sequence FROM world_snapshot_meta').fetchone()[0] == 0
        db.execute('DROP TRIGGER fc01')
    assert create(service)['replayed'] is False


def test_root_response_lost(runtime):
    service, clock, path = runtime
    first = create(service)
    # Discarding the response cannot undo the committed creation.
    second = create(_reopen(path, clock))
    assert second['replayed'] and second['data'] == first['data']
    assert 'claimToken' not in json.dumps(second)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM worlds').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM world_gates').fetchone()[0] == 1


def test_root_ready_guard(runtime):
    service, clock, path = runtime
    created = create(service)
    request = _start(service, created)
    before = service.store.world(created['data']['worldId'])
    refusal(service, 'checkpoint_start_advance', request, 'narration_blocked')
    assert service.store.world(created['data']['worldId']) == before
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM world_advances').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM world_rounds').fetchone()[0] == 0


def test_successful_replay_first(runtime):
    service, clock, path = runtime
    flow = run_t01_flow(service, commit=False)
    accepted = service.execute('commit_point', flow['commit_request'])
    service.execute('lease_release', _payload('fc04_release', flow['world_id'], flow['lease']))
    takeover = service.execute('lease_acquire', {
        'protocolVersion': 2, 'requestId': 'fc04_acquire', 'worldId': flow['world_id'],
        'holderId': 'new_holder'})['data']
    paused = service.execute('checkpoint_pause', _payload(
        'fc04_pause', flow['world_id'], takeover, operation='pause',
        expectedPointId=flow['point_id'], expectedVersion=1,
        expectedCheckpointRevision=flow['revision'] + 1))
    replayed = _reopen(path, clock).execute('commit_point', flow['commit_request'])
    assert replayed['replayed'] and replayed['data'] == accepted['data']
    assert replayed['control'] == paused['control']
    assert replayed['world']['lease']['fenceEpoch'] == 2
    assert 'inputText' not in json.dumps(replayed)
    assert service.store.world(flow['world_id'])['version'] == 1


def test_request_reuse_conflict(runtime):
    service, clock, path = runtime
    created = create(service)
    request = checkpoint(created, 'one_request_id', 'pause')
    service.execute('checkpoint_pause', request)
    before = service.store.world(created['data']['worldId'])
    refusal(service, 'checkpoint_resume', {**request, 'operation': 'resume',
        'expectedCheckpointRevision': 1}, 'request_id_reused')
    assert _reopen(path, clock).store.world(created['data']['worldId']) == before


def test_request_in_progress(runtime):
    service, clock, path = runtime
    created = create(service)
    request = checkpoint(created, 'same_request_after_lock', 'pause')
    service.store.busy_timeout = 0
    with sqlite3.connect(path, isolation_level=None) as owning_transaction:
        owning_transaction.execute('BEGIN IMMEDIATE')
        refusal(service, 'checkpoint_pause', request, 'request_in_progress')
        owning_transaction.rollback()
    result = service.execute('checkpoint_pause', request)
    assert result['requestId'] == request['requestId'] and result['replayed'] is False
    assert service.execute('checkpoint_pause', request)['replayed'] is True


def test_lease_clock_and_fence(runtime):
    service, clock, path = runtime
    flow = begin_work(service)
    request = _point_request(flow, 'expired_discover', 'discover_group',
        groupId=flow['group_id'], initiatorId='person_a', actionText='过期工作不得保存。', targetIds=None)
    clock.now += 120_000
    before = service.store.world(flow['world_id'])
    refusal(service, 'checkpoint_discover_group', request, 'lease_invalid')
    assert service.store.world(flow['world_id']) == before
    service.execute('lease_acquire', {'protocolVersion': 2, 'requestId': 'fc07_takeover',
        'worldId': flow['world_id'], 'holderId': 'second_holder'})
    after = service.store.world(flow['world_id'])
    refusal(service, 'checkpoint_discover_group', request, 'stale_epoch')
    assert service.store.world(flow['world_id']) == after
    assert after['work']['pendingGroup'] is None


def test_gate_cleanup_no_revision(runtime):
    service, clock, path = runtime
    service.store.claim_ttl_milli = 5_000
    created = create(service)
    request = _start(service, created)
    clock.now += 5_000
    refusal(service, 'checkpoint_start_advance', request, 'narration_blocked')
    after = _reopen(path, clock).store.world(created['data']['worldId'])
    assert after['control']['gate']['status'] == 'none'
    assert after['control']['revision'] == 0 and after['_gateBlockedReason'] == 'claim_expired'
    assert after['advance'] is after['round'] is None and 'start' not in after['idempotency']


@pytest.mark.parametrize('change,code', [({'expectedVersion': 1}, 'version_mismatch'),
                                       ({'leaseToken': 'wrong_token'}, 'lease_invalid')])
def test_binding_error_keeps_gate(runtime, change, code):
    service, clock, path = runtime
    service.store.claim_ttl_milli = 5_000
    created = create(service)
    request = _start(service, created)
    clock.now += 5_000
    before = service.store.world(created['data']['worldId'])
    refusal(service, 'checkpoint_start_advance', {**request, **change}, code)
    assert _reopen(path, clock).store.world(created['data']['worldId']) == before


def test_pause_while_pending(runtime):
    service, clock, path = runtime
    created = create(service)
    before = service.store.world(created['data']['worldId'])
    request = checkpoint(created, 'pause_pending', 'pause')
    first = service.execute('checkpoint_pause', request)
    assert first['control']['paused'] and first['control']['revision'] == 1
    assert first['control']['gate'] == before['control']['gate']
    assert first['control']['blockedReasons'] == ['narration_pending', 'paused']
    assert service.execute('checkpoint_pause', request)['replayed']
    repeated = service.execute('checkpoint_pause', checkpoint(created, 'pause_again', 'pause', revision=1))
    assert repeated['control']['revision'] == 1
    assert service.store.world(created['data']['worldId'])['narrations'] == before['narrations']


def test_resume_expired_claim(runtime):
    service, clock, path = runtime
    service.store.claim_ttl_milli = 5_000
    created = create(service)
    service.execute('checkpoint_pause', checkpoint(created, 'pause_for_expiry', 'pause'))
    clock.now += 5_000
    result = service.execute('checkpoint_resume', checkpoint(created, 'resume_expiry', 'resume', revision=1))
    assert result['control']['paused'] is False and result['control']['revision'] == 2
    assert result['control']['gate']['status'] == 'none'
    assert result['control']['blockedReasons'] == ['claim_expired']
    assert result['control']['canCompute'] is False
    assert _reopen(path, clock).store.world(created['data']['worldId'])['control']['paused'] is False


def test_ready_does_not_resume(runtime):
    service, clock, path = runtime
    created = create(service)
    claim = _root_claim(service, created)
    service.execute('checkpoint_pause', checkpoint(created, 'pause_before_ready', 'pause'))
    request = claim_body(created, claim, 'ready_while_paused', outcome='ready',
                         text='原子缓存。', failureReason=None)
    before = service.store.world(created['data']['worldId'])
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER fc12 BEFORE INSERT ON world_narrations BEGIN SELECT RAISE(ABORT,'FC12 cache failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='FC12 cache failure'):
        service.execute('narration_submit', request)
    assert _reopen(path, clock).store.world(created['data']['worldId']) == before
    with sqlite3.connect(path) as db:
        db.execute('DROP TRIGGER fc12')
    ready = service.execute('narration_submit', request)
    assert ready['control']['paused'] is True and ready['control']['revision'] == 1
    assert ready['control']['phase'] == before['control']['phase']
    assert ready['control']['gate']['status'] == 'none'
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT text FROM world_narrations').fetchone()[0] == '原子缓存。'
        assert db.execute('SELECT count(*) FROM world_gates').fetchone()[0] == 0


def test_freeze_action_before_targets(runtime):
    service, clock, path = runtime
    flow = begin_work(service)
    raw = '推开 D。\r\n保留 e\u0301 与 é。'
    request = _point_request(flow, 'freeze_action', 'discover_group', groupId=flow['group_id'],
        initiatorId='person_a', actionText=raw, targetIds=None)
    service.execute('checkpoint_discover_group', request)
    reopened = _reopen(path, clock)
    record = reopened.store.world(flow['world_id'])
    group = record['work']['pendingGroup']
    assert group['actionTexts']['person_a'].encode('utf-8') == raw.encode('utf-8')
    assert group['targetIdsBySource']['person_a'] is None
    assert reopened.execute('checkpoint_discover_group', request)['replayed']
    refusal(reopened, 'checkpoint_discover_group', {**request, 'requestId': 'replace_action',
        'expectedCheckpointRevision': flow['revision'] + 1, 'actionText': '不同的新行动。'}, 'phase_invalid')
    assert reopened.store.world(flow['world_id']) == record


def test_roll_before_expansion(tmp_path):
    from tests.test_world_judgments import fixture
    flow = fixture(tmp_path, result=15)
    first = flow['service'].execute('create_rolls', flow['request'])['data']['rolls'][0]
    restarted = WorldService(SQLiteBaselineStore(flow['path']))
    retry = restarted.execute('create_rolls', {**flow['request'], 'requestId': 'recover_roll'})
    assert retry['data']['rolls'][0] == first
    assert len(flow['calls']) == 1
    assert (first['result'], first['eligible'], first['admitted']) == (15, True, True)
    assert restarted.store.world(flow['world'])['work']['pendingGroup']['memberIds'] == ['person_a']
    with sqlite3.connect(flow['path']) as db:
        assert db.execute('SELECT result,eligible,admitted FROM world_rolls').fetchall() == [(15, 1, 1)]


def test_stage_before_next_actor(tmp_path):
    path = tmp_path / 'stage-prefix.sqlite'
    service, flow, stage = staged(path)
    restarted = WorldService(SQLiteBaselineStore(path))
    record = restarted.store.world(flow['world_id'])
    assert record['round']['cursor'] == 0 and record['round']['actedIds'] == []
    assert record['work']['working'].cursor == 1
    assert record['work']['units'][0]['results'] == {'person_a': '结果\r\n已经走上讲台。'}
    assert record['work']['units'][0]['candidates'] == stage['candidates']
    result = restarted.execute('get_context', {'worldId': flow['world_id'], 'includeRecovery': True,
        'leaseToken': flow['lease']['leaseToken'], 'fenceEpoch': flow['lease']['fenceEpoch']})
    assert result['recovery']['current']['groups'][0]['candidates'] == stage['candidates'].model_dump(mode='json')
    assert result['world']['round']['cursor'] == 0


def test_stage_response_lost(tmp_path):
    path = tmp_path / 'stage-replay.sqlite'
    service, flow, request = staged(path)
    before = service.store.world(flow['world_id'])
    replayed = WorldService(SQLiteBaselineStore(path)).execute('checkpoint_stage_unit', request)
    assert replayed['replayed'] and replayed['data']['unitId'] == before['work']['units'][0]['unitId']
    assert service.store.world(flow['world_id']) == before
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM world_settled_units').fetchone()[0] == 1


def test_cancel_terminal(tmp_path):
    path = tmp_path / 'cancel-terminal.sqlite'
    service, flow, stage = staged(path)
    before = service.store.world(flow['world_id'])
    request = _payload('cancel_terminal', flow['world_id'], flow['lease'], operation='cancel',
        advanceId=flow['advance_id'], roundId=flow['round_id'], expectedPointId=flow['root_id'],
        expectedVersion=0, expectedCheckpointRevision=flow['revision'], cancelReason='显式废弃。')
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER fc26 BEFORE DELETE ON world_work_heads BEGIN SELECT RAISE(ABORT,'FC26 pointer failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='FC26 pointer failure'):
        service.execute('round_conclusion_cancel', request)
    assert WorldService(SQLiteBaselineStore(path)).store.world(flow['world_id']) == before
    with sqlite3.connect(path) as db:
        db.execute('DROP TRIGGER fc26')
    service.execute('round_conclusion_cancel', request)
    record = service.store.world(flow['world_id'])
    assert record['work'] is None and record['advance'] is None and record['state'] == before['state']
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status FROM world_point_work').fetchone()[0] == 'abandoned'
        assert db.execute('SELECT status FROM world_groups').fetchone()[0] == 'abandoned'
        assert db.execute('SELECT input_text,ended FROM world_advances').fetchone() == (None, 1)
    assert service.execute('round_conclusion_cancel', request)['replayed']
    assert service.execute('checkpoint_stage_unit', stage)['replayed']
    assert service.store.world(flow['world_id'])['work'] is None


def test_conclusion_atomic(runtime, tmp_path):
    service, clock, path = runtime
    flow = run_t01_flow(service)
    _claim_and_submit(service, flow['world_id'], flow['lease'], flow['point_id'], 'fc27_ready', '已就绪。')
    allocated = service.execute('allocate_ids', _payload('fc27_alloc', flow['world_id'], flow['lease'],
        allocationKey='fc27_round', slots=[{'slotKey': 'next', 'kind': 'round', 'scope': None}]))
    next_round = allocated['data']['allocations'][0]['id']
    request = _payload('fc27_continue', flow['world_id'], flow['lease'], operation='conclude',
        advanceId=flow['advance_id'], roundId=flow['round_id'], expectedPointId=flow['point_id'], expectedVersion=1,
        expectedCheckpointRevision=flow['revision'], conclusion={
            'kind': 'continue', 'closedBy': 'model', 'cancelReason': None,
            'candidateCharacterIds': ['person_a'], 'nextRoundId': next_round})
    before = service.store.world(flow['world_id'])
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER fc27 BEFORE INSERT ON world_rounds WHEN NEW.trigger='automatic' BEGIN SELECT RAISE(ABORT,'FC27 successor failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='FC27 successor failure'):
        service.execute('round_conclusion_conclude', request)
    assert _reopen(path, clock).store.world(flow['world_id']) == before
    with sqlite3.connect(path) as db:
        db.execute('DROP TRIGGER fc27')
    first = service.execute('round_conclusion_conclude', request)
    assert first['world']['round']['roundId'] == next_round
    assert service.execute('round_conclusion_conclude', request)['replayed']
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM world_rounds').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM world_points').fetchone()[0] == 2
    other = WorldService(SQLiteBaselineStore(tmp_path / 'handback.sqlite', clock=clock))
    other_flow = run_t01_flow(other)
    _claim_and_submit(other, other_flow['world_id'], other_flow['lease'], other_flow['point_id'], 'handback_ready', '就绪。')
    handback = _payload('fc27_handback', other_flow['world_id'], other_flow['lease'], operation='conclude',
        advanceId=other_flow['advance_id'], roundId=other_flow['round_id'], expectedPointId=other_flow['point_id'], expectedVersion=1,
        expectedCheckpointRevision=other_flow['revision'],
        conclusion={'kind': 'handback', 'closedBy': 'model', 'cancelReason': None})
    other.execute('round_conclusion_conclude', handback)
    ended = other.store.world(other_flow['world_id'])
    assert ended['advance'] is None and ended['control']['phase'] == 'complete'
    with sqlite3.connect(other.store.path) as db:
        assert db.execute('SELECT input_text,ended FROM world_advances').fetchone() == (None, 1)


def test_claim_renew_takeover(runtime):
    service, clock, path = runtime
    created = create(service)
    claim = _root_claim(service, created)
    clock.now += 20_000
    lease = service.execute('lease_renew', body(created, 'fc28_lease_renew'))['data']
    renewed = service.execute('narration_claim_renew', claim_body(created, claim, 'fc28_claim_renew'))['data']
    assert renewed['generation'] == claim['generation']
    assert renewed['issuedAtEpochMilli'] == claim['issuedAtEpochMilli']
    clock.now = lease['expiresAtEpochMilli']
    takeover = service.execute('lease_acquire', {'protocolVersion': 2, 'requestId': 'fc28_takeover',
        'worldId': created['data']['worldId'], 'holderId': 'next_holder'})['data']
    new_created = copy.deepcopy(created)
    new_created['data']['lease'] = takeover
    fresh = _root_claim(service, new_created, 'fc28_new_claim')
    assert fresh['generation'] == claim['generation'] + 1 and fresh['fenceEpoch'] == 2
    assert fresh['claimToken'] != claim['claimToken']
    before = service.store.world(created['data']['worldId'])
    refusal(service, 'narration_submit', claim_body(created, claim, 'fc28_late',
        outcome='ready', text='迟到旧文本。', failureReason=None), 'stale_epoch')
    assert _reopen(path, clock).store.world(created['data']['worldId']) == before


def test_cache_missing_old_generation(runtime):
    service, clock, path = runtime
    created = create(service)
    claim = _root_claim(service, created)
    service.execute('narration_submit', claim_body(created, claim, 'fc29_ready',
        outcome='ready', text='旧缓存。', failureReason=None))
    before = service.store.world(created['data']['worldId'])
    service.execute('narration_delete', claim_body(created, claim, 'fc29_delete'))
    fresh = _root_claim(service, created, 'fc29_regenerate')
    assert fresh['generation'] == 2 and fresh['claimToken'] != claim['claimToken']
    refusal(service, 'narration_submit', claim_body(created, claim, 'fc29_late',
        outcome='ready', text='旧缓存迟到。', failureReason=None), 'claim_fenced')
    service.execute('narration_submit', claim_body(created, fresh, 'fc29_new_ready',
        outcome='ready', text='新缓存。', failureReason=None))
    after = service.store.world(created['data']['worldId'])
    assert after['state'] == before['state'] and after['version'] == before['version'] == 0
    assert after['control']['revision'] == before['control']['revision'] == 0
    assert after['narrations'][created['data']['rootPointId']]['text'] == '新缓存。'


def test_pure_time_full_scan(runtime):
    service, clock, path = runtime
    flow = begin_work(service)
    allocated = service.execute('allocate_ids', _payload('fc30_change', flow['world_id'], flow['lease'],
        allocationKey='fc30', slots=[{'slotKey': 'personality', 'kind': 'change', 'scope': flow['point_id']}]))
    change_id = allocated['data']['allocations'][0]['id']
    scan = single_group([], ORDER, None, tasksAchieved={'person_a': ['task_a_root']},
        personalityCoverageIds=ORDER, personalities={'person_a': [{
            'id': change_id, 'text': '完成任务后更加沉着。', 'supersedes': []}]},
        sanities={'person_a': 17})
    request = _point_request(flow, 'fc30_scan', 'stage_time_scan', candidates=scan)
    service.execute('checkpoint_stage_time_scan', request)
    flow['revision'] += 1
    recovered = _reopen(path, clock).store.world(flow['world_id'])
    assert recovered['work']['timeScan'] == scan and recovered['work']['units'] == []
    assert recovered['work']['working'].intentStatus == 'pending'
    preview = service.execute('preview_point', {
        'protocolVersion': 2, 'worldId': flow['world_id'], 'advanceId': flow['advance_id'],
        'roundId': flow['round_id'], 'pointId': flow['point_id'], 'expectedPointId': flow['root_id'],
        'expectedVersion': 0, 'expectedCheckpointRevision': flow['revision'],
        'timeAdvance': TIME_ADVANCE, 'settlementGroups': [scan]})
    service.execute('checkpoint_seal_point', _point_request(flow, 'fc30_seal', 'seal_point'))
    flow['revision'] += 1
    commit = _payload('fc30_commit', flow['world_id'], flow['lease'], advanceId=flow['advance_id'],
        roundId=flow['round_id'], pointId=flow['point_id'], expectedPointId=flow['root_id'], expectedVersion=0,
        expectedCheckpointRevision=flow['revision'], point=preview['data']['pointProjection'], settlementGroups=[])
    service.execute('commit_point', commit)
    record = _reopen(path, clock).store.world(flow['world_id'])
    assert record['state'].characters['person_a'].sanity == 17
    assert record['round']['actedIds'] == [] and record['advance']['intentStatus'] == 'pending'
    assert service.store.replay_state(flow['world_id'], flow['point_id']) == record['state']


def test_preview_budget(runtime, monkeypatch):
    service, clock, path = runtime
    flow = begin_work(service)
    request = {'protocolVersion': 2, 'worldId': flow['world_id'], 'advanceId': flow['advance_id'],
        'roundId': flow['round_id'], 'pointId': flow['point_id'], 'expectedPointId': flow['root_id'],
        'expectedVersion': 0, 'expectedCheckpointRevision': flow['revision'],
        'timeAdvance': TIME_ADVANCE, 'settlementGroups': []}
    before = service.store.world(flow['world_id'])
    refusal(service, 'preview_point', {**request, 'settlementGroups': [single_group(
        ['person_a'], ORDER, 'same_group').model_dump(mode='json')] * 33}, 'preview_budget_exceeded')
    measured = iter([0.0, 2.001])
    monkeypatch.setattr(service.store, '_preview_clock', lambda: next(measured), raising=False)
    refusal(service, 'preview_point', request, 'preview_budget_exceeded')
    monkeypatch.delattr(service.store, '_preview_clock')
    with TestClient(create_world_app(store=service.store)) as client:
        raw = json.dumps(request).encode('utf-8')
        padded = raw + b' ' * (512 * 1024 - len(raw))
        url = f'/worlds/{flow["world_id"]}/preview'
        assert client.post(url, headers=HEADERS, content=padded).status_code == 200
        rejected = client.post(url, headers=HEADERS, content=padded + b' ')
        assert rejected.status_code == 413 and rejected.json()['error']['details']['limit'] == 'request'
        accepted = client.post(url, headers=HEADERS, json=request)
        from app.services.world import preview as preview_module
        monkeypatch.setattr(preview_module, 'PREVIEW_RESPONSE_LIMIT', len(accepted.content) - 1)
        rejected = client.post(url, headers=HEADERS, json=request)
        assert rejected.status_code == 413 and rejected.json()['error']['details']['limit'] == 'response'
    assert service.store.world(flow['world_id']) == before


def test_consume_only_point_groups(tmp_path):
    # FC17 interrupts the real promotion statement after the new point/state
    # writes. The detailed probe also checks both active groups survive rollback.
    from tests.test_world_successor import (
        test_promotion_sql_failure_rolls_back_predecessor_state_and_preserves_reserved_group,
        test_consume_only_predecessor_groups_and_promote_saved_successor_atomically,
    )
    interrupted = tmp_path / 'interrupted'
    interrupted.mkdir()
    test_promotion_sql_failure_rolls_back_predecessor_state_and_preserves_reserved_group(interrupted)
    completed = tmp_path / 'completed'
    completed.mkdir()
    test_consume_only_predecessor_groups_and_promote_saved_successor_atomically(completed)


def test_current_epoch_max(tmp_path, runtime):
    from tests.test_world_recovery import test_visibility_filters_current_epoch_before_considering_attempts
    test_visibility_filters_current_epoch_before_considering_attempts(tmp_path)
    # The SQL view scopes epochs; the service separately rejects an expired
    # authority even before ownership has moved to another epoch.
    service, clock, path = runtime
    flow = begin_work(service)
    clock.now += 120_000
    refusal(service, 'get_context', {'worldId': flow['world_id'], 'includeRecovery': True,
        'leaseToken': flow['lease']['leaseToken'], 'fenceEpoch': 1}, 'lease_invalid')


def test_restore_original_bytes(tmp_path):
    from tests.test_world_recovery import (
        test_sql_copy_fault_rolls_back_all_accepted_payload_and_result_rows,
        test_takeover_hides_all_bytes_until_controlled_copy_then_preserves_original_sources,
    )
    for table in ('world_accepted_work', 'world_frozen_work', 'world_copy_results'):
        folder = tmp_path / table
        folder.mkdir()
        test_sql_copy_fault_rolls_back_all_accepted_payload_and_result_rows(folder, table)
    verified = tmp_path / 'verified'
    verified.mkdir()
    test_takeover_hides_all_bytes_until_controlled_copy_then_preserves_original_sources(verified)


def test_restore_bad_source(tmp_path):
    from tests.test_world_recovery import test_copy_never_accepts_client_reconstructed_or_unreferenced_sources
    for change in ('member', 'hash', 'group', 'point'):
        folder = tmp_path / change
        folder.mkdir()
        test_copy_never_accepts_client_reconstructed_or_unreferenced_sources(folder, change)


def test_restore_missing_or_corrupt(tmp_path):
    from tests.test_world_recovery import test_old_source_fault_preserves_metadata_and_explicitly_blocks_copy
    for fault in ('missing', 'action', 'result', 'candidates', 'targets'):
        folder = tmp_path / fault
        folder.mkdir()
        test_old_source_fault_preserves_metadata_and_explicitly_blocks_copy(
            folder, fault, 'frozen_work_missing' if fault == 'missing' else 'frozen_work_corrupt')


def test_restore_attempt_allocation(tmp_path):
    service, flow, _ = staged(tmp_path / 'attempts.sqlite', clock=Clock())
    world = flow['world_id']
    lease = flow['lease']
    attempts = []
    original_bytes = None
    for owner in ('second', 'third'):
        service.execute('lease_release', _payload('release_' + owner, world, lease))
        lease = service.execute('lease_acquire', {
            'protocolVersion': 2, 'requestId': 'acquire_' + owner,
            'worldId': world, 'holderId': owner})['data']
        context = service.execute('get_context', {**_payload('read', world, lease), 'includeRecovery': True})
        source = context['recovery']['current']['restoreSources'][0]
        request = _payload('copy_' + owner, world, lease, operation='restore_group_work',
            expectedPointId=context['world']['head']['pointId'], expectedVersion=0,
            expectedCheckpointRevision=context['control']['revision'], **source)
        refusal(service, 'checkpoint_restore_group_work', {**request, 'attempt': 999}, 'request_malformed')
        result = service.execute('checkpoint_restore_group_work', request)
        attempts.append(result['data']['attempt'])
        recovered = service.execute('get_context', {**_payload('read', world, lease), 'includeRecovery': True})
        frozen = recovered['recovery']['current']['groups']
        if original_bytes is None:
            original_bytes = frozen
        else:
            assert frozen == original_bytes
    assert attempts[0] > 0 and attempts[1] > attempts[0]


def test_restore_business_dedup(tmp_path):
    from tests.test_world_recovery import test_concurrent_copies_allocate_one_attempt_inside_sqlite_transaction
    test_concurrent_copies_allocate_one_attempt_inside_sqlite_transaction(tmp_path)


@pytest.mark.parametrize('confirmation', ['action', 'targets', 'skip', 'scan', 'roll'])
def test_time_lock(tmp_path, confirmation):
    if confirmation == 'roll':
        from tests.test_world_judgments import fixture
        scenario = fixture(tmp_path)
        service, world = scenario['service'], scenario['world']
        service.execute('create_rolls', scenario['request'])
    else:
        service = WorldService(SQLiteBaselineStore(tmp_path / 'time-lock.sqlite'))
        flow = begin_work(service)
        world = flow['world_id']
        if confirmation in ('action', 'targets'):
            service.execute('checkpoint_discover_group', _point_request(flow, 'confirm', 'discover_group',
                groupId=flow['group_id'], initiatorId='person_a', actionText='锁定时间。',
                targetIds=[] if confirmation == 'targets' else None))
        elif confirmation == 'skip':
            service.execute('checkpoint_record_skip', _point_request(flow, 'confirm', 'record_skip',
                slotActorId='person_a'))
        else:
            service.execute('checkpoint_stage_time_scan', _point_request(flow, 'confirm', 'stage_time_scan',
                candidates=single_group([], ORDER, None)))
    before = service.store.world(world)
    assert before['work']['timeLocked']
    lease = before['lease']
    request = _payload('change_locked_time', world, lease, operation='set_point_time',
        pointId=before['work']['pointId'], expectedPointId=before['headPointId'], expectedVersion=0,
        expectedCheckpointRevision=before['control']['revision'],
        timeAdvance={'boundary': 'elapsed', 'duration': {'amount': 99, 'unit': 'second'}})
    refusal(service, 'checkpoint_set_point_time', request, 'point_time_locked')
    assert service.store.world(world) == before
    def corrupt_baseline(record):
        record['work']['baseline']['stateDigest'] = '0' * 64
    with pytest.raises(ValueError):
        service.store.transact(world, corrupt_baseline)
    assert service.store.world(world) == before


def test_successor_prefix(tmp_path):
    from tests.test_world_successor import test_successor_prefix_binding_corruption_cannot_promote_or_commit
    for fault in ('prefix', 'version', 'state', 'time', 'predecessor'):
        folder = tmp_path / fault
        folder.mkdir()
        test_successor_prefix_binding_corruption_cannot_promote_or_commit(folder, fault)


def test_reference_retention_gc(tmp_path):
    from tests.test_world_recovery import test_active_references_survive_gc_and_terminal_sources_stop_being_restorable
    test_active_references_survive_gc_and_terminal_sources_stop_being_restorable(tmp_path)
