"""Re-run the frozen probe rule (n4-probe-r1-rule.json) over the second-round runs.

The rule and the family checks are imported from judge_probe.py unchanged; only
the run directories differ, so no judgement is retuned.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'n4_narrative_dev'))
from judge_probe import family_issues  # noqa: E402
from score_cf24_baseline import judge  # noqa: E402

RULE = pathlib.Path('artifacts/next-inputs/world-components/n4-probe-r1-rule.json')
ROUND = pathlib.Path('artifacts/next-runs/eval-r2')


def main():
    rule = json.loads(RULE.read_text(encoding='utf-8'))
    units = {}
    for line in pathlib.Path('artifacts/next-inputs/world-components/n4-probe-r1.jsonl').read_text(
            encoding='utf-8').splitlines():
        if line.strip():
            u = json.loads(line)
            units[u['unitId']] = u
    out = {'rule': str(RULE), 'ruleVersion': rule['version'], 'arms': {}}
    for arm in ('c', 'control', 'moved'):
        report = json.loads((ROUND / ('%s-probe' % arm) / 'probe-baseline.json').read_text(encoding='utf-8'))
        rows = []
        for row in report['rows']:
            unit = units[row['unitId']]
            verdict, note, _ = judge(unit, row['text'])
            issues = family_issues(rule, unit, row['text'])
            rows.append({'unitId': row['unitId'], 'family': unit['family'], 'variant': unit['variant'],
                         'text': row['text'], 'verdict': verdict, 'issues': issues})
        out['arms'][arm] = rows
        tail = [r for r in rows if r['family'] == 'tail']
        print('== %s  tail violations %d/%d' % (arm, sum(1 for r in tail if r['issues']), len(tail)))
        for r in rows:
            print('  %-7s %-16s %s | %s%s' % (r['unitId'], r['variant'], r['verdict'], r['text'],
                                              '' if not r['issues'] else '  <<' + ';'.join(
                                                  i.get('matched') or i.get('rule') for i in r['issues'])))
    target = ROUND / 'probe-judged-r2.json'
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('->', target)


if __name__ == '__main__':
    main()
