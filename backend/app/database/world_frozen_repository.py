"""Accepted work manifests and immutable per-epoch payload copies.

The accepted rows and active refs are authority metadata.  Reads can expose
those hashes after takeover without touching old-epoch action bytes.  Only
the controlled copy path is allowed to read that older payload.
"""
import hashlib
import json

from app.database.world_repository import LedgerMismatch, wire
from app.schemas.world.canonical import canonical_digest
from app.schemas.world.contracts import TimelinePoint
from app.schemas.world.v2.work import GroupWorkSource, SettlementGroup, TargetSpec
from app.services.world.preview import preview_point


class FrozenWorkError(LedgerMismatch):
    def __init__(self, code, message, reason=None):
        super().__init__(message)
        self.code = code
        self.details = {'reason': reason or code}


def _fail(code, message, reason=None):
    raise FrozenWorkError(code, message, reason)


def initialize_frozen_schema(connection):
    """Add discovery target identities; payload authority uses the shared DDL.

    discover accepts target IDs before it has TargetSpec.triggerKey fields.
    The service allocates those keys once, instead of fabricating them on read.
    """
    connection.execute('''CREATE INDEX IF NOT EXISTS frozen_group_attempt
        ON world_accepted_work(world_id,point_id,group_id,attempt)''')
    connection.execute('''CREATE TABLE IF NOT EXISTS world_frozen_target_specs (
        world_id TEXT NOT NULL, point_id TEXT NOT NULL, group_id TEXT NOT NULL,
        member_id TEXT NOT NULL, target_id TEXT NOT NULL, trigger_id TEXT NOT NULL,
        PRIMARY KEY(world_id,point_id,group_id,member_id,target_id), UNIQUE(world_id,trigger_id),
        FOREIGN KEY(world_id,point_id,group_id) REFERENCES world_groups(world_id,point_id,id)
    ) STRICT''')
    connection.execute('''CREATE TRIGGER IF NOT EXISTS frozen_target_spec_final
        BEFORE UPDATE ON world_frozen_target_specs
        BEGIN SELECT RAISE(ABORT,'accepted_target_spec_is_final'); END''')
    # Referenced original bytes and current ownership copies remain available
    # until their PointWork is consumed or explicitly abandoned.
    connection.execute('''CREATE TRIGGER IF NOT EXISTS active_frozen_payload_retained
        BEFORE DELETE ON world_frozen_work WHEN EXISTS(
          SELECT 1 FROM world_point_work p WHERE p.world_id=OLD.world_id
            AND p.point_id=OLD.point_id AND p.status='active') AND (
          EXISTS(SELECT 1 FROM world_work_refs r WHERE r.world_id=OLD.world_id
            AND r.point_id=OLD.point_id AND r.group_id=OLD.group_id AND r.member_id=OLD.member_id
            AND r.epoch=OLD.epoch AND r.attempt=OLD.attempt) OR
          EXISTS(SELECT 1 FROM world_copy_results c WHERE c.world_id=OLD.world_id
            AND c.point_id=OLD.point_id AND c.group_id=OLD.group_id
            AND c.target_epoch=OLD.epoch AND c.attempt=OLD.attempt))
        BEGIN SELECT RAISE(ABORT,'active_frozen_payload_is_referenced'); END''')


def _bytes_hash(value):
    return hashlib.sha256(value).hexdigest()


def _hashes(member, action, targets, result, candidates):
    return dict(memberId=member, actionContentHash=_bytes_hash(action),
                targetsContentHash=canonical_digest(targets) if targets is not None else None,
                resultContentHash=_bytes_hash(result) if result is not None else None,
                candidatesContentHash=canonical_digest(candidates) if candidates is not None else None)


def _next_attempt(connection, world, point, group):
    return connection.execute('''SELECT COALESCE(MAX(attempt),0)+1 FROM world_accepted_work
        WHERE world_id=? AND point_id=? AND group_id=?''', (world, point, group)).fetchone()[0]


def _active_group(connection, world, point, group):
    row = connection.execute('''SELECT p.round_id,p.advance_id,p.time_json,p.baseline_digest,
            g.members_json FROM world_point_work p JOIN world_groups g
            ON g.world_id=p.world_id AND g.point_id=p.point_id
            WHERE p.world_id=? AND p.point_id=? AND g.id=?
              AND p.status='active' AND g.status IN ('open','closed','staged')''',
            (world, point, group)).fetchone()
    if row is None:
        _fail('frozen_work_missing', 'source no longer belongs to active work', 'source_not_active')
    return row


