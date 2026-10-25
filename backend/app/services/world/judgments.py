"""Server-owned stable identities, dice and frozen admission decisions."""
import secrets

from app.database.world_judgment_repository import (
    ROLL_COLUMNS, _validated_baseline, require_allocated, roll_outcome,
)
from app.database.world_repository import wire
from app.schemas.world.canonical import canonical_digest


def _refuse(code, detail):
    from .control import ServiceRefusal
    raise ServiceRefusal(code, detail)


def _connection(store):
    connection = getattr(getattr(store, '_local', None), 'connection', None)
    if connection is None:
        raise RuntimeError('Judgments require the active SQLite world transaction')
    return connection


def allocate_ids(store, record, request):
    """A slot's kind and scope are fixed as well as its identity."""
    from .authority import check_lease
    check_lease(store, record, request)
    allocated = []
    bucket = record.setdefault('_allocationMetadata', {}).setdefault(request.allocationKey, {})
    replay = record.setdefault('allocations', {}).setdefault(request.allocationKey, {})
    for slot in request.slots:
        scope = slot.scope
        previous = bucket.get(slot.slotKey)
        if previous is not None:
            if (previous['kind'], previous['scope']) != (slot.kind, scope):
                _refuse('request_malformed', 'allocation slot kind and scope are immutable')
            identity = previous['id']
        else:
            identity = store.next_id(slot.kind)
            bucket[slot.slotKey] = dict(kind=slot.kind, scope=scope, id=identity)
            replay[(scope, slot.slotKey)] = identity
        allocated.append(dict(slotKey=slot.slotKey, id=identity))
    return {'allocations': allocated}


def validate_identity_bindings(connection, record, operation, request):
    """New persistent identities must come from typed world allocation slots."""
    world = record['worldId']
    round_id = (record.get('round') or {}).get('roundId')
    advance_id = (record.get('advance') or {}).get('advanceId')
    point_id = getattr(request, 'pointId', None)
    group_id = getattr(request, 'groupId', None)
    scope = tuple(value for value in (round_id, advance_id, point_id, group_id) if value)
    if operation == 'checkpoint_start_advance':
        if set(request.order) != set(record['state'].characters):
            _refuse('request_malformed', 'a player round must freeze the complete character roster')
        for name, kind in (('advanceId', 'advance'), ('inputId', 'input'), ('roundId', 'round')):
            require_allocated(connection, world, getattr(request, name), kind,
                              (request.advanceId, request.roundId))
        for table, column, identity in (('world_advances', 'id', request.advanceId),
                                       ('world_advances', 'input_id', request.inputId),
                                       ('world_rounds', 'id', request.roundId)):
            if connection.execute(f'SELECT 1 FROM {table} WHERE world_id=? AND {column}=?',
                                  (world, identity)).fetchone():
                _refuse('request_malformed', 'allocated chain identity has already been used')
    elif operation == 'checkpoint_begin_point':
        require_allocated(connection, world, request.pointId, 'point', scope)
        prior = connection.execute('SELECT 1 FROM world_points WHERE world_id=? AND round_id=?',
                                   (world, round_id)).fetchone()
        if (prior is None and request.kind != 'normal') or (prior is not None and request.kind == 'normal'):
            _refuse('request_malformed', 'point kind does not match its first or associated round position')
    elif operation == 'checkpoint_discover_group':
        work = record.get('work')
        cursor = work['working'].cursor if work else 0
        order = record['round']['order']
        if cursor >= len(order) or request.initiatorId != order[cursor]:
            _refuse('request_malformed', 'group initiator is not the next frozen character slot')
        require_allocated(connection, world, request.groupId, 'group', scope)
        if connection.execute('SELECT 1 FROM world_groups WHERE world_id=? AND id=?',
                              (world, request.groupId)).fetchone():
            _refuse('request_malformed', 'allocated group identity has already been used')
    elif operation == 'checkpoint_extend_group' and request.targets is not None:
        for target in request.targets:
            require_allocated(connection, world, target.triggerKey, 'trigger', scope)
    elif operation == 'round_conclusion_conclude' and request.conclusion.kind == 'continue':
        if not set(request.conclusion.candidateCharacterIds) <= set(record['state'].characters):
            _refuse('request_malformed', 'automatic candidates must be registered characters')
        require_allocated(connection, world, request.conclusion.nextRoundId, 'round', scope)
        if connection.execute('SELECT 1 FROM world_rounds WHERE world_id=? AND id=?',
                              (world, request.conclusion.nextRoundId)).fetchone():
            _refuse('request_malformed', 'automatic round identity has already been used')
    candidates = getattr(request, 'candidates', None)
    if candidates is not None:
        for changes in (*candidates.appearances.values(), *candidates.personalities.values()):
            for change in changes:
                require_allocated(connection, world, change.id, 'change', scope)
        for tasks in candidates.subtasksAdded.values():
            for task in tasks:
                require_allocated(connection, world, task.id, 'task', scope)


