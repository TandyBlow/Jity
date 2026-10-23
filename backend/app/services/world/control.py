"""The A2 control service: one transaction per operation over the fixture
baseline store.

Refusal surface: `ServiceRefusal` carries the wire code decided by the
a1-kernel-plan §四 mapping; schema-level payload failures map to
`request_malformed`. Every body write answers with the full OperationResult
envelope (world/control/work snapshots), reads with the ReadResult /
ContextResponse shapes, preview with the ComputeResult shape. Storage keeps
authoritative state only — blockedReasons/canCompute are derived per
response. Roll rows, TTL expiry, restore/takeover copying and crash recovery
stay with A3.

Per-operation order (a1-kernel-plan §四): schema validation → requestId
idempotency (checked authoritatively inside the store transaction, so a
concurrent duplicate replays instead of double-running) → lease fence →
expected head/version/revision binding → ladder preconditions → business
writes → revision increment → response projection. ``CheckpointRequest``
writes bind the committed head; work-in-progress moves only working pointers
and the working intent projection — commit_point promotes them.
"""
import typing

from pydantic import RootModel, ValidationError

from app.schemas.world.canonical import canonical_digest
from app.schemas.world.contracts import TimelinePoint, WorldInitialState
from app.schemas.world.v2.contexts import (
    ControlState, GateView, PointWorkView, WorkingProgress, WorldContext,
)
from app.schemas.world.v2.projections import prefix_projection, request_projection
from app.schemas.world.v2.registry import OPERATION_BY_NAME
from app.schemas.world.v2 import SCHEMA_MODELS as _SCHEMA_MODELS
_ALL_REQUEST_MODELS = [m for m in _SCHEMA_MODELS if m.__name__.endswith('Request')]
from app.schemas.world.v2.requests import PreviewPointRequest

from .apply import apply_point
from .commit import verify_point_binding
from .ladder import check_checkpoint
from .merge import point_entity_deltas
from .preview import preview_point as compute_preview
from .state import build_initial_state, state_digest
from .units import (
    begin_working, scan_working, skip_working, stage_working, unit_content_hash,
    validate_commit_groups,
)

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


def _request_body_fields(model_cls):
    """Body field names: the model's own, or the union of the RootModel
    members' fields (narration requests discriminate on ``mode``)."""
    annotation = (model_cls.model_fields['root'].annotation
                  if issubclass(model_cls, RootModel) else None)
    members = typing.get_args(annotation) if annotation is not None else ()
    if not members:
        return frozenset(model_cls.model_fields)
    keys = set()
    for member in members:
        keys |= set(member.model_fields)
    return frozenset(keys)


def _now(store):
    return store.clock_milli()


def _world_roster(record):
    return frozenset(record['state'].initial.characters)


def _gate(record):
    return record['control']['gate']


def _head_entry(record):
    """The head point's narration entry — the single authoritative narration
    state per point; gate and head summaries derive from it."""
    return record['narrations'][record['headPointId']]


def _blocked(record):
    blocked = []
    if record['control']['paused']:
        blocked.append('paused')
    if _gate(record)['status'] == 'pending':
        blocked.append('narration_pending')
    head = _head_entry(record)['status']
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


_VIOLATION_CODES = {
    'phase': 'phase_invalid', 'pointWork': 'phase_invalid',
    'activePendingGroup': 'phase_invalid', 'settledUnits': 'phase_invalid',
    'timeLocked': 'point_time_locked', 'confirmedWork': 'point_time_locked',
    'paused': 'paused', 'gate': 'narration_blocked',
    'roster': 'version_mismatch', 'coverage': 'request_malformed',
    'identity': 'request_malformed', 'semantic_invalid': 'request_malformed',
}


def _refuse_violations(operation, violations):
    for violation in violations:
        code = _VIOLATION_CODES.get(violation.kind, 'phase_invalid')
        kwargs = {}
        if code in ('paused', 'phase_invalid', 'narration_blocked'):
            kwargs['control_required'] = True
        _refuse(code, f'{operation}: {violation.detail}', **kwargs)


def _ladder(record, operation, work=None):
    proxy = PointWorkProxy(work) if work is not None else None
    control = control_view(record)
    _refuse_violations(operation, check_checkpoint(operation, proxy, control))


