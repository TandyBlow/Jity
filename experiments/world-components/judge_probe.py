"""Judge the probe run with the rule frozen in n4-probe-r1-rule.json.

The fact verdict reuses the frozen cf24 scorer; the family checks are the fixed
string rules declared before the run. Nothing here may be tuned after the fact:
a wrong rule is reported as wrong, not relaxed.
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'n4_narrative_dev'))
from score_cf24_baseline import judge  # noqa: E402

RULE = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(
    'artifacts/next-inputs/world-components/n4-probe-r1-rule.json')


def family_issues(rule, unit, text):
    issues = []
    fam = unit['family']
    if fam == 'tail' and unit['kind'] == 'moved':
        parts = re.split('[，,]', text, maxsplit=1)
        if len(parts) == 2:
            for verb in rule['families']['tail']['bannedVerbs']:
                if verb in parts[1]:
                    issues.append({'family': 'tail', 'span': parts[1], 'matched': verb})
                    break
    if fam == 'quantifier':
        fact_text = unit['fact'].get('resultText') or unit['fact'].get('text') or ''
        if '一叠' in text and '一叠' not in fact_text:
            for m in re.finditer('一叠(.)?', text):
                after = m.group(1) or ''
                if after not in rule['families']['quantifier']['allowedAfter']:
                    issues.append({'family': 'quantifier', 'span': m.group(0), 'matched': after})
    if fam == 'grammar':
        m = re.search('的[^，。！？的]{1,5}的', text)
        if m:
            issues.append({'family': 'grammar', 'rule': 'doubleDe', 'span': m.group(0)})
        if '绳的泥水' in text:
            issues.append({'family': 'grammar', 'rule': 'possessive', 'span': '绳的泥水'})
        if '的里面' in text:
            issues.append({'family': 'grammar', 'rule': 'li', 'span': '的里面'})
    return issues


def main():
    rule = json.loads(RULE.read_text(encoding='utf-8'))
    units = {}
    for line in pathlib.Path('artifacts/next-inputs/world-components/n4-probe-r1.jsonl').read_text(
            encoding='utf-8').splitlines():
        if line.strip():
            u = json.loads(line)
            units[u['unitId']] = u
    summary = {}
    for arm in ('u240', 'c'):
        report = json.loads(pathlib.Path(
            'artifacts/next-runs/eval-r1/probe-%s/probe-baseline.json' % arm).read_text(encoding='utf-8'))
        rows = []
        for row in report['rows']:
            unit = units[row['unitId']]
            verdict, note, _ = judge(unit, row['text'])
            issues = family_issues(rule, unit, row['text'])
            rows.append({'unitId': row['unitId'], 'family': unit['family'],
                         'variant': unit['variant'], 'baseUnit': unit['baseUnit'],
                         'text': row['text'], 'verdict': verdict, 'note': note,
                         'issues': issues, 'seconds': row['seconds']})
        summary[arm] = rows
        print('==', arm)
        for r in rows:
            print(' %-7s %-16s %s | %s%s' % (r['unitId'], r['variant'], r['verdict'], r['text'],
                                             '' if not r['issues'] else '  <<' + ';'.join(
                                                 i.get('matched') or i.get('rule') for i in r['issues'])))
    out = {'rule': str(RULE), 'ruleVersion': rule['version'], 'arms': summary}
    target = pathlib.Path('artifacts/next-runs/eval-r1/probe-judged.json')
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('->', target)


if __name__ == '__main__':
    main()
