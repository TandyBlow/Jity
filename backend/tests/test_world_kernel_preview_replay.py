"""A1a-4/5/6: the time-lock predicate, preview anchors (T01 s16) and full
replay of all traces over both samples from branch-start states rebuilt off
the root. Start states are constructed, never taken from snapshots: the root
digest varies per sample because the server-assigned worldId enters the state.
"""
import json
from pathlib import Path

import pytest

from app.schemas.world.contracts import TimelinePoint, WorldInitialState
from app.schemas.world.v2.work import SettlementGroup
from app.services.world.apply import apply_point
from app.services.world.preview import preview_over_budget, preview_point
from app.services.world.replay import replay_world
from app.services.world.state import build_initial_state, state_digest
from app.services.world.timing import time_lock_trigger

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
            yield instantiate(step['request'], values)['point']


def world_id_of(trace_doc, values):
    for step in trace_doc['steps']:
        if step.get('operation') == 'create_world':
            return values[step['response']['data']['worldId']['$var']]
        if step.get('operation') == 'get_context':
            return values[step['response']['world']['worldId']['$var']]
    raise AssertionError('trace exposes no worldId')


def head_digest_of(trace_doc, values):
    for step in trace_doc['steps']:
        if step.get('operation') == 'get_context':
            head = step['response']['world']['head']['stateDigest']
            return values[head['$var']] if isinstance(head, dict) else head
    return None


CREATION = json.loads(
    (ROOT / 'traces' / 'T01.json').read_text(encoding='utf-8'))['steps'][0]['request']['initial']

# The branch points come from T02 under T02's own variable space (entity deltas
# are empty and the wire ids p1/p2/p3 are fixed; roundId/advanceId never enter
# the state, so one instantiation serves every sample and trace).
_T02_DOC = load_trace('T02')
_T02_VALUES = _T02_DOC['samples'][0]['values']
BRANCH_POINTS = [TimelinePoint.model_validate(instantiate(point, _T02_VALUES))
                 for point in successful_commits(_T02_DOC, _T02_VALUES)]


def sample_start_states(world_id):
    """The three branch starts, rebuilt off the root for one worldId."""
    root = build_initial_state(WorldInitialState.model_validate({'worldId': world_id, **CREATION}))
    timed = apply_point(root, BRANCH_POINTS[0])
    segmented = apply_point(apply_point(timed, BRANCH_POINTS[1]), BRANCH_POINTS[2])
    return {state_digest(root): root, state_digest(timed): timed,
            state_digest(segmented): segmented}


@pytest.mark.parametrize('trace_id', TRACE_IDS)
def test_replay_from_branch_start_matches_expected_digest(trace_id):
    trace_doc = load_trace(trace_id)
    for sample in trace_doc['samples']:
        values = sample['values']
        starts = sample_start_states(world_id_of(trace_doc, values))
        head = head_digest_of(trace_doc, values) or next(iter(starts))
        assert head in starts, f'{trace_id} starts from an unknown branch digest'
        points = [TimelinePoint.model_validate(point)
                  for point in successful_commits(trace_doc, values)]
        final = replay_world(starts[head], points)
        assert len(sample['expectedDigests']) == 1
        assert state_digest(final) == next(iter(sample['expectedDigests'].values()))


def test_t01_preview_matches_trace_anchor():
    from app.schemas.world.v2.requests import PreviewData

    trace_doc = load_trace('T01')
    values = trace_doc['samples'][0]['values']
    starts = sample_start_states(world_id_of(trace_doc, values))
    root_key = state_digest(build_initial_state(WorldInitialState.model_validate(
        {'worldId': world_id_of(trace_doc, values), **CREATION})))
    step = next(step for step in trace_doc['steps'] if step['id'] == 's16')
    request = instantiate(step['request'], values)
    response = instantiate(step['response'], values)
    point = TimelinePoint.model_validate(response['data']['pointProjection'])
    preview = preview_point(starts[root_key], point,
                            [SettlementGroup.model_validate(group)
                             for group in request['settlementGroups']])
    PreviewData.model_validate(preview)
    assert preview['workingStateDigest'] == response['data']['workingStateDigest']
    assert preview['pointProjectionDigest'] == response['data']['pointProjectionDigest']
    assert preview['mergedEntityDeltas'] == response['data']['mergedEntityDeltas']


def test_t03_time_only_preview_matches_commit_outcome():
    trace_doc = load_trace('T03')
    values = trace_doc['samples'][0]['values']
    starts = sample_start_states(world_id_of(trace_doc, values))
    root_key = state_digest(build_initial_state(WorldInitialState.model_validate(
        {'worldId': world_id_of(trace_doc, values), **CREATION})))
    scan_step = next(step for step in trace_doc['steps']
                     if step.get('operation') == 'checkpoint_stage_time_scan'
                     and step.get('responseKind') == 'success')
    scan = SettlementGroup.model_validate(
        instantiate(scan_step['request']['candidates'], values))
    commit_step = next(step for step in trace_doc['steps']
                       if step.get('operation') == 'commit_point'
                       and step.get('responseKind') == 'success')
    point_wire = instantiate(commit_step['request'], values)['point']
    point_wire['entityDeltas'] = {}
    projection = TimelinePoint.model_validate(point_wire)
    preview = preview_point(starts[root_key], projection, [scan])
    assert preview['workingStateDigest'] == next(
        iter(trace_doc['samples'][0]['expectedDigests'].values()))


def test_time_lock_predicate_covers_the_four_confirmed_events():
    # discover_group fires action_confirmed on the saved actionText alone:
    # T01 s7 carries actionText with targetIds=null and time is locked there.
    assert time_lock_trigger('action_confirmed')
    for event in ('target_confirmed', 'member_admitted', 'skip_recorded', 'time_scan_staged'):
        assert time_lock_trigger(event)
    for event in ('begin_point', 'seal_point', 'unit_staged', 'discover_unconfirmed', ''):
        assert not time_lock_trigger(event)


def test_preview_budget_predicate():
    assert preview_over_budget(512 * 1024) is None
    assert preview_over_budget(512 * 1024 + 1) == ('request', 512 * 1024)
    assert preview_over_budget(0, 2 * 1024 * 1024) is None
    assert preview_over_budget(0, 2 * 1024 * 1024 + 1) == ('response', 2 * 1024 * 1024)
