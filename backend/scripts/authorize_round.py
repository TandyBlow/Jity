"""Attach the authoritative authorization to a round input (server side)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

from app.services.world.provenance import authorize  # noqa: E402


def elapsed(points, a, b):
    by_id = {p['id']: p for p in points}
    chain, cur = [], a
    while cur is not None:
        chain.append(cur)
        if cur == b:
            break
        nxt = [p['id'] for p in points if p.get('previousPointId') == cur]
        cur = nxt[0] if len(nxt) == 1 else None
    else:
        return None
    if not chain or chain[-1] != b:
        return None
    total = 0
    for point_id in chain[1:]:
        time_json = by_id[point_id].get('time') or {}
        if time_json.get('boundary') == 'elapsed':
            duration = time_json.get('duration') or {}
            unit = {'second': 1, 'minute': 60, 'hour': 3600}.get(duration.get('unit'), 0)
            total += int(duration.get('amount') or 0) * unit
    return total


def main(source, out):
    payload = json.loads(Path(source).read_text(encoding='utf-8'))
    units, points = payload['units'], payload['points']
    facts = {u['factId']: {'factId': u['factId'], 'worldId': payload['worldId'],
                           'pointIds': (u['pointId'],),
                           'evidenceIds': (u['evidenceId'],), 'sustained': False}
             for u in units}
    index = {u['evidenceId']: u['pointId'] for u in units}
    by_fact = {u['factId']: u for u in units}
    relations = [{'type': 'before', 'fromFactId': item['fromFactId'],
                  'toFactId': item['toFactId'],
                  'evidence': [{'type': 'event', 'evidenceId': by_fact[item['fromFactId']]['evidenceId']},
                               {'type': 'event', 'evidenceId': by_fact[item['toFactId']]['evidenceId']}]}
                 for item in payload['requestedRelations']]
    verdict = authorize(facts, relations, points, index)
    for relation in verdict['relations']:
        relation['elapsedSeconds'] = elapsed(
            points, by_fact[relation['fromFactId']]['pointId'],
            by_fact[relation['toFactId']]['pointId'])
    payload['authorization'] = verdict
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'verdict': verdict['verdict'],
                      'accepted': [(r['fromFactId'], r['toFactId'], r['elapsedSeconds'])
                                   for r in verdict['relations']],
                      'rejected': len(verdict['rejected'])}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
