"""Three-state check of a model sentence against a committed fact.

States
  pass          the sentence carries the fields the display would state, in the supported shape
  mismatch      the sentence contradicts the fact in a way this check can name
  undetermined  this check cannot say; it is not a claim that the model wrote something wrong

Only the pass state lets a model sentence stand in for the deterministic display. Everything else
falls back to the display, because a confirmed contradiction and an unverifiable sentence are both
things the player should not be shown in place of the record.

The pattern lists are deliberately short. They cover the shapes seen in the archived outputs and
nothing else; a sentence outside them comes back undetermined rather than passed.
"""
import re

ARRIVAL = ('走到', '走进', '到了', '回到', '上到', '下到', '穿过', '走过', '上来', '下来',
           '抵达', '来到', '进了', '开了')
PATH_ONLY = ('沿着', '顺着')
STASIS = ('没有变化', '没有新的变化', '没有散', '没有动', '没有好', '没事', '没有新的事情',
          '没有别的动静', '什么也没有再发生')
IMPROVE = ('慢下来', '散了', '松开手', '匀下来', '落回去', '缓过来')
WORSEN = ('发紧', '不听使唤', '闷意', '发沉')
WORLD_ACTION = ('推开', '抱起', '抱着', '蹲到', '船头', '发光', '蹲下')
RELATION_WORDS = ('缠', '挂', '系', '套', '盖', '插', '搭', '卡', '压', '靠', '堆')


def shingles(text, size=2):
    return {text[i:i + size] for i in range(len(text) - size + 1)}


def check(fact, text):
    kind = fact.get('kind')
    name = fact.get('name') or ''
    if kind == 'moved':
        src, dst = fact.get('from') or '', fact.get('to') or ''
        if name and name not in text:
            return 'mismatch', 'subject %s missing' % name
        if dst and dst not in text:
            return 'mismatch', 'destination %s missing' % dst
        if src and src not in text:
            return 'mismatch', 'origin %s missing' % src
        tail = text
        for word in PATH_ONLY:
            head, sep, rest = tail.partition(word)
            if sep:
                tail = rest
        if any(v in text for v in ARRIVAL) or any(v in tail for v in ARRIVAL):
            return 'pass', 'name, origin, destination and an arrival are present'
        return 'mismatch', 'no arrival: the destination is only named, never reached'

    if kind == 'sanity_changed':
        low, high = fact.get('from'), fact.get('to')
        if name and name not in text:
            return 'mismatch', 'subject %s missing' % name
        if any(w in text for w in STASIS):
            return 'mismatch', 'the change is written as no change'
        if isinstance(low, int) and isinstance(high, int):
            if high < low and any(w in text for w in IMPROVE):
                return 'mismatch', 'a drop is written as an improvement'
            if high > low and any(w in text for w in WORSEN):
                return 'mismatch', 'a rise is written as a worsening'
        return 'undetermined', 'direction is neither confirmed nor contradicted'

    if kind == 'no_change':
        if any(w in text for w in WORLD_ACTION):
            return 'mismatch', 'the sentence asserts an action the record does not carry'
        if any(w in text for w in STASIS):
            return 'pass', 'an absence statement is present'
        return 'undetermined', 'no absence statement and no action either'

    if kind in ('appearance_changed', 'outcome', 'personality_changed'):
        body = fact.get('resultText') or fact.get('text') or ''
        relation = fact.get('relation')
        anchor = name
        other = fact.get('other') or ''
        role = fact.get('role')
        if relation and other and role:
            if not anchor or anchor not in text:
                return 'mismatch', 'the location entity %s is missing' % anchor
            if other not in text:
                return 'mismatch', 'the other entity %s is missing' % other
            if '%s在%s' % (relation, anchor) in text:
                return 'pass', 'the relation names the location correctly'
            if '%s%s着' % (anchor, relation) in text:
                return 'mismatch', 'the relation is reversed: the location is written as the agent'
            return 'undetermined', 'both entities are present but the relation shape is not recognised'
        if name and name not in text:
            return 'mismatch', 'subject %s missing' % name
        if any(w in text for w in STASIS):
            return 'mismatch', 'a change is written as no change'
        if '在' in body and any(w in body for w in RELATION_WORDS):
            return 'undetermined', ('the fact text is relational but the record does not say which entity is the '
                                    'location, so the direction cannot be checked')
        shared = shingles(body) & shingles(text)
        if shared:
            return 'pass', 'the subject and part of the state text are both present'
        return 'undetermined', 'the state text is not recognisable in the sentence'

    return 'undetermined', 'unknown fact kind'


def main():
    import argparse
    import json
    import pathlib
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--units', action='append', required=True)
    parser.add_argument('--texts', required=True,
                        help='JSONL with unitId, arm and text from an archived run')
    parser.add_argument('--out', default='artifacts/next-runs/display-r1/check.json')
    args = parser.parse_args()
    facts = {}
    for name in args.units:
        for line in open(name, encoding='utf-8'):
            if line.strip():
                unit = json.loads(line)
                facts[unit['unitId']] = unit['fact']
    rows = []
    for line in open(args.texts, encoding='utf-8'):
        if not line.strip():
            continue
        item = json.loads(line)
        fact = facts.get(item['unitId'])
        if fact is None:
            continue
        state, why = check(fact, item['text'])
        rows.append({'arm': item['arm'], 'unitId': item['unitId'], 'state': state, 'why': why,
                     'text': item['text']})
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'rows': rows}, ensure_ascii=False, indent=1) + '\n',
                      encoding='utf-8', newline='\n')
    print('checked', len(rows))
    counts = {}
    for row in rows:
        counts.setdefault(row['arm'], {}).setdefault(row['state'], 0)
        counts[row['arm']][row['state']] += 1
    for arm, value in sorted(counts.items()):
        print('%-14s %s' % (arm, value))


if __name__ == '__main__':
    main()
