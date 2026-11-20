"""A3 current work is restored from SQL, with terminal history retained."""
import json
import sqlite3

import pytest

from app.database.world_repository import LedgerMismatch
from app.database.world_store import SQLiteBaselineStore, _load
from app.services.world.control import WorldService
from tests.test_world_control_service import (
    ORDER, _payload, begin_work, run_t01_flow, single_group,
)
from tests.test_world_sqlite_store import reopen


def discover(path,*,clock=None):
    service = reopen(path,clock=clock)
    flow = begin_work(service)
    request = _payload('discover', flow['world_id'], flow['lease'], operation='discover_group',
                       expectedPointId=flow['root_id'], expectedVersion=0,
                       expectedCheckpointRevision=flow['revision'], pointId=flow['point_id'],
                       groupId=flow['group_id'], initiatorId='person_a',
                       actionText='原文\r\n走向讲台。', targetIds=None)
    service.execute('checkpoint_discover_group', request)
    flow['revision'] += 1
    return service, flow


def staged(path,*,clock=None):
    service, flow = discover(path,clock=clock)
    def checkpoint(name, **fields):
        request = _payload(name, flow['world_id'], flow['lease'], operation=name,
                           expectedPointId=flow['root_id'], expectedVersion=0,
                           expectedCheckpointRevision=flow['revision'], pointId=flow['point_id'],
                           groupId=flow['group_id'], **fields)
        service.execute('checkpoint_' + name, request)
        flow['revision'] += 1
        return request
    checkpoint('extend_group', sourceId='person_a', targets=[], admittedMember=None)
    checkpoint('close_group')
    request = checkpoint('stage_unit', candidates=single_group(['person_a'], ORDER, flow['group_id']),
                         results={'person_a': '结果\r\n已经走上讲台。'})
    return service, flow, request


def test_work_and_originals_are_relational_not_snapshot_fields(tmp_path):
    path = tmp_path / 'world.sqlite'
    service, flow, _ = staged(path)
    work = reopen(path).store.world(flow['world_id'])['work']
    with sqlite3.connect(path) as db:
        snapshot = _load(db.execute('SELECT record_json FROM world_snapshots').fetchone()[0])
        assert 'work' not in snapshot
        assert db.execute('SELECT status,phase FROM world_point_work').fetchone() == ('active', 'select_actor')
        assert db.execute('SELECT status FROM world_groups').fetchone()[0] == 'staged'
        original, results = db.execute('SELECT group_json,results_json FROM world_group_payloads').fetchone()
        assert json.loads(original)['actionTexts']['person_a'].encode() == '原文\r\n走向讲台。'.encode()
        assert json.loads(original)['targetIdsBySource']['person_a'] == []
        assert json.loads(results)['person_a'].encode() == '结果\r\n已经走上讲台。'.encode()
        assert json.loads(db.execute('SELECT candidates_json FROM world_settled_units').fetchone()[0]) == (
            work['units'][0]['candidates'].model_dump(mode='json'))
    assert work['working'].cursor == 1
    assert service.store.world(flow['world_id'])['round']['cursor'] == 0


def test_unconfirmed_targets_remain_distinct_from_confirmed_empty_targets(tmp_path):
    path = tmp_path / 'world.sqlite'
    service, flow = discover(path)
    before = reopen(path).store.world(flow['world_id'])['work']['pendingGroup']
    assert before['targetIdsBySource']['person_a'] is None
    request = _payload('targets', flow['world_id'], flow['lease'], operation='extend_group',
                       expectedPointId=flow['root_id'], expectedVersion=0,
                       expectedCheckpointRevision=flow['revision'], pointId=flow['point_id'],
                       groupId=flow['group_id'], sourceId='person_a', targets=[], admittedMember=None)
    service.execute('checkpoint_extend_group', request)
    after = reopen(path).store.world(flow['world_id'])['work']['pendingGroup']
    assert after['targetIdsBySource']['person_a'] == []


