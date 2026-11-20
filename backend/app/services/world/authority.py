"""A3 transaction-local lease and narration authority.

The caller owns the SQLite transaction and checks successful request replay
before invoking these functions. Fixture handlers intentionally keep their A2
semantics; the persistent service opts into this module. No clock decision or
credential is delegated to the browser.
"""
import secrets

from app.schemas.world.contracts import MAX_SAFE

LEASE_TTL_MILLI = 120_000
CLAIM_TTL_MILLI = 180_000


def _refuse(code, detail, details=None):
    # Deferred import keeps the control service free to import this module.
    from .control import ServiceRefusal
    raise ServiceRefusal(code, detail, details)


def _expiry(store, kind, issued_at=None):
    now = store.clock_milli()
    default = LEASE_TTL_MILLI if kind == 'lease' else CLAIM_TTL_MILLI
    ttl = getattr(store, f'{kind}_ttl_milli', default)
    expires = now + ttl
    if ttl <= 0 or expires > MAX_SAFE or expires <= (issued_at or now):
        _refuse('version_mismatch', 'authority clock or lifetime is outside the supported range')
    return expires


def _token(kind):
    return f'{kind}_{secrets.token_hex(32)}'


def _clear_gate(record):
    record['control']['gate'] = {
        'status': 'none', 'generation': None,
        'issuedAtEpochMilli': None, 'expiresAtEpochMilli': None,
    }


def check_lease(store, record, request):
    """Fence every new write using the live server clock and retained epoch."""
    lease = record.get('lease')
    epoch = record.get('_leaseEpoch', (lease or {}).get('fenceEpoch', 0))
    if request.fenceEpoch != epoch:
        _refuse('stale_epoch', 'lease epoch has moved on')
    if (lease is None or request.leaseToken != lease['leaseToken']
            or store.clock_milli() >= lease['expiresAtEpochMilli']):
        _refuse('lease_invalid', 'unknown, released or expired lease token')
    return lease


def initialize_world(store, record):
    """Called before the new world's single creation transaction commits."""
    record['_leaseEpoch'] = 1
    record['lease'] = {
        'leaseToken': _token('lease'), 'fenceEpoch': 1,
        'expiresAtEpochMilli': _expiry(store, 'lease'),
    }
    issue_head_claim(store, record)


def _issue_claim(store, record, point_id, mode, generation):
    if generation > MAX_SAFE:
        _refuse('version_mismatch', 'narration generation exhausted')
    now = store.clock_milli()
    claim = {
        'claimToken': _token('claim'), 'generation': generation, 'mode': mode,
        'fenceEpoch': record['lease']['fenceEpoch'] if mode == 'head' else None,
        'issuedAtEpochMilli': now, 'expiresAtEpochMilli': _expiry(store, 'claim', now),
    }
    entry = record['narrations'][point_id]
    entry.update(status='pending', text=None, generation=generation, claim=claim)
    if hasattr(record, 'missing_narrations'):
        record.missing_narrations.discard(point_id)
    if mode == 'head':
        record['control']['gate'] = {
            'status': 'pending', 'generation': generation,
            'issuedAtEpochMilli': now, 'expiresAtEpochMilli': claim['expiresAtEpochMilli'],
        }
        record.pop('_gateBlockedReason', None)
    return claim


def issue_head_claim(store, record, generation=1):
    """The creating point transaction issues generation 1 and its gate."""
    return _issue_claim(store, record, record['headPointId'], 'head', generation)


def _entry(record, point_id):
    entry = record['narrations'].get(point_id)
    if entry is None:
        _refuse('version_mismatch', 'narration requires a committed point')
    return entry


def _bind_mode(store, record, request, point_id):
    if request.mode == 'head':
        check_lease(store, record, request)
        if point_id != record['headPointId']:
            _refuse('version_mismatch', 'head narration targets another point')
    elif point_id == record['headPointId']:
        _refuse('claim_fenced', 'history narration cannot target the current head')


