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


REPLAY = {'module': None, 'error': None}


def load_replay(backend):
    """Import the production replay so a missing checkpoint is not treated as an unrecoverable state."""
    if REPLAY['module'] is not None or REPLAY['error'] is not None:
        return REPLAY['module']
    import sys
    sys.path.insert(0, str(pathlib.Path(backend)))
    try:
        from app.database.world_repository import replay_state, state_digest  # noqa: F401
        REPLAY['module'] = (replay_state, state_digest)
    except Exception as error:  # keep the adapter usable without the backend
        REPLAY['error'] = '%s: %s' % (type(error).__name__, error)
    return REPLAY['module']


def resolve_state(db, world_id, point_id, backend):
    """Checkpoint first, production replay second. Both are reported, neither is assumed."""
    checkpoint = load_checkpoint(db, world_id, point_id)
    point = load_point(db, world_id, point_id)
    result = {'state': None, 'source': None, 'checkpointFound': checkpoint is not None,
              'checkpointDigestMatchesPoint': bool(checkpoint and point and checkpoint['digest'] == point['state_digest']),
              'replayOk': False, 'replayAgreesWithCheckpoint': None, 'replayError': None,
              'replayedDigest': None, 'checkpointDigest': checkpoint['digest'] if checkpoint else None}
    module = load_replay(backend)
    if module is not None:
        replay_state, state_digest = module
        try:
            state = replay_state(db, world_id, point_id)
            digest = state_digest(state)
            result['replayOk'] = True
            result['replayedDigest'] = digest
            result['replayAgreesWithCheckpoint'] = (digest == checkpoint['digest']
                                                    if checkpoint is not None else None)
            result['state'] = json.loads(state.model_dump_json())
            result['source'] = 'replay'
        except Exception as error:
            result['replayError'] = '%s: %s' % (type(error).__name__, error)
    if checkpoint is not None and result['checkpointDigestMatchesPoint']:
        if result['state'] is None:
            result['state'] = checkpoint['state']
            result['source'] = 'checkpoint'
    elif checkpoint is not None and result['state'] is None:
        result['source'] = 'checkpoint rejected: digest does not match the point'
    return result


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


DEFAULT_BACKEND = 'D:/others/Jity/.local/agent-worktree/backend'