def _lease(record):
    return record.get('lease')


def _check_lease(record, request):
    lease = _lease(record)
    if lease is None or request.leaseToken != lease['leaseToken']:
        _refuse('lease_invalid', 'unknown lease token', client_action='reacquire_lease')
    if request.fenceEpoch != lease['fenceEpoch']:
        _refuse('stale_epoch', 'lease epoch has moved on',
                client_action='reacquire_lease')


def _bind_expected(record, request):
    """CheckpointRequest writes bind the committed head, version and the
    pre-operation checkpoint revision (CheckpointRequest contract docstring;
    T01 pins expectedPointId to the captured head for every checkpoint step)."""
    if (request.expectedPointId != record['headPointId']
            or request.expectedVersion != record['version']
            or request.expectedCheckpointRevision != record['control']['revision']):
        _refuse('version_mismatch',
                'head, version or checkpoint revision binding differs',
                client_action='refresh_context')


def _bind_work_point(record, request):
    work = record.get('work')
    if work is not None and request.pointId != work['pointId']:
        # With no active work the ladder's phase/pointWork rows refuse first.
        _refuse('version_mismatch', 'point binding differs from the active work',
                client_action='refresh_context')


def _work_or_none(record):
    return record.get('work')


def _sealed_prefix(record):
    work = _work_or_none(record)
    if work is None or not work['sealed']:
        _refuse('phase_invalid', 'commit requires a sealed point work',
                control_required=True)
    return work


def _issue_gate(store, record, generation):
    now = _now(store)
    record['control']['gate'] = {
        'status': 'pending', 'generation': generation,
        'issuedAtEpochMilli': now, 'expiresAtEpochMilli': now + DEFAULT_TTL_MILLI,
    }


def _new_narration(record, point_id, generation=1):
    record['narrations'][point_id] = {
        'status': 'pending', 'text': None, 'generation': generation, 'claim': None}


# --- response projections ---------------------------------------------------


def _world_view(record):
    state = record['state']
    advance = record.get('advance')
    if advance is not None:
        advance_view = {'advanceId': advance['advanceId'],
                        'inputId': advance['inputId'],
                        'intentStatus': advance['intentStatus'],
                        'inputAvailable': True}
    else:
        advance_view = {'advanceId': None, 'inputId': None,
                        'intentStatus': 'expired', 'inputAvailable': False}
    round_view = record.get('round')
    round_summary = None
    active_round_id = None
    if round_view is not None:
        round_summary = {
            'roundId': round_view['roundId'], 'trigger': round_view['trigger'],
            'order': round_view['order'], 'cursor': round_view['cursor'],
            'actedIds': round_view['actedIds'], 'visitedIds': round_view['visitedIds'],
            'conclusion': round_view['conclusion']}
        active_round_id = round_view['roundId']
    work = record.get('work')
    lease = record.get('lease')
    return WorldContext.model_validate({
        'worldId': record['worldId'],
        'head': {'pointId': record['headPointId'], 'version': record['version'],
                 'stateDigest': state_digest(state),
                 'narrationStatus': _head_entry(record)['status']},
        'advance': advance_view, 'round': round_summary,
        'time': state.time.model_dump(mode='json'),
        'lease': ({'fenceEpoch': lease['fenceEpoch'],
                   'expiresAtEpochMilli': lease['expiresAtEpochMilli']}
                  if lease else None),
        'successor': (work or {}).get('successor'),
        'activePointId': (work or {}).get('pointId'),
        'activeRoundId': active_round_id,
    }).model_dump(mode='json')


def _work_view(record):
    work = record.get('work')
    if work is None:
        return None
    view = {
        'pointId': work['pointId'], 'kind': work['kind'],
        'timeAdvance': work['timeAdvance'], 'timeLocked': work['timeLocked'],
        'sealed': work['sealed'], 'prefixDigest': work['prefixDigest'],
        'predecessorWorkDigest': None,
        'timeScanComplete': work['timeScanComplete'], 'baseline': work['baseline'],
        'phase': work['phase'],
        'working': (work['working'].model_dump(mode='json')
                    if isinstance(work['working'], WorkingProgress) else work['working']),
        'settledUnits': [
            {'unitId': unit['unitId'], 'groupId': unit['groupId'],
             'memberIds': unit['memberIds'], 'contentHash': unit['contentHash']}
            for unit in work['units']],
        'pendingGroup': ({key: value for key, value in work['pendingGroup'].items()
                          if key != 'actionTexts'}
                         if work['pendingGroup'] else None),
        'successor': work['successor'],
    }
    return PointWorkView.model_validate(view).model_dump(mode='json')


