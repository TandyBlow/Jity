"""Turn committed points into the single pipeline input.

Reads the authority database only: points, time advance, evidence rows, entity
names. Emits one JSON the pipeline consumes without any manual file juggling:

  {"worldId", "roundId", "units":[{factId, entityId, name, kind, text,
                                   pointId, evidenceId, sequence}],
   "points":[{id, previousPointId, time}],
   "requestedRelations":[{type, fromFactId, toFactId}]}
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

KIND_MAP = {'appearance': 'appearance_changed', 'personality': 'personality_changed',
            'position': 'moved', 'sanity': 'sanity_changed'}


def entity_names(connection, world_id):
    row = connection.execute('SELECT initial_json FROM worlds WHERE id=?',
                             (world_id,)).fetchone()
    initial = json.loads(row[0])
    return {key: value.get('name') for key, value in initial['characters'].items()}


def points_of(connection, world_id):
    rows = connection.execute(
        'SELECT id,sequence,previous_point_id,time_json FROM world_points'
        ' WHERE world_id=? ORDER BY sequence', (world_id,)).fetchall()
    return [{'id': r[0], 'sequence': r[1], 'previousPointId': r[2],
             'time': json.loads(r[3]) if r[3] else None} for r in rows]


def units_of(connection, world_id, names):
    rows = connection.execute(
        'SELECT evidence_id,point_id,sequence,entity_id,kind,item_key,payload_json'
        ' FROM world_evidence WHERE world_id=? ORDER BY sequence,entity_id,item_key',
        (world_id,)).fetchall()
    units, counter = [], 0
    for evidence_id, point_id, sequence, entity_id, kind, item_key, payload in rows:
        if kind not in KIND_MAP:
            continue
        data = json.loads(payload)
        text = data.get('text') or data.get('goal') or item_key
        units.append({'factId': f'f{counter}', 'entityId': entity_id,
                      'name': names.get(entity_id, entity_id),
                      'kind': KIND_MAP[kind], 'text': text,
                      'pointId': point_id, 'evidenceId': evidence_id,
                      'sequence': sequence})
        counter += 1
    return units


def main(db_path, world_id, plan_path, out_path, points_filter=None):
    connection = sqlite3.connect(db_path)
    names = entity_names(connection, world_id)
    units = units_of(connection, world_id, names)
    points = points_of(connection, world_id)
    if points_filter:
        wanted = set(points_filter)
        units = [u for u in units if u['pointId'] in wanted]
        points = [p for p in points if p['id'] in wanted
                  or p.get('previousPointId') in wanted]
        for index, unit in enumerate(units):
            unit['factId'] = f'f{index}'
    connection.close()
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8'))
    requested = [{'type': 'before', 'fromFactId': item['fromFactId'],
                  'toFactId': item['toFactId']} for item in plan['requestedRelations']]
    payload = {'worldId': world_id, 'units': units, 'points': points,
               'requestedRelations': requested}
    Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                              encoding='utf-8')
    print(json.dumps({'worldId': world_id, 'units': len(units),
                      'points': len(points), 'requested': len(requested)},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    extra = sys.argv[5].split(',') if len(sys.argv) > 5 and sys.argv[5] else None
    raise SystemExit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], extra))
