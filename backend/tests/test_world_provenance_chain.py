"""Real commit path → evidence ledger → fact provenance → before relation.

The chain runs through ``WorldService`` + ``SQLiteBaselineStore``: the real
``create_world`` → ``start_advance`` → ``begin_point`` → ``checkpoint_*`` →
``commit_point`` flow commits two points, each carrying a real entity delta
(a sanity change) and a real time advance. Only then are evidence rows and
fact provenance read back from SQLite and ``before`` validated.

Nothing here invents provenance: facts are bound to the evidence items the
authority itself recorded.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend' / 'tests'))

from app.database.world_evidence_store import ensure_schema, read_point  # noqa: E402
from app.database.world_store import SQLiteBaselineStore  # noqa: E402
from app.services.world.control import WorldService  # noqa: E402
from app.services.world.merge import point_entity_deltas  # noqa: E402
from app.services.world.provenance import bind_fact, validate_relations  # noqa: E402
from app.schemas.world.v2.requests import CommitPointSuccess  # noqa: E402

import test_world_control_service as flow  # noqa: E402

TIME_ADVANCE = {'boundary': 'elapsed', 'duration': {'amount': 2, 'unit': 'second'}}


@pytest.fixture()
def service(tmp_path):
    return WorldService(SQLiteBaselineStore(tmp_path / 'world.db'))


def commit_one_point(service, text='袖口沾了雨', request_id='req'):
    """One real point with a real sanity delta; returns (world_id, point_id, root_id)."""
    state = flow.begin_work(service)
    world_id, root_id, point_id = state['world_id'], state['root_id'], state['point_id']
    group_id, lease, revision = state['group_id'], state['lease'], state['revision']

    def checkpoint(tag, operation, **fields):
        nonlocal revision
        envelope = flow._run(service, operation, flow._payload(
            f'{request_id}_{tag}', world_id, lease,
            operation=operation.removeprefix('checkpoint_'),
            expectedPointId=root_id, expectedVersion=0,
            expectedCheckpointRevision=revision, pointId=point_id, **fields),
            flow._CHECKPOINT_SUCCESS[operation])
        revision += 1
        return envelope

    roster = frozenset(flow.ORDER)
    allocation = flow._run(service, 'allocate_ids', flow._payload(
        f'{request_id}_change', world_id, lease, allocationKey=f'{request_id}_changes',
        slots=[{'slotKey': 'ap1', 'kind': 'change', 'scope': None}]), flow.AllocateIdsSuccess)
    change_id = {i['slotKey']: i['id'] for i in allocation['data']['allocations']}['ap1']
    group = flow.single_group(['person_a'], roster, group_id,
                              appearances={'person_a': [{'id': change_id, 'text': text,
                                                        'supersedes': []}]})
    checkpoint('discover', 'checkpoint_discover_group', groupId=group_id,
               initiatorId='person_a', actionText='深吸一口气。', targetIds=None)
    checkpoint('extend', 'checkpoint_extend_group', groupId=group_id,
               sourceId='person_a', targets=[], admittedMember=None)
    checkpoint('close', 'checkpoint_close_group', groupId=group_id)
    checkpoint('stage', 'checkpoint_stage_unit', groupId=group_id, candidates=group,
               results={'person_a': '呼吸稳了一点。'})
    for index, actor in enumerate(flow.ORDER[1:], start=1):
        checkpoint(f'skip_{index}', 'checkpoint_record_skip', slotActorId=actor)
    checkpoint('seal', 'checkpoint_seal_point')

    merged = point_entity_deltas([group], None)
    request = {
        'protocolVersion': 2, 'requestId': f'{request_id}_commit', 'worldId': world_id,
        'advanceId': state['advance_id'], 'roundId': state['round_id'],
        'expectedPointId': root_id, 'expectedVersion': 0,
        'expectedCheckpointRevision': revision,
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'pointId': point_id,
        'point': {'worldId': world_id, 'id': point_id, 'sequence': 1,
                  'kind': 'normal', 'previousPointId': root_id,
                  'roundId': state['round_id'], 'advanceId': state['advance_id'],
                  'trigger': 'player', 'linkedFromPointId': None,
                  'timeAdvance': TIME_ADVANCE,
                  'entityDeltas': {key: delta.model_dump(mode='json')
                                   for key, delta in merged.items()}},
        'settlementGroups': [group],
    }
    flow._run(service, 'commit_point', request, CommitPointSuccess)
    return world_id, point_id, root_id


def evidence(service, world_id, point_id):
    with service.store._connection() as connection:
        return read_point(connection, world_id, point_id)


def chain_points(service, world_id):
    with service.store._connection() as connection:
        ensure_schema(connection)
        rows = connection.execute(
            'SELECT id,sequence,previous_point_id,time_json FROM world_points'
            ' WHERE world_id=? ORDER BY sequence', (world_id,)).fetchall()
    import json
    return [{'id': r[0], 'worldId': world_id, 'previousPointId': r[2],
             'time': json.loads(r[3]) if r[3] else None} for r in rows]


def test_committed_point_records_its_real_delta(service):
    world_id, point_id, root_id = commit_one_point(service)
    recorded = evidence(service, world_id, point_id)
    assert recorded is not None, 'commit 点没有证据行'
    assert recorded['deltaStatus'] == 'recorded'
    assert recorded['sequence'] == 1 and recorded['previousPointId'] == root_id
    kinds = {(e['entityId'], e['kind']) for e in recorded['events']}
    assert ('person_a', 'appearance') in kinds, kinds
    assert evidence(service, world_id, root_id) is None, '旧根点不得回填证据'


def test_no_delta_commit_is_recorded_as_none(service):
    """The stock T01 fixture stages an action with no state change. That must
    be written as ``none``, never left absent (absent = unrecorded)."""
    state = flow.run_t01_flow(service)
    recorded = evidence(service, state['world_id'], state['point_id'])
    assert recorded is not None
    assert recorded['deltaStatus'] == 'none'
    assert recorded['events'] == []


def test_before_requires_event_evidence_on_both_ends(service):
    world_id, point_id, root_id = commit_one_point(service)
    recorded = evidence(service, world_id, point_id)
    event_id = recorded['events'][0]['evidenceId']
    facts = {'f0': bind_fact('f0', world_id, [point_id], [event_id])}
    points = chain_points(service, world_id)

    point_only = [{'type': 'before', 'fromFactId': 'f0', 'toFactId': 'f0',
                   'evidence': [{'type': 'point', 'pointId': point_id}]}]
    problems = validate_relations(point_only, facts, points, {event_id: point_id})
    assert any('自指' in p for p in problems), problems


def test_point_only_evidence_and_zero_advance_are_refused():
    points = [
        {'id': 'root', 'worldId': 'w', 'previousPointId': None, 'time': None},
        {'id': 'p1', 'worldId': 'w', 'previousPointId': 'root',
         'time': {'boundary': 'elapsed', 'duration': {'amount': 1, 'unit': 'second'}}},
        {'id': 'p2', 'worldId': 'w', 'previousPointId': 'p1',
         'time': {'boundary': 'elapsed', 'duration': {'amount': 0, 'unit': 'second'}}},
    ]
    facts = {'f0': bind_fact('f0', 'w', ['p1'], ['p1/c/appearance/ap1']),
             'f1': bind_fact('f1', 'w', ['p2'], ['p2/c/appearance/ap2'])}
    index = {'p1/c/appearance/ap1': 'p1', 'p2/c/appearance/ap2': 'p2'}
    point_only = [{'type': 'before', 'fromFactId': 'f0', 'toFactId': 'f1',
                   'evidence': [{'type': 'point', 'pointId': 'p1'},
                                {'type': 'point', 'pointId': 'p2'}]}]
    assert any('只有点证据' in p for p in
               validate_relations(point_only, facts, points, index))
    zero = [{'type': 'before', 'fromFactId': 'f0', 'toFactId': 'f1',
             'evidence': [{'type': 'event', 'evidenceId': 'p1/c/appearance/ap1'},
                          {'type': 'event', 'evidenceId': 'p2/c/appearance/ap2'}]}]
    assert any('时间推进为 0' in p for p in
               validate_relations(zero, facts, points, index))


def test_fact_without_evidence_cannot_be_bound():
    with pytest.raises(Exception):
        bind_fact('f0', 'w', ['p1'], [])


def test_sustained_state_cannot_be_ordered():
    sustained = bind_fact('f0', 'w', ['p1', 'p2'], ['e1', 'e2'])
    facts = {'f0': sustained, 'f1': bind_fact('f1', 'w', ['p2'], ['e2'])}
    points = [
        {'id': 'p1', 'worldId': 'w', 'previousPointId': 'root',
         'time': {'boundary': 'elapsed', 'duration': {'amount': 1, 'unit': 'second'}}},
        {'id': 'p2', 'worldId': 'w', 'previousPointId': 'p1',
         'time': {'boundary': 'elapsed', 'duration': {'amount': 1, 'unit': 'second'}}},
    ]
    relations = [{'type': 'before', 'fromFactId': 'f0', 'toFactId': 'f1',
                  'evidence': [{'type': 'event', 'evidenceId': 'e1'},
                               {'type': 'event', 'evidenceId': 'e2'}]}]
    problems = validate_relations(relations, facts, points, {'e1': 'p1', 'e2': 'p2'})
    assert any('持续状态' in p for p in problems), problems



def append_point(service, world_id, previous_point_id, text, change_id):
    """Commit one more point through ``store.transact`` — the same writer and
    transaction the service uses — applying the delta to the real state."""
    from app.database.world_repository import state_digest
    from app.schemas.world.contracts import EntityDelta, TimelinePoint
    from app.services.world.apply import apply_point

    def handler(snapshot):
        previous = snapshot['points'][previous_point_id]
        point = TimelinePoint.model_validate({
            'worldId': world_id, 'id': f'{previous_point_id}_next',
            'sequence': previous.sequence + 1, 'kind': 'normal',
            'previousPointId': previous.id, 'roundId': previous.roundId,
            'advanceId': previous.advanceId, 'trigger': 'player',
            'linkedFromPointId': None, 'timeAdvance': TIME_ADVANCE,
            'entityDeltas': {'person_a': EntityDelta.model_validate({
                'entityId': 'person_a',
                'appearanceChanges': [{'id': change_id, 'text': text,
                                       'supersedes': []}]}).model_dump(mode='json')},
        })
        state = apply_point(snapshot['pointStates'][previous.id]['state'], point)
        snapshot['points'][point.id] = point
        snapshot['pointStates'][point.id] = {'state': state,
                                            'stateDigest': state_digest(state)}
        snapshot['narrations'][point.id] = {'status': 'ready', 'generation': 1, 'text': ''}
        return point.id

    return service.store.transact(world_id, handler)


def test_two_committed_points_authorize_before(service):
    world_id, point_id, _root_id = commit_one_point(service)
    second = append_point(service, world_id, point_id, '袖口干了', 'ap2')
    assert second == f'{point_id}_next'

    first_record = evidence(service, world_id, point_id)
    second_record = evidence(service, world_id, second)
    assert first_record['deltaStatus'] == 'recorded'
    assert second_record['deltaStatus'] == 'recorded'
    first_event = first_record['events'][0]['evidenceId']
    second_event = second_record['events'][0]['evidenceId']

    facts = {'f0': bind_fact('f0', world_id, [point_id], [first_event]),
             'f1': bind_fact('f1', world_id, [second], [second_event])}
    points = chain_points(service, world_id)
    index = {first_event: point_id, second_event: second}
    relations = [{'type': 'before', 'fromFactId': 'f0', 'toFactId': 'f1',
                  'evidence': [{'type': 'event', 'evidenceId': first_event},
                               {'type': 'event', 'evidenceId': second_event}]}]
    assert validate_relations(relations, facts, points, index) == []
