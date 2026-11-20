"""Evidence ledger: real changes recorded at the same commit as the point.

Rules this module keeps:
  * every committed point gets exactly one meta row: ``recorded`` when the
    point carried entity deltas, ``none`` when the settlement asserted that
    nothing changed;
  * a point with no meta row is ``unrecorded`` — legacy history or a commit
    that never went through this writer. Old points are never backfilled;
  * evidence is derived from ``point.entityDeltas`` only, so it cannot drift
    from the state that was applied at commit time.
"""

import json
from pathlib import Path

CONTRACT = 'world-evidence-v1'
DDL = Path(__file__).with_name('world_evidence_v1.sql')
KINDS = ('position', 'appearance', 'personality', 'sanity', 'task_achieved', 'subtask_added')


class EvidenceConflict(ValueError):
    """Recorded evidence differs from what the committed point says."""


def ensure_schema(connection):
    installed = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_evidence_schema'").fetchone()
    if installed:
        version = connection.execute('SELECT version FROM world_evidence_schema').fetchall()
        if version != [(1,)]:
            raise EvidenceConflict('Unsupported evidence schema version')
        return
    script = DDL.read_text(encoding='utf-8')
    for statement in _statements(script):
        connection.execute(statement)
    connection.execute('INSERT INTO world_evidence_schema VALUES(1)')


def _statements(script):
    import sqlite3
    statement = ''
    for line in script.splitlines(keepends=True):
        if line.strip().startswith('--'):
            continue
        statement += line
        if sqlite3.complete_statement(statement):
            if statement.strip():
                yield statement
            statement = ''
    if statement.strip():
        yield statement


def events_of_point(world_id, point):
    """Deterministic evidence items for one point. Empty list is legal."""
    events = []
    for entity_id, delta in point.entityDeltas.items():
        dumped = delta.model_dump(mode='json')
        if dumped.get('positionSet') is not None:
            events.append((entity_id, 'position', 'positionSet', dumped['positionSet']))
        for kind, key in (('appearance', 'appearanceChanges'),
                          ('personality', 'personalityChanges')):
            for change in dumped.get(key) or []:
                events.append((entity_id, kind, change['id'], change))
        if dumped.get('sanitySet') is not None:
            events.append((entity_id, 'sanity', 'sanitySet', dumped['sanitySet']))
        for task_id in dumped.get('tasksAchieved') or []:
            events.append((entity_id, 'task_achieved', task_id, {'taskId': task_id}))
        for task in dumped.get('subtasksAdded') or []:
            events.append((entity_id, 'subtask_added', task['id'], task))
    return [dict(evidenceId=f'{point.id}/{entity_id}/{kind}/{key}', worldId=world_id,
                 pointId=point.id, sequence=point.sequence, entityId=entity_id,
                 kind=kind, itemKey=key, payload=payload)
            for entity_id, kind, key, payload in events]


def delta_status(point):
    return 'recorded' if point.entityDeltas else 'none'


def record_point(connection, world_id, point):
    """Write meta + evidence rows for one point inside the caller's transaction."""
    ensure_schema(connection)
    status = delta_status(point)
    row = (world_id, point.id, point.sequence, point.previousPointId, status, CONTRACT)
    existing = connection.execute(
        'SELECT sequence,previous_point_id,delta_status,contract FROM world_point_evidence'
        ' WHERE world_id=? AND point_id=?', (world_id, point.id)).fetchone()
    if existing is not None:
        if tuple(existing) != (point.sequence, point.previousPointId, status, CONTRACT):
            raise EvidenceConflict(f'evidence meta differs for {point.id}')
        return
    connection.execute('INSERT INTO world_point_evidence VALUES(?,?,?,?,?,?)', row)
    for event in events_of_point(world_id, point):
        connection.execute(
            'INSERT INTO world_evidence VALUES(?,?,?,?,?,?,?,?)',
            (event['evidenceId'], world_id, point.id, point.sequence, event['entityId'],
             event['kind'], event['itemKey'], json.dumps(event['payload'], ensure_ascii=False,
                                                         sort_keys=True)))


def read_point(connection, world_id, point_id):
    """-> {'deltaStatus','sequence','previousPointId','events':[...]} or None."""
    ensure_schema(connection)
    meta = connection.execute(
        'SELECT sequence,previous_point_id,delta_status FROM world_point_evidence'
        ' WHERE world_id=? AND point_id=?', (world_id, point_id)).fetchone()
    if meta is None:
        return None
    events = connection.execute(
        'SELECT evidence_id,entity_id,kind,item_key,payload_json FROM world_evidence'
        ' WHERE world_id=? AND point_id=? ORDER BY evidence_id',
        (world_id, point_id)).fetchall()
    return {'pointId': point_id, 'sequence': meta[0], 'previousPointId': meta[1],
            'deltaStatus': meta[2],
            'events': [{'evidenceId': e[0], 'entityId': e[1], 'kind': e[2], 'itemKey': e[3],
                        'payload': json.loads(e[4])} for e in events]}
