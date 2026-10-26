"""The A2 control service: one transaction per operation over the fixture
baseline store.

Refusal surface: `ServiceRefusal` carries the wire code decided by the
a1-kernel-plan §四 mapping; schema-level payload failures map to
`request_malformed`. HTTP status, client action and the control-snapshot
requirement always derive from the shared `ERROR_CODES` table. Kernel
exceptions (`KernelViolation`) are mapped at the service boundary inside the
transaction, so callers see the documented refusal and no mutation. Every
body write answers with the full OperationResult envelope
(world/control/work snapshots built and validated inside the transaction —
a shape bug refuses and discards the copy instead of committing it), reads
with the ReadResult / ContextResponse shapes, preview with the ComputeResult
shape. Storage keeps authoritative state only — blockedReasons/canCompute
are derived per response. Roll rows, TTL expiry, restore/takeover copying
and crash recovery stay with A3.

Per-operation order (a1-kernel-plan §四): schema validation → requestId
idempotency (checked authoritatively inside the store transaction, so a
concurrent duplicate replays instead of double-running) → lease fence →
expected head/version/revision binding → active-chain binding → ladder
preconditions → business writes → revision increment → response projection.
``CheckpointRequest`` writes bind the committed head; work-in-progress moves
only working pointers and the working intent projection — commit_point
promotes them.
"""
import copy
import time
import typing

from pydantic import RootModel, ValidationError

from app.schemas.world.canonical import canonical_digest
from app.schemas.world.contracts import TimelinePoint, WorldInitialState
from app.schemas.world.v2.contexts import (
    ControlState, GateView, PointWorkView, WorkingProgress, WorldContext,
)
from app.schemas.world.v2.errors import ERROR_CODES
from app.schemas.world.v2.envelopes import ErrorResponse
from app.schemas.world.v2.projections import prefix_projection, request_projection
from app.schemas.world.v2.registry import OPERATION_BY_NAME
from app.schemas.world.v2 import SCHEMA_MODELS as _SCHEMA_MODELS
_ALL_REQUEST_MODELS = [m for m in _SCHEMA_MODELS if m.__name__.endswith('Request')]
from app.schemas.world.v2.requests import PreviewPointRequest

from .apply import apply_point
from . import authority
from .commit import verify_point_binding
from .ladder import check_checkpoint
from .merge import point_entity_deltas
from .preview import preview_point as compute_preview
from .state import build_initial_state, state_digest
from .store import WorldNotFound
from .units import (
    begin_working, scan_working, skip_working, stage_working, unit_content_hash,
    validate_commit_groups,
)
from .violations import KernelViolation, ViolationKind

ENGINE = 'world-engine-v1'
CANONICAL = 'world-canonical-v1'
SCHEMA = 1
PROTOCOL = 2
DEFAULT_TTL_MILLI = 3_600_000


class ServiceRefusal(Exception):
    """Wire refusal; status, client action and the control-snapshot flag come
    from the shared error table so the response can never drift from the
    ErrorResponse contract."""

    def __init__(self, code, detail, details=None):
        spec = ERROR_CODES[code]
        super().__init__(f'{code}: {detail}')
        self.code = code
        self.detail = detail
        self.http_status = spec['httpStatus']
        self.client_action = spec['clientAction']
        self.details = details if details is not None else {}
        self.control_required = spec['controlRequired']


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
    entry = record['narrations'][record['headPointId']]
    if record['headPointId'] in getattr(record, 'missing_narrations', ()):
        return {**entry, 'status': 'missing', 'text': None}
    return entry


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
    if hasattr(record, 'clock_milli'):
        blocked.extend(authority.blocked_reasons(record, record))
    return sorted(set(blocked))


def control_view(record):
    blocked = _blocked(record)
    gate = _gate(record)
    return ControlState(
        phase=record['control']['phase'], paused=record['control']['paused'],
        revision=record['control']['revision'],
        gate=GateView.model_validate(gate), blockedReasons=blocked,
        canCompute=not blocked)


def _refuse(code, detail, details=None):
    raise ServiceRefusal(code, detail, details=details)


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
        _refuse(code, f'{operation}: {violation.detail}')


_KERNEL_CODE_MAP = {
    ViolationKind.PREFIX_BINDING: ('version_mismatch',
                                   {'reason': 'prefix_binding_mismatch'}),
    ViolationKind.TIME_LOCKED: ('point_time_locked', None),
    ViolationKind.POSITION_INVALID: ('request_malformed', None),
    ViolationKind.SEMANTIC_INVALID: ('request_malformed', None),
    ViolationKind.COVERAGE_INCOMPLETE: ('request_malformed', None),
    ViolationKind.ID_UNRESOLVED: ('version_mismatch', None),
}


def _map_kernel(operation, error):
    """Kernel refusals never escape as raw exceptions: the taxonomy maps onto
    the wire codes inside the transaction (T08 s9 pins version_mismatch /
    prefix_binding_mismatch for a sealed-time forgery)."""
    code, details = _KERNEL_CODE_MAP.get(error.kind, ('phase_invalid', None))
    _refuse(code, f'{operation}: {error.detail}', details=details)


def _ladder(record, operation, work=None):
    proxy = PointWorkProxy(work) if work is not None else None
    control = control_view(record)
    _refuse_violations(operation, check_checkpoint(operation, proxy, control))


