"""A3-2 core ledger transactions; work-copy/TTL/H2 remain separate gates."""
import json
import sqlite3
from pathlib import Path

import pytest

from app.database.world_repository import LedgerMismatch
from app.database.world_store import SQLiteBaselineStore, _dump
from tests.test_world_control_service import _claim_and_submit, _payload, run_t01_flow
from tests.test_world_sqlite_store import create_request, reopen


def test_packaged_schema_matches_frozen_specification():
    root = Path(__file__).resolve().parents[2]
    assert (root / 'backend/app/database/world_storage_v2.sql').read_bytes() == (
        root / 'design/world-protocol/v2/storage-contract.sql').read_bytes()


def test_core_tables_and_foreign_keys_after_real_flow(tmp_path):
    path = tmp_path / 'world.sqlite'
    flow = run_t01_flow(reopen(path))
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('SELECT version,revision,active_point_id FROM worlds').fetchone() == (
            1, flow['revision'], flow['point_id'])
        assert db.execute('SELECT count(*) FROM world_points').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM world_state_checkpoints').fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM world_submissions WHERE operation='commit_point'").fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM world_creations').fetchone()[0] == 1


@pytest.mark.parametrize('statement', [
    "CREATE TRIGGER fail BEFORE INSERT ON world_points WHEN NEW.kind='normal' BEGIN SELECT RAISE(ABORT,'fault'); END",
    "CREATE TRIGGER fail BEFORE INSERT ON world_state_checkpoints WHEN NEW.point_id<>'root_3' BEGIN SELECT RAISE(ABORT,'fault'); END",
    "CREATE TRIGGER fail AFTER UPDATE ON world_rounds BEGIN SELECT RAISE(ABORT,'fault'); END",
    "CREATE TRIGGER fail BEFORE INSERT ON world_submissions WHEN NEW.operation='commit_point' BEGIN SELECT RAISE(ABORT,'fault'); END",
    "CREATE TRIGGER fail AFTER UPDATE ON worlds BEGIN SELECT RAISE(ABORT,'fault'); END",
])
def test_core_write_failures_roll_back_point_progress_cache_and_replay(tmp_path, statement):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service, commit=False)
    before = service.store.world(flow['world_id'])
    # Bind the trigger to the dynamically generated root, not a guessed ID.
    statement = statement.replace('root_3', flow['root_id'])
    with sqlite3.connect(path) as db:
        db.execute(statement)
    with pytest.raises(sqlite3.IntegrityError, match='fault'):
        service.execute('commit_point', flow['commit_request'])
    assert reopen(path).store.world(flow['world_id']) == before
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM world_points').fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM world_submissions WHERE operation='commit_point'").fetchone()[0] == 0
        assert db.execute('SELECT version FROM worlds').fetchone()[0] == 0
        db.execute('DROP TRIGGER fail')
    assert reopen(path).execute('commit_point', flow['commit_request'])['replayed'] is False


def test_completed_round_and_ended_input_survive_handback(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service)
    _claim_and_submit(service, flow['world_id'], flow['lease'], flow['point_id'], 'ready', '已经抵达。')
    request = _payload('handback', flow['world_id'], flow['lease'], operation='conclude',
                       advanceId='advance_1', roundId='round_1',
                       expectedPointId=flow['point_id'], expectedVersion=1,
                       expectedCheckpointRevision=flow['revision'],
                       conclusion={'kind': 'handback', 'closedBy': 'model', 'cancelReason': None})
    service.execute('round_conclusion_conclude', request)
    assert reopen(path).execute('round_conclusion_conclude', request)['replayed']
    with sqlite3.connect(path) as db:
        phase, conclusion = db.execute('SELECT phase,conclusion_json FROM world_rounds').fetchone()
        assert phase == 'complete'
        assert json.loads(conclusion)['kind'] == 'handback'
        assert db.execute('SELECT ended,input_text,intent_status FROM world_advances').fetchone() == (
            1, None, 'consumed')


def test_automatic_round_preserves_completed_predecessor(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service)
    _claim_and_submit(service, flow['world_id'], flow['lease'], flow['point_id'], 'ready', '准备继续。')
    request = _payload('continue', flow['world_id'], flow['lease'], operation='conclude',
                       advanceId='advance_1', roundId='round_1',
                       expectedPointId=flow['point_id'], expectedVersion=1,
                       expectedCheckpointRevision=flow['revision'], conclusion={
                           'kind': 'continue', 'closedBy': 'model', 'cancelReason': None,
                           'candidateCharacterIds': ['person_b'], 'nextRoundId': 'round_2'})
    service.execute('round_conclusion_conclude', request)
    assert reopen(path).execute('round_conclusion_conclude', request)['replayed']
    with sqlite3.connect(path) as db:
        rows = db.execute('SELECT id,phase,trigger,conclusion_json FROM world_rounds ORDER BY id').fetchall()
        assert rows[0][:3] == ('round_1', 'complete', 'player')
        assert json.loads(rows[0][3])['nextRoundId'] == 'round_2'
        assert rows[1] == ('round_2', 'select_actor', 'automatic', None)