def test_cancel_keeps_abandoned_originals_and_candidates(tmp_path):
    path = tmp_path / 'world.sqlite'
    service, flow, stage = staged(path)
    before = service.store.world(flow['world_id'])
    request = _payload('cancel', flow['world_id'], flow['lease'], operation='cancel',
                       advanceId=flow['advance_id'], roundId=flow['round_id'], expectedPointId=flow['root_id'],
                       expectedVersion=0, expectedCheckpointRevision=flow['revision'],
                       cancelReason='验收取消')
    service.execute('round_conclusion_cancel', request)
    record = reopen(path).store.world(flow['world_id'])
    assert record['work'] is None and record['state'] == before['state'] and record['version'] == 0
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status FROM world_point_work').fetchone()[0] == 'abandoned'
        assert db.execute('SELECT status FROM world_groups').fetchone()[0] == 'abandoned'
        assert db.execute('SELECT count(*) FROM world_settled_units').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM world_group_payloads').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM world_work_heads').fetchone()[0] == 0
        assert db.execute('SELECT ended,input_text,intent_status FROM world_advances').fetchone() == (1, None, 'expired')
    assert reopen(path).execute('round_conclusion_cancel', request)['replayed']


def test_commit_preserves_consumed_work_without_reopening_it(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service)
    assert reopen(path).store.world(flow['world_id'])['work'] is None
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status FROM world_point_work').fetchone()[0] == 'consumed'
        assert db.execute('SELECT status FROM world_groups').fetchone()[0] == 'consumed'
        assert db.execute('SELECT count(*) FROM world_group_payloads').fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match='terminal_work_is_final'):
            db.execute("UPDATE world_point_work SET status='active'")


@pytest.mark.parametrize('table,column,value', [
    ('world_group_payloads', 'results_json', '{"person_a":"换掉结果"}'),
    ('world_group_payloads', 'group_json', '{}'),
    ('world_settled_units', 'candidates_json', '{}'),
])
def test_sql_cannot_rewrite_confirmed_payloads(tmp_path, table, column, value):
    path = tmp_path / 'world.sqlite'
    service, flow, _ = staged(path)
    before = service.store.world(flow['world_id'])
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match='is_final'):
            db.execute(f'UPDATE {table} SET {column}=?', (value,))
    assert reopen(path).store.world(flow['world_id']) == before


@pytest.mark.parametrize('statement', [
    'DELETE FROM world_group_payloads',
    'DELETE FROM world_settled_units',
    'DELETE FROM world_work_heads',
    'DELETE FROM world_work_details',
    "UPDATE world_groups SET status='closed'",
    "UPDATE world_point_work SET progress_json='{}'",
])
def test_missing_or_corrupt_active_work_blocks_read(tmp_path, statement):
    path = tmp_path / 'world.sqlite'
    service, flow, _ = staged(path)
    with sqlite3.connect(path) as db:
        db.execute(statement)
    with pytest.raises((LedgerMismatch, ValueError)):
        reopen(path).store.world(flow['world_id'])


@pytest.mark.parametrize('table', ['world_settled_units', 'world_group_payloads', 'world_point_work',
                                 'world_work_details', 'world_groups'])
def test_stage_sql_failure_rolls_back_group_working_and_replay(tmp_path, table):
    path = tmp_path / 'world.sqlite'
    service, flow = discover(path)
    for name, fields in [('extend_group', dict(sourceId='person_a', targets=[], admittedMember=None)),
                          ('close_group', {})]:
        service.execute('checkpoint_' + name, _payload(name, flow['world_id'], flow['lease'],
            operation=name, expectedPointId=flow['root_id'], expectedVersion=0,
            expectedCheckpointRevision=flow['revision'], pointId=flow['point_id'], groupId=flow['group_id'], **fields))
        flow['revision'] += 1
    request = _payload('stage', flow['world_id'], flow['lease'], operation='stage_unit',
        expectedPointId=flow['root_id'], expectedVersion=0, expectedCheckpointRevision=flow['revision'],
        pointId=flow['point_id'], groupId=flow['group_id'],
        candidates=single_group(['person_a'], ORDER, flow['group_id']), results={'person_a': '走上讲台。'})
    before = service.store.world(flow['world_id'])
    event = 'INSERT' if table == 'world_settled_units' else 'UPDATE'
    with sqlite3.connect(path) as db:
        db.execute(f"CREATE TRIGGER fail BEFORE {event} ON {table} BEGIN SELECT RAISE(ABORT,'stage fault'); END")
    with pytest.raises(sqlite3.IntegrityError, match='stage fault'):
        service.execute('checkpoint_stage_unit', request)
    assert reopen(path).store.world(flow['world_id']) == before
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM world_settled_units').fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM world_submissions WHERE operation='checkpoint_stage_unit'").fetchone()[0] == 0
        db.execute('DROP TRIGGER fail')
    assert not reopen(path).execute('checkpoint_stage_unit', request)['replayed']


