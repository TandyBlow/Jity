"""A1a-3: the merge/collapse invariant over every successful commit, the T01
apply chain against the frozen anchors, and the T08 prefix-binding refusal.

Helpers mirror test_world_kernel_projections; backend/tests is not importable
as a package, so kernel test modules stay self-contained by convention.
"""
import json
from pathlib import Path

import pytest

from app.schemas.world.contracts import TimeAdvance, TimelinePoint, WorldInitialState
from app.schemas.world.v2.work import SettlementGroup
from app.services.world.apply import apply_point
from app.services.world.commit import verify_point_binding
from app.services.world.merge import point_entity_deltas
from app.services.world.state import build_initial_state, state_digest
from app.services.world.violations import KernelViolation, ViolationKind

ROOT = Path(__file__).resolve().parents[2] / 'design/world-protocol/v2'
TRACE_IDS = ('T01', 'T02', 'T02-empty-linked', 'T03', 'T03-collapse', 'T04', 'T05', 'T06', 'T07', 'T08', 'T09')


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


def successful_commits(trace_doc, values):
    for step in trace_doc['steps']:
        if step.get('operation') == 'commit_point' and step.get('responseKind') == 'success':
            request = instantiate(step['request'], values)
            yield ([SettlementGroup.model_validate(group)
                    for group in request['settlementGroups']], request['point'])


def saved_time_scan(trace_doc, values):
    for step in trace_doc['steps']:
        if (step.get('operation') == 'checkpoint_stage_time_scan'
                and step.get('responseKind') == 'success'):
            return SettlementGroup.model_validate(
                instantiate(step['request']['candidates'], values))
    return None


@pytest.mark.parametrize('trace_id', TRACE_IDS)
def test_committed_entity_deltas_collapse_merged_groups(trace_id):
    trace_doc = load_trace(trace_id)
    for sample in trace_doc['samples']:
        values = sample['values']
        time_scan = saved_time_scan(trace_doc, values)
        for groups, point in successful_commits(trace_doc, values):
            merged = point_entity_deltas(groups, time_scan)
            assert {key: delta.model_dump(mode='json')
                    for key, delta in merged.items()} == point['entityDeltas']


def test_t01_root_and_apply_chain_matches_anchors():
    snapshot = json.loads(
        (ROOT / 'fixtures/projections/normal.expected.json').read_text(encoding='utf-8'))
    state = build_initial_state(WorldInitialState.model_validate(snapshot['initial']))
    trace_doc = load_trace('T01')
    values = trace_doc['samples'][0]['values']
    assert state_digest(state) == values['v4']
    commit = next(successful_commits(trace_doc, values))
    final = apply_point(state, TimelinePoint.model_validate(commit[1]))
    assert state_digest(final) == trace_doc['samples'][0]['expectedDigests']['s21']


def test_t08_prefix_binding_refusal():
    trace_doc = load_trace('T08')
    values = trace_doc['samples'][0]['values']
    begin = next(step for step in trace_doc['steps']
                 if step.get('operation') == 'checkpoint_begin_point'
                 and step.get('responseKind') == 'success')
    sealed = TimeAdvance.model_validate(instantiate(begin['request']['timeAdvance'], values))
    commits = {step['id']: TimelinePoint.model_validate(
        instantiate(step['request'], values)['point'])
        for step in trace_doc['steps'] if step.get('operation') == 'commit_point'}
    with pytest.raises(KernelViolation) as excinfo:
        verify_point_binding(commits['s9'], 'normal', sealed)
    assert excinfo.value.kind is ViolationKind.PREFIX_BINDING
    verify_point_binding(commits['s10'], 'normal', sealed)
