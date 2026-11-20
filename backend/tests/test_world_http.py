"""A2 HTTP adapter: real request/query encoding, envelopes and byte budgets.

ASGI tests are distinct from the external browser/HTTP H1 check.
"""
import json

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from app.routers.worlds import PROTOCOL_HEADER
from app.schemas.world.canonical import parse_json
from app.schemas.world.v2.envelopes import ErrorResponse
from app.schemas.world.v2.requests import NarrationGetSuccess
from app.schemas.world.v2.registry import OPERATION_BY_NAME
from app.services.world.control import ServiceRefusal
from app.services.world.store import FixtureBaselineStore
from app.world_app import create_world_app
from tests.test_world_control_service import (
    TIME_ADVANCE, _claim_and_submit, begin_work, initial_template, run_t01_flow,
)

HEADERS = {PROTOCOL_HEADER: '2'}


class HttpService:
    def __init__(self, client):
        self.client = client

    def execute(self, operation, request):
        spec = OPERATION_BY_NAME[operation]
        path = spec.path.format(**request)
        if spec.method in ('GET', 'DELETE'):
            query = {key: str(request[key]).lower() if isinstance(request[key], bool)
                     else request[key] for key in spec.queryBindings
                     if request.get(key) is not None}
            response = self.client.request(spec.method, path, params=query, headers=HEADERS)
        else:
            response = self.client.request(spec.method, path,
                                           json=jsonable_encoder(request), headers=HEADERS)
        result = response.json()
        if response.is_error:
            error = ErrorResponse.model_validate(result)
            assert error.error.httpStatus == response.status_code
            assert error.error.code in {entry.code for entry in spec.errorCodes}
            raise ServiceRefusal(result['error']['code'], 'HTTP refusal',
                                 details=result['error']['details'])
        assert response.status_code == spec.successHttpStatus
        return result


@pytest.fixture
def client():
    app = create_world_app(store=FixtureBaselineStore(),
                           allowed_origins=['http://localhost:3100'])
    with TestClient(app) as client:
        yield client


def test_t01_flow_over_http_and_query_reads(client):
    service = HttpService(client)
    state = run_t01_flow(service)
    world_id, root, point = state['world_id'], state['root_id'], state['point_id']
    _claim_and_submit(service, world_id, state['lease'], point, 'req_ready', '叙事就绪。')
    context = service.execute('get_context', {'worldId': world_id})
    assert context['control']['canCompute'] is True
    assert context['world']['head']['version'] == 1
    points = service.execute('list_points', {'worldId': world_id, 'after': 0, 'limit': 1})
    assert [entry['pointId'] for entry in points['data']['points']] == [point]
    history = service.execute('get_state', {'worldId': world_id, 'point': root})
    assert history['data']['version'] == 0
    assert history['data']['state']['time']['dateTime'] == '2026-01-01T11:59:00'
    assert service.execute('narration_get', {'worldId': world_id,
                                             'pointId': point})['data']['text'] == '叙事就绪。'


@pytest.mark.parametrize('headers,body,code', [
    ({}, {}, 'protocol_version_unsupported'),
    ({PROTOCOL_HEADER: '3'}, {}, 'protocol_version_unsupported'),
    (HEADERS, {'protocolVersion': 1}, 'protocol_version_unsupported'),
    (HEADERS, {'protocolVersion': True}, 'protocol_version_unsupported'),
    (HEADERS, {'protocolVersion': 2}, 'request_malformed'),
])
def test_version_and_schema_errors_use_world_envelopes(client, headers, body, code):
    response = client.post('/worlds', headers=headers, json=body)
    assert response.status_code == 400
    error = ErrorResponse.model_validate(response.json())
    assert error.error.code == code


@pytest.mark.parametrize('body', ['{', '[]', '{"protocolVersion":2,"x":NaN}'])
def test_invalid_json_is_not_a_fastapi_422(client, body):
    response = client.post('/worlds', headers=HEADERS, content=body)
    assert response.status_code == 400
    assert ErrorResponse.model_validate(response.json()).error.code == 'request_malformed'


