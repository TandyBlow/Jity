"""A2-0: pin next-working-progress semantics against every trace and then the
synthetic edges the traces never cover.

Pinned rules (all 11 traces x 2 samples): begin starts from zero and does not
carry settledUnitIds over; discover/extend/close/seal/pause/resume/restore
leave working untouched; stage_unit advances the cursor by the actor count,
unions actors into actedIds/visitedIds (IdSet normalisation sorts them),
appends the unit id and consumes the input intent; record_skip advances the
cursor and visitedIds only; stage_time_scan closes every slot of the frozen
order at once and never consumes the intent. Committed progress in the round
summary stays untouched until commit_point promotes it.
"""
import json
from pathlib import Path

import pytest

from app.schemas.world.v2.contexts import WorkingProgress
from app.services.world.units import (
    begin_working, scan_working, skip_working, stage_working,
)

ROOT = Path(__file__).resolve().parents[2] / 'design/world-protocol/v2'
TRACE_IDS = ('T01', 'T02', 'T02-empty-linked', 'T03', 'T03-collapse', 'T04', 'T05', 'T06', 'T07', 'T08', 'T09')
STAGE_OPS = {'checkpoint_stage_unit', 'checkpoint_stage_time_scan'}


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


def order_of(trace_doc, values):
    for step in trace_doc['steps']:
        if step.get('responseKind') != 'success':
            continue
        if step.get('operation') == 'get_context':
            round_view = (step['response'].get('world') or {}).get('round')
            if round_view and round_view.get('order'):
                return instantiate(round_view['order'], values)
        if step.get('operation') == 'checkpoint_start_advance':
            return instantiate(step['request']['order'], values)
    raise AssertionError('trace exposes no frozen order')


def expected_working(prev, operation, request, response, order):
    if operation == 'checkpoint_stage_unit':
        unit_id = response['data']['unitId']
        return stage_working(prev, unit_id, request['candidates']['actorIds'])
    if operation == 'checkpoint_record_skip':
        return skip_working(prev, request['slotActorId'])
    if operation == 'checkpoint_stage_time_scan':
        return scan_working(prev, order)
    return prev


@pytest.mark.parametrize('trace_id', TRACE_IDS)
def test_working_evolution_matches_every_trace(trace_id):
    trace_doc = load_trace(trace_id)
    for sample in trace_doc['samples']:
        values = sample['values']
        order = order_of(trace_doc, values)
        prev = None
        head_before = None
        for step in trace_doc['steps']:
            operation = step.get('operation') or ''
            if step.get('responseKind') != 'success':
                continue
            response = instantiate(step['response'], values)
            work = response.get('work')
            request = instantiate(step.get('request') or {}, values)
            if operation == 'checkpoint_begin_point':
                round_view = (response.get('world') or {}).get('round') or {}
                committed = (round_view.get('cursor', 0),
                             round_view.get('actedIds', []),
                             round_view.get('visitedIds', []))
                expected = begin_working(committed, work['working']['intentStatus'])
                assert expected.model_dump(mode='json') == work['working']
                if round_view:
                    head_before = committed
                prev = expected
                continue
            if not (operation.startswith('checkpoint') or operation == 'commit_point'):
                continue
            round_view = (response.get('world') or {}).get('round')
            if round_view is not None:
                committed = (round_view['cursor'], round_view['actedIds'], round_view['visitedIds'])
                if operation == 'commit_point':
                    # commit promotes the head; its response work view is the
                    # consumed point and carries no working semantics to pin.
                    head_before = committed
                    continue
                elif head_before is not None:
                    assert committed == head_before, \
                        f'{trace_id} {step["id"]} moved committed progress'
            if work is None or work.get('working') is None:
                continue
            if prev is not None and operation in STAGE_OPS | {'checkpoint_record_skip'}:
                prev = expected_working(prev, operation, request, response, order)
            assert WorkingProgress.model_validate(work['working']).model_dump(mode='json') \
                == (prev.model_dump(mode='json') if prev is not None else work['working']), \
                f'{trace_id} {step["id"]} {operation} diverges'


def test_synthetic_edges_the_traces_do_not_cover():
    start = begin_working((0, [], []), 'pending')
    # out-of-order actors are normalised by the IdSet validator, not preserved
    staged = stage_working(start, 'unit_x', ['person_d', 'person_c'])
    assert staged.cursor == 2
    assert staged.actedIds == ['person_c', 'person_d']
    assert staged.visitedIds == ['person_c', 'person_d']
    assert staged.settledUnitIds == ['unit_x']
    assert staged.intentStatus == 'consumed'
    # skip/stage interleave without disturbing each other's sets
    skipped = skip_working(staged, 'person_b')
    assert skipped.cursor == 3
    assert skipped.actedIds == ['person_c', 'person_d']
    assert skipped.visitedIds == ['person_b', 'person_c', 'person_d']
    again = stage_working(skipped, 'unit_y', ['person_e'])
    assert again.cursor == 4
    assert again.actedIds == ['person_c', 'person_d', 'person_e']
    assert again.settledUnitIds == ['unit_x', 'unit_y']
    # a time-scan closes the whole remaining order and keeps the intent open
    order = ['person_a', 'person_b', 'person_c', 'person_d', 'person_e', 'person_f']
    scanned = scan_working(start, order)
    assert scanned.cursor == 6
    assert scanned.visitedIds == order
    assert scanned.intentStatus == 'pending'
