"""Read the routed-split evaluation and produce review material.

This does not change any output. It groups the same rows three ways:
  * by fact-kind responsibility: act / state / shared-control (no_change);
  * by evaluation set (four diagnostic sets, ten real rounds);
  * by whether the two arms actually produced different text.

Every text-different pair is written out for manual reading, including pairs
the mechanical judge sees as equal. Same-text pairs that carry a flag are
listed separately as common defects, never as passes.
"""
from __future__ import annotations

import collections
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ART = ROOT / 'artifacts' / 'world-components'
EVAL = ART / 'route-split-eval-v1.json'
OUT_JSON = ART / 'route-split-analysis-v1.json'
OUT_CASES = ART / 'route-split-review-cases-v1.json'
OUT_MD = ART / 'route-split-review-v1.md'
ACT_KINDS = {'moved', 'outcome'}
STATE_KINDS = {'appearance_changed', 'sanity_changed', 'personality_changed'}
METRICS = ('mustExpress', 'binding', 'repetition', 'addition')


def group_of(kind):
    if kind in ACT_KINDS:
        return 'act'
    if kind in STATE_KINDS:
        return 'state'
    if kind == 'no_change':
        return 'shared-control'
    return 'other'


def visible_of(input_text):
    match = re.search(r'地点可见=([^\n]+)', input_text or '')
    return match.group(1) if match else ''


def fact_text(fact, kind):
    if kind == 'moved':
        return f"{fact.get('from', '')} → {fact.get('to', '')}"
    if kind == 'sanity_changed':
        return f"{fact.get('from', '')} → {fact.get('to', '')}"
    if kind == 'no_change':
        return '（无变化）'
    return fact.get('resultText') or fact.get('text') or ''


def flags(arm):
    out = []
    if not arm.get('mustExpress'):
        out.append('must-missing')
    if not arm.get('binding'):
        out.append('binding')
    if arm.get('repetition'):
        if arm.get('literalRepeat'):
            out.append('literal-repeat')
        elif arm.get('semanticRepeat'):
            out.append('semantic-repeat:' + str(arm.get('semanticRepeat')))
        else:
            out.append('repeat')
    if arm.get('addition'):
        if arm.get('extraAction'):
            out.append('extra-action:' + '/'.join(arm['extraAction']))
        if arm.get('extraObject'):
            out.append('extra-object:' + '/'.join(arm['extraObject']))
        if arm.get('extraState'):
            out.append('extra-state:' + '/'.join(arm['extraState']))
    if not arm.get('complete', True):
        out.append('incomplete')
    return out


def metric_delta(control, routed):
    return {
        'mustExpress': int(routed['mustExpress']) - int(control['mustExpress']),
        'binding': int(routed['binding']) - int(control['binding']),
        'repetition': int(control['repetition']) - int(routed['repetition']),
        'addition': int(control['addition']) - int(routed['addition']),
    }


def summarize(rows):
    def arm_summary(arm):
        return {
            'units': len(rows),
            'mustExpress': sum(int(row[arm]['mustExpress']) for row in rows),
            'binding': sum(int(row[arm]['binding']) for row in rows),
            'repetition': sum(int(row[arm]['repetition']) for row in rows),
            'addition': sum(int(row[arm]['addition']) for row in rows),
            'clean': sum(1 for row in rows
                         if row[arm]['mustExpress'] and row[arm]['binding']
                         and not row[arm]['repetition'] and not row[arm]['addition']),
        }
    return {'units': len(rows), 'control': arm_summary('control'),
            'routed': arm_summary('routed'),
            'deltaRoutedMinusControl': {
                'mustExpress': sum(metric_delta(row['control'], row['routed'])['mustExpress']
                                   for row in rows),
                'binding': sum(metric_delta(row['control'], row['routed'])['binding']
                               for row in rows),
                'repetition': sum(metric_delta(row['control'], row['routed'])['repetition']
                                  for row in rows),
                'addition': sum(metric_delta(row['control'], row['routed'])['addition']
                                for row in rows),
            },
            'textChanged': sum(1 for row in rows if row['textChanged']),
            'sameText': sum(1 for row in rows if not row['textChanged']),
            'sameTextFlagged': sum(1 for row in rows
                                   if not row['textChanged']
                                   and (flags(row['control']) or flags(row['routed']))),
            'changedButNoMetricDelta': sum(
                1 for row in rows if row['textChanged']
                and not any(metric_delta(row['control'], row['routed']).values()))}


def load():
    doc = json.loads(EVAL.read_text(encoding='utf-8'))
    cases = []
    for setname, rows in doc['rows'].items():
        for row in rows:
            kind = row['kind']
            cases.append({
                'scope': 'diagnostic', 'set': setname, 'unitId': row['unitId'],
                'kind': kind, 'group': group_of(kind),
                'fact': row.get('fact', {}),
                'factText': fact_text(row.get('fact', {}), kind),
                'input': row.get('input', ''),
                'visible': visible_of(row.get('input', '')),
                'control': row['control'], 'routed': row['routed'],
                'controlText': row['control'].get('text', ''),
                'routedText': row['routed'].get('text', ''),
                'textChanged': (row['control'].get('text', '').strip()
                                != row['routed'].get('text', '').strip()),
                'controlFlags': flags(row['control']),
                'routedFlags': flags(row['routed']),
                'metricDelta': metric_delta(row['control'], row['routed']),
                'routedArm': row['routed'].get('arm'),
            })
    for round_row in doc['roundRows']:
        for unit in round_row['units']:
            kind = unit['kind']
            cases.append({
                'scope': 'round', 'set': round_row['roundId'],
                'unitId': unit['factId'], 'kind': kind, 'group': group_of(kind),
                'fact': {'name': unit.get('name'), 'text': unit.get('factText')},
                'factText': unit.get('factText') or '',
                'input': unit.get('prompt', ''),
                'visible': visible_of(unit.get('prompt', '')),
                'control': unit['control'], 'routed': unit['routed'],
                'controlText': unit['control'].get('text', ''),
                'routedText': unit['routed'].get('text', ''),
                'textChanged': (unit['control'].get('text', '').strip()
                                != unit['routed'].get('text', '').strip()),
                'controlFlags': flags(unit['control']),
                'routedFlags': flags(unit['routed']),
                'metricDelta': metric_delta(unit['control'], unit['routed']),
                'routedArm': unit['routed'].get('arm'),
            })
    return doc, cases


