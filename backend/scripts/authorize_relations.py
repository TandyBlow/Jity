"""Authorize the relations of a real chain and write the N3 payload.

Input: the chain result the browser produced (``provenance-browser.json``) and
the authority database it was written to. Output: a plan fragment N3 can
consume unchanged.
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

from app.services.world.provenance import authorize, bind_fact  # noqa: E402


def load_points(db_path, world_id):
    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        'SELECT id,previous_point_id,time_json FROM world_points'
        ' WHERE world_id=? ORDER BY sequence', (world_id,)).fetchall()
    connection.close()
    return [{'id': r[0], 'worldId': world_id, 'previousPointId': r[1],
             'time': json.loads(r[2]) if r[2] else None} for r in rows]


def main(chain_path, db_path, out_path):
    chain = json.loads(Path(chain_path).read_text(encoding='utf-8'))
    world_id = chain['worldId']
    refs = chain['evidenceRefs']
    point_a, point_b = chain['pointA']['id'], chain['pointB']['id']
    evidence_a = next(r['evidenceId'] for r in refs if r['pointId'] == point_a)
    evidence_b = next(r['evidenceId'] for r in refs if r['pointId'] == point_b)
    facts = {'f0': bind_fact('f0', world_id, [point_a], [evidence_a]),
             'f1': bind_fact('f1', world_id, [point_b], [evidence_b])}
    points = load_points(db_path, world_id)
    index = {evidence_a: point_a, evidence_b: point_b}
    relation = {'type': 'before', 'fromFactId': 'f0', 'toFactId': 'f1',
                'evidence': [{'type': 'event', 'evidenceId': evidence_a},
                             {'type': 'event', 'evidenceId': evidence_b}]}
    payload = authorize(facts, [relation], points, index)
    payload['sources'] = {'f0': facts['f0'], 'f1': facts['f1']}
    payload['points'] = [{'id': p['id'], 'previousPointId': p['previousPointId'],
                          'time': p['time']} for p in points]
    Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                              encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return 0 if payload['verdict'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main(*sys.argv[1:4]))
