"""Judge the role-contrast probes with the rule frozen in n4-rolepair-r1-rule.json."""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'n4_narrative_dev'))
from score_cf24_baseline import judge  # noqa: E402

ROOT = pathlib.Path('.')
ROUND = 'eval-r7'
ARMS = ('moved', 'ctl', 'mix')
DOUBLE_DE = re.compile('的[^，。！？的]{1,6}的')


def judge_row(p, text):
    name, part, other, rel = p['name'], p['part'], p['other'], p['relation']
    name_kept = name in text
    entity = part if p['variant'] == 'possessor' else other
    entity_kept = entity in text
    if p['variant'] == 'possessor':
        state_kept = p['predicate'] in text
        if name_kept and entity_kept:
            role = 'ok'
        elif name_kept and not entity_kept:
            role = 'replaced'
        else:
            role = 'missing'
        relation = 'n/a'
    else:
        state_kept = True
        flip = False
        if name + '的' in text:
            after = text.split(name + '的', 1)[1]
            flip = after.startswith(other) or after.startswith(rel)
        role = 'flip' if flip else ('ok' if entity_kept else 'missing')
        if rel in text:
            relation = 'kept'
        else:
            relation = 'distorted' if any(t in text for t in ('压', '靠', '堆', '插', '搭', '挂', '缠')) else 'dropped'
    dup = text.count(name) >= 2
    syntax = 'broken' if (dup or DOUBLE_DE.search(text)) else 'ok'
    passed = (name_kept and entity_kept and state_kept and role == 'ok'
              and relation in ('kept', 'n/a') and syntax == 'ok')
    return {'nameKept': name_kept, 'entityKept': entity_kept, 'stateKept': state_kept,
            'role': role, 'relation': relation, 'syntax': syntax, 'duplicate': dup, 'pass': passed}


def main():
    probes = {}
    for line in (ROOT / 'artifacts/next-inputs/world-components/n4-rolepair-r1.jsonl').read_text(
            encoding='utf-8').splitlines():
        if line.strip():
            p = json.loads(line)
            probes[p['unitId']] = p
    out = {'rule': 'rolepair-r1', 'arms': {}, 'summary': {}}
    for arm in ARMS:
        report = json.loads((ROOT / ('artifacts/next-runs/%s/rolepair-%s/rolepair-baseline.json'
                                     % (ROUND, arm))).read_text(encoding='utf-8'))
        rows = []
        for row in report['rows']:
            p = probes[row['unitId']]
            c = judge_row(p, row['text'])
            verdict, note, _ = judge(p, row['text'])
            rows.append(dict(unitId=row['unitId'], pair=p['pair'], variant=p['variant'],
                             role_expected=p['role'], text=row['text'], fact=verdict, note=note, **c))
        out['arms'][arm] = rows
        role_err = sum(1 for r in rows if r['role'] in ('replaced', 'flip'))
        poss = [r for r in rows if r['variant'] == 'possessor']
        loc = [r for r in rows if r['variant'] == 'location']
        out['summary'][arm] = {
            'pass': '%d/12' % sum(1 for r in rows if r['pass']),
            'possessorPass': '%d/6' % sum(1 for r in poss if r['pass']),
            'locationPass': '%d/6' % sum(1 for r in loc if r['pass']),
            'entityKept': '%d/12' % sum(1 for r in rows if r['entityKept']),
            'roleErrors': role_err,
            'roleErrorDetail': {'replaced': sum(1 for r in rows if r['role'] == 'replaced'),
                                'flip': sum(1 for r in rows if r['role'] == 'flip'),
                                'missing': sum(1 for r in rows if r['role'] == 'missing')},
            'relationKept': '%d/6' % sum(1 for r in loc if r['relation'] == 'kept'),
            'syntaxBroken': sum(1 for r in rows if r['syntax'] == 'broken'),
            'factS': '%d/12' % sum(1 for r in rows if r['fact'] == 'S')}
        print('== %-6s pass %s (possessor %s, location %s) | entity kept %s | role errors %d %s | relation %s | '
              'syntax broken %d | fact S %s'
              % (arm, out['summary'][arm]['pass'], out['summary'][arm]['possessorPass'],
                 out['summary'][arm]['locationPass'], out['summary'][arm]['entityKept'], role_err,
                 out['summary'][arm]['roleErrorDetail'], out['summary'][arm]['relationKept'],
                 out['summary'][arm]['syntaxBroken'], out['summary'][arm]['factS']))
        for r in rows:
            flag = '' if r['pass'] else '  <<%s' % ','.join(
                k for k, v in (('entity', not r['entityKept']), ('role:' + r['role'], r['role'] != 'ok'),
                               ('rel:' + r['relation'], r['relation'] not in ('kept', 'n/a')),
                               ('syntax', r['syntax'] != 'ok')) if v)
            print('  %-8s %-9s %-8s %s | %s%s' % (r['unitId'], r['variant'], r['fact'], r['text'], '', flag))
    target = ROOT / ('artifacts/next-runs/%s/rolepair-judged.json' % ROUND)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    (ROOT / ('artifacts/next-runs/%s/rolepair-summary.json' % ROUND)).write_text(
        json.dumps(out['summary'], ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('->', target)


if __name__ == '__main__':
    main()
