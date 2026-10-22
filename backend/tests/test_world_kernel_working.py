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
from app.services.world.violations import KernelViolation, ViolationKind

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
    """The order shown by the last get_context before the first begin_point
    is the fresh round's frozen order (an earlier get_context may still show
    the previous scenario's completed round); a start_advance request carries
    it directly."""
    first_begin = next((index for index, step in enumerate(trace_doc['steps'])
                        if step.get('operation') == 'checkpoint_begin_point'), None)
    latest = None
    for index, step in enumerate(trace_doc['steps']):
        if first_begin is not None and index >= first_begin:
            break
        if step.get('responseKind') != 'success':
            continue
        if step.get('operation') == 'checkpoint_start_advance':
            return instantiate(step['request']['order'], values)
        if step.get('operation') == 'get_context':
            round_view = (step['response'].get('world') or {}).get('round')
            if round_view and round_view.get('order'):
                latest = instantiate(round_view['order'], values)
    if latest is not None:
        return latest
    raise AssertionError('trace exposes no frozen order')


def expected_working(prev, operation, request, response, order):
    if operation == 'checkpoint_stage_unit':
        unit_id = response['data']['unitId']
        return stage_working(prev, unit_id, request['candidates']['actorIds'], order)
    if operation == 'checkpoint_record_skip':
        return skip_working(prev, request['slotActorId'], order)
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
        # Operation-before state, observed from any response's world
        # projections — never from the response being asserted.
        head_before = None
        advance_intent = None
        for step in trace_doc['steps']:
            operation = step.get('operation') or ''
            if step.get('responseKind') != 'success':
                continue
            response = instantiate(step['response'], values)
            world = response.get('world') or {}
            work = response.get('work')
            request = instantiate(step.get('request') or {}, values)
            observed_round = world.get('round')
            observed_advance = world.get('advance')

            if operation == 'checkpoint_begin_point':
                assert head_before is not None and advance_intent is not None, \
                    f'{trace_id} {step["id"]} begin without an observed head/advance'
                expected = begin_working(head_before, advance_intent)
                assert expected.model_dump(mode='json') == work['working']
                prev = expected
            elif operation.startswith('checkpoint') or operation == 'commit_point':
                is_commit = operation == 'commit_point'
                if observed_round is not None:
                    committed = (observed_round['cursor'],
                                 observed_round['actedIds'],
                                 observed_round['visitedIds'])
                    if is_commit:
                        head_before = committed
                    elif head_before is not None:
                        assert committed == head_before, \
                            f'{trace_id} {step["id"]} moved committed progress'
                if is_commit:
                    # commit promotes the head; its response work view is the
                    # consumed point and pins no working semantics.
                    pass
                elif work is not None and work.get('working') is not None:
                    if prev is not None and operation in STAGE_OPS | {'checkpoint_record_skip'}:
                        prev = expected_working(prev, operation, request, response, order)
                    if prev is not None:
                        assert WorkingProgress.model_validate(work['working']).model_dump(mode='json') \
                            == prev.model_dump(mode='json'), \
                            f'{trace_id} {step["id"]} {operation} diverges'

            if observed_round is not None and observed_round.get('cursor') is not None:
                head_before = (observed_round['cursor'],
                               observed_round['actedIds'],
                               observed_round['visitedIds'])
            if observed_advance is not None and observed_advance.get('intentStatus') is not None:
                advance_intent = observed_advance['intentStatus']


def test_synthetic_edges_the_traces_do_not_cover():
    order = ['person_a', 'person_b', 'person_c', 'person_d', 'person_e', 'person_f']
    start = begin_working((0, [], []), 'pending')
    # out-of-order actors are normalised by the IdSet validator, not preserved
    staged = stage_working(skip_working(skip_working(start, 'person_a', order),
                                        'person_b', order),
                           'unit_x', ['person_d', 'person_c'], order)
    assert staged.cursor == 4
    assert staged.actedIds == ['person_c', 'person_d']
    assert staged.visitedIds == ['person_a', 'person_b', 'person_c', 'person_d']
    assert staged.settledUnitIds == ['unit_x']
    # the first handled action (here the skip) consumes the pending intent
    assert staged.intentStatus == 'consumed'
    # skip/stage interleave without disturbing each other's sets
    skipped = skip_working(staged, 'person_e', order)
    assert skipped.cursor == 5
    assert skipped.actedIds == ['person_c', 'person_d']
    again = stage_working(skipped, 'unit_y', ['person_f'], order)
    assert again.cursor == 6
    assert again.actedIds == ['person_c', 'person_d', 'person_f']
    assert again.visitedIds == order
    assert again.settledUnitIds == ['unit_x', 'unit_y']
    # pulling a later member never skips the slots in between (order A,B,C,D)
    pulled = stage_working(begin_working((0, [], []), 'pending'), 'unit_p',
                           ['person_a', 'person_d'], order[:4])
    assert pulled.cursor == 1
    assert pulled.visitedIds == ['person_a', 'person_d']
    # re-acting an actor that already acted is refused
    with pytest.raises(KernelViolation) as excinfo:
        stage_working(again, 'unit_z', ['person_c'], order)
    assert excinfo.value.kind is ViolationKind.SEMANTIC_INVALID
    # a time-scan closes the whole remaining order and keeps the intent open
    scanned = scan_working(start, order)
    assert scanned.cursor == 6
    assert scanned.visitedIds == order
    assert scanned.intentStatus == 'pending'
