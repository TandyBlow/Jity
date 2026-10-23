"""A2-1 service acceptance: the T01-shaped flow with its real bindings, plus
regression probes for the independent-review findings (2026-10-23 rounds 2–4).

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

from app.services.world import control as control_module
from app.services.world.control import ServiceRefusal, WorldService
from app.services.world.merge import point_entity_deltas
from app.services.world.store import FixtureBaselineStore
from app.schemas.world.v2.envelopes import ContextResponse
from app.schemas.world.v2.requests import (
    AllocateIdsSuccess, BeginPointSuccess, CloseGroupSuccess, CommitPointSuccess,
    CreateWorldSuccess, DiscoverGroupSuccess, ExtendGroupSuccess, GetStateSuccess,
    ListPointsSuccess, NarrationClaimSuccess, NarrationClaimRenewSuccess,
    NarrationDeleteSuccess, NarrationGetSuccess,
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
    skip = service.execute('checkpoint_record_skip',
                           skip_request('req_ok_skip', slotActorId='person_a'))
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
    # the admitted-members freeze refuses non-members before the roster
    # predicate even runs
    assert excinfo.value.code == 'request_malformed'


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
    before = service.store.world(world_id)
    # the bypass probe: a head-issued token is not history authorization
    head_claim = service.execute('narration_claim', _payload(
        'req_head_claim', world_id, lease, pointId=point_id,
        mode='head', currentClaim=None))
    head_before_history = service.store.world(world_id)['narrations'][point_id]
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_submit', {
            'protocolVersion': 2, 'requestId': 'req_history_with_head_claim',
            'worldId': world_id, 'pointId': point_id, 'mode': 'history',
            'claimToken': head_claim['data']['claimToken'],
            'generation': head_claim['data']['generation'],
            'issuedAtEpochMilli': head_claim['data']['issuedAtEpochMilli'],
            'outcome': 'ready', 'text': '无租约的越权提交。', 'failureReason': None})
    assert excinfo.value.code == 'claim_fenced'
    # and the reverse fence: the head generation cannot be re-claimed history
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_claim', {
            'protocolVersion': 2, 'requestId': 'req_p1_claim_hist_early',
            'worldId': world_id, 'pointId': point_id, 'mode': 'history',
            'currentClaim': None, 'leaseToken': None, 'fenceEpoch': None})
    assert excinfo.value.code == 'claim_fenced'
    context = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    assert context['control']['gate']['status'] == 'pending'
    # The former head is regenerated under a NEW history generation, without
    # changing its issued head token's mode or touching the current head gate.
    history_request = {
        'protocolVersion': 2, 'requestId': 'req_root_claim_hist',
        'worldId': world_id, 'pointId': root_id, 'mode': 'history',
        'currentClaim': None}
    claim = _run(service, 'narration_claim', history_request, NarrationClaimSuccess)
    old = before['narrations'][root_id]
    assert claim['data']['generation'] == old['generation'] + 1
    assert claim['data']['claimToken'] != old['claim']['claimToken']
    assert claim['data']['fenceEpoch'] is None
    historical = service.store.world(world_id)
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_submit', {
            'protocolVersion': 2, 'requestId': 'req_old_head_token_as_history',
            'worldId': world_id, 'pointId': root_id, 'mode': 'history',
            **{key: old['claim'][key] for key in (
                'claimToken', 'generation', 'issuedAtEpochMilli')},
            'outcome': 'ready', 'text': '旧 head token 越权。', 'failureReason': None})
    assert excinfo.value.code == 'claim_fenced'
    assert service.store.world(world_id) == historical
    authority = {key: claim['data'][key] for key in (
        'claimToken', 'generation', 'issuedAtEpochMilli')}
    # Lost-response replay is a token-free summary; a new request needs the
    # history claim's current authority to retrieve its token.
    replay = _run(service, 'narration_claim', history_request, NarrationClaimSuccess)
    assert replay['replayed'] is True
    assert 'claimToken' not in replay['data']
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_claim', dict(
            history_request, requestId='req_history_no_authority'))
    assert excinfo.value.code == 'claim_fenced'
    retrieved = _run(service, 'narration_claim', dict(
        history_request, requestId='req_history_retrieve', currentClaim=authority),
        NarrationClaimSuccess)
    assert retrieved['data'] == claim['data']
    _run(service, 'narration_claim_renew', {
        'protocolVersion': 2, 'requestId': 'req_history_renew',
        'worldId': world_id, 'pointId': root_id, 'mode': 'history', **authority},
        NarrationClaimRenewSuccess)
    submit = {
        'protocolVersion': 2, 'requestId': 'req_root_submit_hist',
        'worldId': world_id, 'pointId': root_id, 'mode': 'history', **authority,
        'outcome': 'ready', 'text': '历史补写的叙事。', 'failureReason': None}
    _run(service, 'narration_submit', submit, NarrationSubmitSuccess)
    # Deleting historical narration invalidates that generation only; a new
    # claim can regenerate it again, still without acquiring the world lease.
    deleted = _run(service, 'narration_delete', {
        'protocolVersion': 2, 'requestId': 'req_history_delete',
        'worldId': world_id, 'mode': 'history', **authority}, NarrationDeleteSuccess)
    assert deleted['data']['pointId'] == root_id
    next_claim = _run(service, 'narration_claim', dict(
        history_request, requestId='req_history_regenerate'), NarrationClaimSuccess)
    assert next_claim['data']['generation'] == claim['data']['generation'] + 1
    assert next_claim['data']['claimToken'] != authority['claimToken']
    after = service.store.world(world_id)
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_submit', dict(submit, requestId='req_history_late'))
    assert excinfo.value.code == 'claim_fenced'
    assert service.store.world(world_id) == after
    next_authority = {key: next_claim['data'][key] for key in authority}
    _run(service, 'narration_submit', dict(
        submit, requestId='req_history_regenerated_submit', **next_authority),
        NarrationSubmitSuccess)
    context = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    assert context['control']['gate']['status'] == 'pending'
    assert context['world']['head']['narrationStatus'] == 'pending'
    assert context['control']['canCompute'] is False
    assert context['control'] == control_module.control_view(before).model_dump(mode='json')
    after = service.store.world(world_id)
    for key in ('state', 'version', 'round', 'advance', 'work', 'pointStates'):
        assert after[key] == before[key]
    assert after['narrations'][point_id] == head_before_history
    # head narration ops only target the committed head
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_claim', _payload(
            'req_head_on_root', world_id, lease, pointId=root_id,
            mode='head', currentClaim=None))
    assert excinfo.value.code == 'version_mismatch'
    # The normal head path remains usable after all historical operations.
    _claim_and_submit(service, world_id, lease, point_id, 'req_head_ready', '当前叙事。')
    context = _run(service, 'get_context', {'worldId': world_id}, ContextResponse)
    assert context['control']['gate']['status'] == 'none'
    assert context['control']['canCompute'] is True


@pytest.mark.parametrize('after_delete', [False, True])
def test_history_cannot_claim_the_current_head_and_head_stays_recoverable(
        service, after_delete):
    created = _run(service, 'create_world', {
        'protocolVersion': 2, 'requestId': 'req_create',
        'initial': initial_template()}, CreateWorldSuccess)
    world_id, root_id, lease = (created['data']['worldId'],
                                created['data']['rootPointId'], created['data']['lease'])
    if after_delete:
        claim, _ = _claim_and_submit(service, world_id, lease, root_id,
                                     'req_initial_ready', '初始叙事。')
        _run(service, 'narration_delete', _payload(
            'req_initial_delete', world_id, lease, mode='head',
            **{key: claim['data'][key] for key in (
                'claimToken', 'generation', 'issuedAtEpochMilli')}), NarrationDeleteSuccess)
    before = service.store.world(world_id)
    request = {'protocolVersion': 2, 'requestId': 'req_history_on_head',
               'worldId': world_id, 'pointId': root_id, 'mode': 'history',
               'currentClaim': None}
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_claim', request)
    assert excinfo.value.code == 'claim_fenced'
    assert service.store.world(world_id) == before
    claim, _ = _claim_and_submit(service, world_id, lease, root_id,
                                 'req_head_recover', '正常推进叙事。')
    _run(service, 'narration_delete', _payload(
        'req_head_delete', world_id, lease, mode='head',
        **{key: claim['data'][key] for key in (
            'claimToken', 'generation', 'issuedAtEpochMilli')}), NarrationDeleteSuccess)
    _claim_and_submit(service, world_id, lease, root_id, 'req_head_again', '恢复后的叙事。')
    context = _run(service, 'get_context', {'worldId': world_id}, ContextResponse)
    assert context['world']['head']['narrationStatus'] == 'ready'
    assert context['control']['gate']['status'] == 'none'
    assert context['control']['canCompute'] is True


def test_head_claim_recovers_a_legacy_history_claim_on_current_head(service):
    created = _run(service, 'create_world', {
        'protocolVersion': 2, 'requestId': 'req_create',
        'initial': initial_template()}, CreateWorldSuccess)
    world_id, root_id, lease = (created['data']['worldId'],
                                created['data']['rootPointId'], created['data']['lease'])
    now = service.store.clock_milli()

    def legacy_claim(record):
        # State formerly reachable via history claim+submit on a fresh root.
        entry = record['narrations'][root_id]
        entry.update(status='ready', text='旧实现写入的叙事。', claim={
            'claimToken': 'legacy_history_claim', 'generation': 1,
            'mode': 'history', 'fenceEpoch': None,
            'issuedAtEpochMilli': now, 'expiresAtEpochMilli': now + 1000})

    service.store.transact(world_id, legacy_claim)
    before = service.store.world(world_id)
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('narration_delete', {
            'protocolVersion': 2, 'requestId': 'req_legacy_history_delete',
            'worldId': world_id, 'mode': 'history',
            'claimToken': 'legacy_history_claim', 'generation': 1,
            'issuedAtEpochMilli': now})
    assert excinfo.value.code == 'claim_fenced'
    assert service.store.world(world_id) == before
    claim, _ = _claim_and_submit(service, world_id, lease, root_id,
                                 'req_head_recover_legacy', '恢复的 head 叙事。')
    assert claim['data']['generation'] == 2
    assert claim['data']['claimToken'] != 'legacy_history_claim'
    context = _run(service, 'get_context', {'worldId': world_id}, ContextResponse)
    assert context['control']['gate']['status'] == 'none'
    assert context['control']['canCompute'] is True
    assert context['control']['revision'] == before['control']['revision']
    assert context['world']['head']['version'] == 0


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


# --- round-3 review probes pinned as regressions ------------------------------


def _closed_group(service, state):
    revision = state['revision']
    world_id, point_id, root_id, group_id, lease = (
        state['world_id'], state['point_id'], state['root_id'],
        state['group_id'], state['lease'])
    _run(service, 'checkpoint_discover_group', _payload(
        'req_discover', world_id, lease, operation='discover_group',
        expectedPointId=root_id, expectedVersion=0,
        expectedCheckpointRevision=revision, pointId=point_id,
        groupId=group_id, initiatorId='person_a', actionText='走向讲台。',
        targetIds=None), DiscoverGroupSuccess)
    _run(service, 'checkpoint_extend_group', _payload(
        'req_extend', world_id, lease, operation='extend_group',
        expectedPointId=root_id, expectedVersion=0,
        expectedCheckpointRevision=revision + 1, pointId=point_id,
        groupId=group_id, sourceId='person_a', targets=[], admittedMember=None),
        ExtendGroupSuccess)
    _run(service, 'checkpoint_close_group', _payload(
        'req_close', world_id, lease, operation='close_group',
        expectedPointId=root_id, expectedVersion=0,
        expectedCheckpointRevision=revision + 2, pointId=point_id,
        groupId=group_id), CloseGroupSuccess)
    state['revision'] = revision + 3
    return state


@pytest.mark.parametrize('targets', [None, [], ['person_b']])
def test_discover_accepts_target_id_lists(service, targets):
    state = begin_work(service)
    response = _run(service, 'checkpoint_discover_group', _payload(
        'req_discover_ids', state['world_id'], state['lease'],
        operation='discover_group', expectedPointId=state['root_id'],
        expectedVersion=0, expectedCheckpointRevision=state['revision'],
        pointId=state['point_id'], groupId=state['group_id'],
        initiatorId='person_a', actionText='走向讲台。', targetIds=targets),
        DiscoverGroupSuccess)
    assert response['data']['targetIds'] == targets
    assert response['work']['pendingGroup']['targetIds'] == (targets or [])


@pytest.mark.parametrize('kind,boundary,amount', [
    ('normal', 'instant', 0), ('linked', 'elapsed', 2),
    ('instant', 'instant', 2),
])
def test_begin_rejects_invalid_kind_time_without_opening_work(
        service, kind, boundary, amount):
    state = open_round(service)
    before = service.store.world(state['world_id'])
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_begin_point', _payload(
            'req_begin_invalid', state['world_id'], state['lease'],
            operation='begin_point', expectedPointId=state['root_id'],
            expectedVersion=0, expectedCheckpointRevision=state['revision'],
            pointId=state['point_id'], kind=kind,
            timeAdvance={'boundary': boundary,
                         'duration': {'amount': amount, 'unit': 'second'}}))
    assert excinfo.value.code == 'request_malformed'
    assert service.store.world(state['world_id']) == before


def test_retime_preserves_the_point_kind_and_rolls_back_refusal(service):
    state = begin_work(service)
    before = service.store.world(state['world_id'])
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_set_point_time', _payload(
            'req_retime_invalid', state['world_id'], state['lease'],
            operation='set_point_time', expectedPointId=state['root_id'],
            expectedVersion=0, expectedCheckpointRevision=state['revision'],
            pointId=state['point_id'],
            timeAdvance={'boundary': 'instant',
                         'duration': {'amount': 0, 'unit': 'second'}}))
    assert excinfo.value.code == 'request_malformed'
    assert service.store.world(state['world_id']) == before


def test_ready_narration_is_immutable_and_claim_survives_cleared_gate(service):
    state = run_t01_flow(service)
    world_id, point_id, lease = state['world_id'], state['point_id'], state['lease']
    first, _ = _claim_and_submit(service, world_id, lease, point_id,
                                 'req_ready', '固定叙事。')
    claim = _run(service, 'narration_claim', _payload(
        'req_ready_reclaim', world_id, lease, pointId=point_id,
        mode='head', currentClaim=None), NarrationClaimSuccess)
    assert claim['data'] == first['data']
    # Gate timestamps are cleared; claim renewal must use its own metadata.
    renewed = service.execute('narration_claim_renew', _payload(
        'req_ready_renew', world_id, lease, pointId=point_id, mode='head',
        claimToken=claim['data']['claimToken'],
        generation=claim['data']['generation'],
        issuedAtEpochMilli=claim['data']['issuedAtEpochMilli']))
    assert renewed['data']['issuedAtEpochMilli'] == claim['data']['issuedAtEpochMilli']
    request = _payload('req_ready_repeat', world_id, lease, pointId=point_id,
                       mode='head', claimToken=claim['data']['claimToken'],
                       generation=claim['data']['generation'],
                       issuedAtEpochMilli=claim['data']['issuedAtEpochMilli'],
                       outcome='ready', text='固定叙事。', failureReason=None)
    _run(service, 'narration_submit', request, NarrationSubmitSuccess)
    before = service.store.world(world_id)
    for mutation in [dict(text='篡改叙事。'),
                     dict(outcome='failed', text=None, failureReason='迟到失败。')]:
        with pytest.raises(ServiceRefusal) as excinfo:
            service.execute('narration_submit', dict(
                request, requestId='req_ready_mutation', **mutation))
        assert excinfo.value.code == 'request_malformed'
        assert service.store.world(world_id) == before


@pytest.mark.parametrize('operation', ['create_world', 'checkpoint_record_skip'])
def test_invalid_success_payload_cannot_commit(service, monkeypatch, operation):
    from pydantic import ValidationError

    if operation == 'create_world':
        request = {'protocolVersion': 2, 'requestId': 'req_create_shape',
                   'initial': initial_template()}
        original = control_module.handle_create_world

        def malformed_create(*args):
            record, data = original(*args)
            data['lease']['expiresAtEpochMilli'] = None
            return record, data

        with monkeypatch.context() as patch:
            patch.setattr(control_module, 'handle_create_world', malformed_create)
            with pytest.raises(ValidationError):
                service.execute(operation, request)
        assert service.store.world('world_1') is None
        assert service.store.global_idempotency() == {}
        _run(service, operation, request, CreateWorldSuccess)
    else:
        state = begin_work(service)
        before = service.store.world(state['world_id'])
        request = _payload(
            'req_skip_shape', state['world_id'], state['lease'],
            operation='record_skip', expectedPointId=state['root_id'],
            expectedVersion=0, expectedCheckpointRevision=state['revision'],
            pointId=state['point_id'], slotActorId='person_a')
        original = control_module.WRITE_HANDLERS[operation]

        def malformed_skip(*args):
            data = original(*args)
            data['pointId'] = None
            return data

        with monkeypatch.context() as patch:
            patch.setitem(control_module.WRITE_HANDLERS, operation, malformed_skip)
            with pytest.raises(ValidationError):
                service.execute(operation, request)
        assert service.store.world(state['world_id']) == before
        _run(service, operation, request, RecordSkipSuccess)


def test_extend_confirms_targets_once_and_close_needs_confirmation(service):
    state = begin_work(service)
    world_id, point_id, root_id, group_id, lease = (
        state['world_id'], state['point_id'], state['root_id'],
        state['group_id'], state['lease'])
    revision = state['revision']
    _run(service, 'checkpoint_discover_group', _payload(
        'req_discover', world_id, lease, operation='discover_group',
        expectedPointId=root_id, expectedVersion=0,
        expectedCheckpointRevision=revision, pointId=point_id,
        groupId=group_id, initiatorId='person_a', actionText='走向讲台。',
        targetIds=None), DiscoverGroupSuccess)
    # unconfirmed targets cannot close (round-3 close_unconfirmed probe)
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_close_group', _payload(
            'req_close_early', world_id, lease, operation='close_group',
            expectedPointId=root_id, expectedVersion=0,
            expectedCheckpointRevision=revision + 1, pointId=point_id,
            groupId=group_id))
    assert excinfo.value.code == 'request_malformed'
    # a nonempty TargetSpec list confirms identities and keeps the wire view
    # string-shaped (round-3 nonempty_targets probe crashed the envelope)
    extend = _run(service, 'checkpoint_extend_group', _payload(
        'req_extend_targets', world_id, lease, operation='extend_group',
        expectedPointId=root_id, expectedVersion=0,
        expectedCheckpointRevision=revision + 1, pointId=point_id,
        groupId=group_id, sourceId='person_a',
        targets=[{'targetId': 'person_b', 'triggerKey': 'trigger_1'}],
        admittedMember=None), ExtendGroupSuccess)
    assert extend['data']['memberIds'] == ['person_a']
    context = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    assert context['work']['pendingGroup']['targetIds'] == ['person_b']
    # confirmed sets — including the confirmed empty one — cannot be rewritten
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_extend_group', _payload(
            'req_extend_rewrite', world_id, lease, operation='extend_group',
            expectedPointId=root_id, expectedVersion=0,
            expectedCheckpointRevision=revision + 2, pointId=point_id,
            groupId=group_id, sourceId='person_a',
            targets=[{'targetId': 'person_c', 'triggerKey': 'trigger_2'}],
            admittedMember=None))
    assert excinfo.value.code == 'request_malformed'


@pytest.mark.parametrize('b_targets', [[], [
    {'targetId': 'person_c', 'triggerKey': 'trigger_bc'},
    {'targetId': 'person_b', 'triggerKey': 'trigger_bb'},
]])
def test_targets_freeze_per_member_and_close_waits_for_every_member(service, b_targets):
    state = begin_work(service)
    world_id, root_id, point_id, group_id, lease = (
        state['world_id'], state['root_id'], state['point_id'],
        state['group_id'], state['lease'])
    revision = state['revision']

    def request(request_id, operation, **fields):
        return _payload(
            request_id, world_id, lease, operation=operation,
            expectedPointId=root_id, expectedVersion=0,
            expectedCheckpointRevision=revision, pointId=point_id,
            groupId=group_id, **fields)

    def checkpoint(request_id, operation, model, **fields):
        nonlocal revision
        result = _run(service, f'checkpoint_{operation}',
                      request(request_id, operation, **fields), model)
        revision += 1
        return result

    checkpoint('req_discover', 'discover_group', DiscoverGroupSuccess,
               initiatorId='person_a', actionText='向 B 招手。', targetIds=None)
    checkpoint('req_targets_a', 'extend_group', ExtendGroupSuccess,
               sourceId='person_a', targets=[
                   {'targetId': 'person_b', 'triggerKey': 'trigger_ab'}],
               admittedMember=None)
    checkpoint('req_admit_b', 'extend_group', ExtendGroupSuccess,
               sourceId='person_a', targets=None,
               admittedMember={'memberId': 'person_b', 'actionText': '回应 A。',
                               'rollRefs': [{'sourceId': 'person_a', 'targetId': 'person_b',
                                             'triggerKey': 'trigger_ab', 'rollId': 'roll_ab'}]})
    before = service.store.world(world_id)
    # A's confirmed set cannot stand in for B's unanswered target question.
    early_close = request('req_close', 'close_group')
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_close_group', early_close)
    assert excinfo.value.code == 'request_malformed'
    assert service.store.world(world_id) == before
    # Nonmembers cannot submit target evidence; A cannot replace its set.
    for source in ['person_c', 'person_a']:
        with pytest.raises(ServiceRefusal) as excinfo:
            service.execute('checkpoint_extend_group', request(
                f'req_bad_source_{source}', 'extend_group', sourceId=source,
                targets=[], admittedMember=None))
        assert excinfo.value.code == 'request_malformed'
        assert service.store.world(world_id) == before
    b = checkpoint('req_targets_b', 'extend_group', ExtendGroupSuccess,
                   sourceId='person_b', targets=b_targets, admittedMember=None)
    assert b['work']['pendingGroup']['targetIds'] == sorted(
        {'person_b'} | {target['targetId'] for target in b_targets})
    before = service.store.world(world_id)
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_extend_group', request(
            'req_targets_b_rewrite', 'extend_group', sourceId='person_b',
            targets=[{'targetId': 'person_d', 'triggerKey': 'trigger_bd'}],
            admittedMember=None))
    assert excinfo.value.code == 'request_malformed'
    assert service.store.world(world_id) == before
    closed = checkpoint('req_close', 'close_group', CloseGroupSuccess)
    assert closed['work']['pendingGroup']['memberIds'] == ['person_a', 'person_b']
    group = single_group(['person_a', 'person_b'], ORDER, group_id)
    staged = checkpoint('req_stage', 'stage_unit', StageUnitSuccess,
                        candidates=group, results={'person_a': '已招手。', 'person_b': '已回应。'})
    assert staged['data']['working']['actedIds'] == ['person_a', 'person_b']
    assert staged['world']['round']['actedIds'] == []


def test_stage_freezes_the_admitted_closed_group(service):
    state = _closed_group(service, begin_work(service))
    world_id, point_id, root_id, group_id, lease = (
        state['world_id'], state['point_id'], state['root_id'],
        state['group_id'], state['lease'])
    # closed members are exactly [person_a]; staging B under the same groupId
    # must refuse even with full coverage (round-3 stage_member_swap probe)
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_stage_unit', _payload(
            'req_stage_swap', world_id, lease, operation='stage_unit',
            expectedPointId=root_id, expectedVersion=0,
            expectedCheckpointRevision=state['revision'], pointId=point_id,
            groupId=group_id,
            candidates=single_group(['person_b'], frozenset(ORDER), group_id),
            results={'person_b': '未经准入的结果。'}))
    assert excinfo.value.code == 'request_malformed'
    staged = service.execute('checkpoint_stage_unit', _payload(
        'req_stage', world_id, lease, operation='stage_unit',
        expectedPointId=root_id, expectedVersion=0,
        expectedCheckpointRevision=state['revision'], pointId=point_id,
        groupId=group_id,
        candidates=single_group(['person_a'], frozenset(ORDER), group_id),
        results={'person_a': '走上了讲台。'}))
    assert staged['data']['working']['actedIds'] == ['person_a']


def test_skip_locks_time_and_records_only_the_current_slot(service):
    state = begin_work(service)
    world_id, point_id, root_id, lease = (
        state['world_id'], state['point_id'], state['root_id'], state['lease'])
    revision = state['revision']
    # cursor 0 sits on person_a: skipping person_f is refused outright
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_record_skip', _payload(
            'req_skip_wrong', world_id, lease, operation='record_skip',
            expectedPointId=root_id, expectedVersion=0,
            expectedCheckpointRevision=revision, pointId=point_id,
            slotActorId='person_f'))
    assert excinfo.value.code == 'request_malformed'
    skipped = _run(service, 'checkpoint_record_skip', _payload(
        'req_skip', world_id, lease, operation='record_skip',
        expectedPointId=root_id, expectedVersion=0,
        expectedCheckpointRevision=revision, pointId=point_id,
        slotActorId='person_a'), RecordSkipSuccess)
    assert skipped['work']['timeLocked'] is True
    # the confirmed skip locked the point time in the same transaction
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('checkpoint_set_point_time', _payload(
            'req_retime', world_id, lease, operation='set_point_time',
            expectedPointId=root_id, expectedVersion=0,
            expectedCheckpointRevision=revision + 1, pointId=point_id,
            timeAdvance={'boundary': 'elapsed',
                         'duration': {'amount': 99, 'unit': 'second'}}))
    assert excinfo.value.code == 'point_time_locked'


def test_cancel_runs_from_open_work_but_needs_a_ready_head(service):
    state = begin_work(service)
    world_id, root_id, lease = state['world_id'], state['root_id'], state['lease']
    # ready head plus open uncommitted work at select_actor: cancellable
    cancelled = service.execute('round_conclusion_cancel', _payload(
        'req_cancel_work', world_id, lease, operation='cancel',
        advanceId='advance_1', roundId='round_1', expectedPointId=root_id,
        expectedVersion=0, expectedCheckpointRevision=state['revision'],
        cancelReason='停止。'))
    assert cancelled['data'] == {'roundId': 'round_1', 'abandonedGroupIds': []}
    assert cancelled['control']['phase'] == 'complete'
    assert cancelled['work'] is None
    assert cancelled['world']['advance']['intentStatus'] == 'expired'
    # a pending head blocks the cancel instead of clearing the input chain
    pending_service = WorldService(FixtureBaselineStore())
    state = run_t01_flow(pending_service)
    context = _run(pending_service, 'get_context', {'protocolVersion': 2,
                                            'worldId': state['world_id']},
                   ContextResponse)
    with pytest.raises(ServiceRefusal) as excinfo:
        pending_service.execute('round_conclusion_cancel', _payload(
            'req_cancel_pending', state['world_id'], state['lease'],
            operation='cancel', advanceId='advance_1', roundId='round_1',
            expectedPointId=state['point_id'], expectedVersion=1,
            expectedCheckpointRevision=context['control']['revision'],
            cancelReason='跳过待写叙事。'))
    assert excinfo.value.code == 'narration_blocked'


def test_commit_and_preview_metadata_bind_the_active_chain(service):
    state = run_t01_flow(service, commit=False)
    world_id = state['world_id']
    forged = copy.deepcopy(state['commit_request'])
    forged['requestId'] = 'req_commit_forged'
    forged.update(advanceId='advance_unrelated', roundId='round_unrelated')
    forged['point'].update(advanceId='advance_unrelated',
                           roundId='round_unrelated', sequence=999,
                           trigger='automatic')
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('commit_point', forged)
    assert excinfo.value.code == 'version_mismatch'
    for tag, mutation, code in [
            ('req_commit_seq', lambda req: req['point'].update(sequence=999),
             'version_mismatch'),
            ('req_commit_trigger',
             lambda req: req['point'].update(trigger='automatic'), 'version_mismatch'),
            ('req_commit_round', lambda req: req['point'].update(roundId='round_x'),
             'request_malformed'),
            ('req_commit_advance',
             lambda req: req.update(advanceId='advance_x'), 'request_malformed')]:
        request = copy.deepcopy(state['commit_request'])
        request['requestId'] = tag
        mutation(request)
        with pytest.raises(ServiceRefusal) as excinfo:
            service.execute('commit_point', request)
        # Internally inconsistent request bindings fail schema validation;
        # consistent metadata forged against stored authority fails in service.
        assert excinfo.value.code == code, tag
    # preview binds the same chain (advance/round/time)
    preview = {'protocolVersion': 2, 'worldId': world_id,
               'advanceId': 'advance_unrelated', 'roundId': 'round_1',
               'pointId': state['point_id'],
               'expectedPointId': state['root_id'], 'expectedVersion': 0,
               'expectedCheckpointRevision': state['revision'],
               'timeAdvance': TIME_ADVANCE, 'settlementGroups': []}
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('preview_point', preview)
    assert excinfo.value.code == 'version_mismatch'
    preview.update(advanceId='advance_1',
                   timeAdvance={'boundary': 'elapsed',
                                'duration': {'amount': 5, 'unit': 'second'}})
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('preview_point', preview)
    assert excinfo.value.code == 'version_mismatch'
    # the untouched request still commits
    commit = service.execute('commit_point', state['commit_request'])
    CommitPointSuccess.model_validate(commit)


@pytest.mark.parametrize('kind,amount', [('linked', 3), ('instant', 0)])
def test_associated_point_previews_carry_their_predecessor(service, kind, amount):
    state = _closed_group(service, begin_work(service))
    world_id, point_id, root_id, group_id, lease = (
        state['world_id'], state['point_id'], state['root_id'],
        state['group_id'], state['lease'])
    roster = frozenset(ORDER)
    group = single_group(['person_a'], roster, group_id)
    _run(service, 'checkpoint_stage_unit', _payload(
        'req_stage', world_id, lease, operation='stage_unit',
        expectedPointId=root_id, expectedVersion=0,
        expectedCheckpointRevision=state['revision'], pointId=point_id,
        groupId=group_id, candidates=group,
        results={'person_a': '走上了讲台。'}), StageUnitSuccess)
    _run(service, 'checkpoint_seal_point', _payload(
        'req_seal', world_id, lease, operation='seal_point',
        expectedPointId=root_id, expectedVersion=0,
        expectedCheckpointRevision=state['revision'] + 1, pointId=point_id),
        SealPointSuccess)
    current = _run(service, 'get_context', {'protocolVersion': 2,
                                            'worldId': world_id}, ContextResponse)
    service.execute('commit_point', _payload(
        'req_partial_commit', world_id, lease,
        advanceId='advance_1', roundId='round_1',
        expectedPointId=root_id, expectedVersion=0,
        expectedCheckpointRevision=current['control']['revision'],
        pointId=point_id, settlementGroups=[group],
        point={'worldId': world_id, 'id': point_id, 'sequence': 1,
               'kind': 'normal', 'previousPointId': root_id,
               'roundId': 'round_1', 'advanceId': 'advance_1',
               'trigger': 'player', 'linkedFromPointId': None,
               'timeAdvance': TIME_ADVANCE, 'entityDeltas': {}}))
    _claim_and_submit(service, world_id, lease, point_id, 'req_ready', '就绪。')
    successor = f'point_{kind}'
    begin_revision = _run(service, 'get_context',
                          {'protocolVersion': 2, 'worldId': world_id},
                          ContextResponse)['control']['revision']
    time = {'boundary': 'instant',
            'duration': {'amount': amount, 'unit': 'second'}}
    _run(service, 'checkpoint_begin_point', _payload(
        f'req_begin_{kind}', world_id, lease, operation='begin_point',
        expectedPointId=point_id, expectedVersion=1,
        expectedCheckpointRevision=begin_revision,
        pointId=successor, kind=kind, timeAdvance=time), BeginPointSuccess)
    preview = _run(service, 'preview_point', {
        'protocolVersion': 2, 'worldId': world_id,
        'advanceId': 'advance_1', 'roundId': 'round_1',
        'pointId': successor, 'expectedPointId': point_id,
        'expectedVersion': 1,
        'expectedCheckpointRevision': begin_revision + 1,
        'timeAdvance': time, 'settlementGroups': []}, PreviewPointSuccess)
    projection = preview['data']['pointProjection']
    assert projection['kind'] == kind
    assert projection['linkedFromPointId'] == point_id
    assert projection['previousPointId'] == point_id


def test_kernel_refusals_map_to_the_wire_table(service):
    from app.schemas.world.v2.errors import ERROR_CODES
    state = run_t01_flow(service, commit=False)
    forged = copy.deepcopy(state['commit_request'])
    forged['requestId'] = 'req_commit_retime'
    forged['point']['timeAdvance']['duration']['amount'] = 99
    with pytest.raises(ServiceRefusal) as excinfo:
        service.execute('commit_point', forged)
    # no raw KernelViolation escapes; the T08 s9 wire code with its reason
    assert excinfo.value.code == 'version_mismatch'
    assert excinfo.value.details == {'reason': 'prefix_binding_mismatch'}
    # refusal metadata derives from ERROR_CODES (coverage refusal is a 400);
    # a fresh service avoids the global create-idempotency table
    probed_service = WorldService(FixtureBaselineStore())
    probed = _closed_group(probed_service, begin_work(probed_service))
    with pytest.raises(ServiceRefusal) as excinfo:
        probed_service.execute('checkpoint_stage_unit', _payload(
            'req_stage_bad', probed['world_id'], probed['lease'],
            operation='stage_unit', expectedPointId=probed['root_id'],
            expectedVersion=0,
            expectedCheckpointRevision=probed['revision'],
            pointId=probed['point_id'], groupId=probed['group_id'],
            candidates=single_group(['person_a'], ['person_a'],
                                    probed['group_id']),
            results={'person_a': '结果。'}))
    assert excinfo.value.code == 'request_malformed'
    table = ERROR_CODES['request_malformed']
    assert excinfo.value.http_status == table['httpStatus'] == 400
    assert excinfo.value.client_action == table['clientAction']


def test_response_snapshots_reflect_their_own_transaction(service):
    class InterleavedStore(FixtureBaselineStore):
        hook = None

        def transact(self, world_id, handler):
            result = super().transact(world_id, handler)
            if self.hook is not None:
                hook, self.hook = self.hook, None
                hook()
            return result

    store = InterleavedStore()
    service = WorldService(store)
    state = begin_work(service)
    world_id, point_id, root_id, group_id, lease = (
        state['world_id'], state['point_id'], state['root_id'],
        state['group_id'], state['lease'])

    def interleaved_discover():
        service.execute('checkpoint_discover_group', _payload(
            'req_discover_late', world_id, lease, operation='discover_group',
            expectedPointId=root_id, expectedVersion=0,
            expectedCheckpointRevision=state['revision'] + 1,
            pointId=point_id, groupId=group_id, initiatorId='person_b',
            actionText='另起一组。', targetIds=None))

    store.hook = interleaved_discover
    response = service.execute('checkpoint_record_skip', _payload(
        'req_skip_first', world_id, lease, operation='record_skip',
        expectedPointId=root_id, expectedVersion=0,
        expectedCheckpointRevision=state['revision'], pointId=point_id,
        slotActorId='person_a'))
    # the skip response carries the skip's own snapshots, not the discover
    # that interleaved after the commit
    assert response['control']['revision'] == state['revision'] + 1
    assert response['work']['pendingGroup'] is None


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
