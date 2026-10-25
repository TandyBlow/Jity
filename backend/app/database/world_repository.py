"""A3 core relational ledger, written in the caller's SQLite transaction.

The packaged DDL is pinned to the shared v2 specification. Work/group rows
are maintained by world_work_repository, judgments and takeover copies by
their dedicated repositories. Core rows are checked on reads so a divergent A2-compatible adapter
cache cannot silently mask ledger corruption.
"""
import json

from app.schemas.world.contracts import TimelinePoint, WorldInitialState, WorldState
from app.services.world.state import build_initial_state, state_digest
from app.services.world.apply import apply_point


def wire(value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


class LedgerMismatch(ValueError):
    """The persistent adapter and relational facts disagree; fail closed."""


def _upsert(connection, table, key_columns, values):
    # Identifiers are internal constants; values always use bound parameters.
    columns = list(values)
    mutable = [name for name in columns if name not in key_columns]
    where = ' AND '.join(f'{name}=?' for name in key_columns)
    keys = tuple(values[name] for name in key_columns)
    existing = connection.execute(f'SELECT {",".join(mutable)} FROM {table} WHERE {where}', keys).fetchone()
    if existing is not None:
        # INSERT ... ON CONFLICT still fires BEFORE INSERT guards. An existing
        # player round must not be treated as a newly starting player round.
        changed = [name for name, old in zip(mutable, existing) if values[name] != old]
        if changed:
            connection.execute(f'UPDATE {table} SET '
                               f'{",".join(f"{name}=?" for name in changed)} WHERE {where}',
                               tuple(values[name] for name in changed) + keys)
    else:
        connection.execute(f'INSERT INTO {table} ({",".join(columns)}) VALUES '
                           f'({",".join("?" for _ in columns)})', tuple(values.values()))


_POINT_IMMUTABLE = ('sequence', 'kind', 'previous_point_id', 'round_id', 'advance_id',
                    'linked_from_point_id', 'time_json', 'delta_json', 'state_digest')


def _point_values(record, point_id):
    """One storage projection shared by the writer and read validator."""
    world_id = record['worldId']
    point = record['points'].get(point_id)
    narration = record['narrations'][point_id]
    claim = narration.get('claim') or {}
    checkpoint = record['pointStates'][point_id]
    return dict(
        world_id=world_id, id=point_id, sequence=point.sequence if point else 0,
        kind=point.kind if point else 'root',
        previous_point_id=point.previousPointId if point else None,
        round_id=point.roundId if point else None,
        advance_id=point.advanceId if point else None,
        linked_from_point_id=point.linkedFromPointId if point else None,
        time_json=wire(point.timeAdvance) if point else None,
        delta_json=wire({key: value.model_dump(mode='json')
                         for key, value in point.entityDeltas.items()}) if point else None,
        state_digest=checkpoint['stateDigest'], narration_status=narration['status'],
        generation=narration['generation'], claim_token=claim.get('claimToken'),
        claim_mode=claim.get('mode'), claim_epoch=claim.get('fenceEpoch'),
        issued_at=claim.get('issuedAtEpochMilli'), expires_at=claim.get('expiresAtEpochMilli'))


def _submission_values(entry):
    return (entry['operation'], entry['digest'], wire(dict(
        data=entry['data'], views=entry['views'], pathPointId=entry.get('pathPointId'))))


def _save_point(connection, record, point_id):
    world_id = record['worldId']
    values = _point_values(record, point_id)
    narration = record['narrations'][point_id]
    checkpoint = record['pointStates'][point_id]
    existing = connection.execute(
        'SELECT sequence,kind,previous_point_id,round_id,advance_id,linked_from_point_id,'
        'time_json,delta_json,state_digest FROM world_points WHERE world_id=? AND id=?',
        (world_id, point_id)).fetchone()
    if existing is not None and tuple(values[key] for key in _POINT_IMMUTABLE) != tuple(existing):
        raise LedgerMismatch('Committed point content cannot change')
    _upsert(connection, 'world_points', ('world_id', 'id'), values)
    # Verify changed checkpoints here; check_core also verifies retained history.
    if state_digest(checkpoint['state']) != checkpoint['stateDigest']:
        raise LedgerMismatch('State checkpoint digest differs from its content')
    _upsert(connection, 'world_state_checkpoints', ('world_id', 'point_id'), dict(
        world_id=world_id, point_id=point_id, canonical_version='world-canonical-v1',
        state_json=wire(checkpoint['state']), state_digest=checkpoint['stateDigest']))
    if narration['status'] == 'ready':
        row = connection.execute(
            'SELECT text FROM world_narrations WHERE world_id=? AND point_id=? AND generation=?',
            (world_id, point_id, narration['generation'])).fetchone()
        if row is not None and row[0] != narration['text']:
            raise LedgerMismatch('Narration text cannot change within a generation')
        connection.execute('INSERT OR IGNORE INTO world_narrations VALUES(?,?,?,?)',
                           (world_id, point_id, narration['generation'], narration['text']))
    else:
        connection.execute('DELETE FROM world_narrations WHERE world_id=? AND point_id=?',
                           (world_id, point_id))


def _save_round(connection, world_id, round_view, advance, phase):
    _upsert(connection, 'world_rounds', ('world_id', 'id'), dict(
        world_id=world_id, id=round_view['roundId'], advance_id=advance['advanceId'],
        trigger=round_view['trigger'], intent_status=advance['intentStatus'], phase=phase,
        order_json=wire(round_view['order']), cursor=round_view['cursor'],
        acted_json=wire(round_view['actedIds']), visited_json=wire(round_view['visitedIds']),
        conclusion_json=wire(round_view['conclusion']) if round_view['conclusion'] else None))


def save_core(connection, before, record):
    """Apply one before/after transition; never commits its own connection."""
    world_id = record['worldId']
    control = record['control']
    # New worlds have no active head until their root is inserted. Deferred FKs
    # allow the final pointers to be installed in this same transaction.
    if before is None:
        connection.execute('INSERT INTO worlds(id,initial_json) VALUES(?,?)',
                           (world_id, wire(record['state'].initial)))
    advance = record.get('advance')
    old_advance = (before or {}).get('advance')
    if advance is not None and advance != old_advance:
        _upsert(connection, 'world_advances', ('world_id', 'id'), dict(
            world_id=world_id, id=advance['advanceId'], input_id=advance['inputId'],
            input_text=advance['inputText'], intent_status=advance['intentStatus'], ended=0))
    elif advance is None and old_advance is not None:
        status = old_advance['intentStatus']
        connection.execute('UPDATE world_advances SET ended=1,input_text=NULL,intent_status=? '
                           'WHERE world_id=? AND id=?',
                           ('expired' if status == 'pending' else status,
                            world_id, old_advance['advanceId']))

    # The root must exist before player-round insertion (ready-head SQL guard).
    def changed_point(point_id):
        return before is None or any(
            record[field].get(point_id) != before[field].get(point_id)
            for field in ('points', 'pointStates', 'narrations'))

    if changed_point(record['rootPointId']):
        _save_point(connection, record, record['rootPointId'])
    if before is None:
        connection.execute('UPDATE worlds SET active_point_id=? WHERE id=?',
                           (record['rootPointId'], world_id))
    current_round = record.get('round')
    old_round = (before or {}).get('round')
    if old_round and current_round and old_round['roundId'] != current_round['roundId']:
        # A2 swaps the active round dict. Persist the closing row before that
        # pointer switch loses it; A3 round conclusion remains one SQL txn.
        closed = dict(old_round)
        closed['conclusion'] = dict(kind='continue', closedBy='model', cancelReason=None,
                                    candidateCharacterIds=current_round['order'],
                                    nextRoundId=current_round['roundId'])
        _save_round(connection, world_id, closed, old_advance, 'complete')
    if current_round and (before is None or current_round != old_round or
                          advance != old_advance or control['phase'] != before['control']['phase']):
        _save_round(connection, world_id, current_round, advance or
                    _round_advance(connection, world_id, current_round['roundId']),
                    'complete' if current_round['conclusion'] else control['phase'])
    for point_id in record['points']:
        if changed_point(point_id):
            _save_point(connection, record, point_id)
    lease = record.get('lease')
    old_lease = (before or {}).get('lease')
    if lease and lease != old_lease:
        _upsert(connection, 'world_leases', ('world_id',), dict(
            world_id=world_id, holder_id=lease.get('holderId', 'initial'),
            token=lease['leaseToken'], epoch=lease['fenceEpoch'],
            expires_at=lease['expiresAtEpochMilli']))
    elif lease is None and old_lease is not None:
        if '_leaseEpoch' in record:
            connection.execute("UPDATE world_leases SET holder_id='',token='',expires_at=1 WHERE world_id=?",
                               (world_id,))
        else:
            connection.execute('DELETE FROM world_leases WHERE world_id=?', (world_id,))
    if '_leaseEpoch' in record:
        if (before and record['_leaseEpoch'] < before.get('_leaseEpoch', 0)) or (
                lease and lease['fenceEpoch'] != record['_leaseEpoch']):
            raise LedgerMismatch('Lease epoch cannot decrease or diverge from its authority')
        _upsert(connection, 'world_authority_meta', ('world_id',), dict(
            world_id=world_id, highest_epoch=record['_leaseEpoch'],
            blocked_reason=record.get('_gateBlockedReason')))
        gate = control['gate']
        if gate['status'] == 'pending':
            claim = record['narrations'][record['headPointId']]['claim']
            _upsert(connection, 'world_gates', ('world_id',), dict(
                world_id=world_id, point_id=record['headPointId'], generation=gate['generation'],
                token=claim['claimToken'], epoch=claim['fenceEpoch'],
                issued_at=gate['issuedAtEpochMilli'], expires_at=gate['expiresAtEpochMilli']))
        else:
            connection.execute('DELETE FROM world_gates WHERE world_id=?', (world_id,))
    previous = (before or {}).get('idempotency', {})
    if not previous.keys() <= record['idempotency'].keys():
        raise LedgerMismatch('Successful submission records cannot be removed')
    for request_id, entry in record['idempotency'].items():
        if request_id in previous:
            if entry != previous[request_id]:
                raise LedgerMismatch('Successful submission record cannot change')
            continue
        # Plain JSON keeps SQL's private-payload trigger effective. Existing
        # records were checked before the handler; only new results are written.
        values = _submission_values(entry)
        if connection.execute('SELECT 1 FROM world_submissions WHERE world_id=? AND request_id=?',
                              (world_id, request_id)).fetchone():
            raise LedgerMismatch('Successful submission record cannot change')
        connection.execute('INSERT INTO world_submissions VALUES(?,?,?,?,?)',
                           (world_id, request_id, *values))
    connection.execute('UPDATE worlds SET version=?,revision=?,paused=?,active_point_id=?,'
                       'active_round_id=? WHERE id=?',
                       (record['version'], control['revision'], int(control['paused']),
                        record['headPointId'], current_round['roundId'] if current_round else None,
                        world_id))


def _round_advance(connection, world_id, round_id):
    row = connection.execute('SELECT a.id,a.intent_status FROM world_advances a '
                             'JOIN world_rounds r ON r.world_id=a.world_id AND r.advance_id=a.id '
                             'WHERE r.world_id=? AND r.id=?', (world_id, round_id)).fetchone()
    if row is None:
        raise LedgerMismatch('Round has no persisted advance')
    return {'advanceId': row[0], 'intentStatus': row[1]}


def check_core(connection, record):
    world_id = record['worldId']
    row = connection.execute('SELECT initial_json,version,revision,paused,active_point_id,active_round_id '
                             'FROM worlds WHERE id=?', (world_id,)).fetchone()
    if row is None or row[0] != wire(record['state'].initial):
        raise LedgerMismatch('Initial world disagrees with relational ledger')
    expected = (record['version'], record['control']['revision'], int(record['control']['paused']),
                record['headPointId'], (record.get('round') or {}).get('roundId'))
    if tuple(row[1:]) != expected:
        raise LedgerMismatch('World head or control disagrees with relational ledger')
    advance = record.get('advance')
    round_view = record.get('round')
    if advance:
        row = connection.execute('SELECT input_id,input_text,intent_status,ended FROM world_advances '
                                 'WHERE world_id=? AND id=?', (world_id, advance['advanceId'])).fetchone()
        if row != (advance['inputId'], advance['inputText'], advance['intentStatus'], 0):
            raise LedgerMismatch('Active input disagrees with relational ledger')
    if round_view:
        row = connection.execute('SELECT trigger,phase,order_json,cursor,acted_json,visited_json,'
                                 'conclusion_json FROM world_rounds WHERE world_id=? AND id=?',
                                 (world_id, round_view['roundId'])).fetchone()
        expected_round = (
            round_view['trigger'], 'complete' if round_view['conclusion'] else record['control']['phase'],
            wire(round_view['order']), round_view['cursor'], wire(round_view['actedIds']),
            wire(round_view['visitedIds']), wire(round_view['conclusion']) if round_view['conclusion'] else None)
        if row != expected_round:
            raise LedgerMismatch('Round progress disagrees with relational ledger')
    lease = record.get('lease')
    lease_row = connection.execute('SELECT token,epoch,expires_at FROM world_leases WHERE world_id=?',
                                   (world_id,)).fetchone()
    expected_lease = (lease['leaseToken'], lease['fenceEpoch'], lease['expiresAtEpochMilli']) if lease else None
    if lease is None and '_leaseEpoch' in record:
        expected_lease = ('', record['_leaseEpoch'], 1)
    if lease_row != expected_lease:
        raise LedgerMismatch('Lease disagrees with relational ledger')
    if '_leaseEpoch' in record:
        meta = connection.execute('SELECT highest_epoch,blocked_reason FROM world_authority_meta WHERE world_id=?',
                                  (world_id,)).fetchone()
        if meta != (record['_leaseEpoch'], record.get('_gateBlockedReason')):
            raise LedgerMismatch('Lease epoch or gate failure differs from authority ledger')
        gate = record['control']['gate']
        expected_gate = None
        if gate['status'] == 'pending':
            claim = record['narrations'][record['headPointId']]['claim']
            if claim is None:
                raise LedgerMismatch('Pending gate has no issued claim')
            expected_gate = (record['headPointId'], gate['generation'], claim['claimToken'],
                             claim['fenceEpoch'], gate['issuedAtEpochMilli'], gate['expiresAtEpochMilli'])
        stored_gate = connection.execute('SELECT point_id,generation,token,epoch,issued_at,expires_at '
                                         'FROM world_gates WHERE world_id=?', (world_id,)).fetchone()
        if stored_gate != expected_gate:
            raise LedgerMismatch('Narration gate differs from authority ledger')
    # Batch read all retained facts in this same transaction. Full validation
    # stays intact, but SQL round trips no longer grow with history length.
    cursor = connection.execute('SELECT * FROM world_points WHERE world_id=?', (world_id,))
    columns = [column[0] for column in cursor.description]
    points = {row['id']: row for row in (dict(zip(columns, values)) for values in cursor)}
    if set(points) != set(record['pointStates']):
        raise LedgerMismatch('Timeline identities disagree with relational ledger')
    submissions = {row[0]: row[1:] for row in connection.execute(
        'SELECT request_id,operation,request_hash,result_json FROM world_submissions WHERE world_id=?',
        (world_id,))}
    if submissions.keys() != record['idempotency'].keys():
        raise LedgerMismatch('Submission identities disagree with relational ledger')
    for request_id, entry in record['idempotency'].items():
        if submissions[request_id] != _submission_values(entry):
            raise LedgerMismatch('Submission replay disagrees with relational ledger')
    narrations = {(point_id, generation): text for point_id, generation, text in connection.execute(
        'SELECT point_id,generation,text FROM world_narrations WHERE world_id=?', (world_id,))}
    if hasattr(record, 'clock_milli'):
        record.missing_narrations = set()
    checkpoints = {row[0]: row[1:] for row in connection.execute(
        'SELECT point_id,state_json,state_digest,canonical_version FROM world_state_checkpoints WHERE world_id=?',
        (world_id,))}
    if checkpoints.keys() != record['pointStates'].keys():
        raise LedgerMismatch('Checkpoint identities disagree with relational ledger')
    for point_id, checkpoint in record['pointStates'].items():
        narration = record['narrations'][point_id]
        if points[point_id] != _point_values(record, point_id):
            raise LedgerMismatch('Committed point disagrees with relational ledger')
        if narration['status'] == 'ready':
            key = (point_id, narration['generation'])
            if key not in narrations and hasattr(record, 'clock_milli'):
                record.missing_narrations.add(point_id)
            elif narrations.get(key) != narration['text']:
                raise LedgerMismatch('Narration cache disagrees with relational ledger')
        row = checkpoints[point_id]
        if (row[1] != checkpoint['stateDigest'] or row[2] != 'world-canonical-v1' or
                state_digest(WorldState.model_validate_json(row[0])) != row[1] or
                wire(checkpoint['state']) != row[0]):
            raise LedgerMismatch('State cache disagrees with relational checkpoint')
    if state_digest(record['state']) != record['pointStates'][record['headPointId']]['stateDigest']:
        raise LedgerMismatch('Current state differs from the committed head')
    head = record['points'].get(record['headPointId'])
    sequence = head.sequence if head is not None else 0
    if record['version'] != sequence or record['pointStates'][record['headPointId']]['version'] != sequence:
        raise LedgerMismatch('Head sequence and world version differ')


def replay_state(connection, world_id, point_id):
    """Reconstruct without reading snapshots or state-checkpoint caches."""
    row = connection.execute('SELECT initial_json FROM worlds WHERE id=?', (world_id,)).fetchone()
    target = connection.execute('SELECT sequence FROM world_points WHERE world_id=? AND id=?',
                                (world_id, point_id)).fetchone()
    if row is None or target is None:
        raise KeyError((world_id, point_id))
    state = build_initial_state(WorldInitialState.model_validate_json(row[0]))
    rows = connection.execute('SELECT id,sequence,kind,previous_point_id,round_id,advance_id,'
                              'linked_from_point_id,time_json,delta_json,state_digest '
                              'FROM world_points WHERE world_id=? AND sequence<=? ORDER BY sequence',
                              (world_id, target[0])).fetchall()
    previous = None
    for expected_sequence, point in enumerate(rows):
        (identity, sequence, kind, parent, round_id, advance_id, linked,
         time_json, delta_json, digest) = point
        if sequence != expected_sequence or parent != previous:
            raise LedgerMismatch('Timeline is not a contiguous committed chain')
        if kind != 'root':
            round_row = connection.execute('SELECT trigger FROM world_rounds WHERE world_id=? AND id=?',
                                           (world_id, round_id)).fetchone()
            if round_row is None:
                raise LedgerMismatch('Committed point has no round')
            projection = TimelinePoint.model_validate(dict(
                worldId=world_id, id=identity, sequence=sequence, kind=kind,
                previousPointId=parent, roundId=round_id, advanceId=advance_id,
                linkedFromPointId=linked, trigger=round_row[0],
                timeAdvance=json.loads(time_json), entityDeltas=json.loads(delta_json)))
            state = apply_point(state, projection)
        elif sequence != 0:
            raise LedgerMismatch('Root must be the first point')
        if state_digest(state) != digest:
            raise LedgerMismatch('Replayed state differs from the committed digest')
        previous = identity
    if previous != point_id:
        raise LedgerMismatch('Replay did not reach the requested point')
    return state
