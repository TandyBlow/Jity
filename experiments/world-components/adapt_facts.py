"""Read-only adapter: committed record -> display facts, with provenance.

The adapter never reads the world head to answer "where was this entity before". It reads the point,
follows `previous_point_id`, and takes the predecessor's checkpoint; if that checkpoint is absent the
fact becomes a gap rather than an inference. Nothing is written: the database is opened read-only.

Per fact the adapter records where every value came from: the current point, the previous point, the
entity, the fields it read, the sentence it produced or the gap that stopped it.
"""
import argparse
import json
import pathlib
import sqlite3

DIRECTION = {'上': '上', '下': '下', '平': ''}


def connect(path):
    return sqlite3.connect('file:%s?mode=ro' % pathlib.Path(path).as_posix(), uri=True)


def load_point(db, world_id, point_id):
    db.row_factory = sqlite3.Row
    row = db.execute('SELECT * FROM world_points WHERE world_id=? AND id=?', (world_id, point_id)).fetchone()
    return dict(row) if row else None


def load_checkpoint(db, world_id, point_id):
    row = db.execute('SELECT state_json, state_digest FROM world_state_checkpoints WHERE world_id=? AND point_id=?',
                     (world_id, point_id)).fetchone()
    if row is None:
        return None
    return {'state': json.loads(row[0]), 'digest': row[1]}


def labels(db, world_id):
    """Names live in the world's initial record, not in the per point state."""
    row = db.execute('SELECT initial_json FROM worlds WHERE id=?', (world_id,)).fetchone()
    if row is None:
        return {}
    initial = json.loads(row[0])
    names = {}
    for group in ('locations', 'characters', 'items'):
        for key, value in (initial.get(group) or {}).items():
            names[key] = value.get('name') or key
    return names


def name_of(names, entity_id):
    return names.get(entity_id, entity_id)


