"""The A2 control service: one transaction per operation over the fixture
baseline store.

Refusal surface: `ServiceRefusal` carries the wire code decided by the
a1-kernel-plan §四 mapping; schema-level payload failures map to
`request_malformed`. Storage keeps authoritative state only —
blockedReasons/canCompute are derived per response. Roll rows, TTL expiry,
restore/takeover copying and crash recovery stay with A3.
"""
import threading

from pydantic import RootModel, ValidationError

from app.schemas.world.canonical import canonical_bytes, canonical_digest
from app.schemas.world.contracts import (
    EntityDelta, RootPoint, TimelinePoint, WorldInitialState, WorldState,
)
from app.schemas.world.v2.contexts import (
    ControlState, GateView, WorkingProgress,
)
from app.schemas.world.v2.projections import prefix_projection, request_projection
from app.schemas.world.v2.registry import OPERATION_BY_NAME
from app.schemas.world.v2 import SCHEMA_MODELS as _SCHEMA_MODELS
_ALL_REQUEST_MODELS = [m for m in _SCHEMA_MODELS if m.__name__.endswith('Request')]
from app.schemas.world.v2.requests import (
    BeginPointRequest, CloseGroupRequest, CommitPointRequest, CreateWorldRequest,
    DiscoverGroupRequest, ExtendGroupRequest, PauseRequest, PreviewPointRequest,
    RecordSkipRequest, ResumeRequest, SealPointRequest, SetPointTimeRequest,
    StageTimeScanRequest, StageUnitRequest, StartAdvanceRequest,
)
from app.schemas.world.v2.work import SettlementGroup

from .apply import apply_point
from .commit import verify_point_binding
from .ladder import check_checkpoint
from .merge import point_entity_deltas
from .state import build_initial_state, state_digest
from .units import (
    begin_working, scan_working, skip_working, stage_working, unit_content_hash,
    validate_commit_groups,
)
from .violations import KernelViolation

ENGINE = 'world-engine-v1'
CANONICAL = 'world-canonical-v1'
SCHEMA = 1
PROTOCOL = 2
DEFAULT_TTL_MILLI = 3_600_000


class ServiceRefusal(Exception):
    def __init__(self, code, detail, http_status=409, client_action='fix_request',
                 details=None, control_required=False):
        super().__init__(f'{code}: {detail}')
        self.code = code
        self.detail = detail
        self.http_status = http_status
        self.client_action = client_action
        self.details = details
        self.control_required = control_required


def _now(store):
    return store.clock_milli()


def _world_roster(record):
    return frozenset(record['state'].initial.characters)


def _gate(record):
    return record['control']['gate']


def _head_narration(record):
    return record['control']['headNarration']


def _blocked(record):
    blocked = []
    if record['control']['paused']:
        blocked.append('paused')
    if _gate(record)['status'] == 'pending':
        blocked.append('narration_pending')
    head = _head_narration(record)['status']
    if head == 'failed':
        blocked.append('narration_failed')
    elif head == 'missing':
        blocked.append('cache_missing')
    return sorted(blocked)


def control_view(record):
    blocked = _blocked(record)
    gate = _gate(record)
    return ControlState(
        phase=record['control']['phase'], paused=record['control']['paused'],
        revision=record['control']['revision'],
        gate=GateView.model_validate(gate), blockedReasons=blocked,
        canCompute=not blocked)


def _refuse(code, detail, **kwargs):
    raise ServiceRefusal(code, detail, **kwargs)


def _ladder(record, operation, work=None):
    control = control_view(record)
    refusals = check_checkpoint(operation, work, control)
    for violation in refusals:
        mapping = {
            'phase': 'phase_invalid', 'pointWork': 'phase_invalid',
            'activePendingGroup': 'phase_invalid', 'settledUnits': 'phase_invalid',
            'timeLocked': 'point_time_locked', 'confirmedWork': 'point_time_locked',
            'paused': 'paused', 'gate': 'narration_blocked',
            'roster': 'version_mismatch', 'coverage': 'request_malformed',
            'identity': 'request_malformed', 'semantic_invalid': 'request_malformed',
        }
        code = mapping.get(violation.kind, 'phase_invalid')
        kwargs = {}
        if code in ('paused', 'phase_invalid', 'narration_blocked'):
            kwargs['control_required'] = True
        _refuse(code, f'{operation}: {violation.detail}', **kwargs)


def _lease(record):
    return record.get('lease')


