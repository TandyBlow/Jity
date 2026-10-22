"""A1a-2: bind orphaned projection snapshots and staged-unit hashes to traces.

Kernel tests deliberately live outside the shared ``test_world_protocol_*``
glob: the common interface check stays byte-identical on both development
branches and must not learn about kernel modules. Expected values come only
from frozen traces and fixtures; nothing here calls a kernel apply.
"""
import json
from pathlib import Path

import pytest

from app.schemas.world.canonical import canonical_digest
from app.schemas.world.contracts import WorldState
from app.schemas.world.v2.work import SettlementGroup

ROOT = Path(__file__).resolve().parents[2] / 'design/world-protocol/v2'
STAGE_OPS = ('checkpoint_stage_unit', 'checkpoint_stage_time_scan')
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


def staged_candidates(trace_doc, values):
    staged = {}
    for step in trace_doc['steps']:
        if step.get('operation') in STAGE_OPS and step.get('responseKind') == 'success':
            candidates = instantiate(step['request']['candidates'], values)
            first = staged.setdefault(candidates.get('groupId'), candidates)
            assert first == candidates, 'group restaged with different candidates'
    return staged


@pytest.mark.parametrize('name,trace_id', [('normal', 'T01'), ('segmented', 'T02'), ('time', 'T03')])
def test_snapshot_binds_trace_final_state(name, trace_id):
    snapshot = json.loads(
        (ROOT / 'fixtures' / 'projections' / f'{name}.expected.json').read_text(encoding='utf-8'))
    snapshot_digest = canonical_digest(WorldState.model_validate(snapshot).model_dump(mode='json'))
    trace_doc = load_trace(trace_id)
    final_step = next(step for step in trace_doc['steps'] if step.get('digestPath') == '/data/stateDigest')
    matched = []
    for sample in trace_doc['samples']:
        state = WorldState.model_validate(instantiate(final_step['expectedProjection'], sample['values']))
        digest = canonical_digest(state.model_dump(mode='json'))
        assert digest == sample['expectedDigests'][final_step['id']]
        if digest == snapshot_digest:
            matched.append(sample['id'])
    assert matched, f'{name} snapshot binds no sample of {trace_id}'


@pytest.mark.parametrize('trace_id', TRACE_IDS)
def test_settled_unit_content_hash_is_candidates_digest(trace_id):
    trace_doc = load_trace(trace_id)
    for sample in trace_doc['samples']:
        values = sample['values']
        staged = staged_candidates(trace_doc, values)
        verified = 0
        for step in trace_doc['steps']:
            if step.get('responseKind') != 'success':
                continue
            for unit in ((step.get('response') or {}).get('work') or {}).get('settledUnits') or []:
                unit = instantiate(unit, values)
                if unit['groupId'] not in staged:
                    # Recovery/traceover scenarios (T07/T09) inherit units staged
                    # in earlier scenarios; their copy semantics belong to A3.
                    continue
                candidates = SettlementGroup.model_validate(staged[unit['groupId']])
                assert canonical_digest(candidates.model_dump(mode='json')) == unit['contentHash']
                verified += 1
        if any(step.get('operation') == 'checkpoint_stage_unit'
               and step.get('responseKind') == 'success' for step in trace_doc['steps']):
            assert verified, f'no settled unit verified in {trace_id}'
