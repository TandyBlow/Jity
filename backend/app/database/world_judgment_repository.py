"""Immutable server judgments and typed, stable allocation slots.

All functions use the caller's existing SQLite transaction. A roll and its
eligibility snapshot are written together; no intermediate admission exists.
"""
import json

from app.database.world_repository import LedgerMismatch, wire
from app.schemas.world.canonical import canonical_digest
from app.schemas.world.v2.requests import RollOutcome


def _refuse(code, detail):
    from app.services.world.control import ServiceRefusal
    raise ServiceRefusal(code, detail)


def initialize_judgment_schema(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS world_roll_baselines (
        world_id TEXT NOT NULL, roll_id TEXT NOT NULL,
        baseline_json TEXT NOT NULL CHECK(json_valid(baseline_json)),
        PRIMARY KEY(world_id,roll_id),
        FOREIGN KEY(world_id,roll_id) REFERENCES world_rolls(world_id,id)
    ) STRICT''')
    connection.execute('''CREATE TRIGGER IF NOT EXISTS roll_baseline_final
        BEFORE UPDATE ON world_roll_baselines
        BEGIN SELECT RAISE(ABORT,'roll_baseline_is_final'); END''')
    connection.execute('''CREATE TRIGGER IF NOT EXISTS allocation_final
        BEFORE UPDATE ON world_id_allocations
        BEGIN SELECT RAISE(ABORT,'allocation_is_final'); END''')


def save_allocations(connection, before, record):
    old = (before or {}).get('_allocationMetadata', {})
    current = record.get('_allocationMetadata', {})
    for key, slots in old.items():
        for slot, value in slots.items():
            if current.get(key, {}).get(slot) != value:
                raise LedgerMismatch('Allocated identity slots cannot be removed or rewritten')
    for key, slots in current.items():
        for slot, value in slots.items():
            if old.get(key, {}).get(slot) == value:
                continue
            expected = (record['worldId'], key, slot, value['kind'], value['id'], wire(value['scope']))
            row = connection.execute('''SELECT world_id,allocation_key,slot_key,kind,allocated_id,scope_json
                FROM world_id_allocations WHERE world_id=? AND allocation_key=? AND slot_key=?''',
                expected[:3]).fetchone()
            if row is None:
                connection.execute('INSERT INTO world_id_allocations VALUES(?,?,?,?,?,?)', expected)
            elif row != expected:
                raise LedgerMismatch('Allocation slot differs from its immutable identity')


def require_allocated(connection, world, identity, kind, scope=None):
    """Scope None is unscoped; otherwise a caller may narrow a global ID."""
    row = connection.execute('''SELECT kind,scope_json FROM world_id_allocations
        WHERE world_id=? AND allocated_id=?''', (world, identity)).fetchone()
    if row is None or row[0] != kind:
        _refuse('request_malformed', f'{kind} identity was not allocated by this world')
    allocated_scope = json.loads(row[1])
    allowed = scope if isinstance(scope, (set, tuple, list)) else (scope,)
    if allocated_scope is not None and allocated_scope not in allowed:
        _refuse('request_malformed', 'allocated identity belongs to another scope')


ROLL_COLUMNS = ('world_id', 'id', 'point_id', 'round_id', 'advance_id', 'group_id',
                'source_id', 'target_id', 'trigger_key', 'rule_version', 'result',
                'target', 'eligibility_digest', 'eligible', 'admitted')


def roll_outcome(row):
    value = dict(zip(ROLL_COLUMNS, row)) if not isinstance(row, dict) else row
    return RollOutcome.model_validate(dict(
        rollId=value['id'], groupId=value['group_id'], sourceId=value['source_id'],
        targetId=value['target_id'], triggerKey=value['trigger_key'],
        ruleVersion=value['rule_version'], target=value['target'], result=value['result'],
        eligibilityBaselineDigest=value['eligibility_digest'],
        eligible=bool(value['eligible']), admitted=bool(value['admitted']),
    )).model_dump(mode='json')


def _validated_baseline(connection, row, cache=None):
    from app.database.world_frozen_repository import FrozenWorkError
    value = dict(zip(ROLL_COLUMNS, row))
    baseline_row = (cache['baselines'].get(value['id']) if cache is not None else
        connection.execute('''SELECT baseline_json FROM world_roll_baselines
            WHERE world_id=? AND roll_id=?''', (value['world_id'], value['id'])).fetchone())
    if baseline_row is None:
        raise FrozenWorkError('frozen_work_missing', 'Judgment eligibility baseline is missing')
    try:
        baseline = json.loads(baseline_row[0])
        if canonical_digest(baseline) != value['eligibility_digest']:
            raise ValueError('eligibility digest differs')
        for column, key in (('world_id', 'worldId'), ('point_id', 'pointId'),
                            ('round_id', 'roundId'), ('advance_id', 'advanceId'),
                            ('group_id', 'groupId')):
            if baseline[key] != value[column]:
                raise ValueError('eligibility identity differs')
        if baseline['ruleVersion'] != 'reaction-eligibility-v1':
            raise ValueError('unknown eligibility rule')
        eligible = value['target_id'] in baseline['characterIds'] \
            and value['target_id'] not in baseline['workingActedIds'] \
            and value['target_id'] not in baseline.get('groupAcceptedIds', [])
        if bool(value['eligible']) != eligible:
            raise ValueError('eligibility differs from the frozen working progress')
        roll_outcome(value)
        work = (cache['work'].get(value['point_id']) if cache is not None else
            connection.execute('''SELECT round_id,advance_id,time_json,baseline_point_id,
                baseline_version,baseline_digest FROM world_point_work
                WHERE world_id=? AND point_id=?''', (value['world_id'], value['point_id'])).fetchone())
        if work is None or work != (value['round_id'], value['advance_id'],
                wire(baseline['timeAdvance']), baseline['baseline']['headPointId'],
                baseline['baseline']['version'], baseline['baseline']['stateDigest']):
            raise ValueError('judgment time or baseline was rebound')
        accepted = (cache['accepted'].get((value['point_id'], value['group_id']), []) if cache is not None else
            connection.execute('''SELECT DISTINCT input_projection_hash FROM world_accepted_work
                WHERE world_id=? AND point_id=? AND group_id=?''',
                (value['world_id'], value['point_id'], value['group_id'])).fetchall())
        if any(item[0] != baseline['inputProjectionHash'] for item in accepted):
            raise ValueError('accepted group input differs from the judgment baseline')
    except (KeyError, TypeError, ValueError) as error:
        raise FrozenWorkError('frozen_work_corrupt', 'Judgment differs from its frozen eligibility snapshot') from error
    return baseline


def validate_admission(connection, record, request):
    """Never trust browser-supplied rollRef/admittedMember as authorization."""
    member = request.admittedMember
    if member is None:
        return
    work, world = record.get('work'), record['worldId']
    group = work.get('pendingGroup') if work else None
    if group is None or request.groupId != group['groupId'] or request.pointId != work['pointId']:
        _refuse('version_mismatch', 'admission is outside the active group')
    seen = set()
    for reference in member.rollRefs:
        key = (reference.sourceId, reference.targetId, reference.triggerKey, reference.rollId)
        if key in seen or reference.targetId != member.memberId or reference.sourceId != request.sourceId:
            _refuse('request_malformed', 'admission references duplicate or unrelated judgments')
        seen.add(key)
        row = connection.execute('SELECT ' + ','.join(ROLL_COLUMNS) + ''' FROM world_rolls
            WHERE world_id=? AND id=?''', (world, reference.rollId)).fetchone()
        if row is None:
            _refuse('request_malformed', 'admission judgment does not exist')
        value = dict(zip(ROLL_COLUMNS, row))
        if (value['point_id'] != work['pointId'] or value['group_id'] != group['groupId']
                or value['source_id'] != reference.sourceId or value['target_id'] != reference.targetId
                or value['trigger_key'] != reference.triggerKey or not value['admitted']
                or reference.sourceId not in group['memberIds']):
            _refuse('request_malformed', 'judgment does not authorize this member admission')
        _validated_baseline(connection, row)


def validate_group_closure(connection, record, request):
    from app.database.world_frozen_repository import confirmed_targets
    work, world = record.get('work'), record['worldId']
    group = work.get('pendingGroup') if work else None
    if group is None or request.groupId != group['groupId'] or request.pointId != work['pointId']:
        _refuse('version_mismatch', 'closure is outside the active group')
    for source in group['memberIds']:
        targets = confirmed_targets(connection, world, work['pointId'], group, source)
        if targets is None:
            _refuse('request_malformed', 'group member targets are still unconfirmed')
        for target in targets:
            row = connection.execute('SELECT ' + ','.join(ROLL_COLUMNS) + ''' FROM world_rolls
                WHERE world_id=? AND round_id=? AND group_id=? AND source_id=?
                  AND target_id=? AND trigger_key=?''', (world, record['round']['roundId'],
                group['groupId'], source, target['targetId'], target['triggerKey'])).fetchone()
            if row is None:
                _refuse('request_malformed', 'group cannot close before every confirmed relation is judged')
            _validated_baseline(connection, row)
            value = dict(zip(ROLL_COLUMNS, row))
            if value['admitted'] and value['target_id'] not in group['memberIds']:
                _refuse('request_malformed', 'group cannot close before an admitted member is saved')


def check_judgments(connection, record):
    from app.database.world_frozen_repository import FrozenWorkError
    world = record['worldId']
    expected = {(key, slot, item['kind'], item['id'], wire(item['scope']))
                for key, slots in record.get('_allocationMetadata', {}).items()
                for slot, item in slots.items()}
    actual = set(connection.execute('''SELECT allocation_key,slot_key,kind,allocated_id,scope_json
        FROM world_id_allocations WHERE world_id=?''', (world,)).fetchall())
    if actual != expected:
        raise LedgerMismatch('Typed allocation ledger differs from its saved slot bindings')
    legacy = record.get('allocations', {})
    for key, slots in record.get('_allocationMetadata', {}).items():
        for slot, item in slots.items():
            if legacy.get(key, {}).get((item['scope'], slot)) != item['id']:
                raise LedgerMismatch('Allocation replay binding differs from the typed ledger')
    rows = connection.execute('SELECT ' + ','.join(ROLL_COLUMNS) + ' FROM world_rolls WHERE world_id=?',
                              (world,)).fetchall()
    ids = {row[1] for row in rows}
    expected_ids = set(record.get('_judgmentIds', []))
    if ids != expected_ids:
        raise FrozenWorkError('frozen_work_missing' if expected_ids - ids else 'frozen_work_corrupt',
                              'Immutable judgment identities differ from their saved bindings')
    digests = record.get('_judgmentDigests', {})
    try:
        if ids != set(digests) or any(canonical_digest(roll_outcome(row)) != digests[row[1]] for row in rows):
            raise ValueError('outcome hash differs')
    except (TypeError, ValueError) as error:
        raise FrozenWorkError('frozen_work_corrupt',
                              'Immutable judgment results differ from their saved outcome hashes') from error
    baselines = {row[0]: row[1:] for row in connection.execute(
        'SELECT roll_id,baseline_json FROM world_roll_baselines WHERE world_id=?', (world,))}
    if ids != set(baselines):
        raise FrozenWorkError('frozen_work_missing' if ids - set(baselines) else 'frozen_work_corrupt',
                              'Judgment rows and eligibility snapshots differ')
    if not rows:
        return
    # Keep full historical checks while bounding database round trips.
    work = {row[0]: row[1:] for row in connection.execute('''SELECT point_id,round_id,advance_id,
        time_json,baseline_point_id,baseline_version,baseline_digest
        FROM world_point_work WHERE world_id=?''', (world,))}
    accepted = {}
    for point, group, digest in connection.execute('''SELECT DISTINCT point_id,group_id,input_projection_hash
            FROM world_accepted_work WHERE world_id=?''', (world,)):
        accepted.setdefault((point, group), []).append((digest,))
    cache = dict(baselines=baselines, work=work, accepted=accepted)
    for row in rows:
        _validated_baseline(connection, row, cache)
