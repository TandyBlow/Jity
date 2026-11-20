"""Acceptance probes beyond the implementation's original happy-path tests."""
import json
import sqlite3

import pytest

from app.database.world_repository import LedgerMismatch
from tests.test_world_sqlite_store import reopen
from tests.test_world_work_store import discover, staged
from tests.test_world_control_service import run_t01_flow


def test_progress_cannot_invent_actor_without_settled_unit(tmp_path):
    path = tmp_path / 'world.sqlite'
    _, flow, _ = staged(path)
    with sqlite3.connect(path) as db:
        progress = json.loads(db.execute('SELECT progress_json FROM world_point_work').fetchone()[0])
        progress['actedIds'].append('person_b')
        progress['visitedIds'].append('person_b')
        progress['cursor'] = 2
        db.execute('UPDATE world_point_work SET progress_json=?', (json.dumps(progress),))
    with pytest.raises(LedgerMismatch):
        reopen(path).store.world(flow['world_id'])


@pytest.mark.parametrize('mutation', ['missing_action', 'blank_action', 'missing_targets',
                                     'missing_specs', 'false_closed', 'extra_action'])
def test_group_payload_recovery_rejects_incomplete_originals(tmp_path, mutation):
    path = tmp_path / 'world.sqlite'
    _, flow = discover(path)
    with sqlite3.connect(path) as db:
        group = json.loads(db.execute('SELECT group_json FROM world_group_payloads').fetchone()[0])
        if mutation == 'missing_action':
            group['actionTexts'] = {}
        elif mutation == 'blank_action':
            group['actionTexts']['person_a'] = '  '
        elif mutation == 'missing_targets':
            group['targetIdsBySource'] = {}
        elif mutation == 'missing_specs':
            group['targetSpecsBySource'] = {}
        elif mutation == 'false_closed':
            group['closed'] = True
        else:
            group['actionTexts']['person_b'] = '另一个人。'
        db.execute('UPDATE world_group_payloads SET group_json=?', (json.dumps(group),))
    with pytest.raises(LedgerMismatch):
        reopen(path).store.world(flow['world_id'])


@pytest.mark.parametrize('value', ['{}', '[]', 'null'])
def test_time_advance_is_validated_before_work_can_be_read(tmp_path, value):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    from tests.test_world_control_service import begin_work
    flow = begin_work(service)
    with sqlite3.connect(path) as db:
        db.execute('UPDATE world_point_work SET time_json=?', (value,))
    with pytest.raises(LedgerMismatch):
        reopen(path).store.world(flow['world_id'])


def test_sealed_work_cannot_be_unsealed_then_retimed(tmp_path):
    path = tmp_path / 'world.sqlite'
    service = reopen(path)
    flow = run_t01_flow(service, commit=False)
    before = service.store.world(flow['world_id'])
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('UPDATE world_point_work SET sealed=0,prefix_digest=NULL,time_json=?',
                (json.dumps({'boundary': 'elapsed', 'duration': {'amount': 9, 'unit': 'second'}}),))
    assert reopen(path).store.world(flow['world_id']) == before
