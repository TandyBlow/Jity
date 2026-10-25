"""Relational current/terminal PointWork and group payload persistence.

These rows own the active work view, not a duplicate inside world_snapshots.
Per-epoch accepted/frozen manifests, controlled copying and reservation
promotion are separate A3 work; the payload table is not a replacement for
those authority records.
"""
import json

from pydantic import TypeAdapter, model_validator

from app.database.world_repository import LedgerMismatch, _upsert, wire
from app.schemas.world.canonical import canonical_digest, parse_json
from app.schemas.world.contracts import Contract, Id, Ids, Text, TimeAdvance
from app.schemas.world.v2.projections import prefix_projection
from app.schemas.world.v2.contexts import PendingGroupView, SuccessorSummary, WorkingProgress
from app.schemas.world.v2.work import SettlementGroup, TargetSpec
from app.services.world.units import unit_content_hash, validate_commit_groups


class _StoredGroup(Contract):
    """Private payload shape, including originals omitted from the wire view."""
    groupId: Id
    sourceId: Id
    memberIds: Ids
    targetIds: Ids | None
    targetIdsBySource: dict[Id, Ids | None]
    targetSpecsBySource: dict[Id, list[TargetSpec] | None]
    frontierIds: Ids
    closed: bool
    actionTexts: dict[Id, Text]

    @model_validator(mode='after')
    def confirmed_originals(self):
        members = set(self.memberIds)
        if (set(self.actionTexts) != members or set(self.targetIdsBySource) != members
                or set(self.targetSpecsBySource) != members):
            raise ValueError('Every member needs its original action and target-confirmation entries')
        PendingGroupView.model_validate({key: value for key, value in self.model_dump(mode='json').items()
                                        if key not in ('actionTexts', 'targetIdsBySource', 'targetSpecsBySource')}
                                       | {'targetIds': self.targetIds or []})
        confirmed = [targets for targets in self.targetIdsBySource.values() if targets is not None]
        expected_targets = sorted({target for targets in confirmed for target in targets}) if confirmed else None
        if self.targetIds != expected_targets:
            raise ValueError('Group target union differs from confirmed member targets')
        for member, specs in self.targetSpecsBySource.items():
            targets = self.targetIdsBySource[member]
            if specs is not None and (targets is None or {spec.targetId for spec in specs} != set(targets)):
                raise ValueError('Member target specifications differ from confirmed targets')
        if self.closed and len(confirmed) != len(members):
            raise ValueError('Closed group still has unconfirmed member targets')
        return self


_RESULTS = TypeAdapter(dict[Id, Text])


def initialize_work_schema(connection):
    connection.execute('''CREATE TABLE world_work_heads (
        world_id TEXT PRIMARY KEY REFERENCES worlds(id), point_id TEXT NOT NULL,
        FOREIGN KEY(world_id,point_id) REFERENCES world_point_work(world_id,point_id)
    ) STRICT''')
    connection.execute('''CREATE TABLE world_work_details (
        world_id TEXT NOT NULL, point_id TEXT NOT NULL,
        pending_group_id TEXT, successor_json TEXT CHECK(successor_json IS NULL OR json_valid(successor_json)),
        PRIMARY KEY(world_id,point_id),
        FOREIGN KEY(world_id,point_id) REFERENCES world_point_work(world_id,point_id),
        FOREIGN KEY(world_id,point_id,pending_group_id) REFERENCES world_groups(world_id,point_id,id)
          DEFERRABLE INITIALLY DEFERRED
    ) STRICT''')
    connection.execute('''CREATE TABLE world_group_payloads (
        world_id TEXT NOT NULL, point_id TEXT NOT NULL, group_id TEXT NOT NULL,
        group_json TEXT NOT NULL CHECK(json_valid(group_json)),
        results_json TEXT CHECK(results_json IS NULL OR json_valid(results_json)),
        PRIMARY KEY(world_id,point_id,group_id),
        FOREIGN KEY(world_id,point_id,group_id) REFERENCES world_groups(world_id,point_id,id)
    ) STRICT''')
    connection.execute('''CREATE TRIGGER group_payload_final BEFORE UPDATE ON world_group_payloads
        WHEN EXISTS(SELECT 1 FROM world_groups g WHERE g.world_id=OLD.world_id
          AND g.point_id=OLD.point_id AND g.id=OLD.group_id AND g.status IN ('staged','consumed','abandoned'))
        BEGIN SELECT RAISE(ABORT,'group_payload_is_final'); END''')
    connection.execute('''CREATE TRIGGER settled_unit_final BEFORE UPDATE ON world_settled_units
        BEGIN SELECT RAISE(ABORT,'settled_unit_is_final'); END''')
    connection.execute('''CREATE TRIGGER terminal_work_final BEFORE UPDATE ON world_point_work
        WHEN OLD.status IN ('consumed','abandoned')
        BEGIN SELECT RAISE(ABORT,'terminal_work_is_final'); END''')
    connection.execute('''CREATE TRIGGER terminal_group_final BEFORE UPDATE ON world_groups
        WHEN OLD.status IN ('consumed','abandoned')
        BEGIN SELECT RAISE(ABORT,'terminal_group_is_final'); END''')