def test_sealed_time_corruption_is_detected_by_prefix_digest(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service, commit=False)
    before = service.store.world(flow['world_id'])
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match='locked|is_final'):
            db.execute('UPDATE world_point_work SET time_json=?',
                       (json.dumps({'boundary': 'elapsed', 'duration': {'amount': 9, 'unit': 'second'}}),))
    assert reopen(path).store.world(flow['world_id']) == before
    # Simulate damage outside the application write path in a disposable DB.
    # The read-time prefix check must still detect it even without SQL guards.
    with sqlite3.connect(path) as db:
        db.execute('DROP TRIGGER sealed_work_content_final')
        db.execute('DROP TRIGGER locked_work_time_final')
        db.execute('UPDATE world_point_work SET time_json=?',
                   (json.dumps({'boundary': 'elapsed', 'duration': {'amount': 9, 'unit': 'second'}}),))
    with pytest.raises(LedgerMismatch, match='prefix digest'):
        reopen(path).store.world(flow['world_id'])


@pytest.mark.parametrize('field', ['action', 'targets'])
def test_confirmed_group_evidence_cannot_be_rewritten_by_store_handler(tmp_path, field):
    path = tmp_path / 'world.sqlite'
    service, flow = discover(path)
    if field == 'targets':
        service.execute('checkpoint_extend_group', _payload('targets', flow['world_id'], flow['lease'],
            operation='extend_group', expectedPointId=flow['root_id'], expectedVersion=0,
            expectedCheckpointRevision=flow['revision'], pointId=flow['point_id'],
            groupId=flow['group_id'], sourceId='person_a', targets=[], admittedMember=None))
    before = service.store.world(flow['world_id'])
    def rewrite(record):
        group = record['work']['pendingGroup']
        if field == 'action':
            group['actionTexts']['person_a'] = '换成另一个行动。'
        else:
            group['targetIdsBySource']['person_a'] = ['person_b']
    with pytest.raises(LedgerMismatch, match='Confirmed action'):
        service.store.transact(flow['world_id'], rewrite)
    assert reopen(path).store.world(flow['world_id']) == before


def test_deleting_work_and_pointer_together_does_not_look_like_no_work(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = begin_work(service)
    with sqlite3.connect(path) as db:
        db.execute('DELETE FROM world_work_heads')
        db.execute('DELETE FROM world_work_details')
        db.execute('DELETE FROM world_point_work')
    with pytest.raises(LedgerMismatch, match='bound active point'):
        reopen(path).store.world(flow['world_id'])


def test_core_only_nonempty_database_requires_explicit_work_migration(tmp_path):
    path = tmp_path / 'world.sqlite'
    service, flow = discover(path)
    with sqlite3.connect(path) as db:
        original = db.execute('SELECT record_json FROM world_snapshots').fetchone()[0]
        db.execute('DROP TABLE world_work_schema')
    with pytest.raises(ValueError, match='explicit work migration'):
        SQLiteBaselineStore(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT record_json FROM world_snapshots').fetchone()[0] == original
        assert db.execute('SELECT count(*) FROM world_point_work').fetchone()[0] == 1


def test_cancel_sql_failure_preserves_active_work_input_and_originals(tmp_path):
    path = tmp_path / 'world.sqlite'
    service, flow, _ = staged(path)
    before = service.store.world(flow['world_id'])
    request = _payload('cancel', flow['world_id'], flow['lease'], operation='cancel',
        advanceId=flow['advance_id'], roundId=flow['round_id'], expectedPointId=flow['root_id'],
        expectedVersion=0, expectedCheckpointRevision=flow['revision'], cancelReason='验收取消')
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER fail BEFORE DELETE ON world_work_heads BEGIN SELECT RAISE(ABORT,'cancel fault'); END")
    with pytest.raises(sqlite3.IntegrityError, match='cancel fault'):
        service.execute('round_conclusion_cancel', request)
    assert reopen(path).store.world(flow['world_id']) == before
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT ended,input_text FROM world_advances').fetchone() == (0, '走进教室。')
        assert db.execute('SELECT status FROM world_groups').fetchone()[0] == 'staged'
        db.execute('DROP TRIGGER fail')
    assert not reopen(path).execute('round_conclusion_cancel', request)['replayed']
