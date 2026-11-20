"""Build one mixed round with real commits.

p1 goes through the real service flow (create → narration → advance → point
workflow → commit). p2..p4 are appended with ``store.transact``, the same
writer ``commit_point`` uses, applying each delta to the real state.

  p1  2 s  person_a: two appearance changes   → two same-subject facts
  p2  3 s  person_b: one appearance change
  p3  1 s  person_c: two appearance changes
  p4  2 s  person_d: one appearance change
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend' / 'tests'))

from app.database.world_repository import state_digest  # noqa: E402
from app.database.world_store import SQLiteBaselineStore  # noqa: E402
from app.schemas.world.contracts import EntityDelta, TimelinePoint  # noqa: E402
from app.schemas.world.v2.requests import CommitPointSuccess  # noqa: E402
from app.services.world.apply import apply_point  # noqa: E402
from app.services.world.control import WorldService  # noqa: E402

import test_world_control_service as flow  # noqa: E402

NAMES = {'person_a': '林川', 'person_b': '周宁', 'person_c': '陈默',
         'person_d': '沈禾', 'person_e': '叶南', 'person_f': '高岭'}
TIME_ADVANCE = {'boundary': 'elapsed', 'duration': {'amount': 2, 'unit': 'second'}}
ROSTER = flow.ORDER


def chinese_initial():
    snapshot = json.loads((ROOT / 'design/world-protocol/v2/fixtures/projections/'
                                  'normal.expected.json').read_text(encoding='utf-8'))
    initial = snapshot['initial']
    del initial['worldId']
    for entity_id, name in NAMES.items():
        initial['characters'][entity_id]['name'] = name
    return initial


def group_of(group_id, change_ids):
    return flow.single_group(
        ['person_a'], frozenset(ROSTER), group_id,
        appearances={'person_a': [{'id': change_id, 'text': text, 'supersedes': []}
                                  for text, change_id in change_ids]})


def commit_first_point(service, store):
    """The real service flow, with person_a carrying two appearance changes."""
    flow.initial_template = chinese_initial
    state = flow.begin_work(service)
    world_id, root_id, point_id = state['world_id'], state['root_id'], state['point_id']
    group_id, lease, revision = state['group_id'], state['lease'], state['revision']

    allocation = flow._run(service, 'allocate_ids', flow._payload(
        'mixed_changes', world_id, lease, allocationKey='mixed_changes',
        slots=[{'slotKey': key, 'kind': 'change', 'scope': None}
               for key in ('ap1', 'ap2')]), flow.AllocateIdsSuccess)
    allocated = {item['slotKey']: item['id']
                 for item in allocation['data']['allocations']}
    changes = [('袖口沾了雨', allocated['ap1']), ('指节发白', allocated['ap2'])]

    def checkpoint(tag, operation, **fields):
        nonlocal revision
        envelope = flow._run(service, operation, flow._payload(
            f'{tag}_{revision}', world_id, lease,
            operation=operation.removeprefix('checkpoint_'),
            expectedPointId=root_id, expectedVersion=0,
            expectedCheckpointRevision=revision, pointId=point_id, **fields),
            flow._CHECKPOINT_SUCCESS[operation])
        revision += 1
        return envelope

    group = group_of(group_id, changes)
    checkpoint('discover', 'checkpoint_discover_group', groupId=group_id,
               initiatorId='person_a', actionText='抬手挡雨。', targetIds=None)
    checkpoint('extend', 'checkpoint_extend_group', groupId=group_id,
               sourceId='person_a', targets=[], admittedMember=None)
    checkpoint('close', 'checkpoint_close_group', groupId=group_id)
    checkpoint('stage', 'checkpoint_stage_unit', groupId=group_id, candidates=group,
               results={'person_a': '抬手挡雨。'})
    for index, actor in enumerate(ROSTER[1:], start=1):
        checkpoint(f'skip{index}', 'checkpoint_record_skip', slotActorId=actor)
    checkpoint('seal', 'checkpoint_seal_point')

    merged = flow.point_entity_deltas([group], None)
    request = {
        'protocolVersion': 2, 'requestId': 'mixed_commit_1', 'worldId': world_id,
        'advanceId': state['advance_id'], 'roundId': state['round_id'],
        'expectedPointId': root_id, 'expectedVersion': 0,
        'expectedCheckpointRevision': revision, 'leaseToken': lease['leaseToken'],
        'fenceEpoch': lease['fenceEpoch'], 'pointId': point_id,
        'point': {'worldId': world_id, 'id': point_id, 'sequence': 1, 'kind': 'normal',
                  'previousPointId': root_id, 'roundId': state['round_id'],
                  'advanceId': state['advance_id'], 'trigger': 'player',
                  'linkedFromPointId': None, 'timeAdvance': TIME_ADVANCE,
                  'entityDeltas': {key: delta.model_dump(mode='json')
                                   for key, delta in merged.items()}},
        'settlementGroups': [group]}
    flow._run(service, 'commit_point', request, CommitPointSuccess)
    return world_id, point_id


def append_point(store, world_id, previous_id, point_id, seconds, changes):
    def handler(snapshot):
        prior = snapshot['points'][previous_id]
        point = TimelinePoint.model_validate({
            'worldId': world_id, 'id': point_id, 'sequence': prior.sequence + 1,
            'kind': 'normal', 'previousPointId': prior.id, 'roundId': prior.roundId,
            'advanceId': prior.advanceId, 'trigger': 'player', 'linkedFromPointId': None,
            'timeAdvance': {'boundary': 'elapsed',
                            'duration': {'amount': seconds, 'unit': 'second'}},
            'entityDeltas': {entity: EntityDelta.model_validate({
                'entityId': entity,
                'appearanceChanges': [{'id': f'{entity}_{index}', 'text': text,
                                       'supersedes': []}
                                      for index, (text, _ignored) in enumerate(items, 1)]
            }).model_dump(mode='json') for entity, items in changes.items()}})
        state = apply_point(snapshot['pointStates'][prior.id]['state'], point)
        snapshot['points'][point.id] = point
        snapshot['pointStates'][point.id] = {'state': state, 'stateDigest': state_digest(state)}
        snapshot['narrations'][point.id] = {'status': 'ready', 'generation': 1, 'text': ''}
        return point.id

    return store.transact(world_id, handler)


def main(db_path):
    store = SQLiteBaselineStore(db_path)
    service = WorldService(store)
    world_id, previous = commit_first_point(service, store)
    plan = [('p2', 3, {'person_b': [('斗篷下摆湿了一片', 'bp1')]}),
            ('p3', 1, {'person_c': [('鞋底沾了泥', 'cp1'), ('袖口湿到肘部', 'cp2')]}),
            ('p4', 2, {'person_d': [('帽檐压得很低', 'dp1')]})]
    for point_id, seconds, changes in plan:
        previous = append_point(store, world_id, previous, point_id, seconds, changes)
    print(json.dumps({'worldId': world_id, 'points': ['point_1', 'p2', 'p3', 'p4'],
                      'last': previous}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
