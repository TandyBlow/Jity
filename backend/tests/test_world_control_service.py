"""A2-1 smoke: the T01-shaped flow against the in-memory control service,
plus idempotency, binding and refusal behaviour.

Identity values are the service's own allocations (trace-side identity
equality was already pinned by the A1a replay tests); this suite pins service
behaviour: working evolution, committed-progress promotion, gate and claim
flow, revision increments, idempotent replay and refusal codes.
"""
import json
from pathlib import Path

import pytest

from app.services.world.control import ServiceRefusal, WorldService
from app.services.world.merge import point_entity_deltas
from app.services.world.store import FixtureBaselineStore
from app.schemas.world.v2.work import SettlementGroup

DESIGN = Path(__file__).resolve().parents[2] / 'design/world-protocol/v2'
ORDER = ['person_a', 'person_b', 'person_c', 'person_d', 'person_e', 'person_f']


def initial_template():
    snapshot = json.loads(
        (DESIGN / 'fixtures/projections/normal.expected.json').read_text(encoding='utf-8'))
    template = snapshot['initial']
    template.pop('worldId', None)
    return template


def single_group(actors, coverage, group_id='group_a'):
    return SettlementGroup.model_validate({
        'groupId': group_id, 'actorIds': actors,
        'positions': {}, 'appearances': {}, 'tasksAchieved': {},
        'subtasksAdded': {}, 'personalities': {}, 'sanities': {},
        'taskCoverageIds': sorted(coverage), 'personalityCoverageIds': [],
    })


@pytest.fixture()
def service():
    return WorldService(FixtureBaselineStore())