def install_work_guards(connection):
    """Idempotent additive guards, including on existing work-schema v1 DBs."""
    immutable = ('world_id', 'point_id', 'round_id', 'advance_id', 'kind',
                 'baseline_point_id', 'baseline_version', 'baseline_digest',
                 'time_json', 'time_locked', 'sealed', 'prefix_digest', 'phase',
                 'progress_json', 'time_scan_json')
    changed = ' OR '.join(f'NEW.{key} IS NOT OLD.{key}' for key in immutable)
    connection.execute(f'''CREATE TRIGGER IF NOT EXISTS sealed_work_content_final BEFORE UPDATE ON world_point_work
        WHEN OLD.sealed=1 AND ({changed})
        BEGIN SELECT RAISE(ABORT,'sealed_work_content_is_final'); END''')
    connection.execute('''CREATE TRIGGER IF NOT EXISTS locked_work_time_final BEFORE UPDATE ON world_point_work
        WHEN OLD.time_locked=1 AND (NEW.time_locked<>1 OR NEW.time_json IS NOT OLD.time_json)
        BEGIN SELECT RAISE(ABORT,'point_time_is_locked'); END''')
    connection.execute('''CREATE TRIGGER IF NOT EXISTS time_scan_final BEFORE UPDATE ON world_point_work
        WHEN OLD.time_scan_json IS NOT NULL AND NEW.time_scan_json IS NOT OLD.time_scan_json
        BEGIN SELECT RAISE(ABORT,'time_scan_is_final'); END''')


def _save_group(connection, world_id, point_id, group, status, results=None):
    keys = (world_id, point_id, group['groupId'])
    existing = connection.execute('SELECT status FROM world_groups WHERE world_id=? AND point_id=? AND id=?', keys).fetchone()
    if existing is None:
        connection.execute('INSERT INTO world_groups VALUES(?,?,?,?,?,?)',
                           (*keys, group['sourceId'], wire(sorted(group['memberIds'])), status))
        connection.execute('INSERT INTO world_group_payloads VALUES(?,?,?,?,?)',
                           (*keys, wire(group), wire(results) if results is not None else None))
        return
    old_row = connection.execute('SELECT group_json FROM world_group_payloads '
                                 'WHERE world_id=? AND point_id=? AND group_id=?', keys).fetchone()
    if old_row is None:
        raise LedgerMismatch('Original group payload is missing')
    old = json.loads(old_row[0])
    if (old['sourceId'] != group['sourceId'] or not set(old['memberIds']) <= set(group['memberIds']) or
            any(group['actionTexts'].get(member) != text for member, text in old['actionTexts'].items()) or
            any(targets is not None and group['targetIdsBySource'].get(member) != targets
                for member, targets in old['targetIdsBySource'].items()) or
            any(targets is not None and group['targetSpecsBySource'].get(member) != targets
                for member, targets in old['targetSpecsBySource'].items()) or
            (old['closed'] and group != old)):
        raise LedgerMismatch('Confirmed action, targets or closed-group membership cannot change')
    _upsert(connection, 'world_group_payloads', ('world_id', 'point_id', 'group_id'), dict(
        world_id=world_id, point_id=point_id, group_id=group['groupId'],
        group_json=wire(group), results_json=wire(results) if results is not None else None))
    _upsert(connection, 'world_groups', ('world_id', 'point_id', 'id'), dict(
        world_id=world_id, point_id=point_id, id=group['groupId'], source_id=group['sourceId'],
        members_json=wire(sorted(group['memberIds'])), status=status))


