# Archived copy note: the original run used an absolute local path; it is
# replaced by an env-overridable relative default below (run from this directory).
import json
import os
from pathlib import Path
import sys
from typing import Annotated, Literal

# 路径已退役：默认 .local/world-server-worktree 不再存在，复跑须以 WORLD_SERVER_WORKTREE 显式指定检出。
ROOT = Path(os.environ.get('WORLD_SERVER_WORKTREE', '../world-server-worktree'))
sys.path.insert(0, str(ROOT / 'backend'))
from pydantic import BeforeValidator, ValidationError, create_model
from app.schemas.world.contracts import _integer
from app.schemas.world.v2.requests import WorldInitialTemplate
from app.schemas.world.v2.trace import TraceDocument

ResponseVersion2 = Annotated[Literal[2], BeforeValidator(_integer)]
TemplateWithSharedAlias2 = create_model('TemplateWithSharedAlias2', __base__=WorldInitialTemplate,
    schemaVersion=(ResponseVersion2, ...))
TraceWithSharedAlias2 = create_model('TraceWithSharedAlias2', __base__=TraceDocument,
    traceFormatVersion=(ResponseVersion2, ...))
initial = json.loads((ROOT / 'design/world-protocol/v2/fixtures/api/create_world/request.json').read_bytes())['initial']
results = []
for value in (1, 2):
    try:
        TemplateWithSharedAlias2.model_validate({**initial, 'schemaVersion': value})
        results.append(dict(templateSchemaVersion=value, accepted=True))
    except ValidationError as error:
        results.append(dict(templateSchemaVersion=value, accepted=False,
                            failures=[dict(location=list(e['loc']), type=e['type']) for e in error.errors()]))
trace = json.loads((ROOT / 'design/world-protocol/v2/traces/T07.json').read_bytes())
try:
    TraceWithSharedAlias2.model_validate(trace)
    trace_rejected = False
except ValidationError as error:
    trace_rejected = any(e['loc'] == ('traceFormatVersion',) for e in error.errors())
assert not any(r['accepted'] for r in results)
assert trace_rejected
report = dict(simulation='Change the response SchemaVersion alias to Literal[2] without separating its other consumers',
              templateResults=results, unchangedTraceFormat1Rejected=trace_rejected)
Path(__file__).with_name('version-alias-probe.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report))
