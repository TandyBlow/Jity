"""Independent A3 work-store acceptance paths over real SQLite databases.

These cover valid multi-unit and time-scan work, including an ASGI HTTP
flow that creates a fresh application and store for every operation.
They do not claim browser/H2, TTL or takeover acceptance.
"""
import copy
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.database.world_repository import LedgerMismatch
from app.services.world.control import ServiceRefusal, WorldService
from app.services.world.store import FixtureBaselineStore
from app.world_app import create_persistent_world_app
from tests.test_world_control_service import (
    ORDER, TIME_ADVANCE, _claim_and_submit, _payload, begin_work,
    initial_template, run_t01_flow, single_group,
)
from tests.test_world_http import HttpService
from tests.test_world_sqlite_store import reopen


class RestartingService:
    def __init__(self, path):
        self.path = path

    def execute(self, operation, request):
        return reopen(self.path).execute(operation, request)


def test_ten_ordered_units_reopen_with_set_semantics_and_commit(tmp_path):
    path = tmp_path / 'ten-units.sqlite'
    service = RestartingService(path)
    initial = initial_template()
    for suffix in 'ghij':
        actor_id, task_id = f'person_{suffix}', f'task_{suffix}_root'
        actor = copy.deepcopy(initial['characters']['person_a'])
        actor.update(id=actor_id, name=suffix.upper(), tasks={task_id: {
            'id': task_id, 'ownerId': actor_id, 'parentTaskId': None,
            'goal': '完成本轮测试。', 'status': 'pending',
        }})
        initial['characters'][actor_id] = actor
    order = sorted(initial['characters'])
    created = service.execute('create_world', {
        'protocolVersion': 2, 'requestId': 'create_ten', 'initial': initial})
    world, head, lease = (created['data']['worldId'], created['data']['rootPointId'],
                          created['data']['lease'])
    _claim_and_submit(service, world, lease, head, 'root_ten', '所有人准备行动。')
    allocations = service.execute('allocate_ids', _payload(
        'allocate_ten', world, lease, allocationKey='ten_units', slots=[
            {'slotKey': 'point', 'kind': 'point', 'scope': None},
            *[{'slotKey': f'group_{index}', 'kind': 'group', 'scope': 'round_ten'}
              for index in range(1, 11)],
        ]))
    identities = {item['slotKey']: item['id'] for item in allocations['data']['allocations']}
    point_id = identities['point']
    service.execute('checkpoint_start_advance', _payload(
        'start_ten', world, lease, operation='start_advance', expectedPointId=head,
        expectedVersion=0, expectedCheckpointRevision=0, advanceId='advance_ten',
        inputId='input_ten', roundId='round_ten', inputText='一起行动。', order=order))
    revision = 1

    def checkpoint(operation, request_id, **fields):
        nonlocal revision
        result = service.execute('checkpoint_' + operation, _payload(
            request_id, world, lease, operation=operation, expectedPointId=head,
            expectedVersion=0, expectedCheckpointRevision=revision,
            pointId=point_id, **fields))
        revision += 1
        return result

    checkpoint('begin_point', 'begin_ten', kind='normal', timeAdvance=TIME_ADVANCE)
    candidates, ordinal_ids = [], []
    for index, actor in enumerate(order, 1):
        group_id = identities[f'group_{index}']
        checkpoint('discover_group', f'discover_{index}', groupId=group_id,
                   initiatorId=actor, actionText=f'{actor} 行动。', targetIds=None)
        checkpoint('extend_group', f'targets_{index}', groupId=group_id,
                   sourceId=actor, targets=[], admittedMember=None)
        checkpoint('close_group', f'close_{index}', groupId=group_id)
        candidate = single_group([actor], order, group_id)
        candidates.append(candidate)
        result = checkpoint('stage_unit', f'stage_{index}', groupId=group_id,
                            candidates=candidate, results={actor: f'{actor} 已完成。'})
        ordinal_ids.append(result['data']['unitId'])
        restored = reopen(path).store.world(world)['work']
        assert [unit['unitId'] for unit in restored['units']] == ordinal_ids
        assert restored['working'].settledUnitIds == sorted(ordinal_ids)
        assert set(restored['working'].settledUnitIds) == set(ordinal_ids)
    # A set-shaped field sorts unit_10 before unit_2; the outer units retain
    # their actual settlement order independently of that representation.
    assert ordinal_ids != sorted(ordinal_ids)
    preview = service.execute('preview_point', {
        'protocolVersion': 2, 'worldId': world, 'advanceId': 'advance_ten',
        'roundId': 'round_ten', 'pointId': point_id, 'expectedPointId': head,
        'expectedVersion': 0, 'expectedCheckpointRevision': revision,
        'timeAdvance': TIME_ADVANCE, 'settlementGroups': candidates,
    })
    checkpoint('seal_point', 'seal_ten')
    commit = _payload(
        'commit_ten', world, lease, advanceId='advance_ten', roundId='round_ten',
        pointId=point_id, expectedPointId=head, expectedVersion=0,
        expectedCheckpointRevision=revision, point=preview['data']['pointProjection'],
        settlementGroups=candidates)
    result = service.execute('commit_point', commit)
    assert result['data']['version'] == 1
    assert service.execute('commit_point', commit)['replayed']
    record = reopen(path).store.world(world)
    assert record['work'] is None and record['round']['actedIds'] == order
    with sqlite3.connect(path) as db:
        assert [row[0] for row in db.execute(
            'SELECT unit_id FROM world_settled_units ORDER BY ordinal')] == ordinal_ids
        assert db.execute('SELECT status FROM world_point_work').fetchone() == ('consumed',)
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_t01_http_restarts_sqlite_app_before_every_operation(tmp_path, monkeypatch):
    path = tmp_path / 'http-restarts.sqlite'
    monkeypatch.setenv('WORLD_SQLITE_PATH', str(path))

    class RestartingHttpService:
        def execute(self, operation, request):
            with TestClient(create_persistent_world_app()) as client:
                return HttpService(client).execute(operation, request)

    service = RestartingHttpService()
    flow = run_t01_flow(service, commit=False)
    world, point = flow['world_id'], flow['point_id']
    stored = reopen(path).store.world(world)
    assert stored['version'] == 0 and stored['work']['sealed']
    committed = service.execute('commit_point', flow['commit_request'])
    replay = service.execute('commit_point', flow['commit_request'])
    assert replay['replayed'] and replay['data'] == committed['data']
    _claim_and_submit(service, world, flow['lease'], point, 'http_ready', '持久存档叙事就绪。')
    context = service.execute('get_context', {'worldId': world})
    assert context['world']['head']['version'] == 1
    assert context['work'] is None and context['control']['gate']['status'] == 'none'
    assert context['control']['canCompute']
    old_state = service.execute('get_state', {'worldId': world, 'point': flow['root_id']})
    assert old_state['data']['version'] == 0
    state = service.execute('get_state', {'worldId': world})
    assert state['data']['state']['time']['dateTime'] == '2026-01-01T11:59:02'
    assert service.execute('narration_get', {
        'worldId': world, 'pointId': point})['data']['text'] == '持久存档叙事就绪。'
    record = reopen(path).store.world(world)
    assert reopen(path).store.replay_state(world, point) == record['state']