def _check_lease(record, request):
    lease = _lease(record)
    if lease is None or request.leaseToken != lease['leaseToken']:
        _refuse('lease_invalid', 'unknown lease token', client_action='reacquire_lease')
    if request.fenceEpoch != lease['fenceEpoch']:
        _refuse('stale_epoch', 'lease epoch has moved on',
                client_action='reacquire_lease')


def _work_or_none(record):
    return record.get('work')


def _sealed_prefix(record):
    work = _work_or_none(record)
    if work is None or not work['sealed']:
        _refuse('phase_invalid', 'commit requires a sealed point work',
                control_required=True)
    return work


def _issue_gate(record, generation):
    now = record['_now']
    record['control']['gate'] = {
        'status': 'pending', 'generation': generation,
        'issuedAtEpochMilli': now, 'expiresAtEpochMilli': now + DEFAULT_TTL_MILLI,
    }
    record['control']['headNarration'] = {
        'status': 'pending', 'text': None, 'generation': generation,
        'claim': None,
    }


def _envelope(store, operation, request, record, data, digest=None):
    control = control_view(record) if record else None
    envelope = {
        'protocolVersion': PROTOCOL, 'engineVersion': ENGINE,
        'schemaVersion': SCHEMA, 'canonicalVersion': CANONICAL,
        'serverTimeEpochMilli': _now(store),
        'operation': operation,
        'requestId': getattr(request, 'requestId', None),
        'replayed': False, 'data': data,
    }
    if digest is not None:
        envelope['requestHash'] = digest
    if control is not None:
        envelope['control'] = control.model_dump(mode='json')
    return envelope


def _reject_replay(entry, fresh_data):
    """Replays return the stored sanitised payload, never a fresh token."""
    replayed = dict(entry['data'])
    replayed['replayed'] = True
    return replayed


# --- per-operation handlers (record is the mutable transaction copy) --------


def handle_create_world(store, record, request):
    world_id = store.next_id('world')
    initial = WorldInitialState.model_validate(
        {'worldId': world_id, **request.initial.model_dump(mode='json', exclude={'worldId'})})
    state = build_initial_state(initial)
    now = _now(store)
    lease = {'holderId': store.next_id('holder'), 'leaseToken': store.next_id('lease'),
             'fenceEpoch': 1, 'expiresAtEpochMilli': now + DEFAULT_TTL_MILLI}
    record = {
        'worldId': world_id, 'state': state, 'version': 0,
        'rootPointId': store.next_id('root'),
        'headPointId': None,
        'points': {}, 'advance': None, 'round': None, 'work': None,
        'control': {'phase': 'select_actor', 'paused': False, 'revision': 0,
                    'gate': {'status': 'pending', 'generation': 1,
                             'issuedAtEpochMilli': now,
                             'expiresAtEpochMilli': now + DEFAULT_TTL_MILLI},
                    'headNarration': {'status': 'pending', 'text': None,
                                      'generation': 1, 'claim': None}},
        'lease': lease, 'idempotency': {}, 'allocations': {},
        'narrations': {}, '_now': now,
    }
    record['headPointId'] = record['rootPointId']
    store.create_world(world_id, record)
    return {'worldId': world_id, 'rootPointId': record['rootPointId'], 'lease': lease}


def handle_allocate_ids(record, request):
    known = request.model_dump(mode='json')['slots']
    allocated = []
    bucket = record['allocations'].setdefault(request.allocationKey, {})
    for slot in known:
        if slot['slotKey'] in bucket:
            allocated.append({'slotKey': slot['slotKey'], 'id': bucket[slot['slotKey']]})
        else:
            new_id = f"{slot['kind']}_{len(bucket) + 1}_{request.allocationKey[-4:]}"
            bucket[slot['slotKey']] = new_id
            allocated.append({'slotKey': slot['slotKey'], 'id': new_id})
    return {'allocations': allocated}


def handle_narration_claim(record, request):
    point_id = request.pointId
    narration = record['narrations'].get(point_id) or _head_narration(record)
    is_head = request.mode == 'head'
    if request.currentClaim is not None:
        claim = narration.get('claim')
        if (claim is None or request.currentClaim.claimToken != claim['claimToken']
                or request.currentClaim.generation != claim['generation']):
            _refuse('claim_fenced', 'caller holds a superseded claim',
                    client_action='refresh_context')
    gate = _gate(record)
    status = narration['status']
    if status != 'pending':
        return {'pointId': point_id, 'mode': request.mode, 'generation': narration['generation'],
                'fenceEpoch': record['lease']['fenceEpoch'] if is_head else None,
                'issuedAtEpochMilli': gate['issuedAtEpochMilli'],
                'expiresAtEpochMilli': gate['expiresAtEpochMilli']}
    token = f'claim_{record["control"]["headNarration"]["generation"]}_{point_id}'
    narration['claim'] = {'claimToken': token, 'generation': narration['generation']}
    data = {'pointId': point_id, 'mode': request.mode, 'claimToken': token,
            'generation': narration['generation'], 'fenceEpoch': None,
            'issuedAtEpochMilli': gate['issuedAtEpochMilli'],
            'expiresAtEpochMilli': gate['expiresAtEpochMilli']}
    if is_head:
        _check_lease(record, request)
        data['fenceEpoch'] = record['lease']['fenceEpoch']
    return data


