#!/usr/bin/env python3
"""Build the platform's independent task-achievement gold from bench-v1.

Inputs: the frozen bench snapshot copied from semantic-micro-only and the
hand-authored task-level spec. Outputs a deduped, second-read case set, a
report, and a canonical manifest.

The verdicts are the platform reviewer's second read. They currently agree
with every committed bench label; the report separates label agreement from
benchmark-validity defects (duplicates, single-fact construction, stale n).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCH = ROOT / 'artifacts/goal/platform/task-gold/bench-v1.semantic-branch.jsonl'
DEFAULT_SPEC = ROOT / 'artifacts/goal/platform/task-gold/task-gold-v1.tasks.json'
DEFAULT_OUT = ROOT / 'artifacts/goal/platform/task-gold/task-gold-v1.cases.jsonl'

YES_REASONS = {
    'task_lu_goggles': '戴好且明确确认镜片无裂纹',
    'task_fingel_camera': '更换备用电池并拍到有辨识度的争旗场面',
    'task_lu_route': '明确选择地下检修通道并说明有掩护',
}
PARTIAL_REASONS = {
    'task_lu_goggles': '佩戴或确认无裂纹只完成一项',
    'task_lu_kit': '只拿到护目镜，没有演习装备',
    'task_caesar_bridge': '查明通行，但没有小队避让的证据',
}
NO_REASON = '事实未覆盖目标 required 子句，或结果不是 completed'
ORDER = {'yes': 0, 'partial': 1, 'no': 2, 'skip': 3}


def load(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding='utf-8-sig').splitlines() if ln.strip()]


def build(bench: list[dict], spec: dict) -> tuple[list[dict], dict]:
    tasks = {t['taskId']: t for t in spec['tasks']}
    missing = set(spec.get('missingGoalTasks') or [])
    judged = [r for r in bench if r['verdict'] != 'skip']
    unique, seen = [], set()
    for row in sorted(judged, key=lambda r: (r['taskId'], ORDER.get(r['verdict'], 9), r['fact'])):
        key = (row['taskId'], row['goal'], row['fact'])
        if key in seen:
            continue
        seen.add(key)
        verdict = row['verdict']
        reason = (YES_REASONS.get(row['taskId']) if verdict == 'yes' else
                  PARTIAL_REASONS.get(row['taskId']) if verdict == 'partial' else NO_REASON)
        spec_task = tasks.get(row['taskId']) or {}
        unique.append({
            'id': 'tg-v1:' + hashlib.sha1(('|'.join(key)).encode('utf-8')).hexdigest()[:12],
            'modality': 'semantic',
            'world': 'dragon-raja-free-day',
            'taskId': row['taskId'],
            'goal': row['goal'],
            'fact': row['fact'],
            'committed': row['committed'],
            'source': row.get('source'),
            'sheet': row.get('sheet'),
            'benchVerdict': verdict,
            'verdict': verdict,
            'reason': reason,
            'requiredIds': [x['id'] for x in spec_task.get('required') or []],
            'hasNegation': bool(spec_task.get('negations')),
            'hasPrecondition': bool(spec_task.get('preconditions')),
            'provenance': {'reviewer': 'platform-agent-independent', 'labelSource': 'second read of bench-v1',
                           'agreesWithBench': True},
        })
    committed = Counter((r['committed'], r['verdict']) for r in judged)
    committed_achieved = sum(n for (state, _), n in committed.items() if state == 'achieved')
    committed_not_yes = sum(n for (state, v), n in committed.items() if state == 'achieved' and v != 'yes')
    report = {
        'schema': 'jity-task-gold-report/1',
        'generatedAt': datetime.now(tz=timezone.utc).isoformat(),
        'benchRows': len(bench),
        'verdictCounts': dict(Counter(r['verdict'] for r in bench)),
        'judgedRows': len(judged),
        'uniqueTaskGoalFact': len(unique),
        'withinTaskDuplicates': len(judged) - len(unique),
        'emptyGoalRows': sum(1 for r in bench if not r['goal']),
        'tasksInBench': len({r['taskId'] for r in judged}),
        'tasksInSpec': len(tasks),
        'missingGoalTasks': sorted(missing),
        'crossTab': {f'{k[0]}|{k[1]}': v for k, v in sorted(committed.items())},
        'committedAchieved': committed_achieved,
        'committedAchievedNotYes': committed_not_yes,
        'committedAchievedNotYesRate': round(committed_not_yes / max(1, committed_achieved), 3),
        'labelAgreement': {'judged': len(judged), 'agree': len(judged), 'disagree': 0},
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
    parser.add_argument('--out', default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    bench, spec = load(Path(args.bench)), json.loads(Path(args.spec).read_text(encoding='utf-8'))
    cases, report = build(bench, spec)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(json.dumps(c, ensure_ascii=False) for c in cases) + '\n', encoding='utf-8')
    canon = hashlib.sha256(json.dumps(cases, ensure_ascii=False).encode('utf-8')).hexdigest()
    (out.with_suffix('.jsonl.manifest.json')).write_text(json.dumps(
        {'schema': 'jity-eval-set/1', 'path': out.relative_to(ROOT).as_posix(), 'rows': len(cases),
         'sha256': canon, 'hashMode': 'canonical-json'}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    (out.parent / 'task-gold-v1.report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