def test_json_integer_spelling_matches_the_shared_contract(client):
    response = client.post('/worlds', headers=HEADERS, json={
        'protocolVersion': 2.0, 'requestId': 'req_integer_version',
        'initial': initial_template()})
    assert response.status_code == 201
    assert response.json()['protocolVersion'] == 2


@pytest.mark.parametrize('number', ['10.0000000000000001', '9.999999999999999999999999', '1e-1000'])
def test_json_preserves_precision_before_integer_validation(client, number):
    payload = {'protocolVersion': 2, 'requestId': 'req_precise',
               'initial': initial_template()}
    raw = json.dumps(payload).replace('"initialSanity": 10',
                                      f'"initialSanity": {number}', 1)
    with pytest.raises(ValueError):
        parse_json(raw)  # The shared wire-number authority rejects the literal.
    response = client.post('/worlds', headers=HEADERS, content=raw)
    assert response.status_code == 400
    assert ErrorResponse.model_validate(response.json()).error.code == 'request_malformed'
    store = client.app.state.world_service.store
    assert store.world('world_1') is None
    assert store.global_idempotency() == {}
    corrected = client.post('/worlds', headers=HEADERS, json=payload)
    assert corrected.status_code == 201  # The refused requestId was not consumed.


@pytest.mark.parametrize('number', ['10.0', '1e1', '10.0000000000000000'])
def test_exact_integral_json_numbers_keep_canonical_idempotency(client, number):
    payload = {'protocolVersion': 2, 'requestId': 'req_integral',
               'initial': initial_template()}
    created = client.post('/worlds', headers=HEADERS, json=payload)
    raw = json.dumps(payload).replace('"initialSanity": 10',
                                      f'"initialSanity": {number}', 1)
    replay = client.post('/worlds', headers=HEADERS, content=raw)
    assert replay.status_code == 201
    assert replay.json()['replayed'] is True
    assert replay.json()['requestHash'] == created.json()['requestHash']
    assert replay.json()['data'] == created.json()['data']


@pytest.mark.parametrize('field', ['same_request_id', 'different_request_id', 'nested_sanity'])
def test_duplicate_json_keys_never_create_a_world(client, field):
    payload = {'protocolVersion': 2, 'requestId': 'req_duplicate',
               'initial': initial_template()}
    raw = json.dumps(payload)
    if field == 'nested_sanity':
        raw = raw.replace('"initialSanity": 10', '"initialSanity": 20, "initialSanity": 10', 1)
    else:
        first_id = 'req_duplicate' if field == 'same_request_id' else 'req_other'
        raw = raw.replace('"requestId": "req_duplicate"',
                          f'"requestId": "{first_id}", "requestId": "req_duplicate"', 1)
    with pytest.raises(ValueError):
        parse_json(raw)
    response = client.post('/worlds', headers=HEADERS, content=raw)
    assert response.status_code == 400
    assert ErrorResponse.model_validate(response.json()).error.code == 'request_malformed'
    store = client.app.state.world_service.store
    assert store.world('world_1') is None
    assert store.global_idempotency() == {}
    assert client.post('/worlds', headers=HEADERS, json=payload).status_code == 201


@pytest.mark.parametrize('point_id', ['invalid%20id', '%E4%B8%AD', 'x' * 129])
def test_bodyless_narration_read_validates_path_ids(client, point_id):
    state = begin_work(HttpService(client))
    world_id = state['world_id']
    store = client.app.state.world_service.store
    before = store.world(world_id)
    response = client.get(f'/worlds/{world_id}/points/{point_id}/narration', headers=HEADERS)
    assert response.status_code == 409
    error = ErrorResponse.model_validate(response.json())
    assert error.error.code == 'version_mismatch'
    assert error.error.code in {entry.code for entry in OPERATION_BY_NAME['narration_get'].errorCodes}
    assert store.world(world_id) == before
    # A syntactically valid unknown point still has the frozen missing response.
    missing = client.get(f'/worlds/{world_id}/points/point_missing/narration', headers=HEADERS)
    assert missing.status_code == 200
    assert NarrationGetSuccess.model_validate(missing.json()).data.narrationStatus == 'missing'