def _envelope_base(store):
    return {'protocolVersion': PROTOCOL, 'engineVersion': ENGINE,
            'schemaVersion': SCHEMA, 'canonicalVersion': CANONICAL,
            'serverTimeEpochMilli': _now(store)}


def _operation_envelope(store, operation, request, record, data, digest):
    """OperationResult: request key, replay flag and the full snapshots."""
    return {**_envelope_base(store), 'operation': operation,
            'requestId': request.requestId, 'requestHash': digest,
            'replayed': False, 'world': _world_view(record),
            'control': control_view(record).model_dump(mode='json'),
            'work': _work_view(record), 'data': data}


def _read_envelope(store, record, data):
    """ReadResult: no request key, no replay flag, no control/work."""
    return {**_envelope_base(store), 'world': _world_view(record), 'data': data}


def _compute_envelope(store, operation, record, data):
    """ComputeResult (preview): no request key, replay flag or digest."""
    return {**_envelope_base(store), 'operation': operation,
            'world': _world_view(record),
            'control': control_view(record).model_dump(mode='json'),
            'work': _work_view(record), 'data': data}


def _context_envelope(store, record, data):
    """ContextResponse: snapshots plus the active input chain and recovery."""
    return {**_envelope_base(store), 'world': data['world'],
            'control': data['control'], 'work': data['work'],
            'activeInput': data['activeInput'], 'recovery': None}


# --- per-operation handlers (record is the mutable transaction copy) --------


def handle_create_world(store, request):
    world_id = store.next_id('world')
    initial = WorldInitialState.model_validate(
        {'worldId': world_id, **request.initial.model_dump(mode='json', exclude={'worldId'})})
    state = build_initial_state(initial)
    now = _now(store)
    lease = {'leaseToken': store.next_id('lease'), 'fenceEpoch': 1,
             'expiresAtEpochMilli': now + DEFAULT_TTL_MILLI}
    root_id = store.next_id('root')
    record = {
        'worldId': world_id, 'state': state, 'version': 0,
        'rootPointId': root_id, 'headPointId': root_id,
        'points': {}, 'pointStates': {},
        'advance': None, 'round': None, 'work': None,
        'control': {'phase': 'select_actor', 'paused': False, 'revision': 0,
                    'gate': {'status': 'pending', 'generation': 1,
                             'issuedAtEpochMilli': now,
                             'expiresAtEpochMilli': now + DEFAULT_TTL_MILLI}},
        'lease': lease, 'idempotency': {}, 'allocations': {},
        'allocationSequence': 0,
        'narrations': {},
    }
    _new_narration(record, root_id)
    record['pointStates'][root_id] = {
        'version': 0, 'state': state, 'stateDigest': state_digest(state)}
    store.create_world(world_id, record)
    return {'worldId': world_id, 'rootPointId': root_id, 'lease': lease}


def handle_allocate_ids(store, record, request):
    _check_lease(record, request)
    allocated = []
    bucket = record['allocations'].setdefault(request.allocationKey, {})
    for slot in request.slots:
        slot_view = slot.model_dump(mode='json')
        key = (slot_view.get('scope'), slot_view['slotKey'])
        if key in bucket:
            allocated.append({'slotKey': slot_view['slotKey'], 'id': bucket[key]})
            continue
        record['allocationSequence'] += 1
        new_id = f"{slot_view['kind']}_{record['allocationSequence']}"
        bucket[key] = new_id
        allocated.append({'slotKey': slot_view['slotKey'], 'id': new_id})
    return {'allocations': allocated}


def _narration_entry(record, point_id):
    entry = record['narrations'].get(point_id)
    if entry is None:
        _refuse('version_mismatch', f'no committed narration for point {point_id}',
                client_action='refresh_context')
    return entry


