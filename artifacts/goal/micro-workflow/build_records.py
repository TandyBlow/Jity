# -*- coding: utf-8 -*-
"""Extract real semantic (prompt, raw) pairs from a recorded acceptance run."""
import json
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
EVIDENCES = sorted(PUB.glob('evidence-record-*.json'))


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
    rows, counts = [], {}
    index = 0
    for path in EVIDENCES:
        data = json.loads(path.read_text(encoding='utf8'))
        run = path.stem.replace('evidence-record-', '')
        for turn in data.get('turns') or []:
            for item in (turn.get('product') or {}).get('semanticLog') or []:
                task = task_of(item['prompt'])
                counts[task] = counts.get(task, 0) + 1
                rows.append({'id': f'{run}-{index:03d}', 'run': run, 'task': task, 'prompt': item['prompt'],
                             'raw': item['raw'], 'ms': round(item.get('ms', 0), 1)})
                index += 1
    (PUB / 'records.jsonl').write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf8')
    print('records', len(rows), counts)


if __name__ == '__main__':
    main()