def save_work(connection, before, record):
    world_id = record['worldId']
    work = record.get('work')
    old = (before or {}).get('work')
    if work == old:
        return
    if old and (work is None or work['pointId'] != old['pointId']):
        status = 'consumed' if old['pointId'] in record['points'] else 'abandoned'
        connection.execute('UPDATE world_point_work SET status=? WHERE world_id=? AND point_id=?',
                           (status, world_id, old['pointId']))
        connection.execute('UPDATE world_groups SET status=? WHERE world_id=? AND point_id=?',
                           (status, world_id, old['pointId']))
        connection.execute('DELETE FROM world_work_heads WHERE world_id=?', (world_id,))
    if work is None:
        return
    round_view, advance = record['round'], record['advance']
    baseline = work['baseline']
    _upsert(connection, 'world_point_work', ('world_id', 'point_id'), dict(
        world_id=world_id, point_id=work['pointId'], round_id=round_view['roundId'], advance_id=advance['advanceId'],
        kind=work['kind'], baseline_point_id=baseline['headPointId'], baseline_version=baseline['version'],
        baseline_digest=baseline['stateDigest'], time_json=wire(work['timeAdvance']),
        time_locked=int(work['timeLocked']), sealed=int(work['sealed']), prefix_digest=work['prefixDigest'],
        phase=work['phase'], progress_json=wire(work['working']),
        time_scan_json=wire(work['timeScan']) if work['timeScan'] is not None else None,
        successor_point_id=None, predecessor_point_id=None, status='active'))
    pending = work['pendingGroup']
    if pending:
        _save_group(connection, world_id, work['pointId'], pending, 'closed' if pending['closed'] else 'open')
    for ordinal, unit in enumerate(work['units']):
        group_id = unit['groupId']
        if unit['contentHash'] != unit_content_hash(unit['candidates']):
            raise LedgerMismatch('Staged candidates differ from their frozen content hash')
        staged_row = connection.execute('SELECT group_json,results_json FROM world_group_payloads '
                                        'WHERE world_id=? AND point_id=? AND group_id=?',
                                        (world_id, work['pointId'], group_id)).fetchone()
        if staged_row is None:
            raise LedgerMismatch('Staged unit has no saved original action group')
        group = json.loads(staged_row[0])
        _save_group(connection, world_id, work['pointId'], group, 'staged', unit['results'])
        values = (world_id, work['pointId'], ordinal, group_id, unit['unitId'],
                  wire(unit['candidates']), unit['contentHash'])
        existing = connection.execute('SELECT world_id,point_id,ordinal,group_id,unit_id,candidates_json,content_hash '
                                      'FROM world_settled_units WHERE world_id=? AND point_id=? AND ordinal=?',
                                      values[:3]).fetchone()
        if existing is not None and existing != values:
            raise LedgerMismatch('Staged unit identity, order or candidates cannot change')
        if existing is None:
            connection.execute('INSERT INTO world_settled_units VALUES(?,?,?,?,?,?,?)', values)
    _upsert(connection, 'world_work_details', ('world_id', 'point_id'), dict(
        world_id=world_id, point_id=work['pointId'],
        pending_group_id=pending['groupId'] if pending else None,
        successor_json=wire(work['successor']) if work['successor'] else None))
    _upsert(connection, 'world_work_heads', ('world_id',), dict(world_id=world_id, point_id=work['pointId']))


def load_work(connection, world_id):
    try:
        return _load_work(connection, world_id)
    except LedgerMismatch:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise LedgerMismatch('Relational work payload is malformed') from error