def handle_narration_renew(record, request):
    narration = record['narrations'].get(request.pointId) or _head_narration(record)
    claim = narration.get('claim')
    if (claim is None or request.claimToken != claim['claimToken']
            or request.generation != claim['generation']):
        _refuse('claim_expired', 'unknown or superseded claim',
                client_action='regenerate_narration')
    gate = _gate(record)
    return {'pointId': request.pointId, 'mode': request.mode,
            'generation': request.generation,
            'fenceEpoch': record['lease']['fenceEpoch'] if request.mode == 'head' else None,
            'issuedAtEpochMilli': gate['issuedAtEpochMilli'],
            'expiresAtEpochMilli': gate['expiresAtEpochMilli']}


def handle_narration_submit(record, request):
    narration = record['narrations'].get(request.pointId) or _head_narration(record)
    claim = narration.get('claim')
    if (claim is None or request.claimToken != claim['claimToken']
            or request.generation != claim['generation']):
        _refuse('claim_fenced', 'submitting with a superseded claim',
                client_action='refresh_context')
    narration['text'] = request.text
    narration['status'] = request.outcome
    if request.outcome == 'ready':
        record['control']['gate'] = {
            'status': 'none', 'generation': None,
            'issuedAtEpochMilli': None, 'expiresAtEpochMilli': None,
        }
    return {'pointId': request.pointId, 'narrationStatus': request.outcome,
            'generation': request.generation}


def handle_narration_get(record, request):
    narration = record['narrations'].get(request.pointId) or _head_narration(record)
    status = narration['status']
    return {'pointId': request.pointId, 'narrationStatus': status,
            'generation': narration['generation'],
            'text': narration['text'] if status == 'ready' else None}


def handle_narration_delete(record, request):
    narration = record['narrations'].get(request.pointId) or _head_narration(record)
    claim = narration.get('claim')
    if claim is None or request.claimToken != claim['claimToken']:
        _refuse('claim_fenced', 'delete with a superseded claim',
                client_action='refresh_context')
    generation = narration['generation']
    record['narrations'][request.pointId] = {
        'status': 'missing', 'text': None, 'generation': generation + 1, 'claim': None}
    if request.pointId == record.get('headPointId'):
        _issue_gate(record, generation + 1)
    return {'pointId': request.pointId, 'narrationStatus': 'missing',
            'invalidatedGeneration': generation}


def handle_lease_acquire(record, request):
    lease = _lease(record)
    if lease is not None:
        _refuse('lease_invalid', 'lease_held', details={'reason': 'lease_held'},
                client_action='none')
    fence = 1
    record['lease'] = {'holderId': request.holderId, 'leaseToken': f'lease_{fence}_{request.holderId}',
                       'fenceEpoch': fence, 'expiresAtEpochMilli': _now(record) + DEFAULT_TTL_MILLI}
    return dict(record['lease'], holderId=request.holderId)


def handle_lease_renew(record, request):
    lease = _lease(record)
    if lease is None or request.leaseToken != lease['leaseToken'] \
            or request.fenceEpoch != lease['fenceEpoch']:
        _refuse('lease_invalid', 'unknown lease token or epoch',
                client_action='reacquire_lease')
    lease['expiresAtEpochMilli'] = _now(record) + DEFAULT_TTL_MILLI
    return dict(lease)


def handle_lease_release(record, request):
    lease = _lease(record)
    if lease is None or request.leaseToken != lease['leaseToken'] \
            or request.fenceEpoch != lease['fenceEpoch']:
        _refuse('lease_invalid', 'unknown lease token or epoch',
                client_action='reacquire_lease')
    record['lease'] = None
    return {'released': True}