def _claim_problem(store, record, claim):
    if claim is None:
        return 'claim_fenced'
    if claim['mode'] == 'head':
        lease = record.get('lease')
        if lease is None or claim['fenceEpoch'] != lease['fenceEpoch']:
            return 'claim_fenced'
    if store.clock_milli() >= claim['expiresAtEpochMilli']:
        return 'claim_expired'
    return None


def _match_current(claim, current):
    return (claim is not None and current.claimToken == claim['claimToken']
            and current.generation == claim['generation']
            and current.issuedAtEpochMilli == claim['issuedAtEpochMilli'])


def _fence_claim(store, record, entry, request):
    if getattr(request, 'pointId', None) in getattr(record, 'missing_narrations', ()):
        _refuse('claim_fenced', 'missing cache requires a new narration generation')
    claim = entry.get('claim')
    if (not _match_current(claim, request)
            or claim['mode'] != request.mode
            or (request.mode == 'head' and claim['fenceEpoch'] != request.fenceEpoch)):
        _refuse('claim_fenced', 'claim identity, issue time, mode or epoch has moved on')
    problem = _claim_problem(store, record, claim)
    if problem is not None:
        _refuse(problem, 'claim authority is no longer valid')
    return claim


def validate_claim(store, record, request, point_id):
    """Bind a DELETE path before resolving its claim or touching its cache."""
    _bind_mode(store, record, request, point_id)
    return _fence_claim(store, record, _entry(record, point_id), request)


def resolve_gate(store, record):
    """Clean only an invalid matching head gate; never change revision.

    A ready cache survives its claim's TTL. Invalid pending authority is
    remembered after clearing the gate so a resume cannot authorize compute.
    """
    gate = record['control']['gate']
    entry = _entry(record, record['headPointId'])
    if (entry['status'] == 'ready'
            and record['headPointId'] not in getattr(record, 'missing_narrations', ())):
        _clear_gate(record)
        record.pop('_gateBlockedReason', None)
        return None
    if gate['status'] != 'pending':
        return record.get('_gateBlockedReason')
    claim = entry.get('claim')
    problem = _claim_problem(store, record, claim)
    if claim is not None and (gate['generation'] != claim['generation']
                             or gate['issuedAtEpochMilli'] != claim['issuedAtEpochMilli']):
        problem = 'claim_fenced'
    if problem is not None:
        _clear_gate(record)
        record['_gateBlockedReason'] = problem
    return problem


def blocked_reasons(store, record):
    """Additional server-time barriers; this projection never mutates state."""
    reasons = set()
    entry = _entry(record, record['headPointId'])
    if entry['status'] != 'ready':
        problem = record.get('_gateBlockedReason') or _claim_problem(
            store, record, entry.get('claim'))
        if problem is not None:
            reasons.add(problem)
    lease = record.get('lease')
    if lease is None or store.clock_milli() >= lease['expiresAtEpochMilli']:
        reasons.add('lease_invalid')
    if record['control']['phase'] == 'complete':
        reasons.add('phase_not_computable')
    return sorted(reasons)


def handle_lease_acquire(store, record, request):
    lease = record.get('lease')
    if lease is not None and store.clock_milli() < lease['expiresAtEpochMilli']:
        _refuse('lease_invalid', 'lease_held', {'reason': 'lease_held'})
    fence = max(record.get('_leaseEpoch', 0), (lease or {}).get('fenceEpoch', 0)) + 1
    if fence > MAX_SAFE:
        _refuse('version_mismatch', 'lease epoch exhausted')
    grant = {
        'holderId': request.holderId, 'leaseToken': _token('lease'),
        'fenceEpoch': fence, 'expiresAtEpochMilli': _expiry(store, 'lease'),
    }
    record['_leaseEpoch'] = fence
    record['lease'] = grant
    return dict(grant)


