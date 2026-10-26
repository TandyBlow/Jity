"""Short lived group checkpoints: explicit DFS order and threat handling facts.

The checkpoint is separate from original prose and immutable roll rows. Every
caller uses the world's existing SQLite transaction; no recovery read repairs a
missing checkpoint or derives one from member order.
"""
import json

from app.database.world_frozen_repository import FrozenWorkError, _input_hash, confirmed_targets
from app.database.world_judgment_repository import ROLL_COLUMNS, _validated_baseline, roll_outcome
from app.database.world_repository import wire
from app.schemas.world.canonical import canonical_digest


def _fail(code, detail):
    raise FrozenWorkError(code, detail)


def initialize_progress_schema(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS world_group_progress (
        world_id TEXT NOT NULL, point_id TEXT NOT NULL, group_id TEXT NOT NULL,
        checkpoint_json TEXT NOT NULL CHECK(json_valid(checkpoint_json)),
        checkpoint_digest TEXT NOT NULL,
        PRIMARY KEY(world_id,point_id,group_id),
        FOREIGN KEY(world_id,point_id,group_id) REFERENCES world_groups(world_id,point_id,id)
    ) STRICT''')
    connection.execute('''CREATE TRIGGER IF NOT EXISTS terminal_group_progress_final
        BEFORE UPDATE ON world_group_progress WHEN EXISTS(
          SELECT 1 FROM world_point_work p WHERE p.world_id=OLD.world_id
            AND p.point_id=OLD.point_id AND p.status IN ('consumed','abandoned'))
        BEGIN SELECT RAISE(ABORT,'terminal_group_progress_is_final'); END''')


def binding(record, work, group):
    return dict(worldId=record['worldId'], pointId=work['pointId'],
                roundId=record['round']['roundId'], advanceId=record['advance']['advanceId'],
                groupId=group['groupId'], baseline=work['baseline'],
                timeAdvance=work['timeAdvance'], inputProjectionHash=_input_hash(record, work, group['groupId']))


def _active_groups(connection, record):
    for key in ('work', '_successorWork'):
        work = record.get(key)
        if work is None:
            continue
        for group_id, raw, status in connection.execute('''SELECT g.id,p.group_json,g.status
                FROM world_groups g LEFT JOIN world_group_payloads p
                  ON p.world_id=g.world_id AND p.point_id=g.point_id AND p.group_id=g.id
                WHERE g.world_id=? AND g.point_id=? AND g.status IN ('open','closed','staged')''',
                (record['worldId'], work['pointId'])):
            if raw is None:
                _fail('frozen_work_missing', 'group checkpoint original confirmation metadata is missing')
            try:
                group = json.loads(raw)
            except (TypeError, ValueError) as error:
                raise FrozenWorkError('frozen_work_corrupt', 'group checkpoint confirmation metadata is malformed') from error
            yield work, group_id, group, status


def load_progress(connection, record):
    world = record['worldId'] if isinstance(record, dict) else record
    result = {}
    groups = connection.execute('''SELECT g.point_id,g.id FROM world_groups g
        JOIN world_point_work p ON p.world_id=g.world_id AND p.point_id=g.point_id
        WHERE g.world_id=? AND p.status='active' AND g.status IN ('open','closed','staged')''',
        (world,)).fetchall()
    for point_id, group_id in groups:
        row = connection.execute('''SELECT checkpoint_json,checkpoint_digest FROM world_group_progress
            WHERE world_id=? AND point_id=? AND group_id=?''',
            (world, point_id, group_id)).fetchone()
        if row is None:
            _fail('frozen_work_missing', 'active group processing checkpoint is missing')
        try:
            value = json.loads(row[0])
            if canonical_digest(value) != row[1]:
                raise ValueError('checkpoint hash differs')
        except (TypeError, ValueError) as error:
            raise FrozenWorkError('frozen_work_corrupt', 'group processing checkpoint is malformed') from error
        result[group_id] = value
    return result


def save_progress(connection, before, record):
    active = {}
    for work, group_id, group, status in _active_groups(connection, record):
        value = record.get('_groupProgress', {}).get(group_id)
        if value is None:
            _fail('frozen_work_missing', 'operation did not save its group processing checkpoint')
        active[group_id] = value
        auto_triggers = {item['id'] for item in record.get('_allocationMetadata', {}).get('_auto_targets', {}).values()}
        old_auto_triggers = {item['id'] for item in (before or {}).get('_allocationMetadata', {}).get('_auto_targets', {}).values()}
        for source, targets in group['targetSpecsBySource'].items():
            for target in targets or []:
                if target['triggerKey'] not in auto_triggers:
                    continue
                target_keys = (record['worldId'], work['pointId'], group_id, source, target['targetId'])
                row = connection.execute('''SELECT trigger_id FROM world_frozen_target_specs
                    WHERE world_id=? AND point_id=? AND group_id=? AND member_id=? AND target_id=?''', target_keys).fetchone()
                if row is None:
                    if target['triggerKey'] in old_auto_triggers:
                        _fail('frozen_work_missing', 'server allocated discover target identity is missing')
                    connection.execute('INSERT INTO world_frozen_target_specs VALUES(?,?,?,?,?,?)',
                                       (*target_keys, target['triggerKey']))
                elif row[0] != target['triggerKey']:
                    _fail('frozen_work_corrupt', 'server allocated discover target identity was rebound')
        keys = (record['worldId'], work['pointId'], group_id)
        payload = (wire(value), canonical_digest(value))
        row = connection.execute('''SELECT checkpoint_json,checkpoint_digest FROM world_group_progress
            WHERE world_id=? AND point_id=? AND group_id=?''', keys).fetchone()
        if row is None:
            connection.execute('INSERT INTO world_group_progress VALUES(?,?,?,?,?)', (*keys, *payload))
        elif row != payload:
            connection.execute('''UPDATE world_group_progress SET checkpoint_json=?,checkpoint_digest=?
                WHERE world_id=? AND point_id=? AND group_id=?''', (*payload, *keys))
    record['_groupProgress'] = active


def _key(value):
    return value['sourceId'], value['targetId'], value['triggerKey']


def _validate(connection, record, work, group, status, value):
    if set(value) != {'binding', 'progress'} or value['binding'] != binding(record, work, group):
        raise ValueError('group processing checkpoint has another baseline or scope')
    auto_triggers = {item['id'] for item in record.get('_allocationMetadata', {}).get('_auto_targets', {}).values()}
    for source, targets in group['targetSpecsBySource'].items():
        for target in targets or []:
            if target['triggerKey'] in auto_triggers:
                row = connection.execute('''SELECT trigger_id FROM world_frozen_target_specs WHERE
                    world_id=? AND point_id=? AND group_id=? AND member_id=? AND target_id=?''',
                    (record['worldId'], work['pointId'], group['groupId'], source, target['targetId'])).fetchone()
                if row is None:
                    _fail('frozen_work_missing', 'server allocated discover target identity is missing')
                if row[0] != target['triggerKey']:
                    raise ValueError('server allocated discover target identity was rebound')
    progress = value['progress']
    if set(progress) != {'sourceStack', 'threats'}:
        raise ValueError('group processing checkpoint fields are incomplete')
    stack, threats = progress['sourceStack'], progress['threats']
    if not isinstance(stack, list) or not isinstance(threats, list) or len(set(stack)) != len(stack):
        raise ValueError('group processing stack is malformed')
    keys = [_key(item) for item in threats]
    if keys != sorted(set(keys)):
        raise ValueError('threat identities must be unique and sorted')
    target_keys = {(source, target['targetId'], target['triggerKey'])
                   for source in group['memberIds']
                   for target in (confirmed_targets(connection, record['worldId'], work['pointId'], group, source) or [])}
    if set(keys) != target_keys:
        raise ValueError('threat processing facts differ from confirmed targets')
    rows = connection.execute('SELECT ' + ','.join(ROLL_COLUMNS) + ''' FROM world_rolls
        WHERE world_id=? AND point_id=? AND group_id=? ORDER BY source_id,target_id,trigger_key''',
        (record['worldId'], work['pointId'], group['groupId'])).fetchall()
    rolls = {}
    for row in rows:
        _validated_baseline(connection, row)
        outcome = roll_outcome(row)
        rolls[_key(outcome)] = outcome
    if len(rolls) != len(rows):
        raise ValueError('duplicate final judgment identities')
    confirmed = {member for member, action in group['actionTexts'].items() if action is not None}
    root, created, roll_ids = group['sourceId'], {}, set()
    for item in threats:
        key, state = _key(item), item['status']
        base = {'sourceId', 'targetId', 'triggerKey', 'status', 'rollId', 'reactionMemberId'}
        if set(item) != base | ({'actionDisposition'} if state == 'handled' else set()):
            raise ValueError('threat processing fields are incomplete')
        outcome = rolls.get(key)
        if state == 'pending_roll':
            if item['rollId'] is not None or item['reactionMemberId'] is not None or outcome is not None:
                raise ValueError('pending roll already has a final judgment')
            continue
        if outcome is None:
            if connection.execute('SELECT 1 FROM world_rolls WHERE world_id=? AND id=?',
                                  (record['worldId'], item['rollId'])).fetchone():
                raise ValueError('threat processing checkpoint references a final judgment in another scope')
            _fail('frozen_work_missing', 'threat processing checkpoint references a missing final judgment')
        if item['rollId'] != outcome['rollId'] or item['rollId'] in roll_ids:
            raise ValueError('threat processing checkpoint references another final judgment')
        roll_ids.add(item['rollId'])
        if state == 'reaction_pending':
            if not outcome['admitted'] or item['reactionMemberId'] is not None or item['targetId'] in confirmed:
                raise ValueError('pending reaction differs from accepted action or judgment')
        elif state == 'handled':
            disposition = item['actionDisposition']
            if not outcome['admitted']:
                if disposition != 'none' or item['reactionMemberId'] is not None:
                    raise ValueError('refused judgment has an accepted reaction')
            else:
                if (disposition not in ('created', 'reused') or item['reactionMemberId'] != item['targetId']
                        or item['targetId'] not in confirmed):
                    raise ValueError('handled admission has no accepted original action')
                if disposition == 'created':
                    if item['targetId'] in created or item['targetId'] == root:
                        raise ValueError('accepted member has duplicate or cyclic creation edges')
                    created[item['targetId']] = item['sourceId']
        else:
            raise ValueError('unknown threat processing state')
    if roll_ids != {item['rollId'] for item in rolls.values()}:
        raise ValueError('final judgment is missing its threat processing association')
    if set(created) != confirmed - {root}:
        raise ValueError('accepted member is missing its unique creation edge')
    if any(not any(item['targetId'] == member and item['status'] == 'reaction_pending' for item in threats)
           for member in set(group['memberIds']) - confirmed):
        raise ValueError('unconfirmed member placeholder has no pending admitted causal relation')
    for member in created:
        seen, cursor = set(), member
        while cursor != root:
            if cursor in seen or cursor not in created:
                raise ValueError('accepted action creation graph is cyclic or disconnected')
            seen.add(cursor)
            cursor = created[cursor]
    # Check the saved order by the unique creation graph and remaining work.
    # This validates the checkpoint; reads never manufacture a replacement.
    unfinished = {member for member in confirmed if group['targetIdsBySource'][member] is None
                  or any(item['sourceId'] == member and item['status'] != 'handled' for item in threats)}
    ancestry = set(unfinished)
    for member in list(unfinished):
        while member in created:
            member = created[member]
            ancestry.add(member)
    expected_stack = []
    if ancestry:
        cursor = root
        while True:
            expected_stack.insert(0, cursor)
            children = [child for child, parent in created.items() if parent == cursor and child in ancestry]
            if len(children) > 1:
                raise ValueError('DFS checkpoint has multiple unfinished accepted child subtrees')
            if not children:
                break
            cursor = children[0]
    if stack != expected_stack:
        raise ValueError('saved DFS stack skips or reorders accepted source work')
    frontier = sorted(member for member in stack if member in unfinished)
    if group['frontierIds'] != frontier:
        raise ValueError('reaction frontier differs from the saved DFS checkpoint')
    if status in ('closed', 'staged') and (stack or frontier or any(t['status'] != 'handled' for t in threats)):
        raise ValueError('closed group has unfinished source work')
    return dict(rolls=[rolls[key] for key in sorted(rolls)], progress=progress)


def check_progress(connection, record):
    persisted = load_progress(connection, record)
    if persisted != record.get('_groupProgress', {}):
        _fail('frozen_work_corrupt', 'transaction processing checkpoint differs from the SQL authority')
    for work, group_id, group, status in _active_groups(connection, record):
        try:
            _validate(connection, record, work, group, status, persisted[group_id])
        except FrozenWorkError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise FrozenWorkError('frozen_work_corrupt', 'group processing checkpoint is inconsistent') from error


def group_progress_view(connection, record, work, group_id):
    try:
        work = next((record[key] for key in ('work', '_successorWork')
                     if record.get(key) and record[key]['pointId'] == work['pointId']), work)
        row = connection.execute('''SELECT p.group_json,g.status FROM world_groups g
            JOIN world_group_payloads p ON p.world_id=g.world_id AND p.point_id=g.point_id AND p.group_id=g.id
            WHERE g.world_id=? AND g.point_id=? AND g.id=?''',
            (record['worldId'], work['pointId'], group_id)).fetchone()
        if row is None or group_id not in record.get('_groupProgress', {}):
            _fail('frozen_work_missing', 'group recovery processing checkpoint is missing')
        return _validate(connection, record, work, json.loads(row[0]), row[1], record['_groupProgress'][group_id])
    except FrozenWorkError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise FrozenWorkError('frozen_work_corrupt', 'group recovery processing checkpoint is inconsistent') from error


def collect_terminal_progress(connection, world_id):
    return connection.execute('''DELETE FROM world_group_progress WHERE world_id=? AND point_id IN (
        SELECT point_id FROM world_point_work WHERE world_id=? AND status IN ('consumed','abandoned'))''',
        (world_id, world_id)).rowcount
