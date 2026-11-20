"""A1b-2: negative cases pinned to their violation taxonomy and exit mapping,
plus the pure-removal chain and calendar clamping fixtures.

Refusals that live in the schema layer surface as pydantic ValidationError;
kernel-layer refusals surface as KernelViolation with a ViolationKind. The
A2 exit-code mapping lives in a1-kernel-plan §四.
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.world.contracts import (
    EntityDelta, TimeAdvance, TimelinePoint, WorldInitialState, WorldTime,
)
from app.schemas.world.v2.work import SettlementGroup
from app.services.world.apply import apply_point
from app.services.world.merge import point_entity_deltas
from app.services.world.replay import replay_world
from app.services.world.state import build_initial_state, state_digest
from app.services.world.timing import advance_time
from app.services.world.units import validate_commit_groups
from app.services.world.violations import KernelViolation, ViolationKind

FIXTURES = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'world'


def make_group(payload):
    return SettlementGroup.model_validate(payload)


def test_month_and_year_additions_clamp_to_month_end():
    cases = json.loads((FIXTURES / 'month-end-cases.json').read_text(encoding='utf-8'))['cases']
    for case in cases:
        moment = advance_time(
            WorldTime.model_validate({'calendar': 'gregorian',
                                      'dateTime': case['from'], 'instantOrdinal': 5}),
            TimeAdvance.model_validate(case['advance']))
        assert moment.dateTime == case['dateTime'], case
        assert moment.instantOrdinal == case['ordinal'], case


def test_pure_removal_chain_matches_fixture():
    fixture = json.loads((FIXTURES / 'pure-removal.json').read_text(encoding='utf-8'))
    state = build_initial_state(WorldInitialState.model_validate(fixture['initial']))
    points = []
    for entry in fixture['points']:
        deltas = {key: EntityDelta.model_validate(delta)
                  for key, delta in entry['deltas'].items()}
        points.append(TimelinePoint.model_validate({
            'worldId': fixture['initial']['worldId'], 'id': entry['pointId'],
            'sequence': entry['sequence'], 'kind': 'normal',
            'previousPointId': 'root_0', 'roundId': 'round_f', 'advanceId': 'advance_f',
            'trigger': 'player', 'linkedFromPointId': None,
            'timeAdvance': entry['timeAdvance'], 'entityDeltas': deltas}))
    final = replay_world(state, points)
    assert final.time.dateTime == fixture['expect']['time']['dateTime']
    assert final.time.instantOrdinal == fixture['expect']['time']['instantOrdinal']
    stored = final.items['item_a'].appearanceChanges
    for index, expected in enumerate(fixture['expect']['item_a']['appearanceChanges']):
        change = stored[index]
        assert change.id == expected['id']
        assert change.active is expected['active']
        assert change.sourcePointId == expected['sourcePointId']
        assert change.sourceSequence == expected['sourceSequence']
        assert change.text == expected.get('text')


def test_cross_unit_actor_reuse_is_refused():
    roster = frozenset({'person_a', 'person_b'})
    groups = [make_group({'groupId': 'g1', 'actorIds': ['person_a'],
                          'positions': {}, 'appearances': {}, 'tasksAchieved': {},
                          'subtasksAdded': {}, 'personalities': {}, 'sanities': {},
                          'taskCoverageIds': sorted(roster), 'personalityCoverageIds': []}),
              make_group({'groupId': 'g2', 'actorIds': ['person_a'],
                          'positions': {}, 'appearances': {}, 'tasksAchieved': {},
                          'subtasksAdded': {}, 'personalities': {}, 'sanities': {},
                          'taskCoverageIds': sorted(roster), 'personalityCoverageIds': []})]
    kinds = {violation.kind for violation in validate_commit_groups(groups, roster)}
    assert kinds == {'semantic_invalid'}


def test_cross_point_supersedes_within_one_point_is_schema_refused():
    roster = frozenset({'person_a'})
    first = make_group({'groupId': 'g1', 'actorIds': ['person_a'],
                        'positions': {}, 'appearances': {'person_a': [
                            {'id': 'ch_x', 'text': '第一句', 'supersedes': []}]},
                        'tasksAchieved': {}, 'subtasksAdded': {},
                        'personalities': {}, 'sanities': {},
                        'taskCoverageIds': ['person_a'], 'personalityCoverageIds': []})
    second = make_group({'groupId': 'g2', 'actorIds': ['person_a'],
                         'positions': {}, 'appearances': {'person_a': [
                             {'id': 'ch_y', 'text': '第二句', 'supersedes': ['ch_x']}]},
                         'tasksAchieved': {}, 'subtasksAdded': {},
                         'personalities': {}, 'sanities': {},
                         'taskCoverageIds': ['person_a'], 'personalityCoverageIds': []})
    with pytest.raises(ValidationError):
        point_entity_deltas([first, second], None)


def test_task_cycle_in_merged_delta_is_schema_refused():
    group = make_group({'groupId': 'g1', 'actorIds': ['person_a'],
                        'positions': {}, 'appearances': {},
                        'tasksAchieved': {},
                        'subtasksAdded': {'person_a': [
                            {'id': 't_a', 'ownerId': 'person_a', 'parentTaskId': 't_b',
                             'goal': 'a', 'status': 'pending'},
                            {'id': 't_b', 'ownerId': 'person_a', 'parentTaskId': 't_a',
                             'goal': 'b', 'status': 'pending'}]},
                        'personalities': {}, 'sanities': {},
                        'taskCoverageIds': ['person_a'], 'personalityCoverageIds': []})
    with pytest.raises(ValidationError):
        point_entity_deltas([group], None)


def _world_and_state():
    fixture = json.loads((FIXTURES / 'pure-removal.json').read_text(encoding='utf-8'))
    return fixture, build_initial_state(WorldInitialState.model_validate(fixture['initial']))


def _point(state, world_id, point_id, sequence, time_amount, deltas):
    return TimelinePoint.model_validate({
        'worldId': world_id, 'id': point_id, 'sequence': sequence, 'kind': 'normal',
        'previousPointId': 'root_0', 'roundId': 'round_f', 'advanceId': 'advance_f',
        'trigger': 'player', 'linkedFromPointId': None,
        'timeAdvance': {'boundary': 'elapsed',
                        'duration': {'amount': time_amount, 'unit': 'second'}},
        'entityDeltas': deltas})


@pytest.mark.parametrize('position,kind', [
    ({'containerId': 'room_missing', 'slotId': None, 'relativeTo': None}, ViolationKind.ID_UNRESOLVED),
    ({'containerId': 'room_a', 'slotId': 'nope', 'relativeTo': None}, ViolationKind.ID_UNRESOLVED),
    ({'containerId': 'room_a', 'slotId': None,
      'relativeTo': {'entityId': 'ghost', 'relation': 'beside'}}, ViolationKind.ID_UNRESOLVED),
])
def test_position_reference_refusals(position, kind):
    fixture, state = _world_and_state()
    world_id = fixture['initial']['worldId']
    point = _point(state, world_id, 'p1', 1, 1,
                   {'person_a': {'entityId': 'person_a', 'positionSet': position}})
    with pytest.raises(KernelViolation) as excinfo:
        apply_point(state, point)
    assert excinfo.value.kind is kind


def test_cross_room_relative_reference_is_refused():
    fixture = json.loads((FIXTURES / 'pure-removal.json').read_text(encoding='utf-8'))
    initial = dict(fixture['initial'])
    initial['locations']['room_b'] = {
        'id': 'room_b', 'name': 'B 房间', 'parentLocationId': None,
        'initialAppearance': '另一间', 'slots': []}
    initial['items']['item_b'] = {
        'id': 'item_b', 'name': '石凳',
        'initialPosition': {'containerId': 'room_b', 'slotId': None, 'relativeTo': None},
        'initialAppearance': '冰冷', 'slots': []}
    state = build_initial_state(WorldInitialState.model_validate(initial))
    point = _point(state, initial['worldId'], 'p1', 1, 1,
                   {'person_a': {'entityId': 'person_a', 'positionSet': {
                       'containerId': 'room_a', 'slotId': None,
                       'relativeTo': {'entityId': 'item_b', 'relation': 'beside'}}}})
    with pytest.raises(KernelViolation) as excinfo:
        apply_point(state, point)
    assert excinfo.value.kind is ViolationKind.SEMANTIC_INVALID


def test_same_room_relative_reference_is_accepted():
    fixture, state = _world_and_state()
    world_id = fixture['initial']['worldId']
    point = _point(state, world_id, 'p1', 1, 1,
                   {'person_a': {'entityId': 'person_a', 'positionSet': {
                       'containerId': 'room_a', 'slotId': None,
                       'relativeTo': {'entityId': 'item_a', 'relation': 'beside'}}}})
    final = apply_point(state, point)
    assert final.characters['person_a'].position.relativeTo.entityId == 'item_a'


def _multi_room_state():
    fixture = json.loads((FIXTURES / 'pure-removal.json').read_text(encoding='utf-8'))
    initial = dict(fixture['initial'])
    initial['locations']['room_b'] = {
        'id': 'room_b', 'name': 'B 房间', 'parentLocationId': None,
        'initialAppearance': '另一间', 'slots': []}
    initial['items']['item_b'] = {
        'id': 'item_b', 'name': '石凳',
        'initialPosition': {'containerId': 'room_b', 'slotId': None, 'relativeTo': None},
        'initialAppearance': '冰冷', 'slots': []}
    return initial, build_initial_state(WorldInitialState.model_validate(initial))


def test_joint_final_graph_is_order_independent():
    initial, state = _multi_room_state()
    world_id = initial['worldId']
    # The reference is item_a — the entity that actually moves. Under the
    # per-entity implementation the person processed first saw item_a still
    # in room_a and was refused, so this exact scenario locks the fix.
    person_move = {'entityId': 'person_a', 'positionSet': {
        'containerId': 'room_b', 'slotId': None,
        'relativeTo': {'entityId': 'item_a', 'relation': 'beside'}}}
    item_move = {'entityId': 'item_a', 'positionSet': {
        'containerId': 'room_b', 'slotId': None, 'relativeTo': None}}
    digests = []
    for deltas in ({'person_a': person_move, 'item_a': item_move},
                   {'item_a': item_move, 'person_a': person_move}):
        digests.append(state_digest(apply_point(
            state, _point(state, world_id, 'p1', 1, 1, deltas))))
    assert digests[0] == digests[1]


def test_dangling_relative_after_reference_move_is_refused():
    initial, state = _multi_room_state()
    world_id = initial['worldId']
    settle = _point(state, world_id, 'p1', 1, 1,
                    {'person_a': {'entityId': 'person_a', 'positionSet': {
                        'containerId': 'room_a', 'slotId': None,
                        'relativeTo': {'entityId': 'item_a', 'relation': 'beside'}}}})
    settled = apply_point(state, settle)
    move = _point(settled, world_id, 'p2', 2, 1,
                  {'item_a': {'entityId': 'item_a', 'positionSet': {
                      'containerId': 'room_b', 'slotId': None, 'relativeTo': None}}})
    with pytest.raises(KernelViolation) as excinfo:
        apply_point(settled, move)
    assert excinfo.value.kind is ViolationKind.SEMANTIC_INVALID


def test_self_container_cycle_is_refused():
    fixture, state = _world_and_state()
    world_id = fixture['initial']['worldId']
    point = _point(state, world_id, 'p1', 1, 1,
                   {'person_a': {'entityId': 'person_a', 'positionSet': {
                       'containerId': 'person_a', 'slotId': None, 'relativeTo': None}}})
    with pytest.raises(KernelViolation) as excinfo:
        apply_point(state, point)
    assert excinfo.value.kind is ViolationKind.SEMANTIC_INVALID


def test_mixed_relative_container_cycle_is_refused():
    initial, state = _multi_room_state()
    world_id = initial['worldId']
    point = _point(state, world_id, 'p1', 1, 1, {
        'person_a': {'entityId': 'person_a', 'positionSet': {
            'containerId': 'room_a', 'slotId': None,
            'relativeTo': {'entityId': 'item_a', 'relation': 'beside'}}},
        'item_a': {'entityId': 'item_a', 'positionSet': {
            'containerId': 'person_a', 'slotId': None, 'relativeTo': None}}})
    with pytest.raises(KernelViolation) as excinfo:
        apply_point(state, point)
    assert excinfo.value.kind is ViolationKind.SEMANTIC_INVALID