def handle_start_advance(record, request):
    _check_lease(record, request)
    if record.get('advance') is not None:
        _refuse('phase_invalid', 'an active advance already exists',
                control_required=True)
    if record['work'] is not None:
        _refuse('phase_invalid', 'a point work is still active', control_required=True)
    head = _head_narration(record)
    if head['status'] != 'ready':
        _refuse('narration_blocked', 'the head narration is not ready',
                control_required=True)
    record['advance'] = {'advanceId': request.advanceId, 'inputId': request.inputId,
                         'inputText': request.inputText, 'intentStatus': 'pending'}
    record['round'] = {'roundId': request.roundId, 'trigger': 'player',
                       'order': request.order, 'cursor': 0, 'actedIds': [],
                       'visitedIds': [], 'conclusion': None}
    record['control']['phase'] = 'select_actor'
    record['control']['revision'] += 1
    return {'advanceId': request.advanceId, 'inputId': request.inputId,
            'roundId': request.roundId}


def handle_begin_point(record, request):
    _check_lease(record, request)
    if record['control']['phase'] not in ('select_actor', 'continue_round'):
        _refuse('phase_invalid', 'begin needs select_actor or continue_round',
                control_required=True)
    if record['work'] is not None:
        _refuse('phase_invalid', 'a point work is still active', control_required=True)
    state = record['state']
    if request.expectedPointId != record.get('headPointId') \
            or request.expectedVersion != record['version'] \
            or request.expectedCheckpointRevision != record['control']['revision']:
        _refuse('version_mismatch', 'point or revision binding differs',
                client_action='refresh_context')
    committed = (record['round']['cursor'], record['round']['actedIds'],
                 record['round']['visitedIds'])
    working = begin_working(committed, record['advance']['intentStatus'])
    record['work'] = {
        'pointId': request.pointId, 'kind': request.kind,
        'timeAdvance': request.timeAdvance.model_dump(mode='json'),
        'timeLocked': False, 'sealed': False, 'prefixDigest': None,
        'timeScanComplete': False, 'timeScan': None,
        'baseline': {'headPointId': record['headPointId'],
                     'version': record['version'],
                     'stateDigest': state_digest(state)},
        'phase': 'select_actor', 'working': working, 'units': [],
        'pendingGroup': None, 'successor': None,
    }
    record['headPointId'] = request.pointId
    record['control']['revision'] += 1
    return {'pointId': request.pointId}


def _work_view(record):
    work = record['work']
    if work is None:
        return None
    return {
        'pointId': work['pointId'], 'kind': work['kind'],
        'timeAdvance': work['timeAdvance'], 'timeLocked': work['timeLocked'],
        'sealed': work['sealed'],
        'prefixDigest': work['prefixDigest'],
        'predecessorWorkDigest': None,
        'timeScanComplete': work['timeScanComplete'],
        'baseline': work['baseline'], 'phase': work['phase'],
        'working': (work['working'].model_dump(mode='json')
                    if isinstance(work['working'], WorkingProgress) else work['working']),
        'settledUnits': [
            {'unitId': unit['unitId'], 'groupId': unit['groupId'],
             'memberIds': unit['memberIds'], 'contentHash': unit['contentHash']}
            for unit in work['units']],
        'pendingGroup': work['pendingGroup'], 'successor': work['successor'],
    }


def handle_discover_group(record, request):
    _check_lease(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_discover_group',
            PointWorkProxy(work) if work else None)
    work['pendingGroup'] = {
        'groupId': request.groupId, 'sourceId': request.initiatorId,
        'memberIds': [request.initiatorId], 'targetIds': request.targetIds or [],
        'frontierIds': [], 'closed': False,
        'actionTexts': {request.initiatorId: request.actionText},
    }
    work['timeLocked'] = True
    work['phase'] = 'build_group'
    record['control']['phase'] = 'build_group'
    record['control']['revision'] += 1
    return {'groupId': request.groupId, 'targetIds': request.targetIds}


