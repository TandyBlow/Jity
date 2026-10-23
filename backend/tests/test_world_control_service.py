"""A2-1 service acceptance: the T01-shaped flow with its real bindings, plus
regression probes for the independent-review findings (2026-10-23 round 2).

Every flow response is validated against its exported success envelope, so
the service answers the shared contract shapes, not an ad-hoc dict. The
checkpoint arithmetic follows the T01 trace: every checkpoint operation
(start_advance, begin_point included) consumes one checkpoint revision, and
every checkpoint write binds the *committed* head — expectedPointId stays the
captured root while the work is active.
"""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.services.world.control import ServiceRefusal, WorldService
from app.services.world.merge import point_entity_deltas
from app.services.world.store import FixtureBaselineStore
from app.schemas.world.v2.envelopes import ContextResponse
from app.schemas.world.v2.requests import (
    AllocateIdsSuccess, BeginPointSuccess, CloseGroupSuccess, CommitPointSuccess,
    CreateWorldSuccess, DiscoverGroupSuccess, ExtendGroupSuccess, GetStateSuccess,
    ListPointsSuccess, NarrationClaimSuccess, NarrationGetSuccess,
    NarrationSubmitSuccess, PreviewPointSuccess, RecordSkipSuccess,
    SealPointSuccess, StageUnitSuccess, StartAdvanceSuccess,
)
from app.schemas.world.v2.work import SettlementGroup

DESIGN = Path(__file__).resolve().parents[2] / 'design/world-protocol/v2'
ORDER = ['person_a', 'person_b', 'person_c', 'person_d', 'person_e', 'person_f']
TIME_ADVANCE = {'boundary': 'elapsed', 'duration': {'amount': 2, 'unit': 'second'}}
_CHECKPOINT_SUCCESS = {
    'checkpoint_discover_group': DiscoverGroupSuccess,
    'checkpoint_extend_group': ExtendGroupSuccess,
    'checkpoint_close_group': CloseGroupSuccess,
    'checkpoint_stage_unit': StageUnitSuccess,
    'checkpoint_record_skip': RecordSkipSuccess,
    'checkpoint_seal_point': SealPointSuccess,
}


def initial_template():
    snapshot = json.loads(
        (DESIGN / 'fixtures/projections/normal.expected.json').read_text(encoding='utf-8'))
    template = snapshot['initial']
    template.pop('worldId', None)
    return template


def single_group(actors, coverage, group_id='group_a', **overrides):
    body = {
        'groupId': group_id, 'actorIds': actors,
        'positions': {}, 'appearances': {}, 'tasksAchieved': {},
        'subtasksAdded': {}, 'personalities': {}, 'sanities': {},
        'taskCoverageIds': sorted(coverage), 'personalityCoverageIds': [],
    }
    body.update(overrides)
    return SettlementGroup.model_validate(body)


@pytest.fixture()
def service():
    return WorldService(FixtureBaselineStore())


def _payload(request_id, world_id, lease, **fields):
    return {'protocolVersion': 2, 'requestId': request_id, 'worldId': world_id,
            'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'], **fields}


def _run(service, operation, request_dict, envelope_model):
    envelope = service.execute(operation, request_dict)
    if envelope_model is not None:
        envelope_model.model_validate(envelope)
    return envelope


def _claim_and_submit(service, world_id, lease, point_id, request_id, text,
                      mode='head'):
    claim = _run(service, 'narration_claim', _payload(
        f'{request_id}_claim', world_id, lease, pointId=point_id, mode=mode,
        currentClaim=None), NarrationClaimSuccess)
    submit = _run(service, 'narration_submit', _payload(
        f'{request_id}_submit', world_id, lease, pointId=point_id, mode=mode,
        claimToken=claim['data']['claimToken'],
        generation=claim['data']['generation'],
        issuedAtEpochMilli=claim['data']['issuedAtEpochMilli'],
        outcome='ready', text=text, failureReason=None), NarrationSubmitSuccess)
    return claim, submit