def test_replay_reads_initial_and_deltas_without_any_snapshot_or_cache(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service)
    expected = service.store.world(flow['world_id'])['state']
    with sqlite3.connect(path) as db:
        db.execute('DELETE FROM world_snapshots')
        db.execute('DELETE FROM world_state_checkpoints')
    assert SQLiteBaselineStore(path).replay_state(flow['world_id'], flow['point_id']) == expected


@pytest.mark.parametrize('statement', [
    'UPDATE worlds SET revision=revision+1',
    "UPDATE world_leases SET token='corrupt'",
    "UPDATE world_state_checkpoints SET state_digest=printf('%064d',0)",
    "DELETE FROM world_submissions WHERE operation='commit_point'",
    "UPDATE world_points SET delta_json='{}' WHERE kind='normal'",
    'UPDATE world_rounds SET cursor=0',
    "UPDATE world_advances SET input_text='wrong input'",
    "UPDATE world_narrations SET text='wrong narration'",
])
def test_relational_drift_is_not_hidden_by_snapshot(tmp_path, statement):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service)
    if 'delta_json' in statement:
        # T01 has empty deltas; change valid time metadata instead so the
        # corrupt row really differs from the independently retained point.
        statement = "UPDATE world_points SET time_json='{}' WHERE kind='normal'"
    with sqlite3.connect(path) as db:
        db.execute(statement)
    with pytest.raises(LedgerMismatch):
        reopen(path).store.world(flow['world_id'])


@pytest.mark.parametrize('table', ['world_points', 'world_leases', 'world_creations'])
def test_root_creation_sql_fault_rolls_back_every_core_row(tmp_path, table):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    with sqlite3.connect(path) as db:
        db.execute(f"CREATE TRIGGER fail BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'fault'); END")
    with pytest.raises(sqlite3.IntegrityError, match='fault'):
        service.execute('create_world', create_request())
    with sqlite3.connect(path) as db:
        for name in ('worlds', 'world_points', 'world_leases', 'world_state_checkpoints',
                     'world_creations', 'world_snapshots', 'world_creation_replays'):
            assert db.execute(f'SELECT count(*) FROM {name}').fetchone()[0] == 0
        assert db.execute('SELECT sequence FROM world_snapshot_meta').fetchone()[0] == 0
        db.execute('DROP TRIGGER fail')
    assert reopen(path).execute('create_world', create_request())['replayed'] is False


def test_replay_rejects_modified_history_without_using_cached_answer(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service)
    with sqlite3.connect(path) as db:
        db.execute('UPDATE world_points SET time_json=? WHERE kind=?',
                   (json.dumps({'boundary': 'elapsed', 'duration': {'amount': 20, 'unit': 'second'}}),
                    'normal'))
    with pytest.raises(LedgerMismatch, match='Replayed state'):
        service.store.replay_state(flow['world_id'], flow['point_id'])


def test_invalid_head_version_rolls_back_even_when_sql_field_is_in_range(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service)
    before = service.store.world(flow['world_id'])
    with pytest.raises(LedgerMismatch, match='sequence'):
        service.store.transact(flow['world_id'], lambda record: record.update(version=999))
    assert reopen(path).store.world(flow['world_id']) == before


def test_nonempty_legacy_snapshot_is_refused_without_data_loss(tmp_path):
    path = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE world_snapshots(world_id TEXT PRIMARY KEY,record_json TEXT NOT NULL)')
        raw = _dump({'legacy': '原数据'})
        db.execute('INSERT INTO world_snapshots VALUES(?,?)', ('world_old', raw))
    with pytest.raises(ValueError, match='explicit migration'):
        SQLiteBaselineStore(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT record_json FROM world_snapshots').fetchone()[0] == raw
        assert db.execute("SELECT name FROM sqlite_master WHERE name='worlds'").fetchone() is None


def test_sql_rejects_cross_world_point_reference(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    first = service.execute('create_world', create_request())
    other_request = create_request()
    other_request['requestId'] = 'other'
    other = service.execute('create_world', other_request)
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA foreign_keys=ON')
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('UPDATE worlds SET active_point_id=? WHERE id=?',
                       (other['data']['rootPointId'], first['data']['worldId']))
            db.commit()
        db.rollback()