def adapt_point(db, world_id, point_id, names=None):
    point = load_point(db, world_id, point_id)
    if point is None:
        return [], [{'pointId': point_id, 'gap': 'point not found'}]
    facts, gaps = [], []
    current = load_checkpoint(db, world_id, point_id)
    if current is None:
        gaps.append({'pointId': point_id, 'gap': 'current checkpoint missing'})
        return facts, gaps
    delta = json.loads(point['delta_json'] or '{}')
    previous_id = point['previous_point_id']
    previous = load_checkpoint(db, world_id, previous_id) if previous_id else None
    provenance = {
        'worldId': world_id, 'pointId': point_id, 'sequence': point['sequence'],
        'previousPointId': previous_id,
        'currentCheckpointDigest': current['digest'][:12],
        'currentDigestMatchesPoint': current['digest'] == point['state_digest'],
        'previousPointFound': previous_id is not None,
        'previousCheckpointFound': previous is not None,
        'branchLinkedFrom': point['linked_from_point_id'],
    }
    if previous and previous_id:
        prev_point = load_point(db, world_id, previous_id)
        provenance['previousDigestMatchesPoint'] = bool(prev_point) and previous['digest'] == prev_point['state_digest']
        provenance['previousSequence'] = prev_point['sequence'] if prev_point else None

    if not delta:
        facts.append({'kind': 'no_change', 'sentence': '第%d点没有实体变化。' % point['sequence'],
                      'complete': True, 'scope': 'point', 'provenance': dict(provenance, entityId=None,
                                                                             fieldsRead=['delta_json'],
                                                                             adapted='empty delta at this point')})
        return facts, gaps

    for entity_id, change in delta.items():
        fields = sorted(k for k, v in change.items() if k != 'entityId' and v not in (None, [], {}))
        base = dict(provenance, entityId=entity_id, fieldsRead=fields)

        if change.get('positionSet') is not None:
            target = change['positionSet']
            to_id = target.get('containerId')
            if previous is None:
                gaps.append(dict(base, gap='position change needs the predecessor state; none is committed'))
            else:
                before = (previous['state'].get('characters') or {}).get(entity_id) or \
                         (previous['state'].get('items') or {}).get(entity_id) or {}
                from_id = (before.get('position') or {}).get('containerId')
                if from_id is None:
                    gaps.append(dict(base, gap='the predecessor state has no position for this entity'))
                elif from_id == to_id:
                    gaps.append(dict(base, gap='position is unchanged; no fact to display'))
                else:
                    places = names or {}
                    sentence = '%s从%s到%s' % (name_of(places, entity_id),
                                              places.get(from_id, from_id), places.get(to_id, to_id))
                    if target.get('slotId'):
                        sentence += '的%s上' % target['slotId']
                    facts.append({'kind': 'moved', 'sentence': sentence + '。', 'complete': True,
                                  'from': from_id, 'to': to_id,
                                  'provenance': dict(base, fieldsRead=fields + ['previous.position'],
                                                     adapted='origin read from %s' % previous_id)})

        if change.get('sanitySet') is not None:  # zero is a value, not an absence
            new_value = change['sanitySet']
            if previous is None:
                gaps.append(dict(base, gap='sanity change needs the predecessor state; none is committed'))
            else:
                before = (previous['state'].get('characters') or {}).get(entity_id) or {}
                old_value = before.get('sanity')
                if not isinstance(old_value, int):
                    gaps.append(dict(base, gap='the predecessor state has no sanity for this entity'))
                else:
                    word = '下降' if new_value < old_value else '上升' if new_value > old_value else '不变'
                    facts.append({'kind': 'sanity_changed',
                                  'sentence': '%s的理智%s（%d→%d）。' % (name_of(names, entity_id),
                                                                     word, old_value, new_value),
                                  'complete': True, 'from': old_value, 'to': new_value,
                                  'provenance': dict(base, fieldsRead=fields + ['previous.sanity'],
                                                     adapted='previous value read from %s' % previous_id)})

        for change_list, kind in (('appearanceChanges', 'appearance_changed'),
                                  ('personalityChanges', 'personality_changed')):
            for entry in change.get(change_list) or []:
                text = entry.get('text')
                if text:
                    facts.append({'kind': kind, 'sentence': '%s：%s。' % (name_of(names, entity_id), text),
                                  'complete': True,
                                  'note': 'the record carries the text only; no direction is verified',
                                  'provenance': dict(base, fieldsRead=fields + [change_list],
                                                     adapted='text copied verbatim')})

        if change.get('tasksAchieved') or change.get('subtasksAdded'):
            gaps.append(dict(base, gap='task delta has no display shape yet'))

    return facts, gaps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--world', action='append')
    parser.add_argument('--point', action='append')
    parser.add_argument('--out-dir', default='artifacts/next-runs/adapt-r1')
    args = parser.parse_args()
    db = connect(args.db)
    worlds = args.world or [r[0] for r in db.execute('SELECT id FROM worlds ORDER BY id')]
    facts, gaps, units = [], [], []
    for world_id in worlds:
        names = labels(db, world_id)
        points = args.point or [r[0] for r in db.execute(
            'SELECT id FROM world_points WHERE world_id=? ORDER BY sequence', (world_id,))]
        for point_id in points:
            point_facts, point_gaps = adapt_point(db, world_id, point_id, names)
            facts.extend(point_facts)
            gaps.extend(point_gaps)
            units.append({'worldId': world_id, 'pointId': point_id, 'facts': len(point_facts),
                          'gaps': len(point_gaps)})
    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'facts.json').write_text(json.dumps({'facts': facts}, ensure_ascii=False, indent=1) + '\n',
                                    encoding='utf-8', newline='\n')
    (out / 'gaps.json').write_text(json.dumps({'gaps': gaps}, ensure_ascii=False, indent=1) + '\n',
                                   encoding='utf-8', newline='\n')
    (out / 'points.json').write_text(json.dumps({'points': units}, ensure_ascii=False, indent=1) + '\n',
                                     encoding='utf-8', newline='\n')
    print('points %d facts %d gaps %d' % (len(units), len(facts), len(gaps)))
    for gap in gaps:
        print('  %-6s %-10s %s' % (gap.get('pointId'), gap.get('entityId'), gap['gap']))


if __name__ == '__main__':
    main()