def _lease(record):
    return record.get('lease')


def _check_lease(record, request):
    if hasattr(record, 'clock_milli'):
        return authority.check_lease(record, record, request)
    lease = _lease(record)
    if lease is None or request.leaseToken != lease['leaseToken']:
        _refuse('lease_invalid', 'unknown lease token')
    if request.fenceEpoch != lease['fenceEpoch']:
        _refuse('stale_epoch', 'lease epoch has moved on')


def _bind_expected(record, request):
    """CheckpointRequest writes bind the committed head, version and the
    pre-operation checkpoint revision (CheckpointRequest contract docstring;
    T01 pins expectedPointId to the captured head for every checkpoint step)."""
    if (request.expectedPointId != record['headPointId']
            or request.expectedVersion != record['version']
            or request.expectedCheckpointRevision != record['control']['revision']):
        _refuse('version_mismatch',
                'head, version or checkpoint revision binding differs')


def _bind_work_point(record, request):
    work = record.get('work')
    if work is not None and request.pointId != work['pointId']:
        # With no active work the ladder's phase/pointWork rows refuse first.
        _refuse('version_mismatch', 'point binding differs from the active work')


def _bind_chain(record, request):
    """Commit/preview/conclusion writes bind the request's advance and round
    identities to the stored active chain — not merely to each other
    (forged outer+inner metadata must not satisfy this)."""
    advance = record.get('advance')
    round_view = record.get('round')
    if (advance is None or request.advanceId != advance['advanceId']
            or round_view is None or request.roundId != round_view['roundId']):
        _refuse('version_mismatch', 'advance or round binding differs from the active chain')


def _work_or_none(record):
    return record.get('work')


def _sealed_prefix(record):
    work = _work_or_none(record)
    if work is None or not work['sealed']:
        _refuse('phase_invalid', 'commit requires a sealed point work')
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


def _views(record):
    """Response snapshots, built and validated while the transaction copy is
    still discardable (a shape bug here must never reach the store)."""
    return {'world': _world_view(record),
            'control': control_view(record).model_dump(mode='json'),
            'work': _work_view(record)}


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


def _pending_group_view(group):
    """Wire projection of the pending group: internal bookkeeping (per-source
    action texts, raw target specs) stays in the store; unconfirmed targets
    project as an empty goal set (PendingGroupView.targetIds is not nullable)."""
    view = {key: value for key, value in group.items()
            if key not in ('actionTexts', 'targetIdsBySource', 'targetSpecsBySource')}
    if view['targetIds'] is None:
        view['targetIds'] = []
    return view


def _work_view(record):
    work = record.get('work')
    if work is None:
        return None
    view = {
        'pointId': work['pointId'], 'kind': work['kind'],
        'timeAdvance': work['timeAdvance'], 'timeLocked': work['timeLocked'],
        'sealed': work['sealed'], 'prefixDigest': work['prefixDigest'],
        'predecessorWorkDigest': work.get('predecessorWorkDigest'),
        'timeScanComplete': work['timeScanComplete'], 'baseline': work['baseline'],
        'phase': work['phase'],
        'working': (work['working'].model_dump(mode='json')
                    if isinstance(work['working'], WorkingProgress) else work['working']),
        'settledUnits': [
            {'unitId': unit['unitId'], 'groupId': unit['groupId'],
             'memberIds': unit['memberIds'], 'contentHash': unit['contentHash']}
            for unit in work['units']],
        'pendingGroup': (_pending_group_view(work['pendingGroup'])
                         if work['pendingGroup'] else None),
        'successor': work['successor'],
    }
    return PointWorkView.model_validate(view).model_dump(mode='json')


def _envelope_base(store):
    return {'protocolVersion': PROTOCOL, 'engineVersion': ENGINE,
            'schemaVersion': SCHEMA, 'canonicalVersion': CANONICAL,
            'serverTimeEpochMilli': _now(store)}


def _operation_envelope(store, operation, request, views, data, digest,
                        replayed=False):
    """OperationResult: request key, replay flag and the full snapshots."""
    return {**_envelope_base(store), 'operation': operation,
            'requestId': request.requestId, 'requestHash': digest,
            'replayed': replayed, **views, 'data': data}


def _validate_success(operation, envelope):
    model = next(model for model in _SCHEMA_MODELS
                 if model.__name__ == OPERATION_BY_NAME[operation].successSchema)
    model.model_validate(envelope)


def _read_envelope(store, record, data):
    """ReadResult: no request key, no replay flag, no control/work."""
    return {**_envelope_base(store), 'world': _world_view(record), 'data': data}


def _compute_envelope(store, operation, views, data):
    """ComputeResult (preview): no request key, replay flag or digest."""
    return {**_envelope_base(store), 'operation': operation, **views, 'data': data}


def _context_envelope(store, data):
    """ContextResponse: snapshots plus the active input chain and recovery."""
    return {**_envelope_base(store), 'world': data['world'],
            'control': data['control'], 'work': data['work'],
            'activeInput': data['activeInput'], 'recovery': data.get('recovery')}


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
    if getattr(store, 'persistent', False):
        record = store.prepare_record(record)
        authority.initialize_world(store, record)
        lease = {key: record['lease'][key] for key in (
            'leaseToken', 'fenceEpoch', 'expiresAtEpochMilli')}
    return record, {'worldId': world_id, 'rootPointId': root_id, 'lease': lease}


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
        _refuse('version_mismatch', f'no committed narration for point {point_id}')
    return entry


