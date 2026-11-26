# -*- coding: utf-8 -*-
"""Evaluate scenario assertions against product acceptance evidence.

Reports run success, state assertions, task assertions, narration consistency
and full-turn time separately. COMPLETED alone is not a quality pass.
"""
import json
import re
import statistics
import sys
from pathlib import Path


def path_value(state, path):
    current = state
    for part in path.split('.'):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def active_changes(changes):
    if not isinstance(changes, list):
        return []
    superseded = {record for change in changes if isinstance(change, dict) for record in (change.get('supersedes') or [])}
    return [change for change in changes if isinstance(change, dict) and change.get('id') not in superseded]


def task_id_of(check):
    match = re.search(r'\.tasks\.([^.]+)\.status$', check.get('path') or '')
    return match.group(1) if match else None


def evaluate_check(state, check):
    if 'anyOf' in check:
        return any(evaluate_check(state, row) for row in check['anyOf'])
    value = path_value(state, check.get('path', ''))
    if 'equals' in check:
        return value == check['equals']
    if 'lte' in check:
        return value is not None and str(value) <= str(check['lte'])
    if 'activeTextMatches' in check or 'noneActiveTextMatches' in check:
        texts = [str(change.get('text') or '') for change in active_changes(value)]
        pattern = check.get('activeTextMatches') or check.get('noneActiveTextMatches')
        hit = any(re.search(pattern, text) for text in texts)
        return not hit if 'noneActiveTextMatches' in check else hit
    return False


def main():
    evidence_path = Path(sys.argv[1])
    scenarios_path = Path(sys.argv[2])
    evidence = json.loads(evidence_path.read_text(encoding='utf8'))
    scenarios = json.loads(scenarios_path.read_text(encoding='utf8'))
    checks_by_id = {row['id']: row for row in scenarios}
    rows = []
    for turn in evidence.get('turns') or []:
        scenario = checks_by_id.get(turn.get('id')) or {}
        record = (turn.get('snapshotAfterTurn') or {}).get('transport') or {}
        state = record.get('state') or {}
        checks = scenario.get('checks') or []
        passed = [check for check in checks if evaluate_check(state, check)]
        failed = [check for check in checks if check not in passed]
        task_checks = [check for check in checks if '.tasks.' in (check.get('path') or '')]
        task_passed = [check for check in task_checks if check in passed]
        expected_achieved = [check for check in task_checks if check.get('equals') == 'achieved']
        expected_pending = [check for check in task_checks if check.get('equals') == 'pending']
        achieved = [check for check in expected_achieved if check in passed]
        missed = [check for check in expected_achieved if check not in passed]
        false_achieved = [check for check in expected_pending if check not in passed]
        problems = turn.get('problems') or []
        rows.append({
            'turn': turn.get('turn'), 'id': turn.get('id'), 'waitMs': (turn.get('timings') or {}).get('doneMs'),
            'checks': len(checks), 'passed': len(passed), 'taskChecks': len(task_checks), 'taskPassed': len(task_passed),
            'expectedAchieved': len(expected_achieved), 'achieved': len(achieved), 'missed': len(missed),
            'falseAchieved': len(false_achieved),
            'expectedTaskIds': {task_id_of(check) for check in expected_achieved if task_id_of(check)},
            'achievedTaskIds': {task_id_of(check) for check in achieved if task_id_of(check)},
            'missedTaskIds': {task_id_of(check) for check in missed if task_id_of(check)},
            'falseTaskIds': {task_id_of(check) for check in false_achieved if task_id_of(check)},
            'failed': [check.get('path') or 'anyOf' for check in failed],
            'problems': problems,
        })
    waits = [row['waitMs'] for row in rows if row['waitMs']]
    checks = sum(row['checks'] for row in rows)
    passed = sum(row['passed'] for row in rows)
    task_checks = sum(row['taskChecks'] for row in rows)
    task_passed = sum(row['taskPassed'] for row in rows)
    expected_achieved = sum(row['expectedAchieved'] for row in rows)
    achieved = sum(row['achieved'] for row in rows)
    missed = sum(row['missed'] for row in rows)
    false_achieved = sum(row['falseAchieved'] for row in rows)
    expected_tasks = set().union(*(row['expectedTaskIds'] for row in rows)) if rows else set()
    achieved_tasks = set().union(*(row['achievedTaskIds'] for row in rows)) if rows else set()
    missed_tasks = set().union(*(row['missedTaskIds'] for row in rows)) if rows else set()
    false_tasks = set().union(*(row['falseTaskIds'] for row in rows)) if rows else set()
    prose_issues = sum(1 for row in rows for problem in row['problems']
                       if problem in ('prose_not_identical_to_record', 'program_text_not_model', 'source_program'))
    summary = {
        'evidence': evidence_path.name,
        'status': evidence.get('status'),
        'turns': len(rows),
        'runSuccess': evidence.get('status') == 'COMPLETED' and not evidence.get('failures'),
        'stateAssertions': f'{passed}/{checks}',
        'stateAssertionRate': round(passed / checks, 3) if checks else None,
        'taskAssertions': f'{task_passed}/{task_checks}',
        'taskAccuracy': round(task_passed / task_checks, 3) if task_checks else None,
        'achievementChecks': f'{achieved}/{expected_achieved}',
        'achievementRate': round(achieved / expected_achieved, 3) if expected_achieved else None,
        'missedAchievements': missed,
        'falseAchievements': false_achieved,
        'uniqueExpectedTasks': sorted(expected_tasks),
        'uniqueAchievedTasks': sorted(achieved_tasks),
        'uniqueMissedTasks': sorted(missed_tasks),
        'uniqueFalseTasks': sorted(false_tasks),
        'uniqueAchievementRate': round(len(achieved_tasks) / len(expected_tasks), 3) if expected_tasks else None,
        'proseIssueTurns': sum(1 for row in rows if set(row['problems']) & {'prose_not_identical_to_record', 'program_text_not_model', 'source_program'}),
        'proseIssues': prose_issues,
        'meanWaitS': round(statistics.mean(waits) / 1000, 1) if waits else None,
        'maxWaitS': round(max(waits) / 1000, 1) if waits else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for row in rows:
        print(f"turn {row['turn']} {row['id']}: state {row['passed']}/{row['checks']} "
              f"task {row['taskPassed']}/{row['taskChecks']} achieved {row['achieved']}/{row['expectedAchieved']} "
              f"false={row['falseAchieved']} missed={row['missed']} wait={round((row['waitMs'] or 0)/1000,1)}s "
              f"problems={','.join(row['problems']) or '-'}")
        if row['failed']:
            print('  failed: ' + '; '.join(row['failed']))


if __name__ == '__main__':
    main()
