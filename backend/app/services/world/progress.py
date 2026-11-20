"""Server owned DFS transitions, saved with targets, rolls and original actions."""
import copy

from app.database.world_progress_repository import binding, _key


def _refuse(detail):
    from .control import ServiceRefusal
    raise ServiceRefusal('request_malformed', detail)


def _current(record):
    work = record.get('work')
    group = work.get('pendingGroup') if work else None
    value = record.get('_groupProgress', {}).get(group['groupId']) if group else None
    return work, group, value


def _first(progress, source):
    return next((item for item in progress['threats']
                 if item['sourceId'] == source and item['status'] != 'handled'), None)


def _advance(group, progress):
    while progress['sourceStack']:
        source = progress['sourceStack'][0]
        if group['targetIdsBySource'][source] is None or _first(progress, source) is not None:
            break
        progress['sourceStack'].pop(0)
    group['frontierIds'] = sorted(source for source in progress['sourceStack']
        if group['targetIdsBySource'][source] is None or _first(progress, source) is not None)


def _targets(group, progress, source):
    targets = group['targetSpecsBySource'][source]
    if targets is not None:
        progress['threats'].extend(dict(sourceId=source, targetId=target['targetId'],
            triggerKey=target['triggerKey'], status='pending_roll', rollId=None, reactionMemberId=None)
            for target in targets)
        progress['threats'].sort(key=_key)


def before_operation(store, record, operation, request):
    work, group, value = _current(record)
    if operation not in ('checkpoint_extend_group', 'checkpoint_close_group', 'create_rolls') or group is None:
        return
    if value is None:
        from app.database.world_frozen_repository import FrozenWorkError
        raise FrozenWorkError('frozen_work_missing', 'active group has no processing checkpoint')
    progress = value['progress']
    if operation == 'checkpoint_close_group':
        if progress['sourceStack'] or any(item['status'] != 'handled' for item in progress['threats']):
            _refuse('group cannot close before its persisted DFS work is complete')
        return
    if (operation == 'checkpoint_extend_group' and request.targets is None
            and group['actionTexts'].get(request.admittedMember.memberId) is not None):
        _refuse(f'{request.admittedMember.memberId} is already a group member')
    if operation == 'create_rolls':
        connection = store._local.connection
        if all(connection.execute('''SELECT 1 FROM world_rolls WHERE world_id=? AND round_id=?
                AND group_id=? AND source_id=? AND target_id=? AND trigger_key=?''',
                (record['worldId'], item.roundId, item.groupId, item.sourceId, item.targetId,
                 item.triggerKey)).fetchone() is not None for item in request.rolls):
            return
    source = request.rolls[0].sourceId if operation == 'create_rolls' and request.rolls else request.sourceId
    if not progress['sourceStack'] or source != progress['sourceStack'][0]:
        _refuse('operation source is not the current persisted DFS source')
    if operation == 'create_rolls':
        if any(item.sourceId != source for item in request.rolls):
            _refuse('one roll batch may only judge the current DFS source')
        return
    if request.targets is None:
        first = _first(progress, source)
        member = request.admittedMember
        if first is None or first['status'] != 'reaction_pending' or first['targetId'] != member.memberId:
            _refuse('reaction acceptance must handle the next fixed source threat')
        expected = (source, member.memberId, first['triggerKey'], first['rollId'])
        if expected not in {(ref.sourceId, ref.targetId, ref.triggerKey, ref.rollId) for ref in member.rollRefs}:
            _refuse('reaction acceptance is missing the next threat causal judgment')


def after_operation(store, record, operation, request, data):
    work, group, value = _current(record)
    if group is None:
        return
    if operation == 'checkpoint_discover_group':
        # Legacy discover supplies target IDs. Allocate real typed trigger IDs
        # now, before save_work; no read path creates them and no FK is bypassed.
        source = group['sourceId']
        if group['targetIdsBySource'][source] is not None:
            targets = []
            for target in group['targetIdsBySource'][source]:
                identity = store.next_id('trigger')
                slot = f"{work['pointId']}:{group['groupId']}:{source}:{target}"
                record.setdefault('_allocationMetadata', {}).setdefault('_auto_targets', {})[slot] = dict(
                    kind='trigger', scope=group['groupId'], id=identity)
                record['allocations'].setdefault('_auto_targets', {})[(group['groupId'], slot)] = identity
                targets.append(dict(targetId=target, triggerKey=identity))
            group['targetSpecsBySource'][source] = targets
        progress = dict(sourceStack=[source], threats=[])
        _targets(group, progress, source)
        value = dict(binding=copy.deepcopy(binding(record, work, group)), progress=progress)
        record.setdefault('_groupProgress', {})[group['groupId']] = value
    elif operation == 'checkpoint_extend_group':
        progress = value['progress']
        if request.targets is not None:
            _targets(group, progress, request.sourceId)
        elif request.admittedMember.actionText is not None:
            member = request.admittedMember.memberId
            first = _first(progress, request.sourceId)
            first.update(status='handled', actionDisposition='created', reactionMemberId=member)
            for item in progress['threats']:
                if item['status'] == 'reaction_pending' and item['targetId'] == member:
                    item.update(status='handled', actionDisposition='reused', reactionMemberId=member)
            progress['sourceStack'].insert(0, member)
    else:
        return
    _advance(group, value['progress'])
    if operation == 'checkpoint_extend_group':
        data['frontierIds'] = list(group['frontierIds'])


def record_roll(record, outcome):
    """The same transaction that inserts a roll records its threat transition."""
    work, group, value = _current(record)
    if value is None:
        from app.database.world_frozen_repository import FrozenWorkError
        raise FrozenWorkError('frozen_work_missing', 'judgment has no active processing checkpoint')
    progress = value['progress']
    item = next((item for item in progress['threats'] if _key(item) == _key(outcome)), None)
    if item is None:
        from app.database.world_frozen_repository import FrozenWorkError
        raise FrozenWorkError('frozen_work_corrupt', 'judgment has no confirmed threat processing identity')
    if item['status'] != 'pending_roll':
        if item['rollId'] != outcome['rollId']:
            from app.database.world_frozen_repository import FrozenWorkError
            raise FrozenWorkError('frozen_work_corrupt', 'judgment processing identity was rebound')
        return
    item['rollId'] = outcome['rollId']
    if outcome['admitted']:
        item['status'] = 'reaction_pending'
    else:
        item.update(status='handled', actionDisposition='none', reactionMemberId=None)
    _advance(group, progress)
