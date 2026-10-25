"""A3-1 real SQLite durability, atomic replay and cross-connection tests.

These exercise the A2 service over persistent snapshots, not normalized
storage constraints, real claim TTL or takeover/H2 acceptance.
"""
import copy
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.database.world_store import SQLiteBaselineStore
from app.services.world.control import ServiceRefusal, WorldService
from app.world_app import create_persistent_world_app
from tests.test_world_control_service import initial_template, run_t01_flow


def create_request():
    return {'protocolVersion': 2, 'requestId': 'create', 'initial': initial_template()}


def reopen(path,*,clock=None):
    return WorldService(SQLiteBaselineStore(path,clock=clock))


def test_creation_replay_and_id_sequence_survive_restart(tmp_path):
    path = tmp_path / 'world.sqlite'
    first = reopen(path).execute('create_world', create_request())
    second = reopen(path).execute('create_world', create_request())
    assert second['replayed'] is True
    assert second['data'] == first['data']
    changed = create_request()
    changed['requestId'] = 'another'
    third = reopen(path).execute('create_world', changed)
    assert third['data']['worldId'] != first['data']['worldId']
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM world_snapshots').fetchone()[0] == 2


def test_sealed_work_restart_commit_and_replay(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service, commit=False)
    before = service.store.world(flow['world_id'])
    resumed = reopen(path)
    assert resumed.store.world(flow['world_id']) == before
    assert before['version'] == 0
    assert before['work']['sealed']
    assert before['work']['units'][0]['results'] == {'person_a': '走上了讲台。'}
    assert before['round']['cursor'] == 0
    assert before['work']['working'].cursor == 6
    committed = resumed.execute('commit_point', flow['commit_request'])
    restarted = reopen(path)
    replay = restarted.execute('commit_point', flow['commit_request'])
    assert replay['replayed']
    assert replay['data'] == committed['data']
    record = restarted.store.world(flow['world_id'])
    assert record['version'] == 1
    assert len(record['points']) == 1
    assert record['work'] is None
    assert record['state'] == record['pointStates'][flow['point_id']]['state']
    point = record['points'][flow['point_id']]
    state = restarted.execute('get_state', {'worldId': flow['world_id']})['data']
    assert state['previousPointId'] == flow['root_id']
    assert state['timeAdvance'] == point.timeAdvance.model_dump(mode='json')
    assert state['entityDeltas'] == {key: delta.model_dump(mode='json')
                                   for key, delta in point.entityDeltas.items()}
    assert state['state'] == record['state'].model_dump(mode='json')
    root = restarted.execute('get_state', {'worldId': flow['world_id'], 'point': flow['root_id']})['data']
    assert root['previousPointId'] is None and root['timeAdvance'] is None
    assert root['entityDeltas'] == {}
    restarted.store.collect_garbage(flow['world_id'])
    assert reopen(path).execute('get_state', {'worldId': flow['world_id']})['data'] == state
    # Tuple-key allocations remain usable, not stringified by JSON encoding.
    bucket = next(iter(before['allocations'].values()))
    assert all(isinstance(key, tuple) for key in bucket)


def test_entire_flow_reopens_storage_before_every_operation(tmp_path):
    path = tmp_path / 'world.sqlite'

    class RestartingService:
        persistent = True

        def execute(self, operation, request):
            return reopen(path).execute(operation, request)

    flow = run_t01_flow(RestartingService())
    record = reopen(path).store.world(flow['world_id'])
    assert record['version'] == 1
    assert record['headPointId'] == flow['point_id']
    assert record['advance']['intentStatus'] == 'consumed'


def test_original_text_bytes_are_not_normalized(tmp_path):
    path = tmp_path / 'world.sqlite'
    text = '第一行\r\n第二行\n组合字符 e\u0301 与 é'

    class TextService(WorldService):
        def execute(self, operation, request):
            request = copy.deepcopy(request)
            if operation == 'checkpoint_discover_group':
                request['actionText'] = text
            elif operation == 'checkpoint_stage_unit':
                request['results']['person_a'] = text
            return super().execute(operation, request)

    # Supply originals before confirmation; finalized work must not be edited.
    flow = run_t01_flow(TextService(SQLiteBaselineStore(path)), commit=False)
    original = reopen(path).store.world(flow['world_id'])['work']['units'][0]['results']['person_a']
    assert original.encode('utf-8') == text.encode('utf-8')
    with sqlite3.connect(path) as db:
        import json
        raw = db.execute('SELECT group_json FROM world_group_payloads').fetchone()[0]
        assert json.loads(raw)['actionTexts']['person_a'].encode('utf-8') == text.encode('utf-8')


