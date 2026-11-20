"""Two isomorphic worlds: the N4 training world and the protocol fixture world.

Both go through the authority writer (service flow for the first point, then
``store.transact``), so every round's facts come from real commits. Each
world carries the SAME round specs: same fact kinds, same counts, same event
structure — only the vocabulary differs.
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

N4_WORLD = ROOT / '.local/world-components-worktree/experiments/world-components/n4_narrative_dev/world.json'

# Five rounds, identical shape on both sides.
#   round = three points: p1 (two changes for X), p2 (one change for Y),
#   p3 (two changes for Z). Relation requested: Y --> Z.
ROUNDS = [
    {'changes': [('袖口沾了雨', 'ap1'), ('指节发白', 'ap2')], 'second': '斗篷下摆湿了一片',
     'third': ['鞋底沾了泥', '袖口湿到肘部']},
    {'changes': [('灯罩蒙了灰', 'ap1'), ('掌心出汗', 'ap2')], 'second': '钟绳磨出了毛边',
     'third': ['衣角结了盐霜', '鬓发被雾打湿']},
    {'changes': [('被雨打湿半幅', 'ap1'), ('袖口开了线', 'ap2')], 'second': '指缝里塞着泥',
     'third': ['鞋跟磨塌了', '裤脚沾了铜油']},
    {'changes': [('围巾松开一截', 'ap1'), ('脸色发白', 'ap2')], 'second': '背上溅了泥点',
     'third': ['手背蹭破了皮', '肩头落着灰']},
    {'changes': [('帽檐压出折痕', 'ap1'), ('脚踝肿了一块', 'ap2')], 'second': '衣领被雨浸透',
     'third': ['指尖磨出茧', '膝盖沾了泥']},
]


def fixture_initial():
    snapshot = json.loads((ROOT / 'design/world-protocol/v2/fixtures/projections/'
                                  'normal.expected.json').read_text(encoding='utf-8'))
    initial = snapshot['initial']
    del initial['worldId']
    names = {'person_a': '林川', 'person_b': '周宁', 'person_c': '陈默',
             'person_d': '沈禾', 'person_e': '叶南', 'person_f': '高岭'}
    for entity_id, name in names.items():
        initial['characters'][entity_id]['name'] = name
    initial['initialTime'] = {'calendar': 'gregorian',
                              'dateTime': '2026-11-02T21:00:00', 'instantOrdinal': 0}
    return initial, ['person_a', 'person_b', 'person_c']


def training_initial():
    """The N4 training world mapped onto the engine's initial-state schema."""
    world = json.loads(N4_WORLD.read_text(encoding='utf-8'))
    locations, items, characters = {}, {}, {}
    for key, value in world['locations'].items():
        locations[key] = {
            'id': key, 'name': value['name'], 'parentLocationId': None,
            'initialAppearance': value.get('appearance') or value['name'],
            'slots': [],
            # keep the vocabulary that the narration model was trained on
            'sublocations': value.get('sublocations', []),
        }
    # The engine only accepts extra keys on its own models, so the vocabulary
    # rides in the appearance text instead of side fields.
    for key, value in world['locations'].items():
        names = '、'.join(sub['name'] for sub in value.get('sublocations', []))
        locations[key]['initialAppearance'] = (
            (value.get('appearance') or value['name']) + (f'（含{names}）' if names else ''))
        locations[key].pop('sublocations', None)
    first_location = next(iter(locations))
    for key, value in world['items'].items():
        items[key] = {'id': key, 'name': value['name'],
                      'initialPosition': {'containerId': first_location, 'slotId': None,
                                          'relativeTo': None},
                      'initialAppearance': value.get('appearance') or value['name'], 'slots': []}
    for key, value in world['characters'].items():
        characters[key] = {
            'id': key, 'name': value['name'],
            'initialPosition': {'containerId': first_location, 'slotId': None,
                                'relativeTo': None},
            'initialAppearance': value.get('appearance') or value['name'], 'slots': [],
            'initialPersonality': value.get('personality') or '沉默', 'initialSanity': 10,
            'tasks': {},
        }
    initial = {'engineVersion': 'world-engine-v1', 'schemaVersion': 1,
               'protagonistId': 'char_shen',
               'initialTime': {'calendar': 'gregorian',
                               'dateTime': '2026-11-02T21:00:00', 'instantOrdinal': 0},
               'locations': locations, 'items': items, 'characters': characters}
    return initial, ['char_shen', 'char_gu', 'char_ye']


ROSTER = []


def group_of(group_id, entity_id, changes):
    return flow.single_group(
        [entity_id], frozenset(ROSTER), group_id,
        appearances={entity_id: [{'id': change_id, 'text': text, 'supersedes': []}
                                 for text, change_id in changes]})


