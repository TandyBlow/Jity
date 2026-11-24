# -*- coding: utf-8 -*-
"""Filter validated semantic calls into training samples.

Raw LLM answers are not labels: a call enters the set only when the engine
reported no error issue, and update positions must point at a real container
slot. The output keeps per-task samples plus a validity report.
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
EVIDENCE = PUB / 'evidence-record-two.json'
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'
ERROR_CODES = {'action_is_task_goal', 'target_unknown', 'target_self', 'absent_character_in_action',
               'absent_item_in_action', 'repair_failed', 'decode_failure', 'model_failure'}
RESULT_LABELS = {'achieved', 'partial', 'not_achieved', 'blocked', 'no_change'}


def slots_of(container: dict | None) -> set[str]:
    return {slot.get('id') for slot in (container or {}).get('slots') or [] if slot.get('id')}


def main():
    world = json.loads(WORLD.read_text(encoding='utf8'))['initial']
    containers = {}
    for loc in world.get('locations', {}).values():
        containers[loc['id']] = slots_of(loc)
    for item in world.get('items', {}).values():
        if item.get('slots'):
            containers[item['id']] = slots_of(item)
    data = json.loads(EVIDENCE.read_text(encoding='utf8'))
    calls = data['turns'][0]['product'].get('semanticCalls') or []
    rows, report = [], {'calls': len(calls), 'valid': 0, 'invalid': 0, 'by_task': Counter(),
                        'invalid_codes': Counter(), 'positions_invalid': [], 'results_labels': Counter(),
                        'action_kinds': Counter(), 'facts': 0, 'appearances': 0}
    for index, call in enumerate(calls):
        issues = call.get('issues') or []
        valid = not any(code in ERROR_CODES for code in issues)
        raw = call.get('raw') or ''
        parsed, parse_error = None, None
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as error:
                parse_error = str(error)
        if parse_error:
            valid = False
        entry = {'id': f'call-{index:03d}', 'task': call['task'], 'key': call['key'], 'ms': call['ms'],
                 'valid': valid, 'issues': issues, 'parsed': parsed, 'raw': raw}
        if call['task'] == 'updates' and isinstance(parsed, dict):
            bad = []
            for pos in parsed.get('positions') or []:
                cid, sid = pos.get('containerId'), pos.get('slotId')
                if cid not in containers or (sid is not None and sid not in containers[cid]):
                    bad.append(pos)
            if bad:
                valid = False
                entry['valid'] = False
                report['positions_invalid'].extend(bad[:3])
            report['appearances'] += len(parsed.get('appearances') or [])
        if call['task'] == 'results' and isinstance(parsed, dict):
            for judgment in parsed.get('judgments') or []:
                label = judgment.get('label')
                if label in RESULT_LABELS:
                    report['results_labels'][label] += 1
                else:
                    valid = False
                    entry['valid'] = False
            report['facts'] += len(parsed.get('facts') or [])
        if call['task'] == 'action' and isinstance(parsed, dict):
            kind = parsed.get('kind')
            report['action_kinds'][kind] += 1
            if kind not in ('act', 'skip'):
                valid = False
                entry['valid'] = False
        report['by_task'][call['task']] += 1
        report['valid' if valid else 'invalid'] += 1
        for code in issues:
            report['invalid_codes'][code] += 1
        rows.append(entry)
    (PUB / 'training.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf8')
    report['by_task'] = dict(report['by_task'])
    report['invalid_codes'] = dict(report['invalid_codes'])
    report['results_labels'] = dict(report['results_labels'])
    report['action_kinds'] = dict(report['action_kinds'])
    report['positions_invalid'] = report['positions_invalid'][:5]
    (PUB / 'training-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