def _load_work(connection, world_id):
    pointer = connection.execute('SELECT point_id FROM world_work_heads WHERE world_id=?', (world_id,)).fetchone()
    active = connection.execute("SELECT point_id FROM world_point_work WHERE world_id=? AND status='active'",
                                (world_id,)).fetchall()
    if pointer is None:
        if active:
            raise LedgerMismatch('Active work has no current-work pointer')
        return None
    point_id = pointer[0]
    if active != [(point_id,)]:
        raise LedgerMismatch('Current-work pointer differs from active work')
    row = connection.execute('SELECT kind,baseline_point_id,baseline_version,baseline_digest,time_json,time_locked,'
                             'sealed,prefix_digest,phase,progress_json,time_scan_json '
                             'FROM world_point_work WHERE world_id=? AND point_id=?', (world_id, point_id)).fetchone()
    details = connection.execute('SELECT pending_group_id,successor_json FROM world_work_details '
                                 'WHERE world_id=? AND point_id=?', (world_id, point_id)).fetchone()
    if row is None or details is None:
        raise LedgerMismatch('Current work or its metadata is missing')
    (kind, head, version, digest, time_json, locked, sealed, prefix, phase, progress, scan) = row
    pending = None
    group_rows = connection.execute('SELECT g.id,g.status,g.source_id,g.members_json,p.group_json,p.results_json '
                                   'FROM world_groups g LEFT JOIN world_group_payloads p '
                                   'ON p.world_id=g.world_id AND p.point_id=g.point_id AND p.group_id=g.id '
                                   'WHERE g.world_id=? AND g.point_id=?', (world_id, point_id)).fetchall()
    groups = {}
    for group_id, status, source, members, raw, results in group_rows:
        if raw is None:
            raise LedgerMismatch('Original group payload is missing')
        group = json.loads(raw)
        _StoredGroup.model_validate(group)
        if (group['groupId'] != group_id or group['sourceId'] != source or
                wire(sorted(group['memberIds'])) != members):
            raise LedgerMismatch('Group payload disagrees with its membership')
        result = _RESULTS.validate_python(json.loads(results)) if results is not None else None
        groups[group_id] = (status, group, result)
        if group_id == details[0]:
            if status not in ('open', 'closed') or group['closed'] != (status == 'closed'):
                raise LedgerMismatch('Pending group phase differs from its saved state')
            pending = group
    if details[0] is not None and pending is None:
        raise LedgerMismatch('Pending group reference is missing')
    pending_ids = {key for key, value in groups.items() if value[0] in ('open', 'closed')}
    if pending_ids != ({details[0]} if details[0] is not None else set()):
        raise LedgerMismatch('Open groups disagree with the pending-group pointer')
    units = []
    for ordinal, group_id, unit_id, raw, content_hash in connection.execute(
            'SELECT ordinal,group_id,unit_id,candidates_json,content_hash FROM world_settled_units '
            'WHERE world_id=? AND point_id=? ORDER BY ordinal', (world_id, point_id)):
        candidates = SettlementGroup.model_validate_json(raw)
        group = groups.get(group_id)
        if (ordinal != len(units) or unit_content_hash(candidates) != content_hash or
                candidates.groupId != group_id or group is None or group[0] != 'staged' or
                sorted(candidates.actorIds) != sorted(group[1]['memberIds']) or group[2] is None or
                set(group[2]) != set(candidates.actorIds)):
            raise LedgerMismatch('Staged unit lost its original group, order, result or content binding')
        units.append(dict(unitId=unit_id, groupId=group_id, memberIds=sorted(candidates.actorIds),
                          contentHash=content_hash, candidates=candidates, results=group[2]))
    if {key for key, value in groups.items() if value[0] == 'staged'} != {unit['groupId'] for unit in units}:
        raise LedgerMismatch('Staged groups and settled units disagree')
    working = WorkingProgress.model_validate_json(progress)
    if set(working.settledUnitIds) != {unit['unitId'] for unit in units}:
        raise LedgerMismatch('Working progress disagrees with settled units')
    time = TimeAdvance.model_validate(parse_json(time_json)).model_dump(mode='json')
    successor = SuccessorSummary.model_validate(parse_json(details[1])).model_dump(mode='json') if details[1] is not None else None
    return dict(pointId=point_id, kind=kind, timeAdvance=time, timeLocked=bool(locked),
                sealed=bool(sealed), prefixDigest=prefix, timeScanComplete=scan is not None,
                timeScan=SettlementGroup.model_validate_json(scan) if scan is not None else None,
                baseline=dict(headPointId=head, version=version, stateDigest=digest),
                phase=phase, working=working, units=units, pendingGroup=pending,
                successor=successor)


