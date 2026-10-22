"""A1b-1: unit/coverage validation over every staged group and the control
ladder predicates replayed along each trace's checkpoint chain."""
import json
from pathlib import Path

import pytest

from app.schemas.world.v2.contexts import ControlState, PointWorkView
from app.schemas.world.v2.work import SettlementGroup
from app.services.world.ladder import check_checkpoint
from app.services.world.units import validate_commit_groups

ROOT = Path(__file__).resolve().parents[2] / 'design/world-protocol/v2'
TRACE_IDS = ('T01', 'T02', 'T02-empty-linked', 'T03', 'T03-collapse', 'T04', 'T05', 'T06', 'T07', 'T08', 'T09')
STAGE_OPS = ('checkpoint_stage_unit', 'checkpoint_stage_time_scan')
# Task coverage lists the world's full cast (T03-collapse stages one actor but
# still covers six), which the creation template fixes.
WORLD_ROSTER = frozenset(json.loads(
    (ROOT / 'traces' / 'T01.json').read_text(encoding='utf-8')
)['steps'][0]['request']['initial']['characters'])


def load_trace(trace_id):
    return json.loads((ROOT / 'traces' / f'{trace_id}.json').read_text(encoding='utf-8'))


def instantiate(node, values):
    if isinstance(node, dict):
        if set(node) == {'$var'}:
            return values[node['$var']]
        return {key: instantiate(item, values) for key, item in node.items()}
    if isinstance(node, list):
        return [instantiate(item, values) for item in node]
    return node


@pytest.mark.parametrize('trace_id', TRACE_IDS)
def test_staged_groups_pass_unit_and_coverage_validation(trace_id):
    trace_doc = load_trace(trace_id)
    for sample in trace_doc['samples']:
        values = sample['values']
        staged = [SettlementGroup.model_validate(instantiate(step['request']['candidates'], values))
                  for step in trace_doc['steps']
                  if step.get('operation') in STAGE_OPS
                  and step.get('responseKind') == 'success']
        violations = validate_commit_groups(staged, WORLD_ROSTER)
        if trace_id == 'T03-collapse':
            # Known-deviant fixture (2026-10-22 ruling): its group achieved a
            # task but declares personalityCoverage=actors; the workflow design
            # §6.3 requires the whole cast. The trace stays untouched, replay
            # does not validate, and refixturing goes through the A0 change
            # process before real traffic can stage such a unit.
            assert {violation.kind for violation in violations} == {'coverage'}
        else:
            assert violations == ()


def make_work(**overrides):
    base = {
        'pointId': 'p1', 'kind': 'normal',
        'timeAdvance': {'boundary': 'elapsed', 'duration': {'amount': 2, 'unit': 'second'}},
        'timeLocked': False, 'sealed': False, 'prefixDigest': None,
        'predecessorWorkDigest': None, 'timeScanComplete': False,
        'baseline': {'headPointId': 'root_0', 'version': 0, 'stateDigest': '0' * 64},
        'phase': 'select_actor',
        'working': {'cursor': 0, 'actedIds': [], 'visitedIds': [],
                    'settledUnitIds': [], 'intentStatus': 'pending'},
        'settledUnits': [], 'pendingGroup': None, 'successor': None,
    }
    return PointWorkView.model_validate({**base, **overrides})


def make_control(**overrides):
    base = {'phase': 'select_actor', 'paused': False, 'revision': 0,
            'gate': {'status': 'none'}, 'blockedReasons': [], 'canCompute': True}
    return ControlState.model_validate({**base, **overrides})


def test_unit_validation_catches_out_of_roster_character_keys():
    ghost = SettlementGroup.model_validate({
        'groupId': 'group_a', 'actorIds': ['person_a'],
        'positions': {}, 'appearances': {},
        'tasksAchieved': {'ghost': ['task_ghost']},
        'subtasksAdded': {}, 'personalities': {'person_b': [
            {'id': 'change_b', 'text': '变了。', 'supersedes': []}]},
        'sanities': {'person_b': 40},
        'taskCoverageIds': sorted(WORLD_ROSTER),
        'personalityCoverageIds': ['person_a'],
    })
    kinds = {violation.kind for violation in
             validate_commit_groups([ghost], WORLD_ROSTER)}
    assert kinds == {'roster', 'coverage'}
    full_cast = SettlementGroup.model_validate({
        'groupId': 'group_a', 'actorIds': ['person_a'],
        'positions': {}, 'appearances': {},
        'tasksAchieved': {'person_a': ['task_a']},
        'subtasksAdded': {}, 'personalities': {'person_b': [
            {'id': 'change_b', 'text': '变了。', 'supersedes': []}]},
        'sanities': {'person_b': 40},
        'taskCoverageIds': sorted(WORLD_ROSTER),
        'personalityCoverageIds': sorted(WORLD_ROSTER),
    })
    assert validate_commit_groups([full_cast], WORLD_ROSTER) == ()


def test_ladder_happy_path_and_refusals():
    work, control = make_work(), make_control()
    assert check_checkpoint('checkpoint_discover_group', work, control) == ()
    kinds = {violation.kind for violation in check_checkpoint(
        'checkpoint_extend_group', work, control)}
    assert kinds == {'phase', 'activePendingGroup'}
    for operation in ('checkpoint_set_point_time', 'checkpoint_record_skip'):
        for broken in (None, make_work(sealed=True, prefixDigest='a' * 64)):
            assert {violation.kind for violation in check_checkpoint(
                operation, broken, control)} >= {'pointWork'}, operation
    assert check_checkpoint('checkpoint_record_skip', work, control) == ()
    paused = make_control(paused=True, canCompute=False, blockedReasons=['paused'])
    assert {violation.kind for violation in check_checkpoint(
        'checkpoint_discover_group', work, paused)} == {'paused'}
    gated = make_control(canCompute=False, blockedReasons=['narration_pending'],
                         gate={'status': 'pending', 'generation': 1,
                               'issuedAtEpochMilli': 1, 'expiresAtEpochMilli': 2})
    assert {violation.kind for violation in check_checkpoint(
        'checkpoint_discover_group', work, gated)} == {'gate'}
    assert {violation.kind for violation in check_checkpoint(
        'checkpoint_set_point_time', make_work(timeLocked=True), control)} == {
        'timeLocked', 'confirmedWork'}
    assert check_checkpoint('checkpoint_seal_point',
                            make_work(sealed=True, prefixDigest='a' * 64),
                            make_control()) != ()


@pytest.mark.parametrize('trace_id', TRACE_IDS)
def test_ladder_holds_along_each_trace_checkpoint_chain(trace_id):
    trace_doc = load_trace(trace_id)
    for sample in trace_doc['samples']:
        values = sample['values']
        prev_work = prev_control = None
        seen_control = False
        for step in trace_doc['steps']:
            operation = step.get('operation') or ''
            ladder_op = (operation.startswith('checkpoint')
                         or operation in ('start_advance', 'commit_point'))
            narration_op = operation in ('narration_claim', 'narration_submit')
            if not (ladder_op or narration_op):
                continue
            if step.get('responseKind') != 'success':
                continue
            if seen_control and ladder_op:
                assert check_checkpoint(operation, prev_work, prev_control) == (), \
                    f'{trace_id} {step["id"]} {operation} breaks the ladder'
            response = instantiate(step['response'], values)
            work = response.get('work')
            control = response.get('control')
            if control is not None:
                prev_control = ControlState.model_validate(control)
                if not narration_op:
                    # A commit consumes the point's work view; the next
                    # begin_point runs against an absent work.
                    prev_work = PointWorkView.model_validate(work) if work else None
                seen_control = True