def _baseline(connection, record, work, group):
    from app.database.world_frozen_repository import _input_hash
    # All members share the input before this group, rather than a new state
    # assembled after individual members have been admitted.
    return dict(
        ruleVersion='reaction-eligibility-v1', worldId=record['worldId'],
        pointId=work['pointId'], roundId=record['round']['roundId'],
        advanceId=record['advance']['advanceId'], groupId=group['groupId'],
        inputProjectionHash=_input_hash(record, work, group['groupId']),
        baseline=work['baseline'], timeAdvance=work['timeAdvance'],
        workingActedIds=sorted(work['working'].actedIds),
        characterIds=sorted(record['state'].characters),
    )


def create_rolls(store, record, request):
    """Insert final roll+eligibility once; business-key retries never resample.

    The outer handler validates live authority, binding, gate and phase first.
    The private RNG/fixture configuration is test/server input, never wire data.
    """
    from app.database.world_frozen_repository import confirmed_targets
    connection = _connection(store)
    work = record.get('work')
    group = work.get('pendingGroup') if work else None
    if group is None or not work['timeLocked'] or group['closed']:
        _refuse('phase_invalid', 'rolls require the active open group with locked time')
    world = record['worldId']
    output = []
    for spec in request.rolls:
        if (spec.advanceId != record['advance']['advanceId']
                or spec.roundId != record['round']['roundId'] or spec.groupId != group['groupId']):
            _refuse('version_mismatch', 'judgment is outside the active chain or group')
        if spec.sourceId not in group['memberIds'] or spec.targetId not in record['state'].characters:
            _refuse('request_malformed', 'judgment source or target is not an active world character')
        targets = confirmed_targets(connection, world, work['pointId'], group, spec.sourceId)
        if targets is None or {'targetId': spec.targetId, 'triggerKey': spec.triggerKey} not in targets:
            _refuse('request_malformed', 'judgment does not name a confirmed complete target set')
        require_allocated(connection, world, spec.triggerKey, 'trigger',
                          (group['groupId'], record['round']['roundId'], work['pointId']))
        key = (world, spec.roundId, spec.groupId, spec.sourceId, spec.targetId, spec.triggerKey)
        row = connection.execute('SELECT ' + ','.join(ROLL_COLUMNS) + ''' FROM world_rolls
            WHERE world_id=? AND round_id=? AND group_id=? AND source_id=? AND target_id=? AND trigger_key=?''',
            key).fetchone()
        if row is not None:
            if (row[2], row[4], row[9], row[11]) != (work['pointId'], spec.advanceId, spec.ruleVersion, spec.target):
                _refuse('request_malformed', 'a fixed judgment cannot change its rule or threshold')
            _validated_baseline(connection, row)
            output.append(roll_outcome(row))
            continue
        baseline = _baseline(connection, record, work, group)
        if spec.ruleVersion == 'reaction-fixture-v1':
            fixed = getattr(store, '_roll_fixtures', {}).get(key)
            if fixed is None or fixed['target'] != spec.target:
                _refuse('request_malformed', 'fixture rule is not configured by this server')
            result = fixed['result']
        else:
            result = getattr(store, '_roll_rng', lambda: secrets.randbelow(20) + 1)()
        if type(result) is not int or not 1 <= result <= 20:
            raise ValueError('Server roll generator must produce an integer in [1,20]')
        eligible = spec.targetId not in baseline['workingActedIds']
        identity = store.next_id('roll')
        values = (world, identity, work['pointId'], spec.roundId, spec.advanceId, spec.groupId,
                  spec.sourceId, spec.targetId, spec.triggerKey, spec.ruleVersion, result,
                  spec.target, canonical_digest(baseline), int(eligible), int(eligible and result >= spec.target))
        connection.execute('INSERT INTO world_rolls VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', values)
        connection.execute('INSERT INTO world_roll_baselines VALUES(?,?,?)', (world, identity, wire(baseline)))
        record.setdefault('_judgmentIds', []).append(identity)
        outcome = roll_outcome(values)
        record.setdefault('_judgmentDigests', {})[identity] = canonical_digest(outcome)
        output.append(outcome)
    return {'rolls': output}