def _bind_head_mode(record, request):
    """Head narration writes fence through the advance lease and only target
    the committed head; history narration carries no lease by schema."""
    if request.mode != 'head':
        return
    _check_lease(record, request)
    if request.pointId != record['headPointId']:
        _refuse('version_mismatch', 'head narration targets another point',
                client_action='refresh_context')


def handle_narration_claim(store, record, request):
    _bind_head_mode(record, request)
    entry = _narration_entry(record, request.pointId)
    if request.currentClaim is not None:
        claim = entry.get('claim')
        if (claim is None or request.currentClaim.claimToken != claim['claimToken']
                or request.currentClaim.generation != claim['generation']):
            _refuse('claim_fenced', 'caller holds a superseded claim',
                    client_action='refresh_context')
    gate = _gate(record)
    fence = record['lease']['fenceEpoch'] if request.mode == 'head' else None
    # Every fresh claim answers with a token (NarrationClaimSuccess: data
    # carries claimToken unless replayed); claiming an already-settled
    # narration re-issues the entry's current claim.
    claim = entry.get('claim')
    if claim is None:
        token = f"claim_{entry['generation']}_{request.pointId}"
        claim = {'claimToken': token, 'generation': entry['generation']}
        entry['claim'] = claim
    return {'pointId': request.pointId, 'mode': request.mode,
            'claimToken': claim['claimToken'],
            'generation': entry['generation'], 'fenceEpoch': fence,
            'issuedAtEpochMilli': gate['issuedAtEpochMilli'],
            'expiresAtEpochMilli': gate['expiresAtEpochMilli']}


def handle_narration_renew(store, record, request):
    _bind_head_mode(record, request)
    entry = _narration_entry(record, request.pointId)
    claim = entry.get('claim')
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


def handle_narration_submit(store, record, request):
    _bind_head_mode(record, request)
    entry = _narration_entry(record, request.pointId)
    claim = entry.get('claim')
    if (claim is None or request.claimToken != claim['claimToken']
            or request.generation != claim['generation']):
        _refuse('claim_fenced', 'submitting with a superseded claim',
                client_action='refresh_context')
    entry['text'] = request.text
    entry['status'] = request.outcome
    # Only the matching head operation clears the gate; a resubmitted history
    # narration never touches the current head's narration flow.
    if request.outcome == 'ready' and request.pointId == record['headPointId']:
        record['control']['gate'] = {
            'status': 'none', 'generation': None,
            'issuedAtEpochMilli': None, 'expiresAtEpochMilli': None,
        }
    return {'pointId': request.pointId, 'narrationStatus': request.outcome,
            'generation': request.generation}


def handle_narration_get(store, record, request):
    entry = record['narrations'].get(request.pointId)
    if entry is None:
        return {'pointId': request.pointId, 'narrationStatus': 'missing',
                'generation': None, 'text': None}
    status = entry['status']
    return {'pointId': request.pointId, 'narrationStatus': status,
            'generation': entry['generation'],
            'text': entry['text'] if status == 'ready' else None}


def handle_narration_delete(store, record, request):
    if request.mode == 'head':
        _check_lease(record, request)
        point_id = record['headPointId']
        entry = _narration_entry(record, point_id)
    else:
        point_id, entry = None, None
        for candidate_id, candidate in record['narrations'].items():
            claim = candidate.get('claim')
            if (claim and request.claimToken == claim['claimToken']
                    and request.generation == claim['generation']):
                point_id, entry = candidate_id, candidate
                break
        if entry is None:
            _refuse('claim_fenced', 'delete with a superseded claim',
                    client_action='refresh_context')
    claim = entry.get('claim')
    if (claim is None or request.claimToken != claim['claimToken']
            or request.generation != claim['generation']):
        _refuse('claim_fenced', 'delete with a superseded claim',
                client_action='refresh_context')
    generation = entry['generation']
    _new_narration(record, point_id, generation + 1)
    record['narrations'][point_id]['status'] = 'missing'
    if point_id == record['headPointId']:
        _issue_gate(store, record, generation + 1)
    return {'pointId': point_id, 'narrationStatus': 'missing',
            'invalidatedGeneration': generation}