def _bind_head_mode(record, request):
    """Head narration writes fence through the advance lease and only target
    the committed head; history narration carries no lease and only targets
    historical points, including a former head regenerated in a new mode."""
    if request.mode == 'history':
        if request.pointId == record['headPointId']:
            _refuse('claim_fenced', 'history narration cannot target the current head')
        return
    _check_lease(record, request)
    if request.pointId != record['headPointId']:
        _refuse('version_mismatch', 'head narration targets another point')


def _fence_claim(entry, request, action):
    """A claim is fixed identity: token, generation and the mode it was
    issued in. A head-mode token is not history authorization."""
    claim = entry.get('claim')
    if (claim is None or request.claimToken != claim['claimToken']
            or request.generation != claim['generation']
            or claim.get('mode') != request.mode):
        _refuse('claim_fenced', f'{action} with a superseded or mismatched claim')
    return claim


def handle_narration_claim(store, record, request):
    _bind_head_mode(record, request)
    entry = _narration_entry(record, request.pointId)
    if request.currentClaim is not None:
        claim = entry.get('claim')
        if (claim is None or request.currentClaim.claimToken != claim['claimToken']
                or request.currentClaim.generation != claim['generation']):
            _refuse('claim_fenced', 'caller holds a superseded claim')
    fence = record['lease']['fenceEpoch'] if request.mode == 'head' else None
    claim = entry.get('claim')
    if claim is not None and claim['mode'] != request.mode:
        # A former head can be regenerated as history, but its issued head
        # token never changes mode. Retire it and issue a new generation.
        # The symmetric head path also repairs a legacy history claim that
        # occupied the current head before the history-mode guard existed.
        generation = entry['generation'] + 1
        _new_narration(record, request.pointId, generation)
        entry = _narration_entry(record, request.pointId)
        if request.mode == 'head':
            _issue_gate(store, record, generation)
        claim = None
    elif (claim is not None and request.mode == 'history'
          and request.currentClaim is None):
        _refuse('claim_fenced', 'retrieving a history claim requires its current authority')
    # Every fresh claim answers with a token (NarrationClaimSuccess: data
    # carries claimToken unless replayed); the claim keeps the mode it was
    # issued in; regenerating in another mode above creates a new identity.
    if claim is None:
        token = f"claim_{entry['generation']}_{request.pointId}"
        now = _now(store)
        claim = {'claimToken': token, 'generation': entry['generation'],
                 'mode': request.mode, 'fenceEpoch': fence,
                 'issuedAtEpochMilli': now,
                 'expiresAtEpochMilli': now + DEFAULT_TTL_MILLI}
        entry['claim'] = claim
    return {'pointId': request.pointId, 'mode': request.mode,
            'claimToken': claim['claimToken'],
            'generation': entry['generation'], 'fenceEpoch': fence,
            'issuedAtEpochMilli': claim['issuedAtEpochMilli'],
            'expiresAtEpochMilli': claim['expiresAtEpochMilli']}


def handle_narration_renew(store, record, request):
    _bind_head_mode(record, request)
    entry = _narration_entry(record, request.pointId)
    claim = _fence_claim(entry, request, 'renewing')
    claim['expiresAtEpochMilli'] = _now(store) + DEFAULT_TTL_MILLI
    return {'pointId': request.pointId, 'mode': request.mode,
            'generation': request.generation,
            'fenceEpoch': record['lease']['fenceEpoch'] if request.mode == 'head' else None,
            'issuedAtEpochMilli': claim['issuedAtEpochMilli'],
            'expiresAtEpochMilli': claim['expiresAtEpochMilli']}


def handle_narration_submit(store, record, request):
    _bind_head_mode(record, request)
    entry = _narration_entry(record, request.pointId)
    _fence_claim(entry, request, 'submitting')
    if (entry['status'] == 'ready'
            and (request.outcome != 'ready' or request.text != entry['text'])):
        # Same generation, same claim: only the identical text replays; a
        # changed text needs narration_delete and a new generation.
        _refuse('request_malformed', 'narration text is immutable within a generation')
    entry['text'] = request.text
    entry['status'] = request.outcome
    # Only the matching head-mode operation on the committed head clears the
    # gate; history-mode writes never touch the current narration flow.
    if (request.outcome == 'ready' and request.mode == 'head'
            and request.pointId == record['headPointId']):
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
    status = ('missing' if request.pointId in getattr(record, 'missing_narrations', ())
              else entry['status'])
    return {'pointId': request.pointId, 'narrationStatus': status,
            'generation': entry['generation'],
            'text': entry['text'] if status == 'ready' else None}


