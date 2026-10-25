"""Redundancy regressions: bounded SQL and unchanged integrity guarantees."""
from contextlib import contextmanager
import sqlite3

import pytest

from app.database.world_repository import LedgerMismatch
from app.services.world.control import ServiceRefusal
from tests.test_world_sqlite_store import create_request, reopen
from tests.test_world_control_service import _payload, run_t01_flow


@contextmanager
def trace_sql(store):
    statements = []
    original = store._connection

    @contextmanager
    def traced_connection():
        with original() as connection:
            connection.set_trace_callback(statements.append)
            yield connection

    store._connection = traced_connection
    try:
        yield statements
    finally:
        store._connection = original


def checkpoint(service, flow, operation, request_id):
    record = service.store.world(flow['world_id'])
    return service.execute('checkpoint_' + operation, _payload(
        request_id, flow['world_id'], flow['lease'], operation=operation,
        expectedPointId=record['headPointId'], expectedVersion=record['version'],
        expectedCheckpointRevision=record['control']['revision']))


def test_history_request_growth_does_not_grow_read_sql_round_trips(tmp_path):
    service = reopen(tmp_path / 'world.sqlite')
    flow = run_t01_flow(service)
    with trace_sql(service.store) as initial_queries:
        initial = service.store.world(flow['world_id'])
    for index in range(12):
        checkpoint(service, flow, 'pause', f'pause_{index}')
        checkpoint(service, flow, 'resume', f'resume_{index}')
    with trace_sql(service.store) as later_queries:
        later = service.store.world(flow['world_id'])
    assert len(later['idempotency']) == len(initial['idempotency']) + 24
    assert len(later_queries) == len(initial_queries)
    assert later['state'] == initial['state']


def test_pause_does_not_reinsert_historical_successes_or_rewrite_points(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service)
    before = service.store.world(flow['world_id'])
    with sqlite3.connect(path) as connection:
        for index, table in enumerate(('world_points', 'world_state_checkpoints')):
            for event in ('INSERT', 'UPDATE'):
                connection.execute(f"CREATE TRIGGER reject_{index}_{event} BEFORE {event} ON {table} "
                                   "BEGIN SELECT RAISE(ABORT,'unexpected historical write'); END")
        connection.execute("CREATE TRIGGER reject_old_submission BEFORE INSERT ON world_submissions "
                           "WHEN NEW.request_id<>'pause_new' BEGIN SELECT RAISE(ABORT,'old success reinserted'); END")
    checkpoint(service, flow, 'pause', 'pause_new')
    after = service.store.world(flow['world_id'])
    assert after['state'] == before['state']
    assert after['points'] == before['points']
    assert after['control']['paused']
    assert len(after['idempotency']) == len(before['idempotency']) + 1


def test_creation_uses_targeted_lookup_and_keeps_atomic_replay(tmp_path, monkeypatch):
    service = reopen(tmp_path / 'world.sqlite')
    def forbid_bulk_lookup():
        raise AssertionError('Creation must not load all historical worlds')
    monkeypatch.setattr(service.store, 'global_idempotency', forbid_bulk_lookup)
    first = service.execute('create_world', create_request())
    replay = service.execute('create_world', create_request())
    assert replay['replayed']
    assert replay['data'] == first['data']


@pytest.mark.parametrize('table', ['world_creations', 'world_creation_replays'])
def test_targeted_creation_lookup_detects_a_missing_counterpart(tmp_path, table):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    service.execute('create_world', create_request())
    with sqlite3.connect(path) as connection:
        connection.execute(f'DELETE FROM {table}')
    with pytest.raises(LedgerMismatch):
        service.execute('create_world', create_request())


@pytest.mark.parametrize('change', ['remove', 'rewrite'])
def test_incremental_writer_still_rejects_changes_to_prior_successes(tmp_path, change):
    service = reopen(tmp_path / 'world.sqlite')
    flow = run_t01_flow(service)
    before = service.store.world(flow['world_id'])
    def mutate(record):
        key = next(iter(record['idempotency']))
        if change == 'remove':
            del record['idempotency'][key]
        else:
            record['idempotency'][key]['digest'] = '0' * 64
    with pytest.raises(LedgerMismatch):
        service.store.transact(flow['world_id'], mutate)
    assert service.store.world(flow['world_id']) == before


def test_normal_write_reads_and_validates_world_only_inside_its_transaction(tmp_path, monkeypatch):
    service = reopen(tmp_path / 'world.sqlite')
    flow = run_t01_flow(service)
    original = service.store.world
    calls = []
    def world(world_id):
        assert getattr(service.store._local, 'connection', None) is not None
        calls.append(world_id)
        return original(world_id)
    monkeypatch.setattr(service.store, 'world', world)
    service.execute('checkpoint_pause', _payload('pause', flow['world_id'], flow['lease'],
        operation='pause', expectedPointId=flow['point_id'], expectedVersion=1,
        expectedCheckpointRevision=flow['revision']))
    assert calls == [flow['world_id']]


def test_unknown_world_write_keeps_its_documented_refusal(tmp_path):
    service = reopen(tmp_path / 'world.sqlite')
    with pytest.raises(ServiceRefusal) as error:
        service.execute('checkpoint_pause', {
            'protocolVersion': 2, 'requestId': 'unknown', 'worldId': 'missing',
            'operation': 'pause', 'leaseToken': 'unknown_lease', 'fenceEpoch': 1,
            'expectedPointId': 'root_missing', 'expectedVersion': 0,
            'expectedCheckpointRevision': 0})
    assert error.value.code == 'version_mismatch'