def handle_lease_renew(store, record, request):
    lease = check_lease(store, record, request)
    lease['expiresAtEpochMilli'] = max(lease['expiresAtEpochMilli'], _expiry(store, 'lease'))
    return {key: lease[key] for key in ('leaseToken', 'fenceEpoch', 'expiresAtEpochMilli')}


def handle_lease_release(store, record, request):
    lease = check_lease(store, record, request)
    record['_leaseEpoch'] = lease['fenceEpoch']
    record['lease'] = None
    return {'released': True}


def handle_narration_claim(store, record, request):
    _bind_mode(store, record, request, request.pointId)
    entry = _entry(record, request.pointId)
    claim = entry.get('claim')
    if request.currentClaim is not None and not _match_current(claim, request.currentClaim):
        _refuse('claim_fenced', 'caller holds a superseded claim')
    problem = _claim_problem(store, record, claim)
    if (claim is not None and request.mode == 'history' and claim['mode'] == 'history'
            and problem is None and request.currentClaim is None):
        _refuse('claim_fenced', 'retrieving a live history claim requires its current authority')
    rotate = (claim is not None and (claim['mode'] != request.mode or problem is not None
                                    or entry['status'] == 'failed'
                                    or request.pointId in getattr(record, 'missing_narrations', ())))
    if claim is None or rotate:
        generation = entry['generation'] + (1 if rotate else 0)
        claim = _issue_claim(store, record, request.pointId, request.mode, generation)
    if request.mode == 'head':
        resolve_gate(store, record)
    return {'pointId': request.pointId, 'mode': request.mode, **claim}


def handle_narration_renew(store, record, request):
    _bind_mode(store, record, request, request.pointId)
    entry = _entry(record, request.pointId)
    claim = _fence_claim(store, record, entry, request)
    claim['expiresAtEpochMilli'] = max(claim['expiresAtEpochMilli'],
                                     _expiry(store, 'claim', claim['issuedAtEpochMilli']))
    if request.mode == 'head' and record['control']['gate']['status'] == 'pending':
        record['control']['gate']['expiresAtEpochMilli'] = claim['expiresAtEpochMilli']
    return {'pointId': request.pointId, 'mode': request.mode,
            **{key: claim[key] for key in ('generation', 'fenceEpoch',
                                          'issuedAtEpochMilli', 'expiresAtEpochMilli')}}


def handle_narration_submit(store, record, request):
    _bind_mode(store, record, request, request.pointId)
    entry = _entry(record, request.pointId)
    _fence_claim(store, record, entry, request)
    if entry['status'] == 'ready' and (request.outcome != 'ready' or request.text != entry['text']):
        _refuse('request_malformed', 'narration text is immutable within a generation')
    entry.update(status=request.outcome, text=request.text)
    if request.mode == 'head':
        _clear_gate(record)
        record.pop('_gateBlockedReason', None)
    return {'pointId': request.pointId, 'narrationStatus': request.outcome,
            'generation': request.generation}


def handle_narration_delete(store, record, request):
    point_id = getattr(request, 'pointId', None)
    if point_id is None and request.mode == 'head':
        point_id = record['headPointId']
    if point_id is None:
        point_id = next((key for key, entry in record['narrations'].items()
                         if _match_current(entry.get('claim'), request)), None)
    if point_id is None:
        _refuse('claim_fenced', 'delete has no matching point claim')
    _bind_mode(store, record, request, point_id)
    entry = _entry(record, point_id)
    _fence_claim(store, record, entry, request)
    generation = entry['generation']
    if generation >= MAX_SAFE:
        _refuse('version_mismatch', 'narration generation exhausted')
    entry.update(status='missing', text=None, generation=generation + 1, claim=None)
    if request.mode == 'head':
        _issue_claim(store, record, point_id, 'head', generation + 1)
        entry['status'] = 'missing'
    return {'pointId': point_id, 'narrationStatus': 'missing',
            'invalidatedGeneration': generation}
