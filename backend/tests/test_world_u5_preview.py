"""Actual Pydantic request boundaries and A's real projection, no mock apply."""
import copy
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.schemas.world.contracts import WorldInitialState, TimelinePoint
from app.schemas.world.v2.requests import PreviewPointRequest, StageUnitRequest, StageTimeScanRequest, CommitPointRequest
from app.schemas.world.v2.work import SettlementGroup
from app.services.world.state import build_initial_state
from app.services.world.preview import preview_request

ROOT = Path(__file__).resolve().parents[2] / 'design/world-protocol/v2/fixtures'
def load(path): return json.loads((ROOT / path).read_text(encoding='utf-8'))

def objects():
    request = load('branches/u5-preview.request.json')
    initial = load('api/create_world/request.json')['initial']
    initial['worldId'] = request['worldId']
    state = build_initial_state(WorldInitialState.model_validate(initial))
    point = TimelinePoint.model_validate(load('api/commit_point/request.json')['point'])
    return request, state, point

def test_u5_actual_projection_is_ephemeral_then_u6_completes():
    request, state, point = objects()
    original = state.model_dump(mode='json')
    projected = preview_request(state, point, request)
    actor = projected['workingState']['characters']['person_c']
    assert actor['personalityChanges'][-1]['text'] == '更谨慎'
    assert actor['sanity'] == state.characters['person_c'].sanity
    assert state.model_dump(mode='json') == original
    complete = copy.deepcopy(request)
    group = complete['settlementGroups'][0]
    group.pop('previewStage'); group['sanities'] = {'person_c': 45}
    final = preview_request(state, point, complete)
    assert final['workingState']['characters']['person_c']['sanity'] == 45
    assert len(final['workingState']['characters']['person_c']['personalityChanges']) == len(actor['personalityChanges'])
    stage = load('api/checkpoint_stage_unit/request.json'); stage['candidates'] = group
    StageUnitRequest.model_validate(stage)
    commit = load('api/commit_point/request.json'); commit['settlementGroups'] = [group]; commit['point'] = final['pointProjection']
    CommitPointRequest.model_validate(commit)

@pytest.mark.parametrize('marker', [True, False])
def test_half_candidate_cannot_stage_or_commit(marker):
    request, _, _ = objects(); group = request['settlementGroups'][0]
    if not marker: group.pop('previewStage')
    stage = load('api/checkpoint_stage_unit/request.json'); stage['candidates'] = group
    commit = load('api/commit_point/request.json'); commit['settlementGroups'] = [group]
    for model, body in [(SettlementGroup,group), (StageUnitRequest,stage), (CommitPointRequest,commit)]:
        with pytest.raises(ValidationError): model.model_validate(body)
    scan = load('api/checkpoint_stage_time_scan/request.json')
    scan['candidates'] = {**group,'groupId':None,'actorIds':[],'positions':{},'appearances':{}}
    with pytest.raises(ValidationError): StageTimeScanRequest.model_validate(scan)

@pytest.mark.parametrize('mutation', ['missing','wrong','sanity','not_last'])
def test_exception_is_only_explicit_last_u5(mutation):
    request, _, _ = objects(); group = request['settlementGroups'][0]
    if mutation == 'missing': group.pop('previewStage')
    if mutation == 'wrong': group['previewStage'] = 'U4'
    if mutation == 'sanity': group['sanities'] = {'person_c':45}
    if mutation == 'not_last': request['settlementGroups'].append(load('api/preview_point/request.json')['settlementGroups'][0])
    with pytest.raises(ValidationError): PreviewPointRequest.model_validate(request)


def test_intermediate_projection_cannot_bypass_groups_in_commit():
    request, state, point = objects()
    data = preview_request(state, point, request)
    commit = load('api/commit_point/request.json')
    commit['point'] = data['pointProjection']
    commit['settlementGroups'] = []
    with pytest.raises(ValidationError, match='committed point personality and sanity must pair'):
        CommitPointRequest.model_validate(commit)
