# Archived copy note: the original run used absolute local paths; they are
# replaced by env-overridable relative defaults below (run from this directory).
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Annotated, Literal

ROOT = Path(os.environ.get('WORLD_SERVER_WORKTREE', '../world-server-worktree'))
BROOT = Path(os.environ.get('JITY_REPO_ROOT', '../..'))
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend/scripts'))
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError, BeforeValidator
from app.schemas.world.contracts import _integer
from app.schemas.world.v2.base import SchemaVersion, StateSchemaVersion, TraceFormatVersion
from app.schemas.world.v2.requests import WorldInitialTemplate
from app.schemas.world.v2.trace import TraceDocument
from world_trace_expected import validate_trace
from tests.test_world_progress import scenario

results = []
def record(name, passed, **details):
    results.append(dict(name=name, passed=passed, **details))

with tempfile.TemporaryDirectory(prefix='jity-response-version-review-') as folder:
    flow = scenario(Path(folder))
    context = flow['service'].execute('get_context', dict(worldId=flow['world'], includeRecovery=False))
    state = flow['service'].execute('get_state', dict(worldId=flow['world'], point=flow['head']))
    old = json.loads((BROOT / 'design/world-protocol/v2/world-protocol.schema.json').read_bytes())
    validator = Draft202012Validator({**old, '$ref': '#/$defs/ContextResponse'})
    errors = list(validator.iter_errors(context))
    record('old_B_rejects_ordinary_first_response_version', context['schemaVersion'] == 2 and
           any(list(e.path) == ['schemaVersion'] for e in errors), schemaVersion=context['schemaVersion'])
    record('live_get_state_response2_nested_state1', state['schemaVersion'] == 2 and
           state['data']['state']['schemaVersion'] == state['data']['state']['initial']['schemaVersion'] == 1)

initial = json.loads((ROOT / 'design/world-protocol/v2/fixtures/api/create_world/request.json').read_bytes())['initial']
record('creation_template1_accepted', WorldInitialTemplate.model_validate(initial).schemaVersion == 1)
try:
    WorldInitialTemplate.model_validate({**initial, 'schemaVersion': 2})
    record('creation_template2_rejected', False)
except ValidationError:
    record('creation_template2_rejected', True)

trace = json.loads((ROOT / 'design/world-protocol/v2/traces/T07.json').read_bytes())
validate_trace(trace)
record('trace_format1_still_valid', TraceDocument.model_validate(trace).traceFormatVersion == 1)

for name, alias in [('response', SchemaVersion), ('state', StateSchemaVersion), ('trace', TraceFormatVersion)]:
    for value in (True, '1'):
        try:
            got = TypeAdapter(alias).validate_python(value, strict=True)
            record(f'{name}_rejects_{value!r}', False, accepted=repr(got))
        except ValidationError:
            record(f'{name}_rejects_{value!r}', True)

# Exercise the actual offline trace loading entry, not only the scalar alias.
for value in (True,):
    mutant = copy.deepcopy(trace)
    mutant['traceFormatVersion'] = value
    try:
        validate_trace(mutant)
        record(f'trace_entry_rejects_{value!r}', False, accepted=True)
    except (ValidationError, ValueError):
        record(f'trace_entry_rejects_{value!r}', True)
    try:
        _integer(value)
        prior_rejected = False
    except ValueError:
        prior_rejected = True
    record(f'prior_integer_guard_rejects_{value!r}', prior_rejected)
    trace_schema = json.loads((ROOT / 'design/world-protocol/v2/trace.schema.json').read_bytes())
    record(f'JSON_schema_rejects_trace_format_{value!r}', not Draft202012Validator(trace_schema).is_valid(mutant))

def visit(value):
    if isinstance(value, dict):
        yield value
        for item in value.values(): yield from visit(item)
    elif isinstance(value, list):
        for item in value: yield from visit(item)

counts = dict(envelopes=0, stateModels=0)
bad = []
for path in (ROOT / 'design/world-protocol/v2').rglob('*.json'):
    for obj in visit(json.loads(path.read_bytes())):
        version = obj.get('schemaVersion')
        if type(version) is not int: continue
        if 'canonicalVersion' in obj:
            counts['envelopes'] += 1
            if version != 2: bad.append(str(path.relative_to(ROOT)))
        else:
            counts['stateModels'] += 1
            if version != 1: bad.append(str(path.relative_to(ROOT)))
record('all_authored_version_fields_classified', not bad, counts=counts, bad=bad)
report = dict(results=results, passed=sum(r['passed'] for r in results), failed=[r for r in results if not r['passed']])
path = Path(__file__).with_suffix('.json')
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(report=str(path), passed=report['passed'], failed=report['failed']), ensure_ascii=False))
