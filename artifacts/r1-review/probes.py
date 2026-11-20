# Archived copy note: the original run used absolute local paths; they are
# replaced by env-overridable relative defaults below (run from this directory).
import copy
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

# 路径已退役：默认 .local/world-server-worktree 不再存在，复跑须以 WORLD_SERVER_WORKTREE 显式指定检出。
ROOT = Path(os.environ.get('WORLD_SERVER_WORKTREE', '../world-server-worktree'))
BROOT = Path(os.environ.get('JITY_REPO_ROOT', '../..'))
sys.path.insert(0, str(ROOT / 'backend'))
from jsonschema import Draft202012Validator, ValidationError as JsonError
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.schemas.world.canonical import canonical_digest
from app.schemas.world.v2 import FrozenGroupView
from app.schemas.world.v2.base import SCHEMA_VERSION
from app.schemas.world.v2.registry import OPERATION_BY_NAME
from app.world_app import create_world_app
from tests.test_world_progress import scenario, targets, rolls, accept, facts
from tests.test_world_http import HEADERS

out = []
def record(name, passed, **details):
    out.append(dict(name=name, passed=passed, **details))

new_schema = json.loads((ROOT / 'design/world-protocol/v2/world-protocol.schema.json').read_bytes())
old_schema = json.loads((BROOT / 'design/world-protocol/v2/world-protocol.schema.json').read_bytes())
old_validator = Draft202012Validator({**old_schema, '$ref': '#/$defs/ContextResponse'})
new_validator = Draft202012Validator({**new_schema, '$ref': '#/$defs/FrozenGroupView'})

with tempfile.TemporaryDirectory(prefix='jity-independent-r1-') as folder:
    flow = scenario(Path(folder))
    ordinary = flow['service'].execute('get_context', dict(worldId=flow['world'], includeRecovery=False))
    old_validator.validate(ordinary)
    protected = flow['service'].execute('get_context', dict(worldId=flow['world'], includeRecovery=True,
        leaseToken=flow['lease']['leaseToken'], fenceEpoch=flow['lease']['fenceEpoch']))
    rejected_protected = not old_validator.is_valid(protected)
    record('old_B_accepts_first_response_then_rejects_recovery', rejected_protected,
           firstResponseSchemaVersion=ordinary['schemaVersion'], oldBFirstResponseAccepted=True,
           oldBRecoveryAccepted=not rejected_protected)
    outcome = rolls(flow, 'person_a', targets(flow, 'person_a', ['person_b']))[0]
    valid = facts(flow)
    for label, changes in [
        ('pending_with_roll_id', dict(status='pending_roll')),
        ('reaction_pending_with_disposition', dict(actionDisposition='none')),
        ('handled_none_with_member', dict(status='handled', actionDisposition='none', reactionMemberId='person_b')),
        ('handled_created_without_member', dict(status='handled', actionDisposition='created')),
    ]:
        value = copy.deepcopy(valid)
        value['progress']['threats'][0].update(changes)
        py_rejected = False
        try:
            FrozenGroupView.model_validate(value)
        except ValidationError:
            py_rejected = True
        record(label, py_rejected and not new_validator.is_valid(value), pythonRejected=py_rejected,
               jsonSchemaRejected=not new_validator.is_valid(value))

def visit(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from visit(item)
    elif isinstance(value, list):
        for item in value:
            yield from visit(item)

trace = json.loads((ROOT / 'design/world-protocol/v2/traces/T07.json').read_bytes())
matches = []
for point in visit(trace):
    if not {'groups', 'work', 'payloadStatus'} <= set(point):
        continue
    for group in point['groups']:
        if group['progress']['sourceStack'] == ['person_f', 'person_e']:
            members = {m['memberId']: m for m in group['members']}
            threats = group['progress']['threats']
            derived = sorted(s for s in group['progress']['sourceStack']
                if members[s]['targets'] is None or any(t['sourceId'] == s and t['status'] != 'handled' for t in threats))
            matches.append(derived == point['work']['pendingGroup']['frontierIds'] == ['person_f'])
record('T07_stack_FE_frontier_F', bool(matches) and all(matches), matchingViews=len(matches))

for code in ('frozen_work_missing', 'frozen_work_corrupt'):
    fixture = json.loads((ROOT / f'design/world-protocol/v2/fixtures/branches/recovery-{code}.error.json').read_bytes())
    allowed = {e.code for e in OPERATION_BY_NAME[fixture['operation']].errorCodes}
    record('error_fixture_declared_' + code, fixture['error']['code'] in allowed)

for fault in ('stack_nested_object', 'threat_null', 'progress_null', 'binding_array'):
    with tempfile.TemporaryDirectory(prefix='jity-independent-corrupt-') as folder:
        flow = scenario(Path(folder))
        rolls(flow, 'person_a', targets(flow, 'person_a', ['person_b']))
        with closing(sqlite3.connect(flow['path'])) as db:
            value = json.loads(db.execute('SELECT checkpoint_json FROM world_group_progress').fetchone()[0])
            if fault == 'stack_nested_object': value['progress']['sourceStack'] = [{}]
            elif fault == 'threat_null': value['progress']['threats'] = [None]
            elif fault == 'progress_null': value['progress'] = None
            else: value['binding'] = []
            db.execute('UPDATE world_group_progress SET checkpoint_json=?,checkpoint_digest=?',
                       (json.dumps(value), canonical_digest(value)))
            db.commit()
        calls = len(flow['calls'])
        spec = OPERATION_BY_NAME['get_context']
        try:
            with TestClient(create_world_app(store=flow['store'])) as client:
                answer = client.get(spec.path.replace('{worldId}', flow['world']), headers=HEADERS,
                    params=dict(includeRecovery='true', leaseToken=flow['lease']['leaseToken'],
                                fenceEpoch=flow['lease']['fenceEpoch']))
            code = answer.json().get('error', {}).get('code')
            record(fault, answer.status_code == 409 and code == 'frozen_work_corrupt' and len(flow['calls']) == calls,
                   httpStatus=answer.status_code, code=code)
        except Exception as error:
            record(fault, False, exception=type(error).__name__, detail=str(error)[:200])

report = Path(__file__).with_name('probes.json')
report.write_text(json.dumps(dict(schemaVersion=SCHEMA_VERSION, probes=out), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(report=str(report), passed=sum(x['passed'] for x in out), failed=[x for x in out if not x['passed']]), ensure_ascii=False))
