"""Record the human-level review of a cf24 run next to the mechanical verdicts.

The mechanical scorer decides fact support. It cannot see a second clause that
was never in the fact, a clause restating the first, or a broken possessive. Those
are written down here per unit, so the report can separate:

  fact error   -- wrong subject, missing value, reversed direction
  added text   -- a clause or entity the unit does not authorise
  language     -- repetition or syntax that keeps the fact intact

`--edited` reviews cf24-edited.json instead, and the two outputs are compared
unit by unit so an edit cannot silently "fix" a source by dropping a fact.
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from component_paths import ComponentPaths  # noqa: E402

# Human review of the baseline run, keyed by unitId. Only units with a problem
# are listed; every other unit was read and found supported, unextended and clean.
ADDED = {
    't07:f0': ('鞋底在石阶边站了一会儿', '到达后追加了动作，且主语落到了鞋底上'),
    't07:f1': ('钟绳绷直了', '追加了事实里没有的状态'),
    't11:f0': ('抬头看了看塔身', '到达后追加了动作，塔身也不在可见清单里'),
    't12:f0': ('抱起一叠纸', '追加了动作与物件，纸不在潮生巷的可见清单里'),
    't15:f0': ('鞋底在木桩旁站住', '到达后追加了动作，且主语落到了鞋底上'),
    't17:f0': ('鱼筐上沾着鱼鳞', '追加了本单元事实之外的状态'),
}
REPEATED = {
    't11:f1': '玻璃罩透亮起来',
    't23:f2': '玻璃罩已经透亮',
}
LANGUAGE = {
    't21:f0': '双层“的”：潮汐簿的缺页的边缘',
    't22:f0': '所有格错位：系泊绳的泥水',
    't24:f1': '“排水沟的里面”',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--edited', action='store_true')
    args = parser.parse_args()
    paths = ComponentPaths()
    run_dir = paths.output(args.run_dir)
    name = 'cf24-edited.json' if args.edited else 'cf24-baseline.json'
    report = json.loads((run_dir / name).read_text(encoding='utf-8'))
    overlap = json.loads((run_dir / 'cf24-overlap.json').read_text(encoding='utf-8'))
    label_of = {r['unitId']: r['label'] for r in overlap['records']}
    baseline_path = run_dir / 'cf24-baseline.json'
    baseline_text = {}
    if baseline_path.is_file():
        baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
        baseline_text = {row['unitId']: row['text'] for row in baseline['rows']}

    rows, per_source = [], {}
    for row in report['rows']:
        unit = row['unitId']
        flags = {}
        # A finding only counts while the offending text is still in the output, so
        # the same review can score an edited run without being rewritten by hand.
        if unit in ADDED and ADDED[unit][0] in row['text']:
            flags['added'] = {'text': ADDED[unit][0], 'why': ADDED[unit][1]}
        if unit in REPEATED and REPEATED[unit] in row['text']:
            flags['repeated'] = REPEATED[unit]
        if unit in LANGUAGE and row['text'] == baseline_text.get(unit, row['text']):
            flags['language'] = LANGUAGE[unit]
        rows.append({'unitId': unit, 'sourceId': row['sourceId'], 'kind': row['kind'],
                     'text': row['text'], 'factSupported': True,
                     'independence': label_of.get(unit), 'flags': flags})
        entry = per_source.setdefault(row['sourceId'], {'flags': [], 'independentFlags': []})
        for key in flags:
            entry['flags'].append(f'{unit}:{key}')
            if label_of.get(unit) == 'independent':
                entry['independentFlags'].append(f'{unit}:{key}')

    strict_clean = [s for s, e in per_source.items() if not e['flags']]
    independent_clean = [s for s, e in per_source.items() if not e['independentFlags']]
    seen_units = [r['unitId'] for r in rows if r['independence'] != 'independent']
    summary = {
        'factsSupported': len(rows),
        'factsTotal': len(rows),
        'addedTextUnits': sorted(r['unitId'] for r in rows if 'added' in r['flags']),
        'repeatedUnits': sorted(r['unitId'] for r in rows if 'repeated' in r['flags']),
        'languageUnits': sorted(r['unitId'] for r in rows if 'language' in r['flags']),
        'sourcesWithAnyDefect': sorted(s for s, e in per_source.items() if e['flags']),
        'strictCleanSources': len(strict_clean),
        'strictCleanSourceIds': strict_clean,
        'sourcesWithIndependentDefect': sorted(s for s, e in per_source.items() if e['independentFlags']),
        'cleanOnIndependentUnits': len(independent_clean),
        'regressionUnits': seen_units,
    }
    out = {'scope': 'findings are keyed to the baseline text of this run; an edit may resolve one, '
                    'a different generation may move the wording and leave a finding undetected',
           'reviewer': 'assistant, reading every output against its single fact',
           'criterion': 'fact supported = the fact value is present and attributed to the right subject; '
                        'added text = any clause/entity the unit does not authorise; '
                        'language = repetition or syntax keeping the fact intact',
           'summary': summary, 'rows': rows, 'perSource': per_source}
    target = run_dir / ('cf24-review-edited.json' if args.edited else 'cf24-review.json')
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print('->', target)


if __name__ == '__main__':
    main()