def open_round(service):
    """create → root narration → allocate → start_advance (no begin yet).
    Returns the ids, the lease and the next expected checkpoint revision (1)."""
    created = _run(service, 'create_world', {
        'protocolVersion': 2, 'requestId': 'req_create',
        'initial': initial_template()}, CreateWorldSuccess)
    world_id = created['data']['worldId']
    root_id = created['data']['rootPointId']
    lease = created['data']['lease']
    assert set(lease) == {'leaseToken', 'fenceEpoch', 'expiresAtEpochMilli'}
    _claim_and_submit(service, world_id, lease, root_id, 'req_root', '开学第一天。')

    allocations = _run(service, 'allocate_ids', _payload(
        'req_alloc', world_id, lease, allocationKey='alloc_round_1',
        slots=[{'slotKey': 'point_1', 'kind': 'point', 'scope': None},
               {'slotKey': 'group_a', 'kind': 'group', 'scope': 'round_1'}]),
        AllocateIdsSuccess)
    ids = {item['slotKey']: item['id'] for item in allocations['data']['allocations']}
    point_id, group_id = ids['point_1'], ids['group_a']

    _run(service, 'checkpoint_start_advance', _payload(
        'req_advance', world_id, lease, operation='start_advance',
        expectedPointId=root_id, expectedVersion=0, expectedCheckpointRevision=0,
        advanceId='advance_1', inputId='input_1', roundId='round_1',
        inputText='走进教室。', order=ORDER), StartAdvanceSuccess)
    return {'world_id': world_id, 'root_id': root_id, 'point_id': point_id,
            'group_id': group_id, 'lease': lease, 'revision': 1,
            'head_digest': created['world']['head']['stateDigest']}


def begin_work(service):
    """open_round plus the first begin_point; revision 2 afterwards."""
    state = open_round(service)
    _run(service, 'checkpoint_begin_point', _payload(
        'req_begin', state['world_id'], state['lease'], operation='begin_point',
        expectedPointId=state['root_id'], expectedVersion=0,
        expectedCheckpointRevision=state['revision'],
        pointId=state['point_id'], kind='normal', timeAdvance=TIME_ADVANCE),
        BeginPointSuccess)
    state['revision'] += 1
    return state


