# -*- coding: utf-8 -*-
"""Extract real semantic (prompt, raw) pairs from a recorded acceptance run."""
import json
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
EVIDENCE = PUB / 'evidence-record-one.json'


def task_of(prompt: str) -> str:
    if '共同结算器' in prompt:
        return 'results'
    if '牵连判断器' in prompt:
        return 'targets'
    if '角色行动判断器' in prompt:
        return 'action'
    if '位置结算器' in prompt:
        return 'updates'
    if prompt.startswith('当前世界时间') and '结算结果' in prompt:
        return 'updates'
    if '自动推进判断器' in prompt:
        return 'continuation'
    if '反应生成器' in prompt:
        return 'reaction'
    return 'other'


def main():
    data = json.loads(EVIDENCE.read_text(encoding='utf8'))
    log = data['turns'][0]['product'].get('semanticLog') or []
    rows, counts = [], {}
    for index, item in enumerate(log):
        task = task_of(item['prompt'])
        counts[task] = counts.get(task, 0) + 1
        rows.append({'id': f'rec-{index:03d}', 'task': task, 'prompt': item['prompt'],
                     'raw': item['raw'], 'ms': round(item.get('ms', 0), 1)})
    (PUB / 'records.jsonl').write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf8')
    print('records', len(rows), counts)


if __name__ == '__main__':
    main()
