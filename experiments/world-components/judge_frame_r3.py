"""Re-judge the archived relation outputs with the r4 frame rule.

Three separate checks: fact relation, entity attribution, syntax. Relation token
presence is only a clue, never a pass on its own. The earlier retention-only file
stays untouched.
"""
import json
import pathlib
import re

ROOT = pathlib.Path('.').resolve()
RULE = json.loads((ROOT / 'artifacts/scoring-rule-r4/rule.json').read_text(encoding='utf-8'))
PROBES = ROOT / 'artifacts/next-inputs/world-components/n4-relation-r1.jsonl'
RUNS = ('moved', 'ctl', 'mix')
DOUBLE_DE = re.compile('的[^，。！？的]{1,6}的')


def other_entity(probe):
    """The subject of the fact value, used to detect a possessor flip."""
    text = probe['fact']['text']
    for token in ('旧缆绳', '缆绳', '干纸', '备用灯芯', '抹布', '银鳞鱼'):
        if token in text:
            return token
    return ''


def checks(probe, text):
    name = probe['fact']['name']
    relation = probe['relation']
    other = other_entity(probe)
    kept = relation in text
    role = 'ok'
    if name not in text:
        role = 'missing'
    elif text.count(name) >= 2:
        role = 'duplicated'
    elif name + '的' in text:
        after = text.split(name + '的', 1)[1]
        if (other and after.startswith(other)) or after.startswith(relation):
            role = 'role-flip'
    if probe['family'] == 'control':
        invented = [t for t in probe['forbidden'] if t in text]
        rel = 'invented' if invented else 'kept'
    else:
        rel = 'kept' if kept else 'dropped'
    broken = text.count(name) >= 2 or bool(DOUBLE_DE.search(text))
    syntax = 'broken' if broken else 'ok'
    passed = rel in ('kept', 'clean') and role == 'ok' and syntax == 'ok'
    return {'factRelation': rel, 'attribution': role, 'syntax': syntax, 'pass': passed}


def main():
    probes = {}
    for line in PROBES.read_text(encoding='utf-8').splitlines():
        if line.strip():
            p = json.loads(line)
            probes[p['unitId']] = p
    out = {'rule': RULE['version'], 'arms': {}}
    for arm in RUNS:
        report = json.loads((ROOT / ('artifacts/next-runs/eval-r6/%s-relation/relation-baseline.json' % arm))
                            .read_text(encoding='utf-8'))
        rows = []
        for row in report['rows']:
            p = probes[row['unitId']]
            c = checks(p, row['text'])
            rows.append(dict(unitId=row['unitId'], family=p['family'], relation=p['relation'],
                             text=row['text'], **c))
        out['arms'][arm] = rows
        ok = sum(1 for r in rows if r['pass'])
        rel = sum(1 for r in rows if r['family'] == 'relation' and r['factRelation'] == 'kept')
        role = sum(1 for r in rows if r['attribution'] != 'ok')
        syn = sum(1 for r in rows if r['syntax'] != 'ok')
        print('== %s  pass %d/10 | relation kept %d/8 | attribution wrong %d | syntax broken %d'
              % (arm, ok, rel, role, syn))
        for r in rows:
            print('  %-7s rel=%-8s attr=%-10s syn=%-7s %s' % (r['unitId'], r['factRelation'],
                                                              r['attribution'], r['syntax'], r['text']))
    target = ROOT / 'artifacts/next-runs/eval-r6/frame-judged.json'
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('->', target)


if __name__ == '__main__':
    main()