def run_t01_flow(service, commit=True):
    """The full T01 operation order with trace-true bindings; with
    commit=False it stops after seal so commit-tamper probes can rebuild the
    request themselves."""
    state = begin_work(service)
    world_id, root_id = state['world_id'], state['root_id']
    point_id, group_id = state['point_id'], state['group_id']
    lease = state['lease']
    revision = state['revision']  # 2 after start_advance + begin

    def checkpoint(request_id, operation, **fields):
        nonlocal revision
        envelope = _run(service, operation, _payload(
            request_id, world_id, lease,
            operation=operation.removeprefix('checkpoint_'),
            expectedPointId=root_id, expectedVersion=0,
            expectedCheckpointRevision=revision, pointId=point_id, **fields),
            _CHECKPOINT_SUCCESS[operation])
        revision += 1
        return envelope

    checkpoint('req_discover', 'checkpoint_discover_group', groupId=group_id,
               initiatorId='person_a', actionText='走向讲台。', targetIds=None)
    checkpoint('req_extend', 'checkpoint_extend_group', groupId=group_id,
               sourceId='person_a', targets=[], admittedMember=None)
    checkpoint('req_close', 'checkpoint_close_group', groupId=group_id)
    roster = frozenset(ORDER)
    stage = checkpoint('req_stage', 'checkpoint_stage_unit', groupId=group_id,
                       candidates=single_group(['person_a'], roster, group_id),
                       results={'person_a': '走上了讲台。'})
    assert stage['data']['working']['cursor'] == 1
    assert stage['data']['working']['actedIds'] == ['person_a']
    assert stage['data']['working']['intentStatus'] == 'consumed'
    for index, actor in enumerate(ORDER[1:], start=1):
        skip = checkpoint(f'req_skip_{index}', 'checkpoint_record_skip',
                          slotActorId=actor)
        assert skip['data']['working']['intentStatus'] == 'consumed'

    # s16: preview runs before the seal, twice, and never moves the revision.
    preview_request = {
        'protocolVersion': 2, 'worldId': world_id, 'advanceId': 'advance_1',
        'roundId': 'round_1', 'pointId': point_id, 'expectedPointId': root_id,
        'expectedVersion': 0, 'expectedCheckpointRevision': revision,
        'timeAdvance': TIME_ADVANCE,
        'settlementGroups': [single_group(['person_a'], roster, group_id)]}
    first = _run(service, 'preview_point', preview_request, PreviewPointSuccess)
    second = _run(service, 'preview_point', preview_request, PreviewPointSuccess)
    assert first['data'] == second['data']
    assert first['data']['pointProjection']['sequence'] == 1
    assert first['data']['pointProjection']['previousPointId'] == root_id
    for key in ('requestId', 'requestHash', 'replayed'):
        assert key not in first
    assert first['data']['workingStateDigest'] == second['data']['workingStateDigest']
    context = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    assert context['control']['revision'] == revision

    seal = checkpoint('req_seal', 'checkpoint_seal_point')
    assert seal['data']['prefixDigest']

    merged = point_entity_deltas([single_group(['person_a'], roster, group_id)], None)
    commit_request = {
        'protocolVersion': 2, 'requestId': 'req_commit', 'worldId': world_id,
        'advanceId': 'advance_1', 'roundId': 'round_1',
        'expectedPointId': root_id, 'expectedVersion': 0,
        'expectedCheckpointRevision': revision,
        'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
        'pointId': point_id,
        'point': {'worldId': world_id, 'id': point_id, 'sequence': 1,
                  'kind': 'normal', 'previousPointId': root_id,
                  'roundId': 'round_1', 'advanceId': 'advance_1',
                  'trigger': 'player', 'linkedFromPointId': None,
                  'timeAdvance': TIME_ADVANCE,
                  'entityDeltas': {key: delta.model_dump(mode='json')
                                   for key, delta in merged.items()}},
        'settlementGroups': [single_group(['person_a'], roster, group_id)]}
    if not commit:
        state.update(revision=revision, commit_request=commit_request)
        return state
    commit = _run(service, 'commit_point', commit_request, CommitPointSuccess)
    assert commit['data']['version'] == 1
    state.update(revision=revision + 1)
    return state


# --- the T01-shaped acceptance flow ------------------------------------------


def test_t01_flow_matches_pinned_service_behaviour(service):
    state = run_t01_flow(service)
    world_id, point_id, root_id = state['world_id'], state['point_id'], state['root_id']
    # head and working pointers: the commit promoted everything at once
    context = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    assert context['world']['head']['pointId'] == point_id
    assert context['world']['head']['version'] == 1
    assert context['world']['advance']['intentStatus'] == 'consumed'
    assert context['world']['round']['cursor'] == 6
    assert context['world']['round']['actedIds'] == ['person_a']
    assert context['control']['phase'] == 'assess_continuation'
    assert context['work'] is None
    assert context['activeInput'] is None
    # historical and head reads answer per point (P2-8)
    head_state = _run(service, 'get_state', {'protocolVersion': 2,
                                             'worldId': world_id}, GetStateSuccess)
    assert head_state['data']['version'] == 1
    assert head_state['data']['state']['time']['dateTime'] == '2026-01-01T11:59:02'
    root_state = _run(service, 'get_state', {'protocolVersion': 2,
                                             'worldId': world_id,
                                             'point': root_id}, GetStateSuccess)
    assert root_state['data']['version'] == 0
    assert root_state['data']['state']['time']['dateTime'] == '2026-01-01T11:59:00'
    assert root_state['data']['stateDigest'] == state['head_digest']
    listing = _run(service, 'list_points', {'protocolVersion': 2,
                                            'worldId': world_id}, ListPointsSuccess)
    assert [point['kind'] for point in listing['data']['points']] == ['root', 'normal']


def test_t01_head_narration_after_commit(service):
    state = run_t01_flow(service)
    world_id, point_id = state['world_id'], state['point_id']
    _claim_and_submit(service, world_id, state['lease'], point_id,
                      'req_p1', '讲台上的粉笔灰。')
    context = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    assert context['world']['head']['narrationStatus'] == 'ready'
    assert context['control']['gate']['status'] == 'none'
    fetched = _run(service, 'narration_get', {'protocolVersion': 2,
                                              'worldId': world_id,
                                              'pointId': point_id,
                                              'mode': 'head'}, NarrationGetSuccess)
    assert fetched['data']['text'] == '讲台上的粉笔灰。'