def active_sources(connection, world, point):
    """Read accepted manifests only. Missing frozen bytes do not hide refs."""
    groups = connection.execute('''SELECT g.id,g.members_json FROM world_groups g
        JOIN world_point_work p ON p.world_id=g.world_id AND p.point_id=g.point_id
        WHERE g.world_id=? AND g.point_id=? AND p.status='active'
          AND g.status IN ('open','closed','staged') ORDER BY g.id''', (world, point)).fetchall()
    sources = []
    for group, raw_members in groups:
        rows = connection.execute('''SELECT r.member_id,r.epoch,r.attempt,a.hashes_json
            FROM world_work_refs r LEFT JOIN world_accepted_work a
            ON a.world_id=r.world_id AND a.point_id=r.point_id AND a.group_id=r.group_id
              AND a.member_id=r.member_id AND a.epoch=r.epoch AND a.attempt=r.attempt
            WHERE r.world_id=? AND r.point_id=? AND r.group_id=? ORDER BY r.member_id''',
            (world, point, group)).fetchall()
        payload_row = connection.execute('SELECT group_json FROM world_group_payloads '
            'WHERE world_id=? AND point_id=? AND group_id=?', (world, point, group)).fetchone()
        if payload_row is None:
            _fail('frozen_work_missing', 'active group confirmation metadata is missing')
        confirmations = json.loads(payload_row[0])['actionTexts']
        expected_members = {member for member in json.loads(raw_members)
                            if confirmations.get(member) is not None}
        if {row[0] for row in rows} != expected_members:
            _fail('frozen_work_missing', 'active members have no accepted manifest', 'accepted_manifest_missing')
        by_source = {}
        for member, epoch, attempt, raw in rows:
            if raw is None:
                _fail('frozen_work_missing', 'active accepted source is missing', 'accepted_manifest_missing')
            try:
                item = json.loads(raw)
                if item['memberId'] != member:
                    raise ValueError('member differs')
                by_source.setdefault((epoch, attempt), []).append(item)
            except (ValueError, KeyError, TypeError) as error:
                raise FrozenWorkError('frozen_work_corrupt', 'accepted manifest is malformed') from error
        for (epoch, attempt), manifest in by_source.items():
            try:
                sources.append(GroupWorkSource.model_validate(dict(pointId=point, groupId=group,
                    sourceEpoch=epoch, sourceAttempt=attempt, manifest=manifest)).model_dump(mode='json'))
            except ValueError as error:
                raise FrozenWorkError('frozen_work_corrupt', 'accepted manifest is malformed') from error
    return sources


def _input_hash(record, work, group_id):
    """The exact time-applied projection preceding this ordered group."""
    groups = []
    for unit in work['units']:
        if unit['groupId'] == group_id:
            break
        groups.append(unit['candidates'])
    from app.services.world.successor import baseline_state
    baseline = work['baseline']
    point = TimelinePoint.model_validate(dict(worldId=record['worldId'], id=work['pointId'],
        sequence=baseline['version'] + 1, kind=work['kind'], previousPointId=baseline['headPointId'],
        roundId=record['round']['roundId'], advanceId=record['advance']['advanceId'],
        trigger=record['round']['trigger'], linkedFromPointId=None if work['kind'] == 'normal'
        else baseline['headPointId'], timeAdvance=work['timeAdvance'], entityDeltas={}))
    return preview_point(baseline_state(record,work), point, groups)['workingStateDigest']


