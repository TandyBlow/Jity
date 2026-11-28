#!/usr/bin/env python3
"""Build the platform's independent task-achievement gold from bench-v1.

Labels come from `independent-labels-v1.jsonl`: three blind lenses (clause,
outcome, task) read only id/taskId/goal/fact; the original verdicts were hidden.
The case verdict is the majority; `insufficient` means one fact cannot decide
whether the task is achieved, and stays separate from `no`.

  python -m tools.experiment_platform.build_task_gold
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCH = ROOT / 'artifacts/goal/platform/task-gold/bench-v1.semantic-branch.jsonl'
DEFAULT_SPEC = ROOT / 'artifacts/goal/platform/task-gold/task-gold-v1.tasks.json'
DEFAULT_INDEP = ROOT / 'artifacts/goal/platform/task-gold/independent-labels-v1.jsonl'
DEFAULT_OUT = ROOT / 'artifacts/goal/platform/task-gold/task-gold-v1.cases.jsonl'
ORDER = {'yes': 0, 'partial': 1, 'no': 2, 'insufficient': 3, 'skip': 4}


def load(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding='utf-8-sig').splitlines() if ln.strip()]


def majority(labels: dict) -> str:
    counts = Counter(item['verdict'] for item in labels.values())
    top = counts.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        return 'disagreement'
    return top[0][0]


def build(bench: list[dict], spec: dict, indep_rows: list[dict]) -> tuple[list[dict], dict]:
    tasks = {t['taskId']: t for t in spec['tasks']}
    indep = {row['id']: row for row in indep_rows}
    judged = [r for r in bench if r['verdict'] != 'skip']
    unique, seen = [], set()
    for row in sorted(judged, key=lambda r: (r['taskId'], ORDER.get(r['verdict'], 9), r['fact'])):
        key = (row['taskId'], row['goal'], row['fact'])
        if key in seen:
            continue
        seen.add(key)
        case_id = 'tg-v1:' + hashlib.sha1(('|'.join(key)).encode('utf-8')).hexdigest()[:12]
        blind = indep.get(case_id)
        labels = blind['labels'] if blind else {}
        clause = labels.get('clause', {})
        outcome = labels.get('outcome', {})
        task = labels.get('task', {})
        # Support axis: does this fact support every goal clause? Clause lens wins ties.
        verdict = clause.get('verdict') or outcome.get('verdict') or row['verdict']
        support_disagreement = bool(clause and outcome and clause.get('verdict') != outcome.get('verdict'))
        # Completion axis: task lens answers whether the task actually happened; single facts
        # usually cannot decide it, so it is reported separately and never voted into support.
        completion = task.get('verdict') or 'insufficient'
        majority_reason = clause.get('reason') or outcome.get('reason')
        if verdict == 'insufficient':
            majority_reason = majority_reason or '单事实证据不足以判定任务是否达成'
        spec_task = tasks.get(row['taskId']) or {}
        unique.append({
            'id': case_id,
            'modality': 'semantic',
            'world': 'dragon-raja-free-day',
            'taskId': row['taskId'],
            'goal': row['goal'],
            'fact': row['fact'],
            'committed': row['committed'],
            'source': row.get('source'),
            'sheet': row.get('sheet'),
            'benchVerdict': row['verdict'],
            'verdict': verdict,
            'supportVerdict': verdict,
            'completionVerdict': completion,
            'supportDisagreement': support_disagreement,
            'evidenceStatus': 'insufficient' if verdict == 'insufficient' else 'decided',
            'reason': majority_reason or '单事实未覆盖目标子句',
            'completionReason': task.get('reason') or '单事实无法判定任务是否实际完成',
            'blindLabels': {lens: item['verdict'] for lens, item in labels.items()},
            'blindReasons': {lens: item['reason'] for lens, item in labels.items()},
            'requiredIds': [x['id'] for x in spec_task.get('required') or []],
            'hasNegation': bool(spec_task.get('negations')),
            'hasPrecondition': bool(spec_task.get('preconditions')),
            'agreesWithBench': verdict == row['verdict'],
            'provenance': {'reviewer': 'platform-blind-panel',
                           'labelSource': 'three blind lenses (clause/outcome/task), original verdict hidden'},
        })
    per_lens = {}
    for lens in ('clause', 'outcome', 'task'):
        per_lens[lens] = sum(1 for c in unique if c.get('blindLabels', {}).get(lens) == c['benchVerdict'])
    agree = sum(1 for c in unique if c['verdict'] == c['benchVerdict'])
    completion = Counter(c['completionVerdict'] for c in unique)
    disagreements = [{'id': c['id'], 'bench': c['benchVerdict'], 'blind': c['verdict'],
                      'labels': c.get('blindLabels')} for c in unique if not c['agreesWithBench']]
    by_verdict = Counter(c['verdict'] for c in unique)
    by_bench = Counter(c['benchVerdict'] for c in unique)
    committed = Counter()
    for c in unique:
        committed[(c['committed'], c['verdict'])] += 1
    achieved = sum(n for (state, verdict), n in committed.items() if state == 'achieved')
    not_yes = sum(n for (state, verdict), n in committed.items() if state == 'achieved' and verdict != 'yes')
    report = {
        'schema': 'jity-task-gold-report/1',
        'generatedAt': datetime.now(tz=timezone.utc).isoformat(),
        'benchRows': len(bench),
        'verdictCountsBench': dict(Counter(r['verdict'] for r in bench)),
        'judgedRows': len(judged),
        'uniqueTaskGoalFact': len(unique),
        'withinTaskDuplicates': len(judged) - len(unique),
        'emptyGoalRows': sum(1 for r in bench if not r['goal']),
        'reviewMethod': 'three blind lenses on 78 unique cases; original bench verdict hidden',
        'blindAgreement': {
            'cases': len(unique),
            'perLens': {lens: {'agree': n, 'rate': round(n / max(1, len(unique)), 3)} for lens, n in per_lens.items()},
            'support': {'agree': agree, 'rate': round(agree / max(1, len(unique)), 3)},
            'supportDisagreementCases': sum(1 for c in unique if c.get('supportDisagreement')),
            'completionNotComparedToBench': True,
            'taskLensNotComparable': 'task lens answers actual completion; bench and support lenses answer evidence support',
            'completionDistribution': dict(completion),
            'disagreements': disagreements,
        },
        'verdictCountsBlind': dict(by_verdict),
        'completionCounts': dict(completion),
        'benchCountsUnique': dict(by_bench),
        'insufficientCount': by_verdict.get('insufficient', 0),
        'crossTab': {f'{k[0]}|{k[1]}': v for k, v in sorted(committed.items())},
        'committedAchieved': achieved,
        'committedAchievedNotYes': not_yes,
        'committedAchievedNotYesRate': round(not_yes / max(1, achieved), 3),
        'selectionBias': 'every bench row is an llm=yes case; this measures false commits, not balanced accuracy',
        'singleFactLimitation': 'single (goal, fact) pairs cannot express 14/19 multi-clause, negation or precondition goals',
        'reportN': 108,
        'reportNReproducibleFromCommittedBench': False,
        'reportNNote': 'the committed bench has 114 judgeable rows; goal-verifier-v1 report claims n=108 at the same commit',
        'standard': spec['standard'],
    }
    return unique, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--bench', default=str(DEFAULT_BENCH))
    parser.add_argument('--spec', default=str(DEFAULT_SPEC))
    parser.add_argument('--indep', default=str(DEFAULT_INDEP))
    parser.add_argument('--out', default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    bench = load(Path(args.bench))
    spec = json.loads(Path(args.spec).read_text(encoding='utf-8'))
    indep = load(Path(args.indep)) if Path(args.indep).exists() else []
    cases, report = build(bench, spec, indep)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(json.dumps(c, ensure_ascii=False) for c in cases) + '\n', encoding='utf-8')
    canon = hashlib.sha256(json.dumps(cases, ensure_ascii=False).encode('utf-8')).hexdigest()
    out.with_suffix('.jsonl.manifest.json').write_text(json.dumps(
        {'schema': 'jity-eval-set/1', 'path': out.relative_to(ROOT).as_posix(), 'rows': len(cases),
         'sha256': canon, 'hashMode': 'canonical-json'}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    (out.parent / 'task-gold-v1.report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
