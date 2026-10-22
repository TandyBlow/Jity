"""Test-only template binding, trace validation and independent expected hashes.

CLI: --trace FILE --sample NAME, or --bindings FILE for captured runtime values.
No production API imports, no actualState/actualDigest input, no apply engine.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import re

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from jsonschema import Draft202012Validator
from app.schemas.world.canonical import canonical_bytes, canonical_digest
from app.schemas.world.contracts import WorldState
from app.schemas.world.v2.trace import TraceDocument

BASE = ROOT / 'design/world-protocol/v2'
MISSING = object()


def pointer(value, path, default=MISSING):
    if path == '': return value
    if not path.startswith('/'): raise ValueError('expected JSON pointer')
    for token in path[1:].split('/'):
        token = token.replace('~1','/').replace('~0','~')
        if token in ('__proto__','constructor','prototype'): raise ValueError('unsafe pointer segment')
        try:
            if isinstance(value, list):
                if not token.isdigit() or (len(token)>1 and token.startswith('0')): raise KeyError(token)
                value=value[int(token)]
            elif isinstance(value, dict): value=value[token]
            else: raise KeyError(token)
        except (KeyError,IndexError):
            if default is not MISSING: return default
            raise ValueError(f'missing capture/assertion path: {path}') from None
    return value


def references(node):
    if isinstance(node, dict):
        if '$var' in node:
            if set(node) != {'$var'} or not isinstance(node['$var'], str): raise ValueError('invalid variable reference')
            yield node['$var']
        elif '$map' in node:
            if set(node) != {'$map'} or not isinstance(node['$map'],list): raise ValueError('invalid keyed map')
            for item in node['$map']:
                if set(item) != {'key','value'}: raise ValueError('invalid keyed map entry')
                yield from references(item['key']); yield from references(item['value'])
        else:
            for value in node.values(): yield from references(value)
    elif isinstance(node,list):
        for item in node: yield from references(item)


def instantiate(node, bindings):
    if isinstance(node,dict):
        if '$var' in node:
            list(references(node))
            if node['$var'] not in bindings: raise ValueError(f'uncaptured variable: {node["$var"]}')
            return copy.deepcopy(bindings[node['$var']])
        if '$map' in node:
            list(references(node)); result={}
            for item in node['$map']:
                key=instantiate(item['key'],bindings)
                if not isinstance(key,str) or key in result: raise ValueError('invalid/duplicate instantiated map key')
                result[key]=instantiate(item['value'],bindings)
            return result
        return {key:instantiate(value,bindings) for key,value in node.items()}
    if isinstance(node,list): return [instantiate(value,bindings) for value in node]
    return node


def value_type(value, kind):
    return {'string':lambda:isinstance(value,str), 'integer':lambda:type(value) is int and abs(value)<=2**53-1,
        'boolean':lambda:type(value) is bool,'object':lambda:isinstance(value,dict),
        'array':lambda:isinstance(value,list),'null':lambda:value is None}[kind]()


def expected_digest(projection, declarations, bindings):
    for name in references(projection):
        if name not in declarations or declarations[name].kind == 'business':
            raise ValueError('business/unknown variable cannot define an expected projection')
    # A caller may only supply declared identities/clocks/ownership. There is no
    # actual-state argument or use of the response when constructing this value.
    result=instantiate(projection,bindings)
    normalized=WorldState.model_validate(result).model_dump(mode='json')
    return normalized, canonical_digest(normalized)


def assertion(response, spec, bindings):
    absent = object()
    value=pointer(response,spec.path,absent)
    if spec.op=='absent':
        if value is not absent: raise ValueError(f'path must be absent: {spec.path}')
        return
    if value is absent: raise ValueError(f'assertion path missing: {spec.path}')
    expected=instantiate(spec.expected,bindings)
    if spec.op in ('eq','ordered'):
        ok=canonical_bytes(value)==canonical_bytes(expected)
    elif spec.op=='ne': ok=canonical_bytes(value)!=canonical_bytes(expected)
    elif spec.op=='set':
        ok=isinstance(value,list) and isinstance(expected,list) and len({canonical_bytes(v) for v in value})==len(value) and sorted(canonical_bytes(v) for v in value)==sorted(canonical_bytes(v) for v in expected)
    elif spec.op=='type': ok=expected in ('string','integer','boolean','object','array','null') and value_type(value,expected)
    elif spec.op in ('range','delta','time_window'):
        if type(value) is not int: raise ValueError('numeric assertion needs safe integers')
        number=value-(instantiate(spec.baseline,bindings) if spec.op in ('delta','time_window') else 0)
        ok=(number==expected if spec.op=='delta' else
            (spec.minimum is None or number>=spec.minimum) and (spec.maximum is None or number<=spec.maximum))
    else: raise ValueError('unknown assertion')
    if not ok: raise ValueError(f'{spec.op} assertion failed: {spec.path}')


def validate_trace(value, sample_id=None):
    trace=TraceDocument.model_validate(value)
    from export_world_protocol import contract_digest
    if trace.contractDigest!=contract_digest(BASE):raise ValueError('trace contract pin mismatch')
    declarations={v.name:v for v in trace.variables}
    if len(declarations)!=len(trace.variables): raise ValueError('duplicate variable declaration')
    step_ids=[step.id for step in trace.steps]
    if len(set(step_ids))!=len(step_ids): raise ValueError('duplicate step id')
    samples=[s for s in trace.samples if sample_id is None or s.id==sample_id]
    if not samples: raise ValueError('unknown sample')
    api=json.loads((BASE/'api-contract.json').read_text(encoding='utf-8'))
    operations={s['operation']:s for s in api['operations']}
    schema=json.loads((BASE/'world-protocol.schema.json').read_text(encoding='utf-8'))
    validators={}
    def validate(name,payload):
        if name not in validators: validators[name]=Draft202012Validator({**schema,'$ref':f'#/$defs/{name}'})
        validators[name].validate(payload)
    outputs={}
    for sample in samples:
        if set(sample.values)!=set(declarations): raise ValueError('sample variable set differs from declarations')
        for name,var in declarations.items():
            if not value_type(sample.values[name],var.valueType): raise ValueError(f'variable type mismatch: {name}')
        bindings={name:sample.values[name] for name,var in declarations.items() if var.origin=='input'}
        digest_steps={}
        for step in trace.steps:
            own={c.variable for c in step.captures}
            for node in [step.scope,step.request]:
                if not set(references(node))<=bindings.keys(): raise ValueError('request references an uncaptured variable')
            if not set(references(step.response)) <= bindings.keys()|own: raise ValueError('response references a future variable')
            for node in [step.expectedProjection,*[a.expected for a in step.assertions],*[a.baseline for a in step.assertions]]:
                for name in references(node):
                    if name not in declarations or declarations[name].kind=='business': raise ValueError('business reference in independent expectation')
                    if name not in bindings and name not in own: raise ValueError('expectation references uncaptured variable')
            request=instantiate(step.request,bindings)
            scope=instantiate(step.scope,bindings)
            response=instantiate(step.response,{**bindings,**{name:sample.values[name] for name in own}})
            spec=operations[step.operation]
            if not isinstance(scope,dict) or set(scope)-{'worldId','pointId'}:raise ValueError('invalid path scope')
            for key in re.findall(r'\{(\w+)\}',spec['path']):
                bound=scope.get(key,request.get(key))
                if not isinstance(bound,str) or not bound or (key in request and request[key]!=bound):raise ValueError('missing or inconsistent path identity')
            if spec.get('requestSchema') is not None: validate(spec['requestSchema'],request)
            elif request!={}: raise ValueError('bodyless request contains fields')
            validate('ErrorResponse' if step.responseKind=='error' else spec['successSchema'],response)
            if response.get('operation') is not None and response['operation']!=step.operation:raise ValueError('response operation mismatch')
            if request.get('requestId') is not None and response.get('requestId') is not None and request['requestId']!=response['requestId']:raise ValueError('response requestId mismatch')
            if step.responseKind=='success' and 'requestHash' in response:
                from app.schemas.world.v2.projections import request_projection
                if response['requestHash']!=canonical_digest(request_projection(step.operation,request)):
                    raise ValueError('request hash differs from instantiated normalized request')
            expected_status=response['error']['httpStatus'] if step.responseKind=='error' else spec['successHttpStatus']
            if step.httpStatus!=expected_status: raise ValueError('HTTP status mismatch')
            if step.responseKind=='error':
                if response['error']['code'] not in {e['code'] for e in spec['errorCodes']}: raise ValueError('error not registered for operation')
                if step.nextAction != response['error']['clientAction']: raise ValueError('error recovery action differs from contract')
            for capture in step.captures:
                if capture.variable not in declarations: raise ValueError('undeclared capture')
                declaration=declarations[capture.variable]
                if capture.variable in bindings or declaration.captureStep!=step.id: raise ValueError('capture overwritten or wrong step')
                captured=pointer(response,capture.path)
                if not value_type(captured,declaration.valueType): raise ValueError('capture type mismatch')
                bindings[capture.variable]=captured
            for item in step.assertions: assertion(response,item,bindings)
            if step.expectedProjection is not None:
                expected,digest=expected_digest(step.expectedProjection,declarations,bindings)
                actual=pointer(response,step.projectionPath)
                # Compare only after independent expectation construction.
                if canonical_bytes(actual)!=canonical_bytes(expected): raise ValueError('state projection mismatch')
                if sample.expectedDigests.get(step.id)!=digest: raise ValueError('stale or mismatched expected digest')
                if pointer(response,step.digestPath)!=digest: raise ValueError('response state digest differs from independent expected digest')
                digest_steps[step.id]=digest
        if set(digest_steps)!=set(sample.expectedDigests): raise ValueError('expected digest step coverage mismatch')
        if set(bindings)!=set(declarations): raise ValueError('declared variable was never captured')
        outputs[sample.id]=digest_steps
    return outputs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace',type=Path,required=True)
    parser.add_argument('--sample')
    parser.add_argument('--bindings',type=Path)
    args=parser.parse_args()
    value=json.loads(args.trace.read_text(encoding='utf-8'))
    if args.bindings:
        bindings=json.loads(args.bindings.read_text(encoding='utf-8'))
        declarations={v.name:v for v in TraceDocument.model_validate(value).variables}
        if any(name not in declarations or declarations[name].kind=='business' for name in bindings): raise ValueError('only declared non-business bindings accepted')
        output={s['id']:expected_digest(s['expectedProjection'],declarations,bindings)[1] for s in value['steps'] if s.get('expectedProjection') is not None}
    else: output=validate_trace(value,args.sample)
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