def test_working_and_head_promote_only_at_commit(service):
    state = run_t01_flow(service, commit=False)
    world_id = state['world_id']
    context = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    # begin must not move the committed head or touch the committed intent
    assert context['world']['head']['pointId'] == state['root_id']
    assert context['world']['head']['version'] == 0
    assert context['world']['activePointId'] == state['point_id']
    assert context['world']['advance']['intentStatus'] == 'pending'
    # stage/skip consume the working intent only
    assert context['work']['working']['intentStatus'] == 'consumed'
    assert context['work']['sealed'] is True
    assert context['work']['baseline']['headPointId'] == state['root_id']
    commit = _run(service, 'commit_point', state['commit_request'], CommitPointSuccess)
    assert commit['data']['version'] == 1
    assert commit['world']['head']['pointId'] == state['point_id']
    assert commit['world']['advance']['intentStatus'] == 'consumed'


# --- P1-1: unified binding and threshold checks ------------------------------


def test_checkpoint_bindings_refuse_wrong_head_version_revision_point(service):
    state = begin_work(service)
    world_id, point_id, root_id = state['world_id'], state['point_id'], state['root_id']
    lease = state['lease']

    def skip_request(request_id, **overrides):
        request = _payload(request_id, world_id, lease, operation='record_skip',
                           expectedPointId=root_id, expectedVersion=0,
                           expectedCheckpointRevision=state['revision'],
                           pointId=point_id, slotActorId='person_b')
        request.update(overrides)
        return request

    for request_id, overrides in [
            ('req_bad_head', {'expectedPointId': point_id}),
            ('req_bad_version', {'expectedVersion': 1}),
            ('req_bad_revision', {'expectedCheckpointRevision': 99}),
            ('req_bad_point', {'pointId': 'point_other'})]:
        with pytest.raises(ServiceRefusal) as excinfo:
            service.execute('checkpoint_record_skip', skip_request(request_id, **overrides))
        assert excinfo.value.code == 'version_mismatch', request_id
    skip = service.execute('checkpoint_record_skip', skip_request('req_ok_skip'))
    RecordSkipSuccess.model_validate(skip)

    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_start_advance', _payload(
            'req_bad_advance', world_id, lease, operation='start_advance',
            expectedPointId=point_id, expectedVersion=0,
            expectedCheckpointRevision=state['revision'],
            advanceId='advance_x', inputId='input_x', roundId='round_x',
            inputText='另一条输入。', order=ORDER))
    assert excinfo.value.code == 'version_mismatch'


def test_head_narration_and_checkpoint_ops_fence_through_lease(service):
    state = begin_work(service)
    world_id, root_id, point_id = state['world_id'], state['root_id'], state['point_id']
    lease = state['lease']
    wrong_token = _payload('req_bad_token', world_id, lease, pointId=root_id,
                           mode='head', outcome='ready',
                           text='x', failureReason=None,
                           claimToken='claim_1_x', generation=1,
                           issuedAtEpochMilli=1)
    wrong_token['leaseToken'] = 'lease_wrong'
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_submit', wrong_token)
    assert excinfo.value.code == 'lease_invalid'
    wrong_epoch = dict(wrong_token, requestId='req_bad_epoch')
    wrong_epoch['leaseToken'] = lease['leaseToken']
    wrong_epoch['fenceEpoch'] = lease['fenceEpoch'] + 1
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_submit', wrong_epoch)
    assert excinfo.value.code == 'stale_epoch'