def check_work(connection, record):
    work = record['work']
    if work is None:
        return
    binding = connection.execute('SELECT round_id,advance_id FROM world_point_work '
                                 'WHERE world_id=? AND point_id=?', (record['worldId'], work['pointId'])).fetchone()
    if binding != (record['round']['roundId'], record['advance']['advanceId']):
        raise LedgerMismatch('Work belongs to another round or input chain')
    if work['phase'] != record['control']['phase']:
        raise LedgerMismatch('Work phase differs from controller phase')
    if work['baseline'] != dict(headPointId=record['headPointId'], version=record['version'],
                               stateDigest=record['pointStates'][record['headPointId']]['stateDigest']):
        raise LedgerMismatch('Work baseline differs from the committed head')
    order = record['round']['order']
    progress = work['working']
    visited, acted = set(progress.visitedIds), set(progress.actedIds)
    roster = frozenset(record['state'].initial.characters)
    candidates = [unit['candidates'] for unit in work['units']]
    if work['timeScan'] is not None:
        if work['timeScan'].groupId is not None or work['units']:
            raise LedgerMismatch('Time-scan work cannot contain action groups')
        candidates.append(work['timeScan'])
    if validate_commit_groups(candidates, roster):
        raise LedgerMismatch('Saved candidates violate roster, coverage or actor uniqueness')
    unit_actors = {actor for unit in work['units'] for actor in unit['candidates'].actorIds}
    committed_actors = set(record['round']['actedIds'])
    if acted != committed_actors | unit_actors or committed_actors & unit_actors:
        raise LedgerMismatch('Working actors have no matching committed or staged settlement')
    expected_intent = record['advance']['intentStatus']
    # A pure time scan visits all remaining slots without consuming input.
    # Confirmed skips have their own persisted success records; use those
    # rather than mistaking the scan's visited set for a skip.
    has_skip = any(entry['operation'] == 'checkpoint_record_skip' and
                   entry['data'].get('pointId') == work['pointId']
                   for entry in record['idempotency'].values())
    if expected_intent == 'pending' and (work['units'] or has_skip):
        expected_intent = 'consumed'
    if progress.intentStatus != expected_intent:
        raise LedgerMismatch('Working input status differs from confirmed settlements or skips')
    cursor = next((index for index, actor in enumerate(order) if actor not in visited), len(order))
    if (not acted <= visited or not visited <= set(order) or progress.cursor != cursor or
            not set(record['round']['actedIds']) <= acted or
            not set(record['round']['visitedIds']) <= visited):
        raise LedgerMismatch('Working progress disagrees with the frozen order or committed progress')
    group = work['pendingGroup']
    if ((work['phase'] == 'select_actor' and group is not None) or
            (work['phase'] != 'select_actor' and group is None) or
            (group and group['closed'] != (work['phase'] == 'settle_group'))):
        raise LedgerMismatch('Working phase disagrees with its pending group')
    if work['sealed']:
        fields = dict(pointId=work['pointId'], kind=work['kind'], baseline=work['baseline'],
                      timeAdvance=work['timeAdvance'], timeLocked=True,
                      working=progress.model_dump(mode='json'), timeScanComplete=work['timeScanComplete'],
                      settledUnits=[{key: unit[key] for key in ('unitId', 'groupId', 'memberIds', 'contentHash')}
                                    for unit in work['units']])
        digest = canonical_digest(prefix_projection(record['worldId'], fields, work['timeScan']))
        if digest != work['prefixDigest']:
            raise LedgerMismatch('Sealed work content differs from its prefix digest')