def test_concurrent_commit_across_stores_applies_once(tmp_path):
    path = tmp_path / 'world.sqlite'
    flow = run_t01_flow(reopen(path), commit=False)
    services = [reopen(path), reopen(path)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda service: service.execute(
            'commit_point', copy.deepcopy(flow['commit_request'])), services))
    assert sorted(result['replayed'] for result in results) == [False, True]
    assert results[0]['data'] == results[1]['data']
    assert reopen(path).store.world(flow['world_id'])['version'] == 1


def test_concurrent_creation_across_stores_creates_once(tmp_path):
    path = tmp_path / 'world.sqlite'
    services = [reopen(path), reopen(path)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda service: service.execute(
            'create_world', create_request()), services))
    assert sorted(result['replayed'] for result in results) == [False, True]
    assert results[0]['data'] == results[1]['data']


def test_sql_commit_failure_rolls_back_world_and_replay_ledger(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service, commit=False)
    before = service.store.world(flow['world_id'])
    with sqlite3.connect(path) as connection:
        connection.execute('''CREATE TRIGGER reject_update AFTER UPDATE ON world_snapshots
                            BEGIN SELECT RAISE(ABORT, 'injected write failure'); END''')
    with pytest.raises(sqlite3.IntegrityError, match='injected write failure'):
        service.execute('commit_point', flow['commit_request'])
    assert reopen(path).store.world(flow['world_id']) == before
    with sqlite3.connect(path) as connection:
        connection.execute('DROP TRIGGER reject_update')
    assert reopen(path).execute('commit_point', flow['commit_request'])['replayed'] is False


def test_sql_creation_failure_rolls_back_world_ids_and_creation_ledger(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    with sqlite3.connect(path) as connection:
        connection.execute('''CREATE TRIGGER reject_replay BEFORE INSERT ON world_creation_replays
                            BEGIN SELECT RAISE(ABORT, 'injected creation failure'); END''')
    with pytest.raises(sqlite3.IntegrityError, match='injected creation failure'):
        service.execute('create_world', create_request())
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM world_snapshots').fetchone()[0] == 0
        assert connection.execute('SELECT sequence FROM world_snapshot_meta').fetchone()[0] == 0
        connection.execute('DROP TRIGGER reject_replay')
    assert reopen(path).execute('create_world', create_request())['replayed'] is False


def test_changed_request_after_restart_is_rejected_without_mutation(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service, commit=False)
    restarted = reopen(path)
    changed = create_request()
    # open_round uses req_create as its original creation ID.
    changed['requestId'] = 'req_create'
    changed['initial']['protagonistId'] = 'person_b'
    before = restarted.store.world(flow['world_id'])
    with pytest.raises(ServiceRefusal) as error:
        restarted.execute('create_world', changed)
    assert error.value.code == 'request_id_reused'
    assert restarted.store.world(flow['world_id']) == before


def test_process_exit_mid_transaction_preserves_previous_record(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service, commit=False)
    before = service.store.world(flow['world_id'])
    script = '''
import os, sys
from app.database.world_store import SQLiteBaselineStore
store = SQLiteBaselineStore(sys.argv[1])
with store.locked():
    store.transact(sys.argv[2], lambda record: record['control'].update(paused=True))
    os._exit(77)
'''
    result = subprocess.run([sys.executable, '-c', script, str(path), flow['world_id']],
                            env=os.environ.copy(), check=False)
    assert result.returncode == 77
    assert reopen(path).store.world(flow['world_id']) == before


def test_http_app_restart_reads_persisted_world(tmp_path, monkeypatch):
    monkeypatch.setenv('WORLD_SQLITE_PATH', str(tmp_path / 'world.sqlite'))
    headers = {'X-World-Protocol-Version': '2'}
    with TestClient(create_persistent_world_app()) as client:
        response = client.post('/worlds', json=create_request(), headers=headers)
        assert response.status_code == 201, response.text
        world_id = response.json()['data']['worldId']
    with TestClient(create_persistent_world_app()) as client:
        response = client.get(f'/worlds/{world_id}/context', headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()['world']['worldId'] == world_id


def test_persistent_factory_requires_explicit_path(monkeypatch):
    monkeypatch.delenv('WORLD_SQLITE_PATH', raising=False)
    with pytest.raises(RuntimeError, match='WORLD_SQLITE_PATH'):
        create_persistent_world_app()


def test_invalid_response_cannot_persist_creation(tmp_path, monkeypatch):
    from pydantic import ValidationError
    from app.services.world import control

    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    original = control.handle_create_world

    def malformed_create(*args):
        record, data = original(*args)
        data['lease']['expiresAtEpochMilli'] = None
        return record, data

    with monkeypatch.context() as patch:
        patch.setattr(control, 'handle_create_world', malformed_create)
        with pytest.raises(ValidationError):
            service.execute('create_world', create_request())
    assert reopen(path).store.global_idempotency() == {}
    assert reopen(path).store.world('world_1') is None
    assert reopen(path).execute('create_world', create_request())['replayed'] is False