def test_conclude_blocked_while_head_narration_pending(service):
    state = run_t01_flow(service)
    service, world_id, point_id, lease = (
        service, state['world_id'], state['point_id'], state['lease'])
    context = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    revision = context['control']['revision']
    conclusion = {'kind': 'handback', 'closedBy': 'model', 'cancelReason': None}
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('round_conclusion_conclude', _payload(
            'req_conclude_early', world_id, lease,
            operation='conclude', advanceId='advance_1',
            roundId='round_1', expectedPointId=point_id, expectedVersion=1,
            expectedCheckpointRevision=revision, conclusion=conclusion))
    assert excinfo.value.code == 'narration_blocked'
    _claim_and_submit(service, world_id, lease, point_id, 'req_p1', '粉笔灰。')
    concluded = service.execute('round_conclusion_conclude', _payload(
        'req_conclude', world_id, lease, operation='conclude',
        advanceId='advance_1', roundId='round_1', expectedPointId=point_id,
        expectedVersion=1, expectedCheckpointRevision=revision, conclusion=conclusion))
    assert concluded['data'] == {'kind': 'handback', 'roundId': 'round_1',
                                 'nextRoundId': None}
    context = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    assert context['control']['phase'] == 'complete'
    assert context['world']['advance']['intentStatus'] == 'expired'


# --- P1-3: frozen candidates are verified in full ----------------------------


def test_stage_refuses_incomplete_coverage(service):
    state = begin_work(service)
    world_id, point_id, group_id, lease = (
        state['world_id'], state['point_id'], state['group_id'], state['lease'])
    _run(service, 'checkpoint_discover_group', _payload(
        'req_discover', world_id, lease, operation='discover_group',
        expectedPointId=state['root_id'], expectedVersion=0,
        expectedCheckpointRevision=state['revision'], pointId=point_id,
        groupId=group_id, initiatorId='person_a', actionText='走向讲台。',
        targetIds=None), DiscoverGroupSuccess)
    _run(service, 'checkpoint_extend_group', _payload(
        'req_extend', world_id, lease, operation='extend_group',
        expectedPointId=state['root_id'], expectedVersion=0,
        expectedCheckpointRevision=state['revision'] + 1, pointId=point_id,
        groupId=group_id, sourceId='person_a', targets=[], admittedMember=None),
        ExtendGroupSuccess)
    _run(service, 'checkpoint_close_group', _payload(
        'req_close', world_id, lease, operation='close_group',
        expectedPointId=state['root_id'], expectedVersion=0,
        expectedCheckpointRevision=state['revision'] + 2, pointId=point_id,
        groupId=group_id), CloseGroupSuccess)
    stage_revision = state['revision'] + 3
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_stage_unit', _payload(
            'req_stage_bad', world_id, lease, operation='stage_unit',
            expectedPointId=state['root_id'], expectedVersion=0,
            expectedCheckpointRevision=stage_revision, pointId=point_id,
            groupId=group_id,
            candidates=single_group(['person_a'], ['person_a'], group_id),
            results={'person_a': '结果。'}))
    assert excinfo.value.code == 'request_malformed'
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_stage_unit', _payload(
            'req_stage_roster', world_id, lease, operation='stage_unit',
            expectedPointId=state['root_id'], expectedVersion=0,
            expectedCheckpointRevision=stage_revision, pointId=point_id,
            groupId=group_id,
            candidates=single_group(['person_z'], frozenset(ORDER), group_id),
            results={'person_z': '结果。'}))
    assert excinfo.value.code == 'version_mismatch'


def test_commit_rejects_tampered_frozen_candidates(service):
    state = run_t01_flow(service, commit=False)
    service, world_id = service, state['world_id']
    roster = frozenset(ORDER)

    counter = [0]

    def commit_with(groups, deltas=None):
        counter[0] += 1
        request = copy.deepcopy(state['commit_request'])
        request['requestId'] = f'req_commit_tamper_{counter[0]}'
        request['settlementGroups'] = [
            group.model_dump(mode='json') if hasattr(group, 'model_dump') else group
            for group in groups]
        if deltas is not None:
            request['point']['entityDeltas'] = deltas
        return service.execute('commit_point', request)

    # 1. sealed appearance mutated and the commit deltas adjusted to match:
    #    the content hash of the frozen candidate no longer matches.
    mutated = single_group(['person_a'], roster, state['group_id'],
                           appearances={'person_a': [
                               {'id': 'desc_tamper', 'text': '伪证',
                                'supersedes': []}]})
    merged = point_entity_deltas([mutated], None)
    with pytest.raises(ServiceRefusal) as excinfo:
        commit_with([mutated], {key: delta.model_dump(mode='json')
                                for key, delta in merged.items()})
    assert excinfo.value.code == 'version_mismatch'
    # 2. closed-group member swapped A → B
    swapped = single_group(['person_b'], roster, state['group_id'])
    with pytest.raises(ServiceRefusal) as excinfo:
        commit_with([swapped])
    assert excinfo.value.code == 'version_mismatch'
    # 3. the untouched frozen candidates still commit verbatim
    commit = service.execute('commit_point', state['commit_request'])
    CommitPointSuccess.model_validate(commit)
    assert commit['replayed'] is False