def handle_lease_acquire(store, record, request):
    lease = _lease(record)
    if lease is not None:
        _refuse('lease_invalid', 'lease_held', details={'reason': 'lease_held'},
                client_action='none')
    fence = 1
    record['lease'] = {'holderId': request.holderId,
                       'leaseToken': f'lease_{fence}_{request.holderId}',
                       'fenceEpoch': fence,
                       'expiresAtEpochMilli': _now(store) + DEFAULT_TTL_MILLI}
    return {'holderId': request.holderId, 'leaseToken': record['lease']['leaseToken'],
            'fenceEpoch': fence,
            'expiresAtEpochMilli': record['lease']['expiresAtEpochMilli']}


def handle_lease_renew(store, record, request):
    lease = _lease(record)
    if lease is None or request.leaseToken != lease['leaseToken'] \
            or request.fenceEpoch != lease['fenceEpoch']:
        _refuse('lease_invalid', 'unknown lease token or epoch',
                client_action='reacquire_lease')
    lease['expiresAtEpochMilli'] = _now(store) + DEFAULT_TTL_MILLI
    return {'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
            'expiresAtEpochMilli': lease['expiresAtEpochMilli']}


def handle_lease_release(store, record, request):
    lease = _lease(record)
    if lease is None or request.leaseToken != lease['leaseToken'] \
            or request.fenceEpoch != lease['fenceEpoch']:
        _refuse('lease_invalid', 'unknown lease token or epoch',
                client_action='reacquire_lease')
    record['lease'] = None
    return {'released': True}