def confirmed_targets(connection, world, point, group, member, allocate=False, record=None):
    """Return accepted full targets, including legacy discover(targetIds)."""
    targets = group['targetSpecsBySource'][member]
    target_ids = group['targetIdsBySource'][member]
    if targets is not None:
        return [TargetSpec.model_validate(target).model_dump(mode='json') for target in targets]
    if target_ids is None:
        return None
    targets = []
    for target in target_ids:
        keys = (world, point, group['groupId'], member, target)
        existing = connection.execute('''SELECT trigger_id FROM world_frozen_target_specs
            WHERE world_id=? AND point_id=? AND group_id=? AND member_id=? AND target_id=?''', keys).fetchone()
        if existing is None:
            if not allocate:
                _fail('frozen_work_missing', 'confirmed target is missing its allocated trigger key',
                      'accepted_target_missing')
            connection.execute('UPDATE world_snapshot_meta SET sequence=sequence+1 WHERE singleton=1')
            sequence = connection.execute('SELECT sequence FROM world_snapshot_meta WHERE singleton=1').fetchone()[0]
            trigger = f'trigger_{sequence}'
            slot = canonical_digest(dict(pointId=point,groupId=group['groupId'],memberId=member,targetId=target))
            if record is None:
                raise LedgerMismatch('Allocating accepted targets requires the transaction record')
            record.setdefault('_allocationMetadata', {}).setdefault('_auto_targets', {})[slot] = {
                'kind': 'trigger', 'scope': group['groupId'], 'id': trigger}
            record['allocations'].setdefault('_auto_targets', {})[(group['groupId'], slot)] = trigger
            connection.execute('INSERT INTO world_frozen_target_specs VALUES(?,?,?,?,?,?)', (*keys, trigger))
        else:
            trigger = existing[0]
        targets.append(dict(targetId=target, triggerKey=trigger))
    return targets


def _payload_members(connection, world, point, group, results, candidates, allocate=False, record=None):
    payloads = []
    for member in sorted(group['memberIds']):
        if group['actionTexts'][member] is None:
            continue
        targets = confirmed_targets(connection, world, point, group, member, allocate=allocate, record=record)
        action = group['actionTexts'][member].encode('utf-8')
        result = results[member].encode('utf-8') if results is not None else None
        payloads.append((member, action, targets, result, candidates,
                         _hashes(member, action, targets, result, candidates)))
    return payloads


def _insert_payload(connection, world, point, group, epoch, attempt, projection,
                    payloads, source=None, update_refs=True):
    for member, action, targets, result, candidates, hashes in payloads:
        keys = (world, point, group, member, epoch, attempt)
        connection.execute('INSERT INTO world_accepted_work VALUES(?,?,?,?,?,?,?,?)',
                           (*keys, projection, wire(hashes)))
        connection.execute('INSERT INTO world_frozen_work VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                           (*keys, action, wire(targets) if targets is not None else None,
                            result, wire(candidates) if candidates is not None else None,
                            source[0] if source else None, source[1] if source else None))
        if update_refs:
            connection.execute('''INSERT INTO world_work_refs VALUES(?,?,?,?,?,?)
                ON CONFLICT(world_id,point_id,group_id,member_id) DO UPDATE SET
                  epoch=excluded.epoch,attempt=excluded.attempt''', keys)


def _visible_source(connection, world, source, epoch):
    if source['sourceEpoch'] == epoch:
        return source
    copied = connection.execute('''SELECT attempt FROM world_copy_results WHERE world_id=?
        AND point_id=? AND group_id=? AND target_epoch=? AND source_epoch=? AND source_attempt=?
        AND manifest_hash=?''', (world, source['pointId'], source['groupId'], epoch,
        source['sourceEpoch'], source['sourceAttempt'], canonical_digest(source['manifest']))).fetchone()
    return dict(source, sourceEpoch=epoch, sourceAttempt=copied[0]) if copied else None


def save_frozen_work(connection, before, record):
    """Call after save_work, inside the same lease-validated transaction.

    Confirmation changes append an immutable complete group generation.
    Merely changing lease ownership never blesses old bytes in the new epoch.
    """
    for key in ('work','_successorWork'):
        work = record.get(key)
        if work is not None and (before or {}).get(key) != work:
            _save_frozen_point(connection,record,work)