def adapt_point(db, world_id, point_id, names=None, backend=DEFAULT_BACKEND):
    point = load_point(db, world_id, point_id)
    if point is None:
        return [], [{'pointId': point_id, 'gap': 'point not found'}]
    facts, gaps, not_displayed = [], [], []
    current = resolve_state(db, world_id, point_id, backend)
    delta = json.loads(point['delta_json'] or '{}')
    previous_id = point['previous_point_id']
    previous = resolve_state(db, world_id, previous_id, backend) if previous_id else None
    if current['state'] is None:
        gaps.append({'pointId': point_id, 'gap': 'state not recoverable',
                     'checkpointFound': current['checkpointFound'],
                     'replayError': current['replayError'],
                     'checkpointDigestMatchesPoint': current['checkpointDigestMatchesPoint']})
        return facts, gaps, not_displayed
    provenance = {
        'worldId': world_id, 'pointId': point_id, 'sequence': point['sequence'],
        'previousPointId': previous_id,
        'stateSource': current['source'],
        'currentCheckpointDigest': (current['checkpointDigest'] or '')[:12],
        'currentDigestMatchesPoint': current['checkpointDigestMatchesPoint'],
        'replayOk': current['replayOk'],
        'replayAgreesWithCheckpoint': current['replayAgreesWithCheckpoint'],
        'replayError': current['replayError'],
        'previousPointFound': previous_id is not None,
        'previousStateSource': previous['source'] if previous else None,
        'previousCheckpointFound': bool(previous and previous['checkpointFound']),
        'branchLinkedFrom': point['linked_from_point_id'],
    }
    if previous and previous_id and previous['state'] is not None:
        prev_point = load_point(db, world_id, previous_id)
        provenance['previousDigestMatchesPoint'] = previous['checkpointDigestMatchesPoint']
        provenance['previousSequence'] = prev_point['sequence'] if prev_point else None

    if not delta:
        facts.append({'kind': 'no_change', 'sentence': '第%d点没有实体变化。' % point['sequence'],
                      'complete': True, 'scope': 'point', 'provenance': dict(provenance, entityId=None,
                                                                             fieldsRead=['delta_json'],
                                                                             adapted='empty delta at this point')})
        return facts, gaps, not_displayed

    for entity_id, change in delta.items():
        fields = sorted(k for k, v in change.items() if k != 'entityId' and v not in (None, [], {}))
        base = dict(provenance, entityId=entity_id, fieldsRead=fields)

        if change.get('positionSet') is not None:
            target = change['positionSet']
            to_id = target.get('containerId')
            if previous is None or previous['state'] is None:
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
            if previous is None or previous['state'] is None:
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
            not_displayed.append(dict(base, reason='task delta has no display shape yet, so it is not shown',
                                      notAChange=True))

    return facts, gaps, not_displayed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--backend', default=DEFAULT_BACKEND)
    parser.add_argument('--world', action='append')
    parser.add_argument('--point', action='append')
    parser.add_argument('--out-dir', default='artifacts/next-runs/adapt-r2')
    args = parser.parse_args()
    db = connect(args.db)
    worlds = args.world or [r[0] for r in db.execute('SELECT id FROM worlds ORDER BY id')]
    facts, gaps, not_displayed, blocks = [], [], [], []
    for world_id in worlds:
        names = labels(db, world_id)
        points = args.point or [r[0] for r in db.execute(
            'SELECT id FROM world_points WHERE world_id=? ORDER BY sequence', (world_id,))]
        for point_id in points:
            point = load_point(db, world_id, point_id)
            point_facts, point_gaps, point_unshown = adapt_point(db, world_id, point_id, names, args.backend)
            facts.extend(point_facts)
            gaps.extend(point_gaps)
            not_displayed.extend(point_unshown)
            blocks.append({'worldId': world_id, 'pointId': point_id,
                           'sequence': point['sequence'] if point else None,
                           'kind': point['kind'] if point else None,
                           'previousPointId': point['previous_point_id'] if point else None,
                           'delta': json.loads(point['delta_json']) if point and point['delta_json'] else None,
                           'sentences': [f['sentence'] for f in point_facts],
                           'notDisplayed': [u['reason'] for u in point_unshown],
                           'gaps': [g['gap'] for g in point_gaps],
                           'provenance': [{'entityId': f['provenance'].get('entityId'),
                                           'stateSource': f['provenance'].get('stateSource'),
                                           'fieldsRead': f['provenance'].get('fieldsRead'),
                                           'checkpointDigestMatchesPoint': f['provenance'].get('currentDigestMatchesPoint'),
                                           'replayOk': f['provenance'].get('replayOk'),
                                           'replayAgreesWithCheckpoint': f['provenance'].get('replayAgreesWithCheckpoint')}
                                          for f in point_facts]})
    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, payload in (('facts.json', {'facts': facts}), ('gaps.json', {'gaps': gaps}),
                          ('not-displayed.json', {'notDisplayed': not_displayed}),
                          ('preview.json', {'blocks': blocks})):
        (out / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + chr(10),
                                encoding='utf-8', newline=chr(10))
    lines = []
    for block in blocks:
        lines.append('[%s %s seq=%s] prev=%s delta=%s' % (
            block['worldId'], block['pointId'], block['sequence'], block['previousPointId'],
            json.dumps(block['delta'], ensure_ascii=False) if block['delta'] is not None else 'null'))
        for sentence, prov in zip(block['sentences'], block['provenance']):
            lines.append('    show  %s' % sentence)
            lines.append('          source=%s fields=%s replayOk=%s agrees=%s' % (
                prov['stateSource'], ','.join(prov['fieldsRead'] or []), prov['replayOk'],
                prov['replayAgreesWithCheckpoint']))
        for reason in block['notDisplayed']:
            lines.append('    unshown  %s' % reason)
        for gap in block['gaps']:
            lines.append('    gap      %s' % gap)
    (out / 'preview.txt').write_text(chr(10).join(lines) + chr(10), encoding='utf-8', newline=chr(10))
    print('points %d facts %d gaps %d notDisplayed %d' % (len(blocks), len(facts), len(gaps), len(not_displayed)))
    for gap in gaps:
        print('  GAP  %-8s %-10s %s' % (gap.get('pointId'), gap.get('entityId'), gap['gap']))
    for item in not_displayed:
        print('  UNSHOWN %-8s %-10s %s' % (item.get('pointId'), item.get('entityId'), item['reason']))


if __name__ == '__main__':
    main()
