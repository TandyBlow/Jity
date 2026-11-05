"""Re-read every output the mechanical pass left open, and separate the causes.

A run only leaves a unit open when the verdict is not "supported": a movement
unit missing an endpoint, a fact whose coverage sits between 0.15 and 0.5, a
missing subject. Each such row across the six runs (three models, cf24 and
final24) is read against its fact here.

Two things are recorded separately:

  * confirmed defects - the output really is missing or contradicts the fact;
  * scorer artefacts  - the unit was open because of a checker bug.

The checker bugs found this round are fixed in score_cf24_baseline.py and this
table is produced with the fixed version: props listed on the 可见 line and
sublocations of the current location are now authorised, and an alias now covers
its canonical name (渡口 for 潮渡, 档案馆 for 潮汐档案馆). Before those fixes the
same runs carried 6 extra "other-place" flags for 长桌, 巷子 and 摊棚; no verdict
changed, and neither did any coverage figure on the current outputs.

Output: artifacts/target-audit-r1/pending-output-review.json
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
WORKTREE = HERE.parents[1]
OUT = WORKTREE / 'artifacts/target-audit-r1/pending-output-review.json'
RUNS = (('cf24', 'u240', 'cf24-u240-baseline', 'cf24-mechanical.json'),
        ('cf24', 'control', 'cf24-ctrl', 'cf24-mechanical.json'),
        ('cf24', 'treatment', 'cf24-treat', 'cf24-mechanical.json'),
        ('final24', 'u240', 'val-u240', 'cf24-mechanical-val-baseline.json'),
        ('final24', 'control', 'val-ctrl', 'cf24-mechanical-val-baseline.json'),
        ('final24', 'treatment', 'val-treat', 'cf24-mechanical-val-baseline.json'))
SETS = ('n4-cf24-contract.jsonl', 'n4-moved24-contract.jsonl', 'n4-final24-contract.jsonl')
# (run, unit) -> (verdict, note); read against the fact, not the score.
DECISIONS = {
    ('cf24-ctrl', 't09:f2'): ('confirmed-missing-quantity+repetition',
                              '事实是“一叠干纸”，输出只写“干纸”；后半句把同一句又写了一遍'),
    ('cf24-ctrl', 't13:f1'): ('confirmed-missing-quantity', '事实是“一叠干纸”，输出只写“干纸”'),
    ('cf24-treat', 't09:f2'): ('confirmed-missing-quantity', '事实是“一叠干纸”，输出只写“干纸”'),
    ('cf24-treat', 't11:f2'): ('confirmed-wrong-qualifier', '事实是“塔顶的灯芯”，输出写成“备用灯芯”'),
    ('cf24-treat', 't13:f1'): ('confirmed-missing-quantity', '事实是“一叠干纸”，输出只写“干纸”'),
    ('cf24-treat', 't23:f3'): ('confirmed-missing-object', '事实是“换好塔顶的灯芯”，输出只有“换好备用”'),
    ('val-treat', 'v13:f1'): ('confirmed-wrong-qualifier', '事实是“塔顶的灯芯”，输出写成“备用灯芯”'),
}


def main():
    units = {}
    for name in SETS:
        path = WORKTREE / 'artifacts/next-inputs/world-components' / name
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                unit = json.loads(line)
                units[unit['unitId']] = unit
    rows, counts = [], {}
    for set_name, arm, run, file_name in RUNS:
        report = json.loads((WORKTREE / 'artifacts/next-runs' / run / file_name).read_text(encoding='utf-8'))
        for row in report['rows']:
            if row['verdict'] == 'S':
                continue
            verdict, note = DECISIONS[(run, row['unitId'])]
            rows.append({'set': set_name, 'arm': arm, 'unitId': row['unitId'],
                         'kind': units[row['unitId']]['kind'],
                         'fact': units[row['unitId']]['fact'],
                         'output': row['text'], 'mechanical': row['verdict'],
                         'mechanicalNote': row['note'], 'flags': row['flags'],
                         'verdict': verdict, 'reason': note})
            counts[verdict] = counts.get(verdict, 0) + 1
    decided = {(run, unit) for run, unit in DECISIONS}
    seen = {(run, row['unitId']) for set_name, arm, run, file_name in RUNS
            for row in json.loads((WORKTREE / 'artifacts/next-runs' / run / file_name)
                                  .read_text(encoding='utf-8'))['rows'] if row['verdict'] != 'S'}
    assert decided == seen, (sorted(seen - decided), sorted(decided - seen))
    body = {'runs': 6, 'openUnits': len(rows),
            'confirmed': sum(1 for row in rows if row['verdict'].startswith('confirmed')),
            'scorerArtefacts': sum(1 for row in rows if not row['verdict'].startswith('confirmed')),
            'byVerdict': dict(sorted(counts.items())),
            'scorerFix': {'beforeFix': 'props on the 可见 line, sublocations and aliases were not authorised',
                          'flagsRemoved': ['other-place:长桌 (v03:f3, v11:f2, v19:f2, v21:f1)',
                                           'other-place:巷子 (v22:f1)', 'other-place:摊棚 (v23:f1)'],
                          'verdictsChanged': 0, 'aliasExpansionChangedVerdicts': 0},
            'records': rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(body, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: body[k] for k in ('openUnits', 'confirmed', 'scorerArtefacts', 'byVerdict')},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