# --- P1-4: idempotency inside the transaction --------------------------------


def test_create_world_idempotency_replays_and_refuses_reuse(service):
    request = {'protocolVersion': 2, 'requestId': 'req_create',
               'initial': initial_template()}
    first = _run(service, 'create_world', request, CreateWorldSuccess)
    replay = service.execute('create_world', request)
    assert replay['replayed'] is True
    assert replay['data']['worldId'] == first['data']['worldId']
    assert service.store.world(first['data']['worldId']) is not None
    assert len(service.store._worlds) == 1
    tampered = dict(request, initial=initial_template() | {'protagonistId': 'person_b'})
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('create_world', tampered)
    assert excinfo.value.code == 'request_id_reused'


def test_concurrent_duplicate_begin_replays(service):
    state = open_round(service)
    service, world_id = service, state['world_id']
    request = _payload('req_begin_race', world_id, state['lease'],
                       operation='begin_point', expectedPointId=state['root_id'],
                       expectedVersion=0,
                       expectedCheckpointRevision=state['revision'],
                       pointId='point_race', kind='normal',
                       timeAdvance=TIME_ADVANCE)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future
                   in [pool.submit(service.execute, 'checkpoint_begin_point', request),
                       pool.submit(service.execute, 'checkpoint_begin_point', request)]]
    assert sorted(result['replayed'] for result in results) == [False, True]
    revision = service.execute('get_context', {'protocolVersion': 2,
                                               'worldId': world_id})['control']['revision']
    assert revision == state['revision'] + 1
    assert service.execute('get_context', {'protocolVersion': 2,
                                           'worldId': world_id})['work']['pointId'] \
        == 'point_race'


def test_idempotent_replay_and_reuse_refusal(service):
    state = run_t01_flow(service)
    world_id, point_id, lease = state['world_id'], state['point_id'], state['lease']
    context = service.execute('get_context', {'protocolVersion': 2,
                                              'worldId': world_id})
    revision = context['control']['revision']
    request = _payload('req_pause', world_id, lease, operation='pause',
                       expectedPointId=point_id, expectedVersion=1,
                       expectedCheckpointRevision=revision)
    first = service.execute('checkpoint_pause', request)
    assert first['replayed'] is False
    revision_after = first['control']['revision']
    replay = service.execute('checkpoint_pause', request)
    assert replay['replayed'] is True
    assert replay['control']['revision'] == revision_after
    tampered = dict(request, expectedCheckpointRevision=revision + 50)
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_pause', tampered)
    assert excinfo.value.code == 'request_id_reused'


# --- P1-5: preview and lease renewal paths -----------------------------------


def test_preview_runs_mid_checkpoint_and_does_not_advance_state(service):
    state = begin_work(service)
    world_id, point_id, root_id, lease = (
        state['world_id'], state['point_id'], state['root_id'], state['lease'])
    revision = state['revision']
    _run(service, 'checkpoint_discover_group', _payload(
        'req_discover', world_id, lease, operation='discover_group',
        expectedPointId=root_id, expectedVersion=0,
        expectedCheckpointRevision=revision, pointId=point_id,
        groupId=state['group_id'], initiatorId='person_a',
        actionText='走向讲台。', targetIds=None), DiscoverGroupSuccess)
    preview_request = {
        'protocolVersion': 2, 'worldId': world_id, 'advanceId': 'advance_1',
        'roundId': 'round_1', 'pointId': point_id, 'expectedPointId': root_id,
        'expectedVersion': 0, 'expectedCheckpointRevision': revision + 1,
        'timeAdvance': TIME_ADVANCE,
        'settlementGroups': [single_group(['person_a'], frozenset(ORDER),
                                          state['group_id'])]}
    preview = _run(service, 'preview_point', preview_request, PreviewPointSuccess)
    assert preview['data']['pointId'] == point_id
    assert preview['data']['workingState']['time']['dateTime'] == '2026-01-01T11:59:02'
    context = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    assert context['control']['revision'] == revision + 1
    assert context['world']['head']['version'] == 0
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('preview_point', dict(preview_request,
                                              expectedCheckpointRevision=99))
    assert excinfo.value.code == 'version_mismatch'