def test_time_scan_only_work_reopens_seals_and_commits(tmp_path):
    path = tmp_path / 'scan-only.sqlite'
    service = RestartingService(path)
    flow = begin_work(service)
    world, point, head, lease = (flow['world_id'], flow['point_id'], flow['root_id'], flow['lease'])
    revision = flow['revision']
    scan = single_group([], ORDER, None)
    service.execute('checkpoint_stage_time_scan', _payload(
        'scan_only', world, lease, operation='stage_time_scan', expectedPointId=head,
        expectedVersion=0, expectedCheckpointRevision=revision, pointId=point, candidates=scan))
    revision += 1
    stored = reopen(path).store.world(world)
    assert stored['work']['timeScan'] == scan and stored['work']['timeScanComplete']
    assert stored['work']['units'] == [] and stored['work']['working'].cursor == len(ORDER)
    assert stored['work']['working'].intentStatus == 'pending'
    assert stored['round']['cursor'] == 0
    preview = service.execute('preview_point', {
        'protocolVersion': 2, 'worldId': world, 'advanceId': 'advance_1',
        'roundId': 'round_1', 'pointId': point, 'expectedPointId': head,
        'expectedVersion': 0, 'expectedCheckpointRevision': revision,
        'timeAdvance': TIME_ADVANCE, 'settlementGroups': [],
    })
    service.execute('checkpoint_seal_point', _payload(
        'seal_scan', world, lease, operation='seal_point', expectedPointId=head,
        expectedVersion=0, expectedCheckpointRevision=revision, pointId=point))
    revision += 1
    assert reopen(path).store.world(world)['work']['sealed']
    commit = _payload(
        'commit_scan', world, lease, advanceId='advance_1', roundId='round_1',
        pointId=point, expectedPointId=head, expectedVersion=0,
        expectedCheckpointRevision=revision, point=preview['data']['pointProjection'],
        settlementGroups=[])
    assert service.execute('commit_point', commit)['data']['version'] == 1
    assert service.execute('commit_point', commit)['replayed']
    record = reopen(path).store.world(world)
    assert record['work'] is None and record['round']['cursor'] == len(ORDER)
    assert record['round']['actedIds'] == []
    assert record['advance']['intentStatus'] == 'pending'
    assert reopen(path).store.replay_state(world, point) == record['state']