def handle_extend_group(record, request):
    _check_lease(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_extend_group', PointWorkProxy(work) if work else None)
    group = work['pendingGroup']
    if request.targets is not None:
        group['targetIds'] = list(request.targets)
    else:
        member = request.admittedMember
        if member.memberId not in group['memberIds']:
            group['memberIds'].append(member.memberId)
        group['actionTexts'][member.memberId] = member.actionText
    record['control']['revision'] += 1
    return {'groupId': request.groupId,
            'memberIds': sorted(set(group['memberIds'])),
            'frontierIds': group['frontierIds']}


def handle_close_group(record, request):
    _check_lease(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_close_group', PointWorkProxy(work) if work else None)
    group = work['pendingGroup']
    group['closed'] = True
    work['phase'] = 'settle_group'
    record['control']['phase'] = 'settle_group'
    record['control']['revision'] += 1
    return {'groupId': request.groupId, 'closed': True}


def handle_stage_unit(record, request):
    _check_lease(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_stage_unit', PointWorkProxy(work) if work else None)
    unit_id = f'unit_{request.groupId}'
    content_hash = unit_content_hash(request.candidates)
    work['units'].append({
        'unitId': unit_id, 'groupId': request.groupId,
        'memberIds': sorted(request.candidates.actorIds),
        'contentHash': content_hash, 'candidates': request.candidates,
        'results': request.results,
    })
    work['working'] = stage_working(work['working'], unit_id,
                                    request.candidates.actorIds,
                                    record['round']['order'])
    if record['advance'] is not None and record['advance']['intentStatus'] == 'pending':
        record['advance']['intentStatus'] = 'consumed'
    work['pendingGroup'] = None
    work['phase'] = 'select_actor'
    record['control']['phase'] = 'select_actor'
    record['control']['revision'] += 1
    return {'groupId': request.groupId, 'unitId': unit_id,
            'working': work['working'].model_dump(mode='json')}


def handle_record_skip(record, request):
    _check_lease(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_record_skip', PointWorkProxy(work) if work else None)
    work['working'] = skip_working(work['working'], request.slotActorId,
                                   record['round']['order'])
    if record['advance'] is not None and record['advance']['intentStatus'] == 'pending':
        record['advance']['intentStatus'] = 'consumed'
    record['control']['revision'] += 1
    return {'pointId': work['pointId'],
            'working': work['working'].model_dump(mode='json')}


def handle_stage_time_scan(record, request):
    _check_lease(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_stage_time_scan', PointWorkProxy(work) if work else None)
    work['timeScan'] = request.candidates
    work['timeScanComplete'] = True
    work['timeLocked'] = True
    work['working'] = scan_working(work['working'], record['round']['order'])
    record['control']['revision'] += 1
    return {'pointId': work['pointId'],
            'working': work['working'].model_dump(mode='json')}


def handle_seal_point(record, request):
    _check_lease(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_seal_point', PointWorkProxy(work) if work else None)
    if not work['units'] and not work['timeScanComplete']:
        _refuse('phase_invalid', 'an empty point needs its time-scan candidates first',
                control_required=True)
    work['sealed'] = True
    projection = prefix_projection(record['worldId'], _prefix_fields(record), work['timeScan'])
    work['prefixDigest'] = canonical_digest(projection)
    record['control']['revision'] += 1
    return {'pointId': work['pointId'], 'prefixDigest': work['prefixDigest']}


def _prefix_fields(record):
    work = record['work']
    return {
        'pointId': work['pointId'], 'kind': work['kind'],
        'baseline': work['baseline'], 'timeAdvance': work['timeAdvance'],
        'timeLocked': True, 'working': work['working'].model_dump(mode='json'),
        'settledUnits': [
            {'unitId': unit['unitId'], 'groupId': unit['groupId'],
             'memberIds': unit['memberIds'], 'contentHash': unit['contentHash']}
            for unit in work['units']],
        'timeScanComplete': work['timeScanComplete'],
    }


def handle_set_point_time(record, request):
    _check_lease(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_set_point_time', PointWorkProxy(work) if work else None)
    work['timeAdvance'] = request.timeAdvance.model_dump(mode='json')
    record['control']['revision'] += 1
    return {'pointId': work['pointId'],
            'timeAdvance': request.timeAdvance.model_dump(mode='json')}


def handle_prepare_successor(record, request):
    _check_lease(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_prepare_successor', PointWorkProxy(work) if work else None)
    work['sealed'] = True
    projection = prefix_projection(record['worldId'], _prefix_fields(record), work['timeScan'])
    work['prefixDigest'] = canonical_digest(projection)
    successor = {
        'pointId': request.successorPointId, 'predecessorPointId': work['pointId'],
        'timeAdvance': request.timeAdvance.model_dump(mode='json'),
        'expectedPredecessorVersion': record['version'],
        'prefixDigest': work['prefixDigest'],
        'expectedPredecessorStateDigest': state_digest(record['state']),
        'baseline': work['baseline'],
    }
    work['successor'] = successor
    record['control']['revision'] += 1
    return {'pointId': work['pointId'], 'successorPointId': request.successorPointId,
            'prefixDigest': work['prefixDigest'], 'successor': successor}


def handle_pause(record, request):
    _check_lease(record, request)
    if not record['control']['paused']:
        record['control']['paused'] = True
        record['control']['revision'] += 1
    return {'paused': True}


def handle_resume(record, request):
    _check_lease(record, request)
    if record['control']['paused']:
        record['control']['paused'] = False
        record['control']['revision'] += 1
    return {'paused': False}


def handle_preview_point(store, record, request):
    work = _work_or_none(record)
    _ladder(record, 'preview_point', PointWorkProxy(work) if work else None)
    projection = TimelinePoint.model_validate({
        'worldId': record['worldId'], 'id': request.pointId, 'sequence': 0,
        'kind': 'normal', 'previousPointId': record['headPointId'],
        'roundId': request.roundId, 'advanceId': request.advanceId,
        'trigger': 'player', 'linkedFromPointId': None,
        'timeAdvance': request.timeAdvance.model_dump(mode='json'),
        'entityDeltas': {}})
    merged = point_entity_deltas(request.settlementGroups, None)
    projection = projection.model_copy(update={
        'entityDeltas': {key: delta for key, delta in merged.items()}})
    working = apply_point(record['state'], projection)
    return {'pointId': request.pointId,
            'pointProjection': projection.model_dump(mode='json'),
            'mergedEntityDeltas': {key: delta.model_dump(mode='json')
                                   for key, delta in merged.items()},
            'workingState': working.model_dump(mode='json'),
            'workingStateDigest': state_digest(working),
            'pointProjectionDigest': canonical_digest(
                canonical_bytes(projection.model_dump(mode='json')))}


def handle_commit_point(record, request):
    work = _sealed_prefix(record)
    _check_lease(record, request)
    _ladder(record, 'commit_point', PointWorkProxy(work) if work else None)
    sealed_time_advance = work['timeAdvance']
    if hasattr(sealed_time_advance, 'model_dump'):
        sealed_time_advance = sealed_time_advance.model_dump(mode='json')
    verify_point_binding(
        request.point, work['kind'],
        type(request.point.timeAdvance).model_validate(sealed_time_advance))
    staged = [(unit['groupId'], unit['memberIds']) for unit in work['units']]
    given = [(group.groupId, sorted(group.actorIds)) for group in request.settlementGroups]
    if staged != given:
        _refuse('version_mismatch',
                'settlementGroups differ from the sealed settledUnits '
                '(identity, members or order)',
                details={'reason': 'prefix_binding_mismatch'})
    merged = point_entity_deltas(request.settlementGroups, work['timeScan'])
    expected_deltas = {key: delta.model_dump(mode='json') for key, delta in merged.items()}
    if expected_deltas != request.point.entityDeltas and \
            {key: delta.model_dump(mode='json')
             for key, delta in request.point.entityDeltas.items()} != expected_deltas:
        _refuse('request_malformed', 'point deltas differ from the merged settlement')
    new_state = apply_point(record['state'], request.point)
    record['state'] = new_state
    record['version'] += 1
    record['points'][request.pointId] = request.point
    digests = record.setdefault('pointDigests', {})
    digests[request.pointId] = state_digest(new_state)
    round_view = record['round']
    round_view['cursor'] = work['working'].cursor
    round_view['actedIds'] = work['working'].actedIds
    round_view['visitedIds'] = work['working'].visitedIds
    record['work'] = None
    record['headPointId'] = request.pointId
    _issue_gate(record, 1)
    record['narrations'][request.pointId] = {
        'status': 'pending', 'text': None, 'generation': 1, 'claim': None}
    if round_view['cursor'] == len(round_view['order']) and round_view['conclusion'] is None:
        record['control']['phase'] = 'assess_continuation'
    record['control']['revision'] += 1
    return {'pointId': request.pointId, 'version': record['version'],
            'stateDigest': state_digest(new_state)}


def handle_round_conclusion_cancel(record, request):
    _check_lease(record, request)
    if record['control']['phase'] != 'assess_continuation':
        _refuse('phase_invalid', 'cancel runs from assess_continuation',
                control_required=True)
    round_view = record['round']
    round_view['conclusion'] = {
        'kind': 'handback', 'closedBy': 'cancel', 'cancelReason': request.cancelReason}
    record['control']['phase'] = 'complete'
    record['advance'] = None
    record['control']['revision'] += 1
    return {'kind': 'handback', 'roundId': request.roundId, 'nextRoundId': None}


def handle_round_conclusion_conclude(record, request):
    _check_lease(record, request)
    if record['control']['phase'] != 'assess_continuation':
        _refuse('phase_invalid', 'conclude runs from assess_continuation',
                control_required=True)
    conclusion = request.conclusion
    if conclusion.kind == 'continue':
        record['round']['conclusion'] = {
            'kind': 'continue', 'closedBy': 'model', 'cancelReason': None,
            'candidateCharacterIds': conclusion.candidateCharacterIds,
            'nextRoundId': conclusion.nextRoundId}
        record['round'] = {
            'roundId': conclusion.nextRoundId, 'trigger': 'automatic',
            'order': conclusion.candidateCharacterIds, 'cursor': 0,
            'actedIds': [], 'visitedIds': [], 'conclusion': None}
        record['control']['phase'] = 'select_actor'
        data = {'kind': 'continue', 'roundId': request.roundId,
                'nextRoundId': conclusion.nextRoundId}
    else:
        record['round']['conclusion'] = {
            'kind': 'handback', 'closedBy': 'model', 'cancelReason': None}
        record['control']['phase'] = 'complete'
        record['advance'] = None
        data = {'kind': 'handback', 'roundId': request.roundId, 'nextRoundId': None}
    record['control']['revision'] += 1
    return data


def handle_get_state(record, request):
    point_id = request.point or record['headPointId']
    point = record['points'].get(point_id)
    state = record['state']
    return {'pointId': point_id, 'version': record['version'],
            'state': state.model_dump(mode='json'),
            'stateDigest': state_digest(state)}


def handle_list_points(record, request):
    points = [{'pointId': root_id, 'sequence': 0, 'kind': 'root',
               'roundId': None, 'advanceId': None,
               'stateDigest': state_digest(build_initial_state(record['state'].initial))}
              for root_id in [record['rootPointId']]]
    points += [
        {'pointId': point.id, 'sequence': point.sequence, 'kind': point.kind,
         'roundId': point.roundId, 'advanceId': point.advanceId,
         'stateDigest': record['pointDigests'].get(point.id, '')}
        for point in record['points'].values()]
    return {'points': points}


CHECKPOINT_HANDLERS = {
    'checkpoint_begin_point': handle_begin_point,
    'checkpoint_discover_group': handle_discover_group,
    'checkpoint_extend_group': handle_extend_group,
    'checkpoint_close_group': handle_close_group,
    'checkpoint_stage_unit': handle_stage_unit,
    'checkpoint_record_skip': handle_record_skip,
    'checkpoint_stage_time_scan': handle_stage_time_scan,
    'checkpoint_seal_point': handle_seal_point,
    'checkpoint_set_point_time': handle_set_point_time,
    'checkpoint_prepare_successor': handle_prepare_successor,
    'checkpoint_pause': handle_pause,
    'checkpoint_resume': handle_resume,
}




def handle_get_context(record, request):
    world = {
        'worldId': record['worldId'],
        'head': {'pointId': record['headPointId'], 'version': record['version'],
                 'stateDigest': state_digest(record['state']),
                 'narrationStatus': _head_narration(record)['status']},
        'advance': None, 'round': None, 'time': record['state'].time.model_dump(mode='json'),
        'lease': ({k: v for k, v in record['lease'].items()
                   if k in ('fenceEpoch', 'expiresAtEpochMilli')}
                  if record['lease'] else None),
        'successor': None,
        'activePointId': (record['work'] or {}).get('pointId'),
        'activeRoundId': (record['round'] or {}).get('roundId'),
    }
    advance = record.get('advance')
    if advance is not None:
        world['advance'] = {'advanceId': advance['advanceId'],
                            'inputId': advance['inputId'],
                            'intentStatus': advance['intentStatus'],
                            'inputAvailable': advance['intentStatus'] == 'pending'}
    round_view = record.get('round')
    if round_view is not None:
        world['round'] = {
            'roundId': round_view['roundId'], 'trigger': round_view['trigger'],
            'order': round_view['order'], 'cursor': round_view['cursor'],
            'actedIds': round_view['actedIds'], 'visitedIds': round_view['visitedIds'],
            'conclusion': round_view['conclusion']}
    return {'world': world, 'control': control_view(record).model_dump(mode='json'),
            'work': _work_view(record)}


READ_HANDLERS = {
    'get_state': handle_get_state,
    'list_points': handle_list_points,
    'get_context': handle_get_context,
    'narration_get': handle_narration_get,
}

WRITE_HANDLERS = dict(CHECKPOINT_HANDLERS)
WRITE_HANDLERS.update({
    'create_world': lambda record, request: handle_create_world(_CREATING_STORE[0], record, request),
    'allocate_ids': handle_allocate_ids,
    'checkpoint_start_advance': handle_start_advance,
    'preview_point': lambda record, request: handle_preview_point(record, request),
    'commit_point': handle_commit_point,
    'lease_acquire': handle_lease_acquire,
    'lease_renew': handle_lease_renew,
    'lease_release': handle_lease_release,
    'narration_claim': handle_narration_claim,
    'narration_claim_renew': handle_narration_renew,
    'narration_submit': handle_narration_submit,
    'narration_delete': handle_narration_delete,
    'round_conclusion_conclude': handle_round_conclusion_conclude,
    'round_conclusion_cancel': handle_round_conclusion_cancel,
})

_CREATING_STORE = [None]


class _BareRequest:
    def __init__(self, raw):
        self._raw = dict(raw)

    def __getattr__(self, item):
        try:
            return self._raw[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


class PointWorkProxy:
    """Adapts the stored work record to the read-only fields the ladder
    predicates consume."""

    def __init__(self, work):
        self.pointId = work['pointId']
        self.kind = work['kind']
        self.timeLocked = work['timeLocked']
        self.sealed = work['sealed']
        self.pendingGroup = work['pendingGroup']
        self.settledUnits = work['units']
        self.phase = work['phase']
        self.working = work['working']



class WorldService:
    """Entry point: validate, check idempotency before bindings, run the
    handler in one store transaction, and shape the response envelope."""

    def __init__(self, store):
        self.store = store
        _CREATING_STORE[0] = store

    def execute(self, operation, request_dict):
        spec = OPERATION_BY_NAME[operation]
        if spec.idempotency.scope == 'none':
            # GET reads: query models bind only their query fields (path
            # fields are not part of the query model) and carry no request
            # hash; several reads have requestSchema=None.
            query = {}
            if spec.requestSchema is not None:
                model_cls = next(model for model in _ALL_REQUEST_MODELS
                                 if model.__name__ == spec.requestSchema)
                query = {key: value for key, value in request_dict.items()
                         if key in model_cls.model_fields}
                request = model_cls.model_validate(query)
            else:
                request = model_cls.model_validate({}) if False else None
                request = _BareRequest(request_dict)
            record = self.store.world(request_dict.get('worldId'))
            if record is None:
                _refuse('version_mismatch', 'unknown world',
                        client_action='refresh_context')
            data = READ_HANDLERS[operation](record, request)
            envelope = _envelope(self.store, operation, request, record, data)
            envelope.pop('requestId', None)
            envelope.pop('requestHash', None)
            if operation == 'get_context':
                for key in ('world', 'control', 'work'):
                    if key in data:
                        envelope[key] = data[key]
                envelope.pop('data', None)
            return envelope
        model_cls = next(model for model in _ALL_REQUEST_MODELS
                         if model.__name__ == spec.requestSchema)
        try:
            request = model_cls.model_validate(request_dict)
        except ValidationError as error:
            raise ServiceRefusal(
                'request_malformed', str(error)[:400], http_status=400) from error
        if isinstance(request, RootModel):
            request = request.root
        digest = canonical_digest(
            request_projection(operation, request.model_dump(mode='json')))
        if operation == 'create_world':
            data = handle_create_world(self.store, None, request)
            self.store.note_global(request.requestId, {
                'operation': operation, 'digest': digest, 'data': data})
            return _envelope(self.store, operation, request, None, data, digest)
        world_id = request.worldId
        record = self.store.world(world_id)
        digest = canonical_digest(
            request_projection(operation, request.model_dump(mode='json')))
        entry = record['idempotency'].get(request.requestId)
        if entry is not None:
            if entry['operation'] != operation or entry['digest'] != digest:
                _refuse('request_id_reused',
                        'same requestId with a different operation or payload',
                        client_action='fix_request')
            data = dict(entry['data'])
            data['replayed'] = True
            envelope = _envelope(self.store, operation, request, self.store.world(world_id),
                                 data, digest)
            envelope['replayed'] = True
            return envelope

        def handler(record):
            data = WRITE_HANDLERS[operation](record, request)
            stored = ({key: value for key, value in data.items() if key != 'claimToken'}
                      if operation == 'narration_claim' else data)
            record['idempotency'][request.requestId] = {
                'operation': operation, 'digest': digest, 'data': stored}
            return data

        data = self.store.transact(world_id, handler)
        envelope = _envelope(self.store, operation, request,
                             self.store.world(world_id), data, digest)
        if spec.mutatesRevision:
            envelope['control'] = control_view(
                self.store.world(world_id)).model_dump(mode='json')
        return envelope