@pytest.mark.parametrize('authority,code', [
    ('valid', 'frozen_work_missing'), ('wrong_lease', 'lease_invalid'),
    ('wrong_point', 'version_mismatch'),
])
def test_fixture_restore_refuses_with_declared_error_and_no_writes(client, authority, code):
    service = HttpService(client)
    state = begin_work(service)
    world_id = state['world_id']
    store = client.app.state.world_service.store
    before = store.world(world_id)
    payload = {
        'protocolVersion': 2, 'requestId': 'req_restore', 'worldId': world_id,
        'operation': 'restore_group_work', 'pointId': state['point_id'],
        'groupId': state['group_id'], 'expectedPointId': state['root_id'],
        'expectedVersion': 0, 'expectedCheckpointRevision': state['revision'],
        'leaseToken': state['lease']['leaseToken'], 'fenceEpoch': state['lease']['fenceEpoch'],
        'sourceEpoch': 1, 'sourceAttempt': 1,
        'manifest': [{'memberId': 'person_a', 'actionContentHash': '0' * 64,
                      'targetsContentHash': None, 'resultContentHash': None,
                      'candidatesContentHash': None}],
    }
    if authority == 'wrong_lease':
        payload['leaseToken'] = 'lease_invalid'
    elif authority == 'wrong_point':
        payload['pointId'] = 'point_unrelated'
    response = client.put(f'/worlds/{world_id}/checkpoint', headers=HEADERS, json=payload)
    assert response.status_code == 409
    error = ErrorResponse.model_validate(response.json())
    assert error.error.code == code
    assert error.error.code in {entry.code for entry in OPERATION_BY_NAME['checkpoint_restore_group_work'].errorCodes}
    if authority == 'valid':
        assert error.error.details == {'reason': 'source_not_active'}
    assert store.world(world_id) == before


def test_unknown_fields_and_path_body_mismatch_do_not_write(client):
    service = HttpService(client)
    state = begin_work(service)
    world_id = state['world_id']
    before = client.app.state.world_service.store.world(world_id)
    payload = {
        'protocolVersion': 2, 'requestId': 'req_pause', 'operation': 'pause',
        'worldId': world_id, **state['lease'], 'expectedPointId': state['root_id'],
        'expectedVersion': 0, 'expectedCheckpointRevision': state['revision'],
    }
    payload.pop('expiresAtEpochMilli')
    response = client.put(f'/worlds/{world_id}/checkpoint', headers=HEADERS,
                          json={**payload, 'extraField': 'not allowed'})
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'request_malformed'
    response = client.put(f'/worlds/{world_id}/checkpoint', headers=HEADERS,
                          json={**payload, 'worldId': 'another_world'})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'version_mismatch'
    assert client.app.state.world_service.store.world(world_id) == before


def test_control_required_error_and_idempotent_replay(client):
    service = HttpService(client)
    state = begin_work(service)
    world_id = state['world_id']
    payload = {'protocolVersion': 2, 'requestId': 'req_skip', 'worldId': world_id,
               'operation': 'record_skip', 'pointId': state['point_id'],
               'expectedPointId': state['root_id'], 'expectedVersion': 0,
               'expectedCheckpointRevision': state['revision'],
               'leaseToken': state['lease']['leaseToken'], 'fenceEpoch': 99,
               'slotActorId': 'person_a'}
    response = client.put(f'/worlds/{world_id}/checkpoint', headers=HEADERS, json=payload)
    error = ErrorResponse.model_validate(response.json())
    assert response.status_code == 409
    assert error.error.code == 'stale_epoch'
    assert error.control.revision == state['revision']
    payload['fenceEpoch'] = state['lease']['fenceEpoch']
    first = service.execute('checkpoint_record_skip', payload)
    replay = service.execute('checkpoint_record_skip', payload)
    assert replay['replayed'] is True
    assert first['data'] == replay['data']
    response = client.put(f'/worlds/{world_id}/checkpoint', headers=HEADERS,
                          json={**payload, 'slotActorId': 'person_b'})
    assert ErrorResponse.model_validate(response.json()).error.code == 'request_id_reused'