def test_reaction_group_preserves_each_members_confirmed_work_across_reopens(tmp_path):
    path = tmp_path / 'reaction-group.sqlite'
    service = RestartingService(path)
    flow = begin_work(service)
    world, point, head, lease, group_id = (
        flow['world_id'], flow['point_id'], flow['root_id'], flow['lease'], flow['group_id'])
    revision = flow['revision']
    source_text, reaction_text = '原始行动\r\n向 B 招手。', '原始反应\r\n回应 A。'

    def checkpoint(operation, request_id, **fields):
        nonlocal revision
        response = service.execute('checkpoint_' + operation, _payload(
            request_id, world, lease, operation=operation, expectedPointId=head,
            expectedVersion=0, expectedCheckpointRevision=revision,
            pointId=point, groupId=group_id, **fields))
        revision += 1
        return response

    checkpoint('discover_group', 'react_discover', initiatorId='person_a',
               actionText=source_text, targetIds=None)
    checkpoint('extend_group', 'react_targets_a', sourceId='person_a',
               targets=[{'targetId': 'person_b', 'triggerKey': 'trigger_ab'}], admittedMember=None)
    checkpoint('extend_group', 'react_admit_b', sourceId='person_a', targets=None,
               admittedMember={
                   'memberId': 'person_b', 'actionText': reaction_text,
                   'rollRefs': [{'sourceId': 'person_a', 'targetId': 'person_b',
                                 'triggerKey': 'trigger_ab', 'rollId': 'roll_ab'}],
               })
    pending = reopen(path).store.world(world)['work']['pendingGroup']
    assert pending['targetIdsBySource'] == {'person_a': ['person_b'], 'person_b': None}
    assert pending['actionTexts'] == {'person_a': source_text, 'person_b': reaction_text}
    checkpoint('extend_group', 'react_targets_b', sourceId='person_b', targets=[], admittedMember=None)
    checkpoint('close_group', 'react_close')
    candidates = single_group(['person_a', 'person_b'], ORDER, group_id)
    results = {'person_a': '已招手。\r\n', 'person_b': '已回应。\r\n'}
    checkpoint('stage_unit', 'react_stage', candidates=candidates, results=results)
    work = reopen(path).store.world(world)['work']
    assert work['working'].actedIds == ['person_a', 'person_b']
    assert work['working'].cursor == 2
    assert work['units'][0]['candidates'] == candidates and work['units'][0]['results'] == results
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status FROM world_groups').fetchone() == ('staged',)
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('storage', ['memory', 'sqlite'])
@pytest.mark.parametrize('changed_candidates', [False, True])
def test_confirmed_time_scan_cannot_be_reconfirmed_but_original_request_replays(
        tmp_path, storage, changed_candidates):
    path = tmp_path / 'frozen-scan.sqlite'
    service = (RestartingService(path) if storage == 'sqlite'
               else WorldService(FixtureBaselineStore()))
    flow = begin_work(service)
    world, point, head, lease = (flow['world_id'], flow['point_id'], flow['root_id'], flow['lease'])
    scan = single_group([], ORDER, None)
    request = _payload(
        'first_scan', world, lease, operation='stage_time_scan', expectedPointId=head,
        expectedVersion=0, expectedCheckpointRevision=flow['revision'], pointId=point, candidates=scan)
    accepted = service.execute('checkpoint_stage_time_scan', request)

    def record():
        return (reopen(path).store if storage == 'sqlite' else service.store).world(world)

    before = record()
    replay = service.execute('checkpoint_stage_time_scan', request)
    assert replay['replayed'] and replay['data'] == accepted['data']
    assert record() == before
    replacement = dict(request, requestId='second_scan',
                       expectedCheckpointRevision=before['control']['revision'])
    if changed_candidates:
        replacement['candidates'] = single_group(
            [], ORDER, None, tasksAchieved={'person_a': ['task_a_root']}, personalityCoverageIds=ORDER)
    with pytest.raises(ServiceRefusal) as error:
        service.execute('checkpoint_stage_time_scan', replacement)
    assert error.value.code == 'request_malformed'
    assert record() == before
    assert service.execute('checkpoint_stage_time_scan', request)['replayed']
    assert record()['control']['revision'] == accepted['control']['revision']