def write_markdown(cases, doc):
    lines = ['# Routed-split review cases', '',
             f"Selected point: {doc['selectedPoint']}; decode budget: "
             f"{doc['decodeBudgetSeconds']} s; judge: mechanical "
             "`judge_expression.py`.", '',
             'Every row below is a case where the two arms produced different '
             'text. Same-text rows are not listed here; flagged same-text rows '
             'are in the common-defect section.', '']
    for group in ('act', 'state', 'shared-control', 'other'):
        subset = [case for case in cases if case['group'] == group and case['textChanged']]
        if not subset:
            continue
        lines += [f'## {group} — changed text ({len(subset)} cases)', '']
        subset.sort(key=lambda case: (case['scope'], case['set'], case['unitId']))
        for index, case in enumerate(subset, 1):
            lines += [
                f"### {group}-{index:03d} {case['scope']}/{case['set']}/{case['unitId']} "
                f"({case['kind']})",
                f"- 事实：`{case['factText']}`",
                f"- 地点可见：`{case['visible']}`",
                f"- control（{case['routedArm']} 对照）：{case['controlText']}",
                f"- routed（{case['routedArm']}）：{case['routedText']}",
                f"- 机械差：{json.dumps(case['metricDelta'], ensure_ascii=False)}；"
                f"control flags={case['controlFlags']}; routed flags={case['routedFlags']}",
                f"- 人工判定：",
                '']
    common = [case for case in cases if not case['textChanged']
              and (case['controlFlags'] or case['routedFlags'])]
    lines += [f'## same text with mechanical flags ({len(common)} cases)', '',
              'These are not passes. The two arms produced the same text; the '
              'defect belongs to both. Additional common defects found by the '
              'manual scan are listed in route-split-manual-review-v1.json.', '']
    for index, case in enumerate(common, 1):
        lines += [
            f"### common-{index:03d} {case['scope']}/{case['set']}/{case['unitId']} "
            f"({case['kind']})",
            f"- 事实：`{case['factText']}`",
            f"- 共同输出：{case['controlText']}",
            f"- flags：control={case['controlFlags']}; routed={case['routedFlags']}",
            f"- 机械差：{json.dumps(case['metricDelta'], ensure_ascii=False)}",
            '']
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')


def main():
    doc, cases = load()
    by_scope = collections.defaultdict(list)
    for case in cases:
        by_scope[case['scope']].append(case)
    by_group = collections.defaultdict(list)
    for case in cases:
        by_group[case['group']].append(case)
    by_set = collections.defaultdict(list)
    for case in cases:
        by_set[(case['scope'], case['set'])].append(case)
    by_group_set = collections.defaultdict(list)
    for case in cases:
        by_group_set[(case['group'], case['scope'], case['set'])].append(case)

    analysis = {
        'version': 'route-split-analysis-v1',
        'selectedPoint': doc['selectedPoint'],
        'decodeBudgetSeconds': doc['decodeBudgetSeconds'],
        'byScope': {scope: summarize(rows) for scope, rows in by_scope.items()},
        'byGroup': {group: summarize(rows) for group, rows in by_group.items()},
        'bySet': {f'{scope}/{name}': summarize(rows)
                  for (scope, name), rows in by_set.items()},
        'byGroupAndSet': {f'{group}/{scope}/{name}': summarize(rows)
                          for (group, scope, name), rows in by_group_set.items()},
        'changedButNoMetricDelta': [
            {'scope': case['scope'], 'set': case['set'], 'unitId': case['unitId'],
             'kind': case['kind'], 'group': case['group'],
             'factText': case['factText'],
             'controlText': case['controlText'], 'routedText': case['routedText'],
             'controlFlags': case['controlFlags'], 'routedFlags': case['routedFlags']}
            for case in cases if case['textChanged']
            and not any(case['metricDelta'].values())],
        'sameTextFlagged': [
            {'scope': case['scope'], 'set': case['set'], 'unitId': case['unitId'],
             'kind': case['kind'], 'group': case['group'],
             'text': case['controlText'],
             'controlFlags': case['controlFlags'], 'routedFlags': case['routedFlags']}
            for case in cases if not case['textChanged']
            and (case['controlFlags'] or case['routedFlags'])],
    }
    OUT_JSON.write_text(json.dumps(analysis, ensure_ascii=False, indent=2),
                        encoding='utf-8')
    OUT_CASES.write_text(json.dumps(cases, ensure_ascii=False, indent=2),
                         encoding='utf-8')
    write_markdown(cases, doc)
    print(json.dumps({key: analysis[key] for key in
                      ('byScope', 'byGroup', 'bySet', 'byGroupAndSet')},
                     ensure_ascii=False, indent=1))
    print('changedButNoMetricDelta', len(analysis['changedButNoMetricDelta']))
    print('sameTextFlagged', len(analysis['sameTextFlagged']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