def test_delete_binds_the_point_path_and_supports_query_credentials(client):
    service = HttpService(client)
    state = run_t01_flow(service)
    world_id, point, lease = state['world_id'], state['point_id'], state['lease']
    claim, _ = _claim_and_submit(service, world_id, lease, point, 'req_ready', '就绪。')
    payload = {'protocolVersion': 2, 'requestId': 'req_delete', 'worldId': world_id,
               'pointId': point, 'mode': 'head',
               'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
               **{key: claim['data'][key] for key in (
                   'claimToken', 'generation', 'issuedAtEpochMilli')}}
    before = client.app.state.world_service.store.world(world_id)
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_delete', {**payload, 'pointId': state['root_id']})
    assert excinfo.value.code == 'version_mismatch'
    assert client.app.state.world_service.store.world(world_id) == before
    deleted = service.execute('narration_delete', payload)
    assert deleted['data']['pointId'] == point
    assert service.execute('narration_delete', payload)['replayed'] is True
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_delete', {**payload, 'pointId': state['root_id']})
    assert excinfo.value.code == 'request_id_reused'


def test_preview_budgets_count_actual_utf8_wire_bytes(client, monkeypatch):
    from app.services.world import preview as preview_module
    service = HttpService(client)
    state = begin_work(service)
    world_id = state['world_id']
    payload = {'protocolVersion': 2, 'worldId': world_id, 'advanceId': 'advance_1',
               'roundId': 'round_1', 'pointId': state['point_id'],
               'expectedPointId': state['root_id'], 'expectedVersion': 0,
               'expectedCheckpointRevision': state['revision'],
               'timeAdvance': TIME_ADVANCE, 'settlementGroups': []}
    url = f'/worlds/{world_id}/preview'
    before = client.app.state.world_service.store.world(world_id)
    raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    monkeypatch.setattr(preview_module, 'PREVIEW_REQUEST_LIMIT', len(raw))
    accepted = client.post(url, headers=HEADERS, content=raw)
    assert accepted.status_code == 200
    rejected = client.post(url, headers=HEADERS, content=raw + b' ')
    assert rejected.status_code == 413
    assert rejected.json()['error']['details']['limit'] == 'request'
    monkeypatch.setattr(preview_module, 'PREVIEW_RESPONSE_LIMIT', len(accepted.content))
    assert client.post(url, headers=HEADERS, content=raw).status_code == 200
    monkeypatch.setattr(preview_module, 'PREVIEW_RESPONSE_LIMIT', len(accepted.content) - 1)
    rejected = client.post(url, headers=HEADERS, content=raw)
    assert rejected.status_code == 413
    assert ErrorResponse.model_validate(rejected.json()).error.details['limit'] == 'response'
    assert client.app.state.world_service.store.world(world_id) == before


