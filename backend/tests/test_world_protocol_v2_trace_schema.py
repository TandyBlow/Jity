"""Shared trace grammar, binding safety and failure-first validation."""
import copy
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
from pydantic import ValidationError
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend/scripts'))
from world_trace_expected import validate_trace, instantiate, expected_digest, assertion
from app.schemas.world.v2.trace import TraceDocument, TraceAssertion
from app.schemas.world.v2.registry import OPERATION_BY_NAME

BASE=ROOT/'design/world-protocol/v2'
def load(name='T01'):return json.loads((BASE/f'traces/{name}.json').read_text(encoding='utf-8'))


def test_trace_schema_and_all_operation_coverage():
    schema=json.loads((BASE/'trace.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    seen=set()
    for path in (BASE/'traces').glob('T*.json'):
        value=json.loads(path.read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(value)
        seen.update(s['operation'] for s in value['steps'])
    assert seen==set(OPERATION_BY_NAME),'no fixture-only exemptions: every operation must have a trace step'


@pytest.mark.parametrize('mutation',['business','future','duplicate','missing_assertion','missing_response_field','missing_capture','wrong_pin','unknown_field','request_hash','bool_trace_version'])
def test_bad_trace_is_rejected(mutation):
    value=load()
    if mutation=='business':
        name=next(v['name'] for v in value['variables'] if any(v['name'] in json.dumps(s['expectedProjection']) for s in value['steps']))
        next(v for v in value['variables'] if v['name']==name)['kind']='business'
    elif mutation=='future':value['steps'][0]['request']={'$var':value['variables'][-1]['name']}
    elif mutation=='duplicate':value['steps'][1]['captures']+=copy.deepcopy(value['steps'][0]['captures'])
    elif mutation=='missing_assertion':value['steps'][0]['assertions']=[]
    elif mutation=='missing_response_field':value['steps'][0]['response'].pop('control')
    elif mutation=='missing_capture':value['steps'][0]['captures'][0]['path']='/nonexistent'
    elif mutation=='wrong_pin':value['contractDigest']='0'*64
    elif mutation=='request_hash':value['steps'][0]['response']['requestHash']='0'*64
    elif mutation=='bool_trace_version':value['traceFormatVersion']=True
    else:value['unexpected']=True
    with pytest.raises(Exception):validate_trace(value)


def test_trace_format_version_rejects_bools_on_both_validation_sides():
    """Regression guard for the R1 fix round: the trace format alias must keep
    the shared integer guard, because a bare Literal[1] accepts True (== 1)
    while the exported JSON schema rejects it — a Python/JSON split."""
    value=load('T07')
    schema=json.loads((BASE/'trace.schema.json').read_text(encoding='utf-8'))
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate({**value,'traceFormatVersion':True})
    with pytest.raises(ValidationError):
        TraceDocument.model_validate({**value,'traceFormatVersion':True})
    with pytest.raises(Exception):
        validate_trace({**value,'traceFormatVersion':True})
    # the shared _integer guard still admits an integral float, as before
    TraceDocument.model_validate({**value,'traceFormatVersion':1.0})


def test_failed_response_cannot_supply_a_missing_capture_to_later_steps():
    value=load('T09')
    step=next(s for s in value['steps'] if s['responseKind']=='error')
    value['variables'].append({'name':'missing','kind':'identity','valueType':'string','origin':'capture','captureStep':step['id']})
    step['captures'].append({'variable':'missing','path':'/data/pointId'})
    for sample in value['samples']:sample['values']['missing']='p'
    with pytest.raises(ValueError,match='missing capture'):validate_trace(value)


def test_expected_tool_refuses_actual_business_bindings():
    value=TraceDocument.model_validate(load())
    declarations={v.name:v for v in value.variables}
    variable=next(iter(declarations.values())).model_copy(update={'kind':'business'})
    with pytest.raises(ValueError,match='business'):
        expected_digest({'worldId':{'$var':variable.name}},{variable.name:variable},{variable.name:'copied_from_actual'})


def test_absent_assertion_is_distinct_from_null_and_range_checks_are_real():
    assertion({'ok':None},TraceAssertion(op='absent',path='/missing'),{})
    with pytest.raises(ValueError):assertion({'ok':None},TraceAssertion(op='absent',path='/ok'),{})
    assertion({'n':11},TraceAssertion(op='range',path='/n',minimum=10,maximum=12),{})
    with pytest.raises(ValueError):assertion({'n':9},TraceAssertion(op='range',path='/n',minimum=10),{})
    with pytest.raises(ValueError):TraceAssertion(op='time_window',path='/n',baseline=0)


def test_dynamic_key_binding_rejects_collisions_and_unresolved_names():
    assert instantiate({'$map':[{'key':{'$var':'id'},'value':1}]},{'id':'new_id'})=={'new_id':1}
    with pytest.raises(ValueError):instantiate({'$var':'missing'}, {})
    with pytest.raises(ValueError):instantiate({'$map':[{'key':'same','value':1},{'key':'same','value':2}]},{})