def run_t01_flow(service):
    """Drive the T01 operation sequence; returns the final service record."""
    created = service.execute('create_world', {
        'protocolVersion': 2, 'requestId': 'req_create',
        'initial': initial_template()})
    world_id = created['data']['worldId']
    root_id = created['data']['rootPointId']
    lease = created['data']['lease']

    claim = service.execute('narration_claim', {
        'protocolVersion': 2, 'requestId': 'req_claim_root', 'worldId': world_id,
        'pointId': root_id, 'mode': 'head',
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'currentClaim': None})
    service.execute('narration_submit', {
        'protocolVersion': 2, 'requestId': 'req_submit_root', 'worldId': world_id,
        'pointId': root_id, 'mode': 'head', 'claimToken': claim['data']['claimToken'],
        'generation': claim['data']['generation'],
        'issuedAtEpochMilli': claim['data']['issuedAtEpochMilli'],
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'outcome': 'ready', 'text': '开学第一天。', 'failureReason': None})

    allocations = service.execute('allocate_ids', {
        'protocolVersion': 2, 'requestId': 'req_alloc', 'worldId': world_id,
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'allocationKey': 'alloc_round_1',
        'slots': [{'slotKey': 'point_1', 'kind': 'point', 'scope': None},
                  {'slotKey': 'group_a', 'kind': 'group', 'scope': 'round_1'}]})
    ids = {item['slotKey']: item['id'] for item in allocations['data']['allocations']}
    point_id, group_id = ids['point_1'], ids['group_a']

    revision = service.execute('get_context', {
        'protocolVersion': 2, 'worldId': world_id})['control']['revision']
    service.execute('checkpoint_start_advance', {
        'protocolVersion': 2, 'requestId': 'req_advance', 'worldId': world_id,
        'operation': 'start_advance',
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'expectedPointId': root_id, 'expectedVersion': 0,
        'expectedCheckpointRevision': revision,
        'advanceId': 'advance_1', 'inputId': 'input_1', 'roundId': 'round_1',
        'inputText': '走进教室。', 'order': ORDER})

    begin_request = {
        'protocolVersion': 2, 'requestId': 'req_begin', 'worldId': world_id,
        'operation': 'begin_point',
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'expectedPointId': root_id, 'expectedVersion': 0,
        'expectedCheckpointRevision': revision + 1,
        'pointId': point_id, 'kind': 'normal',
        'timeAdvance': {'boundary': 'elapsed', 'duration': {'amount': 2, 'unit': 'second'}}}
    service.execute('checkpoint_begin_point', begin_request)

    def checkpoint(request_id, operation, **fields):
        payload = {'protocolVersion': 2, 'requestId': request_id, 'worldId': world_id,
                   'operation': operation.replace('checkpoint_', '', 1),
                   'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
                   'expectedPointId': point_id, 'expectedVersion': 0,
                   'expectedCheckpointRevision': None, 'pointId': point_id}
        payload.update(fields)
        return service.execute(operation, payload)

    revision += 1  # start_advance
    service.execute('checkpoint_discover_group', {
        'protocolVersion': 2, 'requestId': 'req_discover', 'worldId': world_id,
        'operation': 'discover_group',
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'expectedPointId': point_id, 'expectedVersion': 0,
        'expectedCheckpointRevision': revision, 'pointId': point_id,
        'groupId': group_id, 'initiatorId': 'person_a',
        'actionText': '走向讲台。', 'targetIds': None})
    service.execute('checkpoint_extend_group', {
        'protocolVersion': 2, 'requestId': 'req_extend', 'worldId': world_id,
        'operation': 'extend_group',
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'expectedPointId': point_id, 'expectedVersion': 0,
        'expectedCheckpointRevision': revision + 1, 'pointId': point_id,
        'groupId': group_id, 'sourceId': 'person_a', 'targets': [],
        'admittedMember': None})
    service.execute('checkpoint_close_group', {
        'protocolVersion': 2, 'requestId': 'req_close', 'worldId': world_id,
        'operation': 'close_group',
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'expectedPointId': point_id, 'expectedVersion': 0,
        'expectedCheckpointRevision': revision + 2, 'pointId': point_id,
        'groupId': group_id})
    roster = frozenset(ORDER)
    stage = service.execute('checkpoint_stage_unit', {
        'protocolVersion': 2, 'requestId': 'req_stage', 'worldId': world_id,
        'operation': 'stage_unit',
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'expectedPointId': point_id, 'expectedVersion': 0,
        'expectedCheckpointRevision': revision + 3, 'pointId': point_id,
        'groupId': group_id,
        'candidates': single_group(['person_a'], roster, group_id).model_dump(mode='json'),
        'results': {'person_a': '走上了讲台。'}})
    assert stage['data']['working']['cursor'] == 1
    assert stage['data']['working']['actedIds'] == ['person_a']
    for index, actor in enumerate(ORDER[1:], start=1):
        service.execute('checkpoint_record_skip', {
            'protocolVersion': 2, 'requestId': f'req_skip_{index}', 'worldId': world_id,
            'operation': 'record_skip',
            'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
            'expectedPointId': point_id, 'expectedVersion': 0,
            'expectedCheckpointRevision': revision + 3 + index, 'pointId': point_id,
            'slotActorId': actor})
    service.execute('checkpoint_seal_point', {
        'protocolVersion': 2, 'requestId': 'req_seal', 'worldId': world_id,
        'operation': 'seal_point',
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'expectedPointId': point_id, 'expectedVersion': 0,
        'expectedCheckpointRevision': revision + 9, 'pointId': point_id})

    merged = point_entity_deltas(
        [single_group(['person_a'], roster)], None)
    commit = service.execute('commit_point', {
        'protocolVersion': 2, 'requestId': 'req_commit', 'worldId': world_id,
        'advanceId': 'advance_1', 'roundId': 'round_1',
        'expectedPointId': root_id, 'expectedVersion': 0,
        'expectedCheckpointRevision': revision + 10,
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'pointId': point_id,
        'point': {'worldId': world_id, 'id': point_id, 'sequence': 1,
                  'kind': 'normal', 'previousPointId': root_id,
                  'roundId': 'round_1', 'advanceId': 'advance_1',
                  'trigger': 'player', 'linkedFromPointId': None,
                  'timeAdvance': {'boundary': 'elapsed',
                                  'duration': {'amount': 2, 'unit': 'second'}},
                  'entityDeltas': {key: delta.model_dump(mode='json')
                                   for key, delta in merged.items()}},
        'settlementGroups': [single_group(['person_a'], roster, group_id).model_dump(mode='json')]})
    assert commit['data']['version'] == 1
    return service, world_id, point_id, root_id, lease


def test_t01_flow_matches_pinned_service_behaviour(service):
    service, world_id, point_id, root_id, lease = run_t01_flow(service)
    state = service.execute('get_state', {'protocolVersion': 2, 'worldId': world_id})
    assert state['data']['version'] == 1
    assert state['data']['stateDigest']
    context = service.execute('get_context', {'protocolVersion': 2, 'worldId': world_id})
    assert context['world']['round']['cursor'] == 6
    assert context['world']['round']['actedIds'] == ['person_a']
    assert context['control']['phase'] == 'assess_continuation'
    listing = service.execute('list_points', {'protocolVersion': 2, 'worldId': world_id})
    assert {point['kind'] for point in listing['data']['points']} >= {'normal'}


def test_t01_head_narration_after_commit(service):
    service, world_id, point_id, root_id, lease = run_t01_flow(service)
    claim = service.execute('narration_claim', {
        'protocolVersion': 2, 'requestId': 'req_claim_p1', 'worldId': world_id,
        'pointId': point_id, 'mode': 'head',
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'currentClaim': None})
    submit = service.execute('narration_submit', {
        'protocolVersion': 2, 'requestId': 'req_submit_p1', 'worldId': world_id,
        'pointId': point_id, 'mode': 'head', 'claimToken': claim['data']['claimToken'],
        'generation': claim['data']['generation'],
        'issuedAtEpochMilli': claim['data']['issuedAtEpochMilli'],
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'outcome': 'ready', 'text': '讲台上的粉笔灰。', 'failureReason': None})
    assert submit['data']['narrationStatus'] == 'ready'
    fetched = service.execute('narration_get', {
        'protocolVersion': 2, 'worldId': world_id, 'pointId': point_id,
        'mode': 'head'})
    assert fetched['data']['text'] == '讲台上的粉笔灰。'