def test_lease_renew_and_release(service):
    state = begin_work(service)
    world_id, lease = state['world_id'], state['lease']
    renewed = _run(service, 'lease_renew', _payload(
        'req_renew', world_id, lease), None)
    assert renewed['data']['leaseToken'] == lease['leaseToken']
    assert renewed['data']['fenceEpoch'] == lease['fenceEpoch']
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('lease_renew', _payload(
            'req_renew_bad', world_id,
            {'leaseToken': 'lease_wrong', 'fenceEpoch': lease['fenceEpoch'],
             'expiresAtEpochMilli': lease['expiresAtEpochMilli']}))
    assert excinfo.value.code == 'lease_invalid'
    released = service.execute('lease_release', _payload(
        'req_release', world_id, lease))
    assert released['data'] == {'released': True}
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_pause', _payload(
            'req_pause_dead', world_id, lease, operation='pause',
            expectedPointId=state['point_id'], expectedVersion=0,
            expectedCheckpointRevision=state['revision']))
    assert excinfo.value.code == 'lease_invalid'


# --- P1-6: narration state is authoritative per point ------------------------


def test_history_narration_never_clears_the_head_gate(service):
    state = run_t01_flow(service)
    world_id, root_id, point_id, lease = (
        state['world_id'], state['root_id'], state['point_id'], state['lease'])
    # history narration carries no lease fields by schema
    root_claim = service.execute('narration_claim', {
        'protocolVersion': 2, 'requestId': 'req_root_claim_hist',
        'worldId': world_id, 'pointId': root_id, 'mode': 'history',
        'currentClaim': None, 'leaseToken': None, 'fenceEpoch': None})
    NarrationClaimSuccess.model_validate(root_claim)
    service.execute('narration_submit', {
        'protocolVersion': 2, 'requestId': 'req_root_submit_hist',
        'worldId': world_id, 'pointId': root_id, 'mode': 'history',
        'claimToken': root_claim['data']['claimToken'],
        'generation': root_claim['data']['generation'],
        'issuedAtEpochMilli': root_claim['data']['issuedAtEpochMilli'],
        'outcome': 'ready', 'text': '历史补写的叙事。', 'failureReason': None})
    context = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    assert context['control']['gate']['status'] == 'pending'
    assert context['world']['head']['narrationStatus'] == 'pending'
    # head narration ops only target the committed head
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_claim', _payload(
            'req_head_on_root', world_id, lease, pointId=root_id, mode='head',
            currentClaim=None))
    assert excinfo.value.code == 'version_mismatch'
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_claim', {'protocolVersion': 2,
                                            'requestId': 'req_unknown_point',
                                            'worldId': world_id,
                                            'pointId': 'point_missing',
                                            'mode': 'history',
                                            'currentClaim': None,
                                            'leaseToken': None,
                                            'fenceEpoch': None})
    assert excinfo.value.code == 'version_mismatch'
    # the matching head submit clears the gate
    _claim_and_submit(service, world_id, lease, point_id, 'req_p1', '粉笔灰。')
    context = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    assert context['control']['gate']['status'] == 'none'
    assert context['world']['head']['narrationStatus'] == 'ready'


# --- P1-7: allocation ids are unique across keys and scopes ------------------


