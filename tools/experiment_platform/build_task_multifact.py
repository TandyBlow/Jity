#!/usr/bin/env python3
"""Build multi-fact, cross-turn task cases from scenario acceptance evidence.

Each case is (task goal, accumulated committed result facts up to turn t, old
task status at that turn). Facts come from the turn's point prompts after the
settlement section, so a case can contain several facts and span turns.

Labels are intentionally empty: this is a dev/regression set for the semantic
agent; the frozen 8-scenario set has driven fixes and is not independent.

  python -m tools.experiment_platform.build_task_multifact
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.experiment_platform.build_narration_holdout import (  # noqa: E402
    parse_facts_block, result_lines, split_prompt,
)

EVIDENCE = ROOT / 'artifacts/goal/narration-rules/scenarios8-rules.json'
OUT = ROOT / 'artifacts/goal/platform/task-gold/task-multifact-v1.jsonl'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--evidence', default=str(EVIDENCE))
    parser.add_argument('--out', default=str(OUT))
    args = parser.parse_args(argv)
    doc = json.loads(Path(args.evidence).read_text(encoding='utf-8-sig'))
    cases, seen = [], set()
    accumulated: list[str] = []
    for index, turn in enumerate(doc.get('turns') or [], 1):
        product = turn.get('product') or {}
        for item in product.get('pointPrompts') or []:
            if not isinstance(item, dict) or not item.get('prompt'):
                continue
            facts = split_prompt(item['prompt'])
            if not facts:
                continue
            _, settlement = parse_facts_block(facts)
            accumulated.extend(result_lines(settlement))
        facts = list(dict.fromkeys(accumulated))
        state = ((turn.get('snapshotAfterTurn') or {}).get('transport') or {}).get('state') or {}
        for owner in (state.get('characters') or {}).values():
            for task in (owner.get('tasks') or {}).values():
                goal = task.get('goal')
                if not goal:
                    continue
                key = (task.get('id'), tuple(facts))
                if key in seen:
                    continue
                seen.add(key)
                cases.append({
                    'id': 'tmf-v1:' + hashlib.sha1((str(task.get('id')) + '|' + '|'.join(facts)).encode('utf-8')).hexdigest()[:12],
                    'modality': 'semantic', 'world': 'dragon-raja-free-day', 'split': 'dev',
                    'taskId': task.get('id'), 'goal': goal, 'ownerId': task.get('ownerId'),
                    'turnId': turn.get('id'), 'turnIndex': index,
                    'facts': facts, 'factCount': len(facts),
                    'oldStatus': task.get('status'), 'verdict': None, 'needsReview': True,
                    'provenance': {'labelSource': 'scenario point prompts settlement lines accumulated to this turn',
                                   'note': 'multi-fact cross-turn dev case; labels intentionally empty'},
                })
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(json.dumps(c, ensure_ascii=False) for c in cases) + '\n', encoding='utf-8')
    canon = hashlib.sha256(json.dumps(cases, ensure_ascii=False).encode('utf-8')).hexdigest()
    out.with_suffix('.jsonl.manifest.json').write_text(json.dumps(
        {'schema': 'jity-eval-set/1', 'path': out.relative_to(ROOT).as_posix(), 'rows': len(cases),
         'sha256': canon, 'hashMode': 'canonical-json'}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    summary = {'schema': 'jity-task-multifact/1', 'turns': len(doc.get('turns') or []),
               'cases': len(cases), 'avgFacts': round(sum(c['factCount'] for c in cases) / max(1, len(cases)), 1),
               'tasks': len({c['taskId'] for c in cases}),
               'oldAchieved': sum(1 for c in cases if c['oldStatus'] == 'achieved'),
               'usage': 'dev/regression; scenario set has driven fixes, not independent'}
    out.with_suffix('.summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