def _skip_then_scan(path):
    service = RestartingService(path)
    flow = begin_work(service)
    world, point, head, lease = (flow['world_id'], flow['point_id'], flow['root_id'], flow['lease'])
    revision = flow['revision']
    service.execute('checkpoint_record_skip', _payload(
        'skip_before_scan', world, lease, operation='record_skip', expectedPointId=head,
        expectedVersion=0, expectedCheckpointRevision=revision, pointId=point,
        slotActorId=ORDER[0]))
    revision += 1
    assert reopen(path).store.world(world)['work']['working'].intentStatus == 'consumed'
    service.execute('checkpoint_stage_time_scan', _payload(
        'scan_after_skip', world, lease, operation='stage_time_scan', expectedPointId=head,
        expectedVersion=0, expectedCheckpointRevision=revision, pointId=point,
        candidates=single_group([], ORDER, None)))
    flow['revision'] = revision + 1
    return service, flow


def test_skip_then_time_scan_keeps_input_consumed_across_restart_and_commit(tmp_path):
    path = tmp_path / 'skip-then-scan.sqlite'
    service, flow = _skip_then_scan(path)
    world, point, head, lease = (flow['world_id'], flow['point_id'], flow['root_id'], flow['lease'])
    revision = flow['revision']
    work = reopen(path).store.world(world)['work']
    assert work['timeScanComplete'] and work['units'] == []
    assert work['working'].intentStatus == 'consumed'
    assert work['working'].cursor == len(ORDER) and work['working'].actedIds == []
    assert reopen(path).store.world(world)['advance']['intentStatus'] == 'pending'
    preview = service.execute('preview_point', {
        'protocolVersion': 2, 'worldId': world, 'advanceId': 'advance_1',
        'roundId': 'round_1', 'pointId': point, 'expectedPointId': head,
        'expectedVersion': 0, 'expectedCheckpointRevision': revision,
        'timeAdvance': TIME_ADVANCE, 'settlementGroups': [],
    })
    service.execute('checkpoint_seal_point', _payload(
        'seal_after_skip_scan', world, lease, operation='seal_point', expectedPointId=head,
        expectedVersion=0, expectedCheckpointRevision=revision, pointId=point))
    commit = _payload(
        'commit_after_skip_scan', world, lease, advanceId='advance_1', roundId='round_1',
        pointId=point, expectedPointId=head, expectedVersion=0,
        expectedCheckpointRevision=revision + 1, point=preview['data']['pointProjection'],
        settlementGroups=[])
    assert service.execute('commit_point', commit)['data']['version'] == 1
    assert service.execute('commit_point', commit)['replayed']
    record = reopen(path).store.world(world)
    assert record['work'] is None and record['advance']['intentStatus'] == 'consumed'
    assert record['round']['actedIds'] == []
    assert reopen(path).store.replay_state(world, point) == record['state']


@pytest.mark.parametrize('confirmed_work', ['staged_unit', 'skip_then_scan'])
def test_consumed_input_cannot_revert_to_pending_in_restored_work(tmp_path, confirmed_work):
    path = tmp_path / 'corrupt-intent.sqlite'
    if confirmed_work == 'staged_unit':
        from tests.test_world_work_store import staged
        _, flow, _ = staged(path)
    else:
        _, flow = _skip_then_scan(path)
    assert reopen(path).store.world(flow['world_id'])['work']['working'].intentStatus == 'consumed'
    with sqlite3.connect(path) as db:
        raw = db.execute('SELECT progress_json FROM world_point_work').fetchone()[0]
        progress = json.loads(raw)
        progress['intentStatus'] = 'pending'
        db.execute('UPDATE world_point_work SET progress_json=?', (json.dumps(progress),))
    with pytest.raises(LedgerMismatch):
        reopen(path).store.world(flow['world_id'])