def test_allocate_ids_are_unique_across_keys_and_scopes(service):
    state = begin_work(service)
    world_id, lease = state['world_id'], state['lease']

    def allocate(request_id, allocation_key, slots):
        envelope = service.execute('allocate_ids', _payload(
            request_id, world_id, lease, allocationKey=allocation_key,
            slots=slots))
        return envelope['data']['allocations']

    first = allocate('req_alloc_1', 'first_same',
                     [{'slotKey': 'point_1', 'kind': 'point', 'scope': None}])
    other = allocate('req_alloc_2', 'other_same',
                     [{'slotKey': 'point_1', 'kind': 'point', 'scope': None}])
    # the probe's collision: same trailing key fragment, different buckets
    assert first[0]['id'] != other[0]['id']
    again = allocate('req_alloc_1b', 'first_same',
                     [{'slotKey': 'point_1', 'kind': 'point', 'scope': None}])
    assert again[0]['id'] == first[0]['id']
    scoped = allocate('req_alloc_3', 'key_three',
                      [{'slotKey': 'group_a', 'kind': 'group', 'scope': 'round_1'},
                       {'slotKey': 'group_a', 'kind': 'group', 'scope': 'round_2'}])
    assert len({item['id'] for item in scoped}) == 2


# --- P2-8: historical reads and unknown points -------------------------------


def test_get_state_rejects_unknown_points(service):
    state = begin_work(service)
    world_id = state['world_id']
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('get_state', {'protocolVersion': 2, 'worldId': world_id,
                                      'point': 'point_missing'})
    assert excinfo.value.code == 'version_mismatch'
    root_state = _run(service, 'get_state', {'protocolVersion': 2,
                                             'worldId': world_id,
                                             'point': state['root_id']},
                      GetStateSuccess)
    assert root_state['data']['version'] == 0
    assert root_state['data']['stateDigest'] == state['head_digest']


# --- ladder and lease refusals kept from round 1 ------------------------------


def test_binding_and_lease_refusals(service):
    state = run_t01_flow(service)
    world_id, point_id, lease = state['world_id'], state['point_id'], state['lease']
    context = service.execute('get_context', {'protocolVersion': 2,
                                              'worldId': world_id})
    revision = context['control']['revision']
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_record_skip', _payload(
            'req_bad_lease', world_id, lease, operation='record_skip',
            expectedPointId=point_id, expectedVersion=1,
            expectedCheckpointRevision=revision, pointId=point_id,
            slotActorId='person_b') | {'leaseToken': 'lease_wrong'})
    assert excinfo.value.code == 'lease_invalid'
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_record_skip', _payload(
            'req_bad_epoch', world_id, lease, operation='record_skip',
            expectedPointId=point_id, expectedVersion=1,
            expectedCheckpointRevision=revision, pointId=point_id,
            slotActorId='person_b') | {'fenceEpoch': 7})
    assert excinfo.value.code == 'stale_epoch'
    # after commit the round sits in assess_continuation; binding is checked
    # first, so a stale version is a version_mismatch, not a phase error.
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_begin_point', _payload(
            'req_bad_begin', world_id, lease, operation='begin_point',
            expectedPointId=point_id, expectedVersion=5,
            expectedCheckpointRevision=revision, pointId='point_new',
            kind='normal', timeAdvance=TIME_ADVANCE))
    assert excinfo.value.code == 'version_mismatch'


def test_ladder_refusals_on_committed_round(service):
    state = run_t01_flow(service)
    world_id, point_id, lease = state['world_id'], state['point_id'], state['lease']
    context = service.execute('get_context', {'protocolVersion': 2,
                                              'worldId': world_id})
    revision = context['control']['revision']
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_record_skip', _payload(
            'req_skip_committed', world_id, lease, operation='record_skip',
            expectedPointId=point_id, expectedVersion=1,
            expectedCheckpointRevision=revision, pointId=point_id,
            slotActorId='person_b'))
    assert excinfo.value.code == 'phase_invalid'
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_stage_time_scan', _payload(
            'req_scan_committed', world_id, lease, operation='stage_time_scan',
            expectedPointId=point_id, expectedVersion=1,
            expectedCheckpointRevision=revision, pointId=point_id,
            candidates=single_group([], frozenset(ORDER), None)))
    assert excinfo.value.code == 'phase_invalid'
