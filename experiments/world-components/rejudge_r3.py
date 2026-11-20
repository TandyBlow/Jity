"""Re-judge the archived outputs under artifacts/scoring-rule-r3/rule.json.

Only the two places where the rule is operational are recomputed: clause 2 of a
moved unit, and the no_change allowance. Every other recorded judgement stays as
read. No generation happens here.
"""
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
RULE_PATH = ROOT / 'artifacts/scoring-rule-r3/rule.json'
RULE = json.loads(RULE_PATH.read_text(encoding='utf-8'))
RUNS = (('eval-r1', ('u240', 'a', 'b', 'c')), ('eval-r2', ('c', 'control', 'moved')))
SETS = ('cf24', 'final24', 'moved24')
REVIEWS = (('eval-r1', ROOT / 'artifacts/next-runs/eval-r1/review-r1.json'),
           ('eval-r2', ROOT / 'artifacts/next-runs/eval-r2/review-r2.json'))
MOVED = RULE['added']['movedVerbList']
ENTITIES = RULE['added']['movedEntityList']
FORMS = RULE['added']['movedAllowedForms']


def clause2(text):
    parts = text.replace(',', '，').split('，')
    return parts[1] if len(parts) > 1 else ''


def moved_violation(text):
    """Entity or body token anywhere is an addition, even inside clause 1.

    Clause 2 is checked separately for post-arrival actions. A path noun such as
    石滩 sits outside both checks; that gap is recorded in the rule file.
    """
    for token in ENTITIES:
        if token in text:
            return token
    tail = clause2(text)
    if not tail:
        return None
    for token in MOVED:
        if token in tail:
            return token
    stripped = re.sub(r'^(一直|沿着|顺着|从)', '', tail)
    if any(stripped.startswith(form) for form in FORMS):
        return None
    return 'not-movement'


def main():
    recorded = {}
    for tag, path in REVIEWS:
        for e in json.loads(path.read_text(encoding='utf-8'))['entries']:
            recorded.setdefault((tag, e['arm'], e['set'], e['unitId']), set()).add(e['kind'])
    out = {'rule': RULE['version'],
           'ruleSha256': hashlib.sha256(RULE_PATH.read_bytes()).hexdigest(),
           'note': 'added is recomputed only for moved and no_change rows; other kinds keep the '
                   'recorded judgement because they were read individually',
           'runs': {}, 'diffs': []}
    for tag, arms in RUNS:
        for arm in arms:
            for setname in SETS:
                path = ROOT / ('artifacts/next-runs/%s/%s-%s/%s-baseline.json' % (tag, arm, setname, setname))
                if not path.is_file():
                    continue
                rows = json.loads(path.read_text(encoding='utf-8'))['rows']
                recorded_added = {k[3] for k in recorded
                                  if k[:3] == (tag, arm, setname) and 'added' in recorded[k]}
                kinds = {r['unitId']: r['kind'] for r in rows}
                kept = {u for u in recorded_added if kinds[u] not in ('moved', 'no_change')}
                mech = {r['unitId'] for r in rows if r['kind'] == 'moved' and moved_violation(r['text'])}
                nochange = set()
                results = {}
                for r in rows:
                    if r['kind'] == 'no_change':
                        bad = [w for w in RULE['added']['noChangeForbidden'] if w in r['text']]
                        if bad:
                            nochange.add(r['unitId'])
                            results[r['unitId']] = bad
                final = kept | mech | nochange
                key = '%s/%s-%s' % (tag, arm, setname)
                out['runs'][key] = {'recorded': sorted(recorded_added), 'final': sorted(final),
                                    'movedMechanical': sorted(mech), 'noChangeViolations': len(nochange)}
                for unit in sorted(recorded_added - final):
                    out['diffs'].append({'run': key, 'unitId': unit, 'kind': kinds[unit],
                                         'change': 'dropped', 'text': next(r['text'] for r in rows if r['unitId'] == unit),
                                         'reason': 'recorded as added, but clause 2 is a movement continuation'
                                                   if kinds[unit] == 'moved' else 'no_change allowance'})
                for unit in sorted(final - recorded_added):
                    out['diffs'].append({'run': key, 'unitId': unit, 'kind': kinds[unit],
                                         'change': 'added', 'text': next(r['text'] for r in rows if r['unitId'] == unit),
                                         'reason': 'clause 2 is not a movement continuation'})
    target = ROOT / 'artifacts/next-runs/rejudge-r3.json'
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('%-28s %8s %8s' % ('run', 'recorded', 'final'))
    for key, v in out['runs'].items():
        print('%-28s %8d %8d' % (key, len(v['recorded']), len(v['final'])))
    print('\ndiffs', len(out['diffs']))
    for d in out['diffs']:
        print('  %-26s %-8s %-6s %s | %s' % (d['run'], d['unitId'], d['change'], d['kind'], d['text']))


if __name__ == '__main__':
    main()
