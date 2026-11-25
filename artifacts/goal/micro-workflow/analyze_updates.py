# -*- coding: utf-8 -*-
"""Break the updates task down per arm: real calls, program skips, retries,
prompt sizes and time. Answers where the slowdown comes from."""
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

PUB = Path('D:/others/Jity/artifacts/goal/micro-workflow')


def arm(path):
    data = json.loads(Path(path).read_text(encoding='utf8'))
    calls = [c for c in (data['turns'][0].get('product') or {}).get('semanticCalls') or [] if c['task'] == 'updates']
    by_key = defaultdict(list)
    for call in calls:
        by_key[call['key']].append(call)
    stages = Counter()
    real_ms = defaultdict(float)
    skip_calls = retries = 0
    chars = []
    for key, group in by_key.items():
        stage = key.split('#')[-1] if '#' in key else 'merged'
        stages[stage] += len(group)
        if len(group) > 1:
            retries += len(group) - 1
        for call in group:
            ms = call.get('ms') or 0
            size = call.get('promptChars') or 0
            if ms == 0 and size == 0:
                skip_calls += 1
                continue
            real_ms[stage] += ms
            chars.append(size)
    return {
        'file': str(path),
        'calls': len(calls),
        'program_skips': skip_calls,
        'real_calls': len(calls) - skip_calls,
        'retry_calls': retries,
        'stage_calls': dict(stages),
        'real_ms': {k: round(v) for k, v in real_ms.items()},
        'total_real_ms': round(sum(real_ms.values())),
        'prompt_chars_median': int(statistics.median(chars)) if chars else 0,
        'prompt_chars_max': max(chars) if chars else 0,
    }


def main():
    rows = [arm(p) for p in sys.argv[1:]]
    out = PUB / 'updates-breakdown.json'
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf8')
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == '__main__':
    main()