def test_idempotent_replay_and_reuse_refusal(service):
    # pause is a checkpoint op on the active work; use the flow mid-flight by
    # pausing right after begin (the flow itself runs to a sealed commit).
    service, world_id, point_id, root_id, lease = run_t01_flow(service)
    context = service.execute('get_context', {'protocolVersion': 2, 'worldId': world_id})
    revision = context['control']['revision']
    context = service.execute('get_context', {'protocolVersion': 2, 'worldId': world_id})
    revision = context['control']['revision']
    request = {
        'protocolVersion': 2, 'requestId': 'req_pause', 'worldId': world_id,
        'operation': 'pause',
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'expectedPointId': point_id, 'expectedVersion': 1,
        'expectedCheckpointRevision': revision}
    first = service.execute('checkpoint_pause', request)
    assert first['replayed'] is False
    revision_after = first['control']['revision']
    replay = service.execute('checkpoint_pause', request)
    assert replay['replayed'] is True
    assert replay['control']['revision'] == revision_after
    # schema-legal but different content: the reuse refusal fires before any
    # binding validation; schema-illegal payloads get request_malformed.
    tampered = dict(request, expectedCheckpointRevision=revision + 50)
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_pause', tampered)
    assert excinfo.value.code == 'request_id_reused'


def test_binding_and_lease_refusals(service):
    service, world_id, point_id, root_id, lease = run_t01_flow(service)
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_record_skip', {
            'protocolVersion': 2, 'requestId': 'req_bad_lease', 'worldId': world_id,
                'operation': 'record_skip',
            'leaseToken': 'lease_wrong', 'fenceEpoch': lease['fenceEpoch'],
            'expectedPointId': point_id, 'expectedVersion': 1,
            'expectedCheckpointRevision': 99, 'pointId': point_id,
            'slotActorId': 'person_b'})
    assert excinfo.value.code == 'lease_invalid'
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_record_skip', {
            'protocolVersion': 2, 'requestId': 'req_bad_version', 'worldId': world_id,
                'operation': 'record_skip',
            'leaseToken': lease['leaseToken'], 'fenceEpoch': 7,
            'expectedPointId': point_id, 'expectedVersion': 1,
            'expectedCheckpointRevision': 99, 'pointId': point_id,
            'slotActorId': 'person_b'})
    assert excinfo.value.code == 'stale_epoch'
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_begin_point', {
            'protocolVersion': 2, 'requestId': 'req_bad_begin', 'worldId': world_id,
            'operation': 'begin_point',
            'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
            'expectedPointId': root_id, 'expectedVersion': 5,
            'expectedCheckpointRevision': 5, 'pointId': 'point_new',
            'kind': 'normal',
            'timeAdvance': {'boundary': 'elapsed',
                            'duration': {'amount': 1, 'unit': 'second'}}})
    # after commit the round is in assess_continuation: begin is refused on
    # phase before the version binding is even evaluated.
    assert excinfo.value.code == 'phase_invalid'


def test_ladder_refusals_on_sealed_work(service):
    service, world_id, point_id, root_id, lease = run_t01_flow(service)
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_record_skip', {
            'protocolVersion': 2, 'requestId': 'req_skip_sealed', 'worldId': world_id,
        'operation': 'record_skip',
            'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
            'expectedPointId': point_id, 'expectedVersion': 1,
            'expectedCheckpointRevision': 99, 'pointId': point_id,
            'slotActorId': 'person_b'})
    assert excinfo.value.code in ('phase_invalid', 'version_mismatch')
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_stage_time_scan', {
            'protocolVersion': 2, 'requestId': 'req_scan_sealed', 'worldId': world_id,
        'operation': 'stage_time_scan',
            'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
            'expectedPointId': point_id, 'expectedVersion': 1,
            'expectedCheckpointRevision': 99, 'pointId': point_id,
            'candidates': SettlementGroup.model_validate({
                'groupId': None, 'actorIds': [], 'positions': {}, 'appearances': {},
                'tasksAchieved': {}, 'subtasksAdded': {}, 'personalities': {},
                'sanities': {}, 'taskCoverageIds': sorted(ORDER),
                'personalityCoverageIds': []}).model_dump(mode='json')})
    assert excinfo.value.code in ('phase_invalid', 'version_mismatch')
