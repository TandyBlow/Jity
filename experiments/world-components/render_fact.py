"""Deterministic fact display: render a committed fact as a sentence, by fact type.

This is not a general Chinese renderer and it does not paraphrase. Each fact type gets its own
sentence shape built only from fields that the record actually carries. When the fields are not
enough to state the fact, the renderer returns a contract gap instead of guessing a filler.

Returned per fact:
  sentence   the deterministic sentence, or None when the fields are insufficient
  fields     which required fields were present
  gap        the name of the missing field set, when sentence is None
  complete   True only when every required field is present
"""
import json

DIRECTION_WORD = {'上': '上', '下': '下', '平': ''}


def _text(fact, key):
    value = fact.get(key)
    return value if isinstance(value, str) and value.strip() else None


def render(fact):
    kind = fact.get('kind')
    if kind == 'moved':
        name, src, dst = _text(fact, 'name'), _text(fact, 'from'), _text(fact, 'to')
        missing = [k for k, v in (('name', name), ('from', src), ('to', dst)) if not v]
        if missing:
            return {'sentence': None, 'gap': 'moved lacks ' + ','.join(missing),
                    'fields': {'name': bool(name), 'from': bool(src), 'to': bool(dst)}, 'complete': False}
        direction = fact.get('direction')
        if direction == '上':
            body = '%s从%s上到%s' % (name, src, dst)
        elif direction == '下':
            body = '%s从%s下到%s' % (name, src, dst)
        else:
            body = '%s从%s到%s' % (name, src, dst)
        return {'sentence': body + '。', 'gap': None,
                'fields': {'name': True, 'from': True, 'to': True, 'direction': direction is not None},
                'complete': True,
                'note': '' if direction is not None else 'direction field absent; the sentence does not claim height'}

    if kind == 'sanity_changed':
        name, low, high = _text(fact, 'name'), fact.get('from'), fact.get('to')
        if not name or not isinstance(low, int) or not isinstance(high, int):
            return {'sentence': None, 'gap': 'sanity lacks name or a numeric from/to',
                    'fields': {'name': bool(name), 'from': isinstance(low, int), 'to': isinstance(high, int)},
                    'complete': False}
        word = '下降' if high < low else '上升' if high > low else '不变'
        return {'sentence': '%s的理智%s（%d→%d）。' % (name, word, low, high), 'gap': None,
                'fields': {'name': True, 'from': True, 'to': True}, 'complete': True}

    if kind in ('appearance_changed', 'outcome', 'personality_changed'):
        body_key = 'resultText' if kind == 'outcome' else 'text'
        name = _text(fact, 'name')
        text = _text(fact, body_key) or _text(fact, 'text')
        relation = _text(fact, 'relation')
        if relation:
            anchor, other, role = name, _text(fact, 'other'), _text(fact, 'role')
            if not anchor or not other or not role:
                return {'sentence': None,
                        'gap': 'relation fact lacks anchor, the other entity, or which side is the location',
                        'fields': {'name': bool(anchor), 'other': bool(other), 'role': bool(role)},
                        'complete': False}
            if role == 'locationReference':
                sentence = '%s在%s%s的%s%s。' % (relation, anchor,
                                                 '里' if relation in ('堆', '插') else '上', other, text or '')
            else:
                sentence = '%s%s着%s，%s。' % (anchor, relation, other, text or '')
            return {'sentence': sentence, 'gap': None,
                    'fields': {'name': True, 'other': True, 'relation': True, 'role': True},
                    'complete': True}
        if not name or not text:
            return {'sentence': None, 'gap': '%s lacks name or text' % kind,
                    'fields': {'name': bool(name), 'text': bool(text)}, 'complete': False}
        return {'sentence': '%s：%s。' % (name, text), 'gap': None,
                'fields': {'name': True, 'text': True}, 'complete': True,
                'note': ('no structured relation field: the subject and the original fact text are shown, '
                         'the direction is not verified')}

    if kind == 'no_change':
        scope, span = _text(fact, 'name'), _text(fact, 'scope')
        if not span:
            # without a scope field the record cannot tell a quiet turn from one quiet entity, so the
            # turn level sentence is not derivable here
            return {'sentence': None,
                    'gap': 'no_change carries no scope: an entity or action scope cannot be widened to the turn',
                    'fields': {'name': bool(scope), 'scope': False}, 'complete': False}
        if scope:
            return {'sentence': '%s这一回合没有新的变化。' % scope, 'gap': None,
                    'fields': {'name': True, 'scope': True}, 'complete': True}
        return {'sentence': '这一回合没有新的变化。', 'gap': None,
                'fields': {'scope': True}, 'complete': True}

    return {'sentence': None, 'gap': 'unknown fact kind: %s' % kind, 'fields': {}, 'complete': False}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--units', action='append', required=True)
    parser.add_argument('--out', default='artifacts/next-runs/display-r1/render.json')
    args = parser.parse_args()
    rows, gaps = [], {}
    for name in args.units:
        for line in open(name, encoding='utf-8'):
            if not line.strip():
                continue
            unit = json.loads(line)
            result = render(unit['fact'])
            rows.append({'unitId': unit['unitId'], 'fact': unit['fact'], **result})
            if result['gap']:
                gaps.setdefault(result['gap'], []).append(unit['unitId'])
    import pathlib
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'rows': rows, 'gaps': gaps}, ensure_ascii=False, indent=1) + '\n',
                      encoding='utf-8', newline='\n')
    complete = sum(1 for r in rows if r['complete'])
    print('units %d complete %d gaps %d' % (len(rows), complete, len(rows) - complete))
    for gap, ids in sorted(gaps.items(), key=lambda kv: -len(kv[1])):
        print('  %-60s %d  %s' % (gap, len(ids), ','.join(ids[:4])))


if __name__ == '__main__':
    main()
