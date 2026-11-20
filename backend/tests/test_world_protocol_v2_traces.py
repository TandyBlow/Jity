"""Two dynamic identity/ownership/clock samples and independent full states."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend/scripts'))
from world_trace_expected import validate_trace

BASE=ROOT/'design/world-protocol/v2/traces'
PATHS=sorted(BASE.glob('T*.json'))


@pytest.mark.parametrize('path',PATHS,ids=lambda p:p.stem)
def test_both_dynamic_samples_have_independent_projection_hashes(path):
    trace=json.loads(path.read_text(encoding='utf-8'))
    result=validate_trace(trace)
    assert len(result)==2
    assert result['sample_1']!=result['sample_2']
    assert trace['acceptanceLayer']=='contract'
    assert trace['runtimeTarget'] in ('runtime-A2','runtime-A3')


@pytest.mark.parametrize('mutation',['old_hash','changed_identity','changed_business','wrong_order','epoch_not_incremented'])
def test_semantic_trace_mutations_fail(mutation):
    name='T07' if mutation=='epoch_not_incremented' else 'T01'
    trace=json.loads((BASE/f'{name}.json').read_text(encoding='utf-8'))
    if mutation=='old_hash':trace['samples'][1]['expectedDigests']=copy.deepcopy(trace['samples'][0]['expectedDigests'])
    elif mutation=='changed_identity':
        variable=next(v for v in trace['variables'] if v['name'] in json.dumps(trace['steps'][-3]['expectedProjection']))
        trace['samples'][1]['values'][variable['name']]='different_identity'
    elif mutation=='changed_business':
        step=next(s for s in trace['steps'] if s['expectedProjection'] is not None)
        step['expectedProjection']['characters']['person_a']['sanity']=99
    elif mutation=='wrong_order':
        step=next(s for s in trace['steps'] if s['operation']=='checkpoint_start_advance')
        step['response']['world']['round']['order'].reverse()
    else:
        field=trace['steps'][0]['response']['data']['fenceEpoch']['$var']
        trace['samples'][0]['values'][field]=trace['samples'][0]['values']['previous_epoch']
    with pytest.raises(Exception):validate_trace(trace)
