"""R1 reads and restore refusals over real HTTP serialization and SQLite."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.database.world_frozen_repository import active_sources
from app.database.world_store import SQLiteBaselineStore, _load
from app.schemas.world.canonical import canonical_digest
from app.schemas.world.v2 import ErrorResponse
from app.schemas.world.v2.registry import OPERATION_BY_NAME
from app.world_app import create_world_app
from tests.test_world_control_service import _payload
from tests.test_world_http import HEADERS
from tests.test_world_progress import accept, facts, rolls, scenario, targets


def dump(path):
    with sqlite3.connect(path) as connection:
        return tuple(connection.iterdump())


@pytest.mark.parametrize('operation', ['get_context', 'checkpoint_restore_group_work'])
@pytest.mark.parametrize('fault,expected', [
    ('missing_progress', 'frozen_work_missing'),
    ('missing_roll', 'frozen_work_missing'),
    ('missing_baseline', 'frozen_work_missing'),
    ('progress_hash', 'frozen_work_corrupt'),
    ('progress_stack', 'frozen_work_corrupt'),
    ('roll_content', 'frozen_work_corrupt'),
    ('group_shape', 'frozen_work_corrupt'),
])
def test_missing_or_damaged_facts_return_declared_http_refusals_without_writes(tmp_path,operation,fault,expected):
    flow = scenario(tmp_path)
    rolls(flow, 'person_a', targets(flow, 'person_a', ['person_b']))
    with flow['store'].locked():
        record = flow['store'].world(flow['world'])
        source = active_sources(flow['store']._local.connection, flow['world'], flow['ids']['point'])[0]
    with sqlite3.connect(flow['path']) as connection:
        if fault == 'missing_progress':
            connection.execute('DELETE FROM world_group_progress')
        elif fault == 'missing_roll':
            connection.execute('DELETE FROM world_rolls')
        elif fault == 'missing_baseline':
            connection.execute('DELETE FROM world_roll_baselines')
        elif fault == 'roll_content':
            # Simulate storage damage, bypassing the normal immutable-row guard.
            for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='world_rolls'").fetchall():
                connection.execute(f'DROP TRIGGER "{name}"')
            connection.execute('UPDATE world_rolls SET result=19')
        elif fault == 'group_shape':
            group = json.loads(connection.execute('SELECT group_json FROM world_group_payloads').fetchone()[0])
            group['actionTexts']['person_a'] = False
            connection.execute('UPDATE world_group_payloads SET group_json=?', (json.dumps(group),))
        else:
            value = json.loads(connection.execute('SELECT checkpoint_json FROM world_group_progress').fetchone()[0])
            if fault == 'progress_stack':
                value['progress']['sourceStack'] = []
            digest = '0' * 64 if fault == 'progress_hash' else canonical_digest(value)
            connection.execute('UPDATE world_group_progress SET checkpoint_json=?,checkpoint_digest=?',
                               (json.dumps(value), digest))
    before = dump(flow['path'])
    calls = len(flow['calls'])
    spec = OPERATION_BY_NAME[operation]
    url = spec.path.replace('{worldId}', flow['world'])
    with TestClient(create_world_app(store=flow['store'])) as client:
        if operation == 'get_context':
            response = client.get(url, headers=HEADERS, params=dict(includeRecovery='true',
                leaseToken=flow['lease']['leaseToken'], fenceEpoch=flow['lease']['fenceEpoch']))
        else:
            request = _payload('restore_damaged', flow['world'], flow['lease'],
                operation='restore_group_work', expectedPointId=flow['head'], expectedVersion=0,
                expectedCheckpointRevision=record['control']['revision'], **source)
            response = client.request(spec.method, url, headers=HEADERS, json=request)
    assert response.status_code == 409, response.text
    body = ErrorResponse.model_validate(response.json())
    assert body.operation == operation and body.error.code == expected
    assert expected in {entry.code for entry in spec.errorCodes}
    assert dump(flow['path']) == before
    assert len(flow['calls']) == calls


def test_http_reopen_reads_explicit_order_and_full_rolls_from_sql_not_adapter_copy(tmp_path):
    flow = scenario(tmp_path)
    outcome = rolls(flow, 'person_a', targets(flow, 'person_a', ['person_b']))[0]
    accept(flow, outcome, 'B 已确认的反应\r\n')
    expected = facts(flow)
    with sqlite3.connect(flow['path']) as connection:
        snapshot = _load(connection.execute('SELECT record_json FROM world_snapshots').fetchone()[0])
        assert '_groupProgress' not in snapshot and 'work' not in snapshot
    reopened = SQLiteBaselineStore(flow['path'], clock=lambda: flow['now'])
    url = OPERATION_BY_NAME['get_context'].path.replace('{worldId}', flow['world'])
    with TestClient(create_world_app(store=reopened)) as client:
        response = client.get(url, headers=HEADERS, params=dict(includeRecovery='true',
            leaseToken=flow['lease']['leaseToken'], fenceEpoch=flow['lease']['fenceEpoch']))
    assert response.status_code == 200, response.text
    actual = response.json()['recovery']['current']['groups'][0]
    assert actual == expected
    assert actual['progress']['sourceStack'] == ['person_b', 'person_a']
    assert actual['rolls'] == [outcome]
    assert actual['progress']['threats'][0]['actionDisposition'] == 'created'