def _save_frozen_point(connection,record,work):
    lease = record.get('lease')
    if lease is None:
        raise LedgerMismatch('Confirmed work must be written with a lease')
    world, point, epoch = record['worldId'], work['pointId'], lease['fenceEpoch']
    rows = connection.execute('''SELECT g.id,p.group_json,p.results_json,u.candidates_json
        FROM world_groups g JOIN world_group_payloads p
          ON p.world_id=g.world_id AND p.point_id=g.point_id AND p.group_id=g.id
        LEFT JOIN world_settled_units u
          ON u.world_id=g.world_id AND u.point_id=g.point_id AND u.group_id=g.id
        WHERE g.world_id=? AND g.point_id=? AND g.status IN ('open','closed','staged')''',
        (world, point)).fetchall()
    for group, raw, result, candidates in rows:
        payloads = _payload_members(connection, world, point, json.loads(raw),
                                   json.loads(result) if result is not None else None,
                                   json.loads(candidates) if candidates is not None else None, allocate=True,record=record)
        refs = connection.execute('''SELECT r.member_id,r.epoch,a.hashes_json,a.input_projection_hash,r.attempt
            FROM world_work_refs r JOIN world_accepted_work a
            ON a.world_id=r.world_id AND a.point_id=r.point_id AND a.group_id=r.group_id
              AND a.member_id=r.member_id AND a.epoch=r.epoch AND a.attempt=r.attempt
            WHERE r.world_id=? AND r.point_id=? AND r.group_id=?''', (world, point, group)).fetchall()
        existing = {row[0]: json.loads(row[2]) for row in refs}
        expected = {row[0]: row[-1] for row in payloads}
        if existing == expected:
            continue
        if any(row[1] != epoch for row in refs):
            previous_sources = {}
            for row in refs:
                previous_sources.setdefault((row[1], row[4]), []).append(json.loads(row[2]))
            # The group payload has already accepted the new confirmation in
            # this transaction. Check the previous refs directly: a newly
            # confirmed member cannot have a ref until this append completes.
            for (source_epoch, source_attempt), manifest in previous_sources.items():
                source = dict(pointId=point, groupId=group, sourceEpoch=source_epoch,
                              sourceAttempt=source_attempt, manifest=manifest)
                visible = _visible_source(connection, world, source, epoch)
                if visible is None:
                    _fail('frozen_work_missing', 'restore accepted work before changing its payload', 'restore_required')
                _verified_payload(connection, world, visible)
        projection = refs[0][3] if refs else _input_hash(record, work, group)
        _insert_payload(connection, world, point, group, epoch,
                        _next_attempt(connection, world, point, group), projection, payloads)


def _verified_payload(connection, world, source):
    """The only path that can explicitly read an old-epoch frozen row."""
    payloads, projection = [], None
    for item in source['manifest']:
        keys = (world, source['pointId'], source['groupId'], item['memberId'],
                source['sourceEpoch'], source['sourceAttempt'])
        row = connection.execute('''SELECT a.input_projection_hash,a.hashes_json,
                f.action_bytes,f.targets_json,f.result_bytes,f.candidates_json
            FROM world_accepted_work a LEFT JOIN world_frozen_work f
              ON f.world_id=a.world_id AND f.point_id=a.point_id AND f.group_id=a.group_id
               AND f.member_id=a.member_id AND f.epoch=a.epoch AND f.attempt=a.attempt
            WHERE a.world_id=? AND a.point_id=? AND a.group_id=? AND a.member_id=?
              AND a.epoch=? AND a.attempt=?''', keys).fetchone()
        if row is None or row[2] is None:
            _fail('frozen_work_missing', 'accepted frozen payload is missing', 'source_row_missing')
        try:
            input_hash, raw_hashes, action, raw_targets, result, raw_candidates = row
            if not isinstance(action, bytes) or (result is not None and not isinstance(result, bytes)):
                raise ValueError('text must be UTF-8 bytes')
            action.decode('utf-8')
            if result is not None:
                result.decode('utf-8')
            targets = json.loads(raw_targets) if raw_targets is not None else None
            if targets is not None:
                targets = [TargetSpec.model_validate(t).model_dump(mode='json') for t in targets]
            candidates = SettlementGroup.model_validate_json(raw_candidates).model_dump(mode='json') if raw_candidates else None
            if candidates is not None and candidates['groupId'] != source['groupId']:
                raise ValueError('candidates name another group')
            hashes = _hashes(item['memberId'], action, targets, result, candidates)
            if hashes != item or json.loads(raw_hashes) != item or (projection and projection != input_hash):
                raise ValueError('accepted payload hash or projection differs')
            projection = input_hash
            payloads.append((item['memberId'], action, targets, result, candidates, hashes))
        except (ValueError, KeyError, TypeError, UnicodeError) as error:
            raise FrozenWorkError('frozen_work_corrupt', 'accepted frozen bytes failed integrity checks',
                                  'content_hash_mismatch') from error
    return projection, payloads