def handle_narration_delete(store, record, request):
    if request.mode == 'head':
        _check_lease(record, request)
        point_id = record['headPointId']
        entry = _narration_entry(record, point_id)
        _fence_claim(entry, request, 'deleting')
    else:
        point_id, entry = None, None
        for candidate_id, candidate in record['narrations'].items():
            claim = candidate.get('claim')
            if (claim and request.claimToken == claim['claimToken']
                    and request.generation == claim['generation']
                    and claim.get('mode') == request.mode):
                point_id, entry = candidate_id, candidate
                break
        if entry is None:
            _refuse('claim_fenced', 'delete with a superseded or mismatched claim')
        _bind_head_mode(record, _BareRequest({'mode': 'history', 'pointId': point_id}))
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
        _refuse('lease_invalid', 'lease_held', details={'reason': 'lease_held'})
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
        _refuse('lease_invalid', 'unknown lease token or epoch')
    lease['expiresAtEpochMilli'] = _now(store) + DEFAULT_TTL_MILLI
    return {'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch'],
            'expiresAtEpochMilli': lease['expiresAtEpochMilli']}


def handle_lease_release(store, record, request):
    lease = _lease(record)
    if lease is None or request.leaseToken != lease['leaseToken'] \
            or request.fenceEpoch != lease['fenceEpoch']:
        _refuse('lease_invalid', 'unknown lease token or epoch')
    record['lease'] = None
    return {'released': True}


