"""Verify the browser chain with the authoritative Python validator.

Reads the ids the browser chain reported (``provenance-browser.json``) and the
timeline the authority actually stored, then runs the positive case plus three
negative controls against the same real data:

  N1 fact without provenance (no event reference)
  N2 point-only evidence (submission order, not event order)
  N3 zero time advance between the two evidence points
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

from app.services.world.provenance import bind_fact, validate_relations  # noqa: E402

DB = ROOT / '.local/world-chain-full/prov2.db'
CHAIN = ROOT / '.local/world-chain-full/provenance-browser.json'
OUT = ROOT / '.local/world-chain-full/provenance-browser-verify.json'


def load_points(world_id):
    connection = sqlite3.connect(DB)
    rows = connection.execute(
        'SELECT id,sequence,previous_point_id,time_json FROM world_points'
        ' WHERE world_id=? ORDER BY sequence', (world_id,)).fetchall()
    connection.close()
    return [{'id': r[0], 'worldId': world_id, 'previousPointId': r[2],
             'time': json.loads(r[3]) if r[3] else None} for r in rows]


def main():
    chain = json.loads(CHAIN.read_text(encoding='utf-8'))
    world_id = chain['worldId']
    point_a, point_b = chain['pointA']['id'], chain['pointB']['id']
    refs = chain['evidenceRefs']
    evidence_a = next(r['evidenceId'] for r in refs if r['pointId'] == point_a)
    evidence_b = next(r['evidenceId'] for r in refs if r['pointId'] == point_b)
    points = load_points(world_id)
    index = {evidence_a: point_a, evidence_b: point_b}
    facts = {'f0': bind_fact('f0', world_id, [point_a], [evidence_a]),
             'f1': bind_fact('f1', world_id, [point_b], [evidence_b])}

    positive = [{'type': 'before', 'fromFactId': 'f0', 'toFactId': 'f1',
                 'evidence': [{'type': 'event', 'evidenceId': evidence_a},
                              {'type': 'event', 'evidenceId': evidence_b}]}]
    results = {'worldId': world_id, 'pointA': point_a, 'pointB': point_b,
               'evidenceRefs': [evidence_a, evidence_b],
               'positive': validate_relations(positive, facts, points, index)}

    point_only = [{'type': 'before', 'fromFactId': 'f0', 'toFactId': 'f1',
                   'evidence': [{'type': 'point', 'pointId': point_a},
                                {'type': 'point', 'pointId': point_b}]}]
    results['N2_pointOnly'] = validate_relations(point_only, facts, points, index)

    zeroed = [dict(p) for p in points]
    for p in zeroed:
        if p['id'] == point_b:
            p['time'] = {'boundary': 'elapsed',
                         'duration': {'amount': 0, 'unit': 'second'}}
    results['N3_zeroAdvance'] = validate_relations(positive, facts, zeroed, index)

    try:
        bind_fact('f9', world_id, [point_a], [])
        results['N1_missingProvenance'] = ['未被拒绝（异常）']
    except Exception as error:  # noqa: BLE001 - the refusal is the point
        results['N1_missingProvenance'] = [f'拒绝：{error}']

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=1))
    ok = (results['positive'] == []
          and any('只有点证据' in p for p in results['N2_pointOnly'])
          and any('时间推进为 0' in p for p in results['N3_zeroAdvance'])
          and results['N1_missingProvenance'][0].startswith('拒绝'))
    print('VERIFY', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