def handle_start_advance(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _ladder(record, 'checkpoint_start_advance', None)
    if record.get('advance') is not None:
        _refuse('phase_invalid', 'an active advance already exists',
                control_required=True)
    if record['work'] is not None:
        _refuse('phase_invalid', 'a point work is still active', control_required=True)
    if _head_entry(record)['status'] != 'ready':
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


def handle_begin_point(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _ladder(record, 'checkpoint_begin_point', None)
    if record['work'] is not None:
        _refuse('phase_invalid', 'a point work is still active', control_required=True)
    if request.pointId == record['rootPointId'] or request.pointId in record['points']:
        _refuse('version_mismatch', 'point id is already committed',
                client_action='refresh_context')
    state = record['state']
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
    # The committed head only moves at commit; begin opens the working view.
    record['control']['revision'] += 1
    return {'pointId': request.pointId}


def _bind_group(record, request):
    work = _work_or_none(record)
    group = work['pendingGroup']
    if group is None or request.groupId != group['groupId']:
        _refuse('version_mismatch', 'group binding differs from the pending group',
                client_action='refresh_context')


def handle_discover_group(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_discover_group', work)
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


def handle_extend_group(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_extend_group', work)
    _bind_group(record, request)
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


def handle_close_group(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_close_group', work)
    _bind_group(record, request)
    work['pendingGroup']['closed'] = True
    work['phase'] = 'settle_group'
    record['control']['phase'] = 'settle_group'
    record['control']['revision'] += 1
    return {'groupId': request.groupId, 'closed': True}


def handle_stage_unit(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_stage_unit', work)
    _bind_group(record, request)
    candidates = request.candidates
    if candidates.groupId != request.groupId:
        _refuse('request_malformed', 'candidates name another group')
    _refuse_violations('checkpoint_stage_unit',
                       validate_commit_groups([candidates], _world_roster(record)))
    unit_id = f"unit_{len(work['units']) + 1}_{request.groupId}"
    work['units'].append({
        'unitId': unit_id, 'groupId': request.groupId,
        'memberIds': sorted(candidates.actorIds),
        'contentHash': unit_content_hash(candidates), 'candidates': candidates,
        'results': request.results,
    })
    work['working'] = stage_working(work['working'], unit_id,
                                    candidates.actorIds,
                                    record['round']['order'])
    work['pendingGroup'] = None
    work['phase'] = 'select_actor'
    record['control']['phase'] = 'select_actor'
    record['control']['revision'] += 1
    return {'groupId': request.groupId, 'unitId': unit_id,
            'working': work['working'].model_dump(mode='json')}


def handle_record_skip(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_record_skip', work)
    if request.slotActorId not in record['round']['order']:
        _refuse('request_malformed', 'slot actor is not in the round order')
    work['working'] = skip_working(work['working'], request.slotActorId,
                                   record['round']['order'])
    record['control']['revision'] += 1
    return {'pointId': work['pointId'],
            'working': work['working'].model_dump(mode='json')}


def handle_stage_time_scan(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_stage_time_scan', work)
    if request.candidates.groupId is not None:
        _refuse('request_malformed', 'time-scan candidates cannot name a group')
    _refuse_violations('checkpoint_stage_time_scan',
                       validate_commit_groups([request.candidates],
                                              _world_roster(record)))
    work['timeScan'] = request.candidates
    work['timeScanComplete'] = True
    work['timeLocked'] = True
    work['working'] = scan_working(work['working'], record['round']['order'])
    record['control']['revision'] += 1
    return {'pointId': work['pointId'],
            'working': work['working'].model_dump(mode='json')}


def handle_seal_point(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_seal_point', work)
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


def handle_set_point_time(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_set_point_time', work)
    work['timeAdvance'] = request.timeAdvance.model_dump(mode='json')
    record['control']['revision'] += 1
    return {'pointId': work['pointId'],
            'timeAdvance': request.timeAdvance.model_dump(mode='json')}


def handle_prepare_successor(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_prepare_successor', work)
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


def handle_pause(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _ladder(record, 'checkpoint_pause', None)
    if not record['control']['paused']:
        record['control']['paused'] = True
        record['control']['revision'] += 1
    return {'paused': True}


def handle_resume(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _ladder(record, 'checkpoint_resume', None)
    if record['control']['paused']:
        record['control']['paused'] = False
        record['control']['revision'] += 1
    return {'paused': False}


def handle_preview_point(store, record, request):
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'preview_point', work)
    round_view = record.get('round')
    projection = TimelinePoint.model_validate({
        'worldId': record['worldId'], 'id': request.pointId,
        'sequence': len(record['points']) + 1,
        'kind': work['kind'], 'previousPointId': record['headPointId'],
        'roundId': request.roundId, 'advanceId': request.advanceId,
        'trigger': round_view['trigger'] if round_view else 'player',
        'linkedFromPointId': None,
        'timeAdvance': request.timeAdvance.model_dump(mode='json'),
        'entityDeltas': {}})
    return compute_preview(record['state'], projection,
                           list(request.settlementGroups))


def handle_commit_point(store, record, request):
    work = _sealed_prefix(record)
    _check_lease(record, request)
    _bind_expected(record, request)
    _ladder(record, 'commit_point', work)
    sealed_time_advance = work['timeAdvance']
    if hasattr(sealed_time_advance, 'model_dump'):
        sealed_time_advance = sealed_time_advance.model_dump(mode='json')
    verify_point_binding(
        request.point, work['kind'],
        type(request.point.timeAdvance).model_validate(sealed_time_advance))
    if request.pointId != work['pointId']:
        _refuse('version_mismatch', 'commit targets another point than the sealed work',
                client_action='refresh_context')
    if request.point.previousPointId != record['headPointId']:
        _refuse('version_mismatch', 'point chains from another head',
                client_action='refresh_context')
    given = list(request.settlementGroups)
    staged = work['units']
    if len(given) != len(staged):
        _refuse('version_mismatch',
                'settlementGroups differ from the sealed settledUnits',
                details={'reason': 'prefix_binding_mismatch'})
    for unit, group in zip(staged, given):
        if (unit['groupId'] != group.groupId
                or unit['memberIds'] != sorted(group.actorIds)
                or unit['contentHash'] != unit_content_hash(group)):
            _refuse('version_mismatch',
                    'settlementGroups differ from the sealed settledUnits '
                    '(identity, members or content)',
                    details={'reason': 'prefix_binding_mismatch'})
    _refuse_violations('commit_point',
                       validate_commit_groups(given, _world_roster(record)))
    merged = point_entity_deltas(given, work['timeScan'])
    expected_deltas = {key: delta.model_dump(mode='json') for key, delta in merged.items()}
    if {key: delta.model_dump(mode='json')
            for key, delta in request.point.entityDeltas.items()} != expected_deltas:
        _refuse('request_malformed', 'point deltas differ from the merged settlement')
    new_state = apply_point(record['state'], request.point)
    record['state'] = new_state
    record['version'] += 1
    record['points'][request.pointId] = request.point
    record['pointStates'][request.pointId] = {
        'version': record['version'], 'state': new_state,
        'stateDigest': state_digest(new_state)}
    round_view = record['round']
    round_view['cursor'] = work['working'].cursor
    round_view['actedIds'] = work['working'].actedIds
    round_view['visitedIds'] = work['working'].visitedIds
    if record['advance'] is not None:
        # The committed intent is the one the sealed work projected; stage and
        # skip only ever moved the working copy.
        record['advance']['intentStatus'] = work['working'].intentStatus
    record['work'] = None
    record['headPointId'] = request.pointId
    _new_narration(record, request.pointId)
    _issue_gate(store, record, 1)
    if round_view['cursor'] == len(round_view['order']) and round_view['conclusion'] is None:
        record['control']['phase'] = 'assess_continuation'
    record['control']['revision'] += 1
    return {'pointId': request.pointId, 'version': record['version'],
            'stateDigest': state_digest(new_state)}


def handle_round_conclusion_cancel(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _ladder(record, 'round_conclusion_cancel',
            _work_or_none(record))
    if record['control']['phase'] != 'assess_continuation':
        _refuse('phase_invalid', 'cancel runs from assess_continuation',
                control_required=True)
    round_view = record['round']
    round_view['conclusion'] = {
        'kind': 'handback', 'closedBy': 'cancel', 'cancelReason': request.cancelReason}
    record['control']['phase'] = 'complete'
    record['advance'] = None
    record['control']['revision'] += 1
    return {'roundId': request.roundId, 'abandonedGroupIds': []}


def handle_round_conclusion_conclude(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _ladder(record, 'round_conclusion_conclude',
            _work_or_none(record))
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


def handle_get_state(store, record, request):
    point_id = request.point or record['headPointId']
    cached = record['pointStates'].get(point_id)
    if cached is None:
        _refuse('version_mismatch', 'unknown point', client_action='refresh_context')
    return {'pointId': point_id, 'version': cached['version'],
            'state': cached['state'].model_dump(mode='json'),
            'stateDigest': cached['stateDigest']}


def handle_list_points(store, record, request):
    points = []
    for point_id, cached in record['pointStates'].items():
        if point_id == record['rootPointId']:
            points.append({'pointId': point_id, 'sequence': 0, 'kind': 'root',
                           'roundId': None, 'advanceId': None,
                           'stateDigest': cached['stateDigest']})
        else:
            point = record['points'][point_id]
            points.append({'pointId': point_id, 'sequence': point.sequence,
                           'kind': point.kind, 'roundId': point.roundId,
                           'advanceId': point.advanceId,
                           'stateDigest': cached['stateDigest']})
    return {'points': points}


def handle_get_context(store, record, request):
    advance = record.get('advance')
    active_input = None
    if advance is not None and advance['intentStatus'] == 'pending':
        active_input = {'advanceId': advance['advanceId'],
                        'inputId': advance['inputId'],
                        'text': advance['inputText']}
    return {'world': _world_view(record),
            'control': control_view(record).model_dump(mode='json'),
            'work': _work_view(record), 'activeInput': active_input}


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


READ_HANDLERS = {
    'get_state': handle_get_state,
    'list_points': handle_list_points,
    'get_context': handle_get_context,
    'narration_get': handle_narration_get,
}

WRITE_HANDLERS = dict(CHECKPOINT_HANDLERS)
WRITE_HANDLERS.update({
    'allocate_ids': handle_allocate_ids,
    'checkpoint_start_advance': handle_start_advance,
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

    def execute(self, operation, request_dict):
        spec = OPERATION_BY_NAME[operation]
        if spec.idempotency.scope == 'none':
            return self._execute_scopeless(operation, request_dict, spec)
        model_cls = next(model for model in _ALL_REQUEST_MODELS
                         if model.__name__ == spec.requestSchema)
        body = {key: value for key, value in request_dict.items()
                if key in _request_body_fields(model_cls)}
        try:
            request = model_cls.model_validate(body)
        except ValidationError as error:
            raise ServiceRefusal(
                'request_malformed', str(error)[:400], http_status=400) from error
        if isinstance(request, RootModel):
            request = request.root
        digest = canonical_digest(
            request_projection(operation, request.model_dump(mode='json')))
        if operation == 'create_world':
            return self._execute_create(operation, request, digest)
        # worldId may arrive as a path parameter the body schema forbids
        # (lease_release); the raw dict remains the routing authority.
        return self._execute_write(operation, request, digest,
                                   request_dict.get('worldId'))

    # -- scope-none operations: reads plus the stateless preview ------------

    def _execute_scopeless(self, operation, request_dict, spec):
        if operation == 'preview_point':
            try:
                request = PreviewPointRequest.model_validate(request_dict)
            except ValidationError as error:
                raise ServiceRefusal(
                    'request_malformed', str(error)[:400], http_status=400) from error
            record = self._record(request.worldId)
            data = handle_preview_point(self.store, record, request)
            return _compute_envelope(self.store, operation, record, data)
        request = None
        if spec.requestSchema is not None:
            model_cls = next(model for model in _ALL_REQUEST_MODELS
                             if model.__name__ == spec.requestSchema)
            try:
                query = {key: value for key, value in request_dict.items()
                         if key in model_cls.model_fields}
                request = model_cls.model_validate(query)
            except ValidationError as error:
                raise ServiceRefusal(
                    'request_malformed', str(error)[:400], http_status=400) from error
        else:
            # requestSchema=None reads (narration_get) bind only their path
            # fields; a bare attribute view is enough.
            request = _BareRequest(request_dict)
        record = self._record(request_dict.get('worldId'))
        data = READ_HANDLERS[operation](self.store, record, request)
        if operation == 'get_context':
            return _context_envelope(self.store, record, data)
        return _read_envelope(self.store, record, data)

    # -- body writes ---------------------------------------------------------

    def _record(self, world_id):
        record = self.store.world(world_id) if world_id else None
        if record is None:
            _refuse('version_mismatch', 'unknown world',
                    client_action='refresh_context')
        return record

    def _execute_create(self, operation, request, digest):
        # Creation idempotency lives in the store-global table; check and
        # insert under one lock acquisition so a concurrent duplicate cannot
        # create a second world.
        with self.store.locked():
            entry = self.store.global_idempotency().get(request.requestId)
            if entry is not None:
                if entry['operation'] != operation or entry['digest'] != digest:
                    _refuse('request_id_reused',
                            'same requestId with a different operation or payload',
                            client_action='fix_request')
                record = self.store.world(entry['data']['worldId'])
                envelope = _operation_envelope(
                    self.store, operation, request, record, entry['data'], digest)
                envelope['replayed'] = True
                return envelope
            data = handle_create_world(self.store, request)
            self.store.note_global(request.requestId, {
                'operation': operation, 'digest': digest, 'data': data})
        record = self.store.world(data['worldId'])
        return _operation_envelope(self.store, operation, request, record, data, digest)

    def _execute_write(self, operation, request, digest, world_id):
        self._record(world_id)

        def handler(snapshot):
            # The idempotency decision runs inside the transaction: a request
            # that races a duplicate replays the stored payload instead of
            # double-running the handler.
            entry = snapshot['idempotency'].get(request.requestId)
            if entry is not None:
                if entry['operation'] != operation or entry['digest'] != digest:
                    _refuse('request_id_reused',
                            'same requestId with a different operation or payload',
                            client_action='fix_request')
                return entry['data'], True
            data = WRITE_HANDLERS[operation](self.store, snapshot, request)
            stored = ({key: value for key, value in data.items() if key != 'claimToken'}
                      if operation == 'narration_claim' else data)
            snapshot['idempotency'][request.requestId] = {
                'operation': operation, 'digest': digest, 'data': stored}
            return data, False

        data, replayed = self.store.transact(world_id, handler)
        record = self.store.world(world_id)
        envelope = _operation_envelope(self.store, operation, request, record,
                                       data, digest)
        envelope['replayed'] = replayed
        return envelope