def first_point(service, initial, entity_id, changes, tag, roster):
    flow.initial_template = lambda: initial
    state = flow.begin_work(service)
    world_id, root_id, point_id = state['world_id'], state['root_id'], state['point_id']
    group_id, lease, revision = state['group_id'], state['lease'], state['revision']
    allocation = flow._run(service, 'allocate_ids', flow._payload(
        f'{tag}_changes', world_id, lease, allocationKey=f'{tag}_changes',
        slots=[{'slotKey': key, 'kind': 'change', 'scope': None}
               for key in ('c1', 'c2')]), flow.AllocateIdsSuccess)
    ids = {item['slotKey']: item['id'] for item in allocation['data']['allocations']}
    changes = [(changes[0][0], ids['c1']), (changes[1][0], ids['c2'])]
    roster = roster

    def checkpoint(tag_, operation, **fields):
        nonlocal revision
        envelope = flow._run(service, operation, flow._payload(
            f'{tag}_{tag_}_{revision}', world_id, lease,
            operation=operation.removeprefix('checkpoint_'),
            expectedPointId=root_id, expectedVersion=0,
            expectedCheckpointRevision=revision, pointId=point_id, **fields),
            flow._CHECKPOINT_SUCCESS[operation])
        revision += 1
        return envelope

    group = group_of(group_id, entity_id, changes)
    checkpoint('discover', 'checkpoint_discover_group', groupId=group_id,
               initiatorId=entity_id, actionText='抬起手。', targetIds=None)
    checkpoint('extend', 'checkpoint_extend_group', groupId=group_id,
               sourceId=entity_id, targets=[], admittedMember=None)
    checkpoint('close', 'checkpoint_close_group', groupId=group_id)
    checkpoint('stage', 'checkpoint_stage_unit', groupId=group_id, candidates=group,
               results={entity_id: '抬起手。'})
    for index, actor in enumerate(roster[1:], start=1):
        checkpoint(f'skip{index}', 'checkpoint_record_skip', slotActorId=actor)
    checkpoint('seal', 'checkpoint_seal_point')

    merged = flow.point_entity_deltas([group], None)
    request = {
        'protocolVersion': 2, 'requestId': f'{tag}_commit', 'worldId': world_id,
        'advanceId': state['advance_id'], 'roundId': state['round_id'],
        'expectedPointId': root_id, 'expectedVersion': 0,
        'expectedCheckpointRevision': revision, 'leaseToken': lease['leaseToken'],
        'fenceEpoch': lease['fenceEpoch'], 'pointId': point_id,
        'point': {'worldId': world_id, 'id': point_id, 'sequence': 1, 'kind': 'normal',
                  'previousPointId': root_id, 'roundId': state['round_id'],
                  'advanceId': state['advance_id'], 'trigger': 'player',
                  'linkedFromPointId': None,
                  'timeAdvance': {'boundary': 'elapsed',
                                  'duration': {'amount': 2, 'unit': 'second'}},
                  'entityDeltas': {key: delta.model_dump(mode='json')
                                   for key, delta in merged.items()}},
        'settlementGroups': [group]}
    flow._run(service, 'commit_point', request, CommitPointSuccess)
    return world_id, point_id


def append(store, world_id, previous, point_id, seconds, entity_id, texts):
    def handler(snapshot):
        prior = snapshot['points'].get(previous)
        if prior is None:
            sequence, round_id, advance_id = 0, snapshot['round']['roundId'],                 snapshot['advance']['advanceId']
            base_state = snapshot['pointStates'][previous]['state']
        else:
            sequence, round_id, advance_id = prior.sequence, prior.roundId, prior.advanceId
            base_state = snapshot['pointStates'][prior.id]['state']
        point = TimelinePoint.model_validate({
            'worldId': world_id, 'id': point_id, 'sequence': sequence + 1,
            'kind': 'normal', 'previousPointId': previous, 'roundId': round_id,
            'advanceId': advance_id, 'trigger': 'player', 'linkedFromPointId': None,
            'timeAdvance': {'boundary': 'elapsed',
                            'duration': {'amount': seconds, 'unit': 'second'}},
            'entityDeltas': {entity_id: EntityDelta.model_validate({
                'entityId': entity_id,
                'appearanceChanges': [{'id': f'{point_id}_{index}', 'text': text,
                                       'supersedes': []}
                                      for index, text in enumerate(texts, 1)]
            }).model_dump(mode='json')}})
        state = apply_point(base_state, point)
        snapshot['points'][point.id] = point
        snapshot['pointStates'][point.id] = {'state': state, 'stateDigest': state_digest(state)}
        snapshot['narrations'][point.id] = {'status': 'ready', 'generation': 1, 'text': ''}
        return point.id

    return store.transact(world_id, handler)


def build(side, initial, entities, db_path):
    global ROSTER
    ROSTER = list(initial['characters'].keys())
    flow.ORDER = ROSTER            # a player round freezes the whole roster
    store = SQLiteBaselineStore(db_path)
    service = WorldService(store)
    rounds = []
    previous = None
    for index, spec in enumerate(ROUNDS, start=1):
        first_entity, second_entity, third_entity = entities
        if previous is None:
            flow.initial_template = lambda: initial
            state = flow.open_round(service)
            world_id = state['world_id']
            previous = state['root_id']
        else:
            world_id = store_lock['world_id']
        previous = append(store, world_id, previous, f'{side}_r{index}_p1', 2,
                          first_entity, [text for text, _ in spec['changes']])
        store_lock['world_id'] = world_id
        second = append(store, world_id, previous, f'{side}_r{index}_p2', 3,
                        second_entity, [spec['second']])
        third = append(store, world_id, second, f'{side}_r{index}_p3', 1,
                       third_entity, spec['third'])
        rounds.append({'round': index, 'points': [previous, second, third],
                       'worldId': world_id})
        previous = third
    return rounds


store_lock = {'world_id': None}


def main(base):
    base = Path(base)
    result = {}
    for side, (initial, entities) in (('train', training_initial()),
                                      ('fixture', fixture_initial())):
        path = base / f'{side}.db'
        if path.exists():
            path.unlink()
        result[side] = build(side, initial, entities, str(path))
    out = Path(base) / 'pair-worlds.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({side: [r['points'] for r in rounds]
                      for side, rounds in result.items()}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