def restore_group_work(connection, record, request):
    source = GroupWorkSource.model_validate({key: getattr(request, key) for key in
        ('pointId', 'groupId', 'sourceEpoch', 'sourceAttempt', 'manifest')}).model_dump(mode='json')
    source['manifest'].sort(key=lambda item: item['memberId'])
    world, point, group = record['worldId'], source['pointId'], source['groupId']
    _active_group(connection, world, point, group)
    epoch = record['lease']['fenceEpoch']
    manifest_hash = canonical_digest(source['manifest'])
    copy_key = (world, point, group, epoch, source['sourceEpoch'], source['sourceAttempt'], manifest_hash)
    previous = connection.execute('SELECT attempt FROM world_copy_results WHERE world_id=? AND point_id=? '
        'AND group_id=? AND target_epoch=? AND source_epoch=? AND source_attempt=? AND manifest_hash=?', copy_key).fetchone()
    sources = active_sources(connection, world, point)
    matching = source in sources
    # A new requestId retains the first attempt; the accepted refs still name
    # the original source. Validate current-epoch copied bytes before replay.
    if previous:
        attempt = previous[0]
        destination = dict(source, sourceEpoch=epoch, sourceAttempt=attempt)
        if not matching:
            _fail('frozen_work_missing', 'copied source is no longer active', 'source_not_active')
        _verified_payload(connection, world, destination)
    else:
        if not matching:
            _fail('frozen_work_missing', 'request does not match the active accepted source', 'source_not_active')
        projection, payloads = _verified_payload(connection, world, source)
        attempt = _next_attempt(connection, world, point, group)
        _insert_payload(connection, world, point, group, epoch, attempt, projection, payloads,
                        (source['sourceEpoch'], source['sourceAttempt']), update_refs=False)
        connection.execute('INSERT INTO world_copy_results VALUES(?,?,?,?,?,?,?,?)', (*copy_key, attempt))
    return dict(pointId=point, groupId=group, fenceEpoch=epoch, attempt=attempt,
                sourceEpoch=source['sourceEpoch'], sourceAttempt=source['sourceAttempt'],
                restoredMemberIds=sorted(item['memberId'] for item in source['manifest']))


def point_payload(connection, record, point_view):
    """Return one recovery projection; never select old bytes for visibility."""
    if point_view is None:
        return None
    world, point, epoch = record['worldId'], point_view['pointId'], record['lease']['fenceEpoch']
    sources = active_sources(connection, world, point)
    old = [source for source in sources if _visible_source(connection, world, source, epoch) is None]
    if old:
        return dict(work=point_view, payloadStatus='restore_required', restoreSources=old,
                    groups=[], timeScanCandidates=None)
    groups = []
    by_group = {}
    for source in sources:
        by_group.setdefault(source['groupId'], []).append(source)
    for group, refs in by_group.items():
        members, accepted, candidates, projection = [], [], None, None
        for source in refs:
            visible = _visible_source(connection, world, source, epoch)
            input_hash, payloads = _verified_payload(connection, world, visible)
            if projection is not None and projection != input_hash:
                _fail('frozen_work_corrupt', 'group sources disagree on the frozen input')
            projection = input_hash
            for member, action, targets, result, candidate, hashes in payloads:
                rolls = connection.execute('''SELECT source_id,target_id,trigger_key,id FROM world_rolls
                    WHERE world_id=? AND point_id=? AND group_id=? AND source_id=? ORDER BY target_id,trigger_key''',
                    (world, point, group, member)).fetchall()
                members.append(dict(memberId=member, actionText=action.decode('utf-8'), targets=targets,
                    resultText=result.decode('utf-8') if result is not None else None,
                    rollRefs=[dict(sourceId=s, targetId=t, triggerKey=k, rollId=r) for s,t,k,r in rolls]))
                accepted.append(dict(**hashes, sourceEpoch=source['sourceEpoch'], sourceAttempt=source['sourceAttempt']))
                if candidates is not None and candidates != candidate:
                    _fail('frozen_work_corrupt', 'member candidates differ within a group')
                candidates = candidate
        group_row = connection.execute('SELECT members_json FROM world_groups '
            'WHERE world_id=? AND point_id=? AND id=?', (world, point, group)).fetchone()
        present = {member['memberId'] for member in members}
        for member in json.loads(group_row[0]):
            if member not in present:
                members.append(dict(memberId=member, actionText=None, targets=None,
                                    resultText=None, rollRefs=[]))
        groups.append(dict(groupId=group, pointId=point, inputProjectionHash=projection,
                           members=sorted(members, key=lambda m:m['memberId']),
                           acceptedSources=sorted(accepted,key=lambda s:s['memberId']), candidates=candidates))
    scan = connection.execute('SELECT time_scan_json FROM world_point_work WHERE world_id=? AND point_id=?',
                              (world, point)).fetchone()
    return dict(work=point_view, payloadStatus='available', restoreSources=[], groups=groups,
                timeScanCandidates=json.loads(scan[0]) if scan and scan[0] is not None else None)