def test_cors_preflight_and_browser_response_headers(client):
    response = client.options('/worlds', headers={
        'Origin': 'http://localhost:3100', 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': f'content-type,{PROTOCOL_HEADER}',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:3100'
    response = client.post('/worlds', headers={**HEADERS, 'Origin': 'http://localhost:3100'},
                           json={'protocolVersion': 2, 'requestId': 'req_cors',
                                 'initial': initial_template()})
    assert response.status_code == 201
    assert response.headers['access-control-allow-origin'] == 'http://localhost:3100'
    denied = client.options('/worlds', headers={
        'Origin': 'http://another-origin', 'Access-Control-Request-Method': 'POST'})
    assert denied.status_code == 400
    assert 'access-control-allow-origin' not in denied.headers


@pytest.mark.parametrize('suffix', [
    '/points?limit=0', '/points?limit=abc', '/points?limit=1&limit=2',
    '/state?point=invalid%20id', '/context?includeRecovery=1',
])
def test_invalid_queries_return_declared_errors(client, suffix):
    state = begin_work(HttpService(client))
    response = client.get(f'/worlds/{state["world_id"]}{suffix}', headers=HEADERS)
    error = ErrorResponse.model_validate(response.json())
    assert response.status_code in (400, 409)
    assert error.error.code in {
        entry.code for entry in OPERATION_BY_NAME[error.operation].errorCodes}


def test_recovery_query_requires_lease_even_on_fixture_store(client):
    state = begin_work(HttpService(client))
    url = f'/worlds/{state["world_id"]}/context'
    response = client.get(url, headers=HEADERS, params={
        'includeRecovery': 'true', 'leaseToken': 'invalid_token', 'fenceEpoch': 1})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'lease_invalid'
    response = client.get(url, headers=HEADERS, params={
        'includeRecovery': 'true', 'leaseToken': state['lease']['leaseToken'],
        'fenceEpoch': state['lease']['fenceEpoch']})
    assert response.status_code == 200
    assert response.json()['recovery'] is None  # A3 payloads are unavailable.


def test_actual_preview_request_limit_accepts_512_kib_and_refuses_one_more_byte(client):
    state = begin_work(HttpService(client))
    world_id = state['world_id']
    payload = {'protocolVersion': 2, 'worldId': world_id, 'advanceId': 'advance_1',
               'roundId': 'round_1', 'pointId': state['point_id'],
               'expectedPointId': state['root_id'], 'expectedVersion': 0,
               'expectedCheckpointRevision': state['revision'],
               'timeAdvance': TIME_ADVANCE, 'settlementGroups': []}
    raw = json.dumps(payload).encode('utf-8')
    raw += b' ' * (512 * 1024 - len(raw))
    url = f'/worlds/{world_id}/preview'
    assert client.post(url, headers=HEADERS, content=raw).status_code == 200
    rejected = client.post(url, headers=HEADERS, content=raw + b' ')
    assert rejected.status_code == 413
    assert rejected.json()['error']['details']['limit'] == 'request'


def test_actual_preview_response_limit_counts_utf8_characters(client):
    template = initial_template()
    template['characters']['person_a']['initialAppearance'] = '汉' * 750_000
    service = HttpService(client)
    created = service.execute('create_world', {
        'protocolVersion': 2, 'requestId': 'req_create', 'initial': template})
    # This initial world is valid; preview alone has a 2 MiB response budget.
    world_id, root, lease = (created['data']['worldId'],
                             created['data']['rootPointId'], created['data']['lease'])
    _claim_and_submit(service, world_id, lease, root, 'req_root', '就绪。')
    bind = {'protocolVersion': 2, 'worldId': world_id,
            'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
            'expectedPointId': root, 'expectedVersion': 0}
    service.execute('checkpoint_start_advance', {
        **bind, 'requestId': 'req_advance', 'expectedCheckpointRevision': 0,
        'operation': 'start_advance', 'advanceId': 'advance_1', 'inputId': 'input_1',
        'roundId': 'round_1', 'inputText': '开始。', 'order': list(template['characters'])})
    service.execute('checkpoint_begin_point', {
        **bind, 'requestId': 'req_begin', 'expectedCheckpointRevision': 1,
        'operation': 'begin_point', 'pointId': 'point_large', 'kind': 'normal',
        'timeAdvance': TIME_ADVANCE})
    before = client.app.state.world_service.store.world(world_id)
    response = client.post(f'/worlds/{world_id}/preview', headers=HEADERS, json={
        'protocolVersion': 2, 'worldId': world_id, 'advanceId': 'advance_1',
        'roundId': 'round_1', 'pointId': 'point_large', 'expectedPointId': root,
        'expectedVersion': 0, 'expectedCheckpointRevision': 2,
        'timeAdvance': TIME_ADVANCE, 'settlementGroups': []})
    assert response.status_code == 413
    assert response.json()['error']['details']['limit'] == 'response'
    assert client.app.state.world_service.store.world(world_id) == before


def test_fixture_instances_are_isolated_and_existing_app_installs_routes(client):
    from app.main import app
    with TestClient(app) as integrated:
        response = integrated.get('/worlds/world_unknown/context', headers=HEADERS)
        assert response.status_code == 409
        ErrorResponse.model_validate(response.json())
    service = HttpService(client)
    state = begin_work(service)
    with TestClient(create_world_app(store=FixtureBaselineStore())) as other:
        response = other.get(f'/worlds/{state["world_id"]}/context', headers=HEADERS)
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'version_mismatch'