def handle_start_advance(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _ladder(record, 'checkpoint_start_advance', None)
    if record.get('advance') is not None:
        _refuse('phase_invalid', 'an active advance already exists')
    if record['work'] is not None:
        _refuse('phase_invalid', 'a point work is still active')
    if _head_entry(record)['status'] != 'ready':
        _refuse('narration_blocked', 'the head narration is not ready')
    record['advance'] = {'advanceId': request.advanceId, 'inputId': request.inputId,
                         'inputText': request.inputText, 'intentStatus': 'pending'}
    record['round'] = {'roundId': request.roundId, 'trigger': 'player',
                       'order': request.order, 'cursor': 0, 'actedIds': [],
                       'visitedIds': [], 'conclusion': None}
    record['control']['phase'] = 'select_actor'
    record['control']['revision'] += 1
    return {'advanceId': request.advanceId, 'inputId': request.inputId,
            'roundId': request.roundId}


def _point_time_guard(kind, time):
    """Mirror the TimelinePoint kind/time rules at begin so a poisoned work
    cannot surface first as a preview/commit failure."""
    if kind == 'normal':
        if time.boundary != 'elapsed':
            _refuse('request_malformed', 'normal points start rounds with elapsed time')
    elif (time.boundary != 'instant'
            or (kind == 'instant' and time.duration.amount != 0)):
        _refuse('request_malformed',
                'associated points need instant time (zero duration for instant kind)')


def handle_begin_point(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _ladder(record, 'checkpoint_begin_point', None)
    if record['work'] is not None:
        _refuse('phase_invalid', 'a point work is still active')
    if request.pointId == record['rootPointId'] or request.pointId in record['points']:
        _refuse('version_mismatch', 'point id is already committed')
    _point_time_guard(request.kind, request.timeAdvance)
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
        _refuse('version_mismatch', 'group binding differs from the pending group')


def handle_discover_group(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_discover_group', work)
    # Discover carries identities; extend carries TargetSpec objects. Keep
    # None (unconfirmed) distinct from the confirmed empty target set.
    targets = request.targetIds
    work['pendingGroup'] = {
        'groupId': request.groupId, 'sourceId': request.initiatorId,
        'memberIds': [request.initiatorId],
        'targetIds': targets,
        'targetIdsBySource': {request.initiatorId: targets},
        'targetSpecsBySource': {request.initiatorId: None},
        'frontierIds': [], 'closed': False,
        'actionTexts': {request.initiatorId: request.actionText},
    }
    work['timeLocked'] = True
    work['phase'] = 'build_group'
    record['control']['phase'] = 'build_group'
    record['control']['revision'] += 1
    return {'groupId': request.groupId, 'targetIds': targets}


def handle_extend_group(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_extend_group', work)
    _bind_group(record, request)
    group = work['pendingGroup']
    if request.sourceId not in group['memberIds']:
        _refuse('request_malformed', 'target source is not a group member')
    if request.targets is not None:
        if getattr(store, 'persistent', False) and group['actionTexts'][request.sourceId] is None:
            _refuse('request_malformed', 'confirm the member action before its targets')
        if group['targetIdsBySource'][request.sourceId] is not None:
            # A confirmed target set — even the confirmed empty one — is
            # closed evidence; only admission can follow it.
            _refuse('request_malformed', 'targets are already confirmed for this member')
        group['targetIdsBySource'][request.sourceId] = [
            spec.targetId for spec in request.targets]
        group['targetSpecsBySource'][request.sourceId] = [
            {'targetId': spec.targetId, 'triggerKey': spec.triggerKey}
            for spec in request.targets]
        group['targetIds'] = sorted({
            target for targets in group['targetIdsBySource'].values()
            for target in (targets or [])})
    else:
        member = request.admittedMember
        if member.memberId in group['memberIds']:
            if (not getattr(store, 'persistent', False)
                    or group['actionTexts'][member.memberId] is not None or member.actionText is None):
                _refuse('request_malformed', f'{member.memberId} is already a group member')
        else:
            group['memberIds'].append(member.memberId)
            group['targetIdsBySource'][member.memberId] = None
            group['targetSpecsBySource'][member.memberId] = None
        group['actionTexts'][member.memberId] = member.actionText
    if getattr(store, 'persistent', False):
        group['frontierIds'] = sorted(member for member in group['memberIds']
                                     if group['actionTexts'][member] is None
                                     or group['targetIdsBySource'][member] is None)
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
    group = work['pendingGroup']
    if any(group['targetIdsBySource'][member] is None
           for member in group['memberIds']):
        # Closure readiness: the target question must have been answered
        # (extend_group confirms it, empty sets included) before closing.
        _refuse('request_malformed', 'close needs every member target set confirmed first')
    if group['frontierIds']:
        _refuse('request_malformed', 'close requires an empty reaction frontier')
    group['closed'] = True
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
    # The closed group's admitted membership is authoritative: staging freezes
    # exactly those actors, nobody else (round-3 probe: same groupId, member
    # swapped A→B without admission).
    if sorted(candidates.actorIds) != sorted(set(work['pendingGroup']['memberIds'])):
        _refuse('request_malformed',
                'staged actors differ from the admitted closed-group members')
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
    order = record['round']['order']
    cursor = work['working'].cursor
    if cursor >= len(order) or request.slotActorId != order[cursor]:
        _refuse('request_malformed', 'skip must record the current order slot')
    # A confirmed skip is confirmed work: the point time locks in the same
    # transaction (registry note; round-3 probe skipped then retimed).
    work['timeLocked'] = True
    work['working'] = skip_working(work['working'], request.slotActorId, order)
    record['control']['revision'] += 1
    return {'pointId': work['pointId'],
            'working': work['working'].model_dump(mode='json')}


def handle_stage_time_scan(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    work = _work_or_none(record)
    _ladder(record, 'checkpoint_stage_time_scan', work)
    if work['timeScanComplete']:
        _refuse('request_malformed', 'time-scan candidates are already confirmed')
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
        _refuse('phase_invalid', 'an empty point needs its time-scan candidates first')
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
    _point_time_guard(work['kind'], request.timeAdvance)
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


def handle_restore_group_work(store, record, request):
    """The fixture store has no accepted cross-epoch restore references.

    Refuse within restore's frozen error vocabulary after binding authority;
    SQLite's byte-copy and accepted-reference handling remain with A3.
    """
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_work_point(record, request)
    _refuse('frozen_work_missing', 'no active accepted restore source in the fixture store',
            details={'reason': 'source_not_active'})


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
    _bind_chain(record, request)
    work = _work_or_none(record)
    _ladder(record, 'preview_point', work)
    if request.timeAdvance.model_dump(mode='json') != work['timeAdvance']:
        _refuse('version_mismatch', 'preview time differs from the begin reservation')
    round_view = record['round']
    kind = work['kind']
    projection = TimelinePoint.model_validate({
        'worldId': record['worldId'], 'id': request.pointId,
        'sequence': work['baseline']['version'] + 1,
        'kind': kind, 'previousPointId': work['baseline']['headPointId'],
        'roundId': request.roundId, 'advanceId': request.advanceId,
        'trigger': round_view['trigger'] if round_view else 'player',
        # Associated points (instant/linked) carry their predecessor on the
        # projection; only normal points start a fresh chain.
        'linkedFromPointId': None if kind == 'normal' else work['baseline']['headPointId'],
        'timeAdvance': request.timeAdvance.model_dump(mode='json'),
        'entityDeltas': {}})
    return compute_preview(record['state'], projection,
                           list(request.settlementGroups))


def handle_commit_point(store, record, request):
    work = _sealed_prefix(record)
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_chain(record, request)
    _ladder(record, 'commit_point', work)
    sealed_time_advance = work['timeAdvance']
    if hasattr(sealed_time_advance, 'model_dump'):
        sealed_time_advance = sealed_time_advance.model_dump(mode='json')
    verify_point_binding(
        request.point, work['kind'],
        type(request.point.timeAdvance).model_validate(sealed_time_advance))
    if request.pointId != work['pointId']:
        _refuse('version_mismatch', 'commit targets another point than the sealed work')
    if request.point.previousPointId != record['headPointId']:
        _refuse('version_mismatch', 'point chains from another head')
    round_view = record['round']
    # Metadata binds to the stored chain: identities, the round's own trigger
    # and the next sequence number are server facts, not request opinions.
    if (request.point.advanceId != request.advanceId
            or request.point.roundId != request.roundId
            or request.point.sequence != record['version'] + 1
            or request.point.trigger != round_view['trigger']):
        _refuse('version_mismatch', 'commit point metadata differs from the active chain')
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
    if getattr(store, 'persistent', False):
        authority.issue_head_claim(store, record)
    if round_view['cursor'] == len(round_view['order']) and round_view['conclusion'] is None:
        record['control']['phase'] = 'assess_continuation'
    record['control']['revision'] += 1
    return {'pointId': request.pointId, 'version': record['version'],
            'stateDigest': state_digest(new_state)}


def handle_round_conclusion_cancel(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_chain(record, request)
    # The registry names only lease and head narration for cancel — the ladder
    # skips both as opaque, so readiness is explicit here: any phase may
    # cancel (open uncommitted work included, paused included), but the head
    # narration must be ready first.
    if _head_entry(record)['status'] != 'ready':
        _refuse('narration_blocked', 'cancel needs a ready head narration')
    _ladder(record, 'round_conclusion_cancel', _work_or_none(record))
    abandoned = []
    work = _work_or_none(record)
    if work is not None:
        if work['pendingGroup'] is not None:
            abandoned = [work['pendingGroup']['groupId']]
        record['work'] = None
    round_view = record['round']
    round_view['conclusion'] = {
        'kind': 'handback', 'closedBy': 'cancel', 'cancelReason': request.cancelReason}
    record['control']['phase'] = 'complete'
    record['advance'] = None
    record['control']['revision'] += 1
    return {'roundId': request.roundId, 'abandonedGroupIds': abandoned}


def handle_round_conclusion_conclude(store, record, request):
    _check_lease(record, request)
    _bind_expected(record, request)
    _bind_chain(record, request)
    _ladder(record, 'round_conclusion_conclude', _work_or_none(record))
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
        _refuse('version_mismatch', 'unknown point')
    state = cached['state']
    digest = cached['stateDigest']
    if getattr(store, 'persistent', False):
        from app.database.world_repository import LedgerMismatch
        state = store.replay_state(record['worldId'], point_id)
        if state_digest(state) != digest:
            raise LedgerMismatch('Canonical replay differs from the saved state checkpoint')
    # The point's own saved record rides along for narration assembly:
    # historical reads answer per requested point, never the head.
    if point_id == record['rootPointId']:
        previous_point_id = None
        time_advance = None
        entity_deltas = {}
    else:
        point = record['points'][point_id]
        previous_point_id = point.previousPointId
        time_advance = point.timeAdvance.model_dump(mode='json')
        entity_deltas = {entity_id: delta.model_dump(mode='json')
                         for entity_id, delta in point.entityDeltas.items()}
    return {'pointId': point_id, 'version': cached['version'],
            'state': state.model_dump(mode='json'),
            'stateDigest': digest,
            'previousPointId': previous_point_id,
            'timeAdvance': time_advance,
            'entityDeltas': entity_deltas}


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
    points.sort(key=lambda point: point['sequence'])
    if request.after is not None:
        points = [point for point in points if point['sequence'] > request.after]
    return {'points': points[:request.limit]}


def handle_get_context(store, record, request):
    if request.includeRecovery:
        _check_lease(record, request)
    advance = record.get('advance')
    active_input = None
    if advance is not None and advance['intentStatus'] == 'pending':
        active_input = {'advanceId': advance['advanceId'],
                        'inputId': advance['inputId'],
                        'text': advance['inputText']}
    recovery = (store.recovery_view(record, _work_view)
                if request.includeRecovery and getattr(store, 'persistent', False) else None)
    return {**_views(record), 'activeInput': active_input, 'recovery': recovery}


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
    'checkpoint_restore_group_work': handle_restore_group_work,
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

_AUTHORITY_HANDLERS = {
    'lease_acquire': authority.handle_lease_acquire,
    'lease_renew': authority.handle_lease_renew,
    'lease_release': authority.handle_lease_release,
    'narration_claim': authority.handle_narration_claim,
    'narration_claim_renew': authority.handle_narration_renew,
    'narration_submit': authority.handle_narration_submit,
    'narration_delete': authority.handle_narration_delete,
}


class _DeferredRefusal:
    """A gate-only cleanup committed before returning the business refusal."""

    def __init__(self, error):
        self.error = error


def _persistent_gate_entry(store, record, operation, request, custom_handler):
    """Successful replay precedes this step; invalid binding cannot clean a gate."""
    gate_entry = (operation.startswith('checkpoint_') or operation.startswith('round_conclusion_')
                  or operation in ('commit_point', 'create_rolls'))
    if not gate_entry:
        prepare = getattr(store, 'prepare_operation', None)
        if prepare is not None:
            prepare(operation, record, request)
        return
    _check_lease(record, request)
    _bind_expected(record, request)
    if operation in ('commit_point', 'round_conclusion_conclude', 'round_conclusion_cancel'):
        _bind_chain(record, request)
    if hasattr(request, 'pointId') and not custom_handler:
        _bind_work_point(record, request)
    prepare = getattr(store, 'prepare_operation', None)
    if prepare is not None:
        prepare(operation, record, request)
    authority.resolve_gate(store, record)
    if operation not in ('checkpoint_pause', 'checkpoint_resume', 'checkpoint_restore_group_work'):
        if _head_entry(record)['status'] != 'ready':
            _refuse('narration_blocked', 'the head narration is not ready')
        if record['control']['paused'] and operation != 'round_conclusion_cancel':
            _refuse('paused', 'the controller is paused')
    validate = getattr(store, 'validate_operation', None)
    if validate is not None:
        validate(operation, record, request)


def _retain_gate_cleanup(record, before):
    """Keep only the legal lazy cleanup when a computation is gate-blocked."""
    gate = copy.deepcopy(record['control']['gate'])
    reason = record.get('_gateBlockedReason')
    changed = (gate != before['control']['gate'] or reason != before.get('_gateBlockedReason'))
    if changed:
        record.clear()
        record.update(before)
        record['control']['gate'] = gate
        if reason is None:
            record.pop('_gateBlockedReason', None)
        else:
            record['_gateBlockedReason'] = reason
    return changed


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

    def error_response(self, error, operation=None, request_id=None, world_id=None):
        from app.database.world_repository import LedgerMismatch
        try:
            record = self.store.world(world_id) if world_id else None
        except LedgerMismatch:
            # A damaged recovery ledger cannot be read again to decorate its
            # own refusal. The protocol permits an error without state views.
            record = None
        return ErrorResponse.model_validate({
            **_envelope_base(self.store), 'replayed': False,
            'operation': operation, 'requestId': request_id, 'worldId': world_id,
            'error': {'code': error.code, **{key: ERROR_CODES[error.code][key]
                       for key in ('httpStatus', 'retryable', 'clientAction')},
                      'details': error.details},
            **(_views(record) if record is not None else {}),
        }).model_dump(mode='json')

    def execute(self, operation, request_dict):
        spec = OPERATION_BY_NAME[operation]
        if spec.idempotency.scope == 'none':
            return self._execute_scopeless(operation, request_dict, spec)
        model_cls = next(model for model in _ALL_REQUEST_MODELS
                         if model.__name__ == spec.requestSchema)
        allowed_fields = _request_body_fields(model_cls)
        path_fields = {'worldId'} | ({'pointId'} if operation == 'narration_delete' else set())
        if set(request_dict) - allowed_fields - path_fields:
            _refuse('request_malformed', 'unknown request fields')
        body = {key: value for key, value in request_dict.items()
                if key in allowed_fields}
        try:
            request = model_cls.model_validate(body)
        except ValidationError as error:
            raise ServiceRefusal('request_malformed', str(error)[:400]) from error
        if isinstance(request, RootModel):
            request = request.root
        digest = canonical_digest(
            request_projection(operation, request.model_dump(mode='json')))
        if operation == 'create_world':
            return self._execute_create(operation, request, digest)
        # worldId may arrive as a path parameter the body schema forbids
        # (lease_release); the raw dict remains the routing authority.
        return self._execute_write(operation, request, digest,
                                   request_dict.get('worldId'),
                                   request_dict.get('pointId') if operation == 'narration_delete' else None)

    # -- scope-none operations: reads plus the stateless preview ------------

    def _execute_scopeless(self, operation, request_dict, spec):
        if operation == 'preview_point':
            if (isinstance(request_dict.get('settlementGroups'), list)
                    and len(request_dict['settlementGroups']) > 32):
                _refuse('preview_budget_exceeded', 'settlement-unit budget exceeded',
                        details={'limit': 'request'})
            compute_clock = getattr(self.store, '_preview_clock', time.perf_counter)
            compute_start = compute_clock()
            try:
                request = PreviewPointRequest.model_validate(request_dict)
            except ValidationError as error:
                raise ServiceRefusal('request_malformed', str(error)[:400]) from error
            record = self._record(request.worldId)
            selection = None
            try:
                if getattr(self.store, 'persistent', False):
                    from .successor import select_operation
                    _bind_expected(record, request)
                    _bind_chain(record, request)
                    selection = select_operation(self.store, record, operation, request)
                if getattr(self.store, 'persistent', False) and _head_entry(record)['status'] != 'ready':
                    _bind_expected(record, request)
                    _bind_work_point(record, request)
                    _bind_chain(record, request)
                    _refuse('narration_blocked', 'the head narration is not ready')
                data = handle_preview_point(self.store, record, request)
            except KernelViolation as error:
                _map_kernel(operation, error)
            finally:
                if selection is not None:
                    from .successor import finish_operation
                    finish_operation(self.store, record, operation, request, None, selection)
            envelope = _compute_envelope(self.store, operation, _views(record), data)
            if compute_clock() - compute_start > getattr(self.store, '_preview_budget_seconds', 2.0):
                _refuse('preview_budget_exceeded', 'preview computation exceeded its time budget',
                        details={'limit': 'compute'})
            return envelope
        request = None
        if spec.requestSchema is not None:
            model_cls = next(model for model in _ALL_REQUEST_MODELS
                             if model.__name__ == spec.requestSchema)
            try:
                query = {key: value for key, value in request_dict.items()
                         if key in model_cls.model_fields}
                request = model_cls.model_validate(query)
            except ValidationError as error:
                raise ServiceRefusal('request_malformed', str(error)[:400]) from error
        else:
            # requestSchema=None reads (narration_get) bind only their path
            # fields; a bare attribute view is enough.
            request = _BareRequest(request_dict)
        if operation == 'get_context' and getattr(self.store, 'persistent', False):
            # Recovery authority, active pointers and original payload must all
            # belong to one database snapshot, including concurrent takeovers.
            from app.database.world_frozen_repository import FrozenWorkError
            from app.database.world_repository import LedgerMismatch
            try:
                with self.store.locked():
                    record = self._record(request_dict.get('worldId'))
                    data = READ_HANDLERS[operation](self.store, record, request)
                    return _context_envelope(self.store, data)
            except FrozenWorkError as error:
                raise ServiceRefusal(error.code, str(error), error.details) from error
            except LedgerMismatch as error:
                raise ServiceRefusal('frozen_work_corrupt', str(error),
                                     {'reason': 'recovery_ledger_mismatch'}) from error
        record = self._record(request_dict.get('worldId'))
        data = READ_HANDLERS[operation](self.store, record, request)
        if operation == 'get_context':
            return _context_envelope(self.store, data)
        return _read_envelope(self.store, record, data)

    # -- body writes ---------------------------------------------------------

    def _record(self, world_id):
        record = self.store.world(world_id) if world_id else None
        if record is None:
            _refuse('version_mismatch', 'unknown world')
        return record

    def _execute_create(self, operation, request, digest):
        # Creation idempotency lives in the store-global table; check, build
        # and insert under one lock acquisition so a concurrent duplicate
        # cannot create a second world.
        with self.store.locked():
            entry = self.store.get_creation(request.requestId)
            if entry is not None:
                if entry['operation'] != operation or entry['digest'] != digest:
                    _refuse('request_id_reused',
                            'same requestId with a different operation or payload')
                views = (_views(self._record(entry['data']['worldId']))
                         if getattr(self.store, 'persistent', False) else entry['views'])
                return _operation_envelope(self.store, operation, request,
                                           views, entry['data'], digest,
                                           replayed=True)
            record, data = handle_create_world(self.store, request)
            views = _views(record)
            _validate_success(operation, _operation_envelope(
                self.store, operation, request, views, data, digest))
            self.store.create_world(data['worldId'], record)
            self.store.note_global(request.requestId, {
                'operation': operation, 'digest': digest, 'data': data,
                'views': views})
        return _operation_envelope(self.store, operation, request, views,
                                   data, digest)

    def _execute_write(self, operation, request, digest, world_id, path_point_id=None):
        persistent = getattr(self.store, 'persistent', False)
        custom_handler = (self.store.operation_handler(operation) if persistent else None)
        operation_handler = (custom_handler or (_AUTHORITY_HANDLERS.get(operation) if persistent else None)
                             or WRITE_HANDLERS.get(operation))
        if operation_handler is None:
            self._record(world_id)
            _refuse('phase_invalid', 'operation requires the A3 store',
                    details={'reason': 'fixture_store_unsupported'})

        def handler(snapshot):
            # The idempotency decision runs inside the transaction: a request
            # that races a duplicate replays the stored payload instead of
            # double-running the handler.
            entry = snapshot['idempotency'].get(request.requestId)
            if entry is not None:
                if (entry['operation'] != operation or entry['digest'] != digest
                        or entry.get('pathPointId') != path_point_id):
                    _refuse('request_id_reused',
                            'same requestId with a different operation or payload')
                views = _views(snapshot) if persistent else entry['views']
                return entry['data'], views, True
            before = copy.deepcopy(snapshot) if persistent else None
            try:
                if persistent:
                    _persistent_gate_entry(self.store, snapshot, operation, request, custom_handler)
                if operation == 'narration_delete' and path_point_id is not None:
                    bound = _BareRequest({**request.model_dump(mode='json'),
                                          'pointId': path_point_id})
                    if persistent:
                        authority.validate_claim(self.store, snapshot, bound, path_point_id)
                        request_for_handler = bound
                    else:
                        _bind_head_mode(snapshot, bound)
                        _fence_claim(_narration_entry(snapshot, path_point_id), request,
                                     'deleting narration at this path')
                        request_for_handler = request
                else:
                    request_for_handler = request
                data = operation_handler(self.store, snapshot, request_for_handler)
                finish = getattr(self.store, 'finish_operation', None) if persistent else None
                if finish is not None:
                    finish(operation, snapshot, request, data)
            except KernelViolation as error:
                abort = getattr(self.store, 'abort_operation', None) if persistent else None
                if abort is not None:
                    abort(operation, snapshot, request)
                _map_kernel(operation, error)
            except ServiceRefusal as error:
                abort = getattr(self.store, 'abort_operation', None) if persistent else None
                if abort is not None:
                    abort(operation, snapshot, request)
                if (persistent and error.code == 'narration_blocked'
                        and _retain_gate_cleanup(snapshot, before)):
                    return _DeferredRefusal(error)
                raise
            # Snapshots are built and validated while the copy is still
            # discardable; the response then reflects exactly this
            # transaction, never a later interleaved one.
            views = _views(snapshot)
            _validate_success(operation, _operation_envelope(
                self.store, operation, request, views, data, digest))
            stored = ({key: value for key, value in data.items() if key != 'claimToken'}
                      if operation == 'narration_claim' else data)
            snapshot['idempotency'][request.requestId] = {
                'operation': operation, 'digest': digest, 'data': stored,
                'views': views, 'pathPointId': path_point_id}
            return data, views, False

        from app.database.world_repository import LedgerMismatch
        try:
            result = self.store.transact(world_id, handler)
        except WorldNotFound:
            _refuse('version_mismatch', 'unknown world')
        except LedgerMismatch as error:
            from app.database.world_frozen_repository import FrozenWorkError
            if operation == 'checkpoint_restore_group_work':
                if isinstance(error, FrozenWorkError):
                    raise ServiceRefusal(error.code, str(error), error.details) from error
                raise ServiceRefusal('frozen_work_corrupt', str(error),
                                     {'reason': 'recovery_ledger_mismatch'}) from error
            raise
        if isinstance(result, _DeferredRefusal):
            raise result.error
        data, views, replayed = result
        return _operation_envelope(self.store, operation, request, views,
                                   data, digest, replayed=replayed)