def require_current_payload(connection, record, point_id=None):
    work = record.get('work')
    point = point_id or (work['pointId'] if work else None)
    if point is None:
        return
    for source in active_sources(connection, record['worldId'], point):
        visible = _visible_source(connection, record['worldId'], source, record['lease']['fenceEpoch'])
        if visible is None:
            _fail('frozen_work_missing', 'restore accepted work before continuing', 'restore_required')
        _verified_payload(connection, record['worldId'], visible)


def check_frozen_work(connection, record):
    """Check authority metadata against active work without reading old bytes.

    Missing/corrupt old payload remains a controlled restore error, so reading
    the authoritative source manifest cannot accidentally become a model retry.
    """
    for key in ('work','_successorWork'):
        work = record.get(key)
        if work is not None:
            _check_frozen_point(connection,record,work)


def _check_frozen_point(connection,record,work):
    world, point = record['worldId'], work['pointId']
    sources = active_sources(connection, world, point)
    by_group = {}
    for source in sources:
        by_group.setdefault(source['groupId'], {}).update({item['memberId']: item for item in source['manifest']})
        expected_projection = _input_hash(record, work, source['groupId'])
        projections = connection.execute('''SELECT DISTINCT a.input_projection_hash FROM world_work_refs r
            JOIN world_accepted_work a ON a.world_id=r.world_id AND a.point_id=r.point_id
              AND a.group_id=r.group_id AND a.member_id=r.member_id AND a.epoch=r.epoch AND a.attempt=r.attempt
            WHERE r.world_id=? AND r.point_id=? AND r.group_id=?''',
            (world, point, source['groupId'])).fetchall()
        if projections != [(expected_projection,)]:
            _fail('frozen_work_corrupt', 'accepted input projection differs from active work',
                  'input_projection_mismatch')
    for group, raw, results, candidate in connection.execute('''SELECT g.id,p.group_json,p.results_json,u.candidates_json
        FROM world_groups g JOIN world_group_payloads p
          ON p.world_id=g.world_id AND p.point_id=g.point_id AND p.group_id=g.id
        LEFT JOIN world_settled_units u
          ON u.world_id=g.world_id AND u.point_id=g.point_id AND u.group_id=g.id
        WHERE g.world_id=? AND g.point_id=? AND g.status IN ('open','closed','staged')''', (world, point)):
        payloads = _payload_members(connection, world, point, json.loads(raw),
                                   json.loads(results) if results else None,
                                   json.loads(candidate) if candidate else None)
        if by_group.get(group) != {item[0]: item[-1] for item in payloads}:
            _fail('frozen_work_corrupt', 'active payload differs from its accepted manifest', 'content_hash_mismatch')


def collect_terminal_frozen(connection, world_id):
    """Explicit GC after consumption/abandonment; never touch active refs."""
    counts = {}
    for table in ('world_frozen_work', 'world_work_refs', 'world_copy_results',
                  'world_accepted_work', 'world_frozen_target_specs',
                  'world_group_payloads', 'world_settled_units'):
        cursor = connection.execute(f'''DELETE FROM {table} WHERE world_id=? AND point_id IN (
            SELECT point_id FROM world_point_work WHERE world_id=? AND status IN ('consumed','abandoned'))''',
            (world_id, world_id))
        counts[table] = cursor.rowcount
    return counts
