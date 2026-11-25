# -*- coding: utf-8 -*-
"""Action retry breakdown from one or more turn evidence files.

Task-level records carry a source and issue codes; attempt records carry an
error string. Counts are separated so retries are not reported as tasks.
"""
import json
import sys
from collections import Counter
from pathlib import Path


def main():
    total = Counter()
    per_file = {}
    for path in sys.argv[1:]:
        data = json.loads(Path(path).read_text(encoding='utf8'))
        calls = [c for c in (data['turns'][0].get('product') or {}).get('semanticCalls') or [] if c['task'] == 'action']
        tasks = [c for c in calls if c.get('source')]
        attempts = [c for c in calls if not c.get('source')]
        issues = Counter()
        for call in tasks:
            issues.update(call.get('issues') or [])
        errors = Counter()
        for call in attempts:
            if call.get('error'):
                errors[call['error'][:60]] += 1
        per_file[path] = {
            'task_records': len(tasks), 'attempt_records': len(attempts),
            'task_sources': dict(Counter(c.get('source') for c in tasks)),
            'issue_codes': dict(issues), 'attempt_errors': dict(errors),
        }
        total.update(issues)
        total.update(errors)
    out = {'files': per_file, 'all_issue_codes': dict(total)}
    Path('D:/others/Jity/artifacts/goal/micro-workflow/action-retry-report.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
