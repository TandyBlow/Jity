# -*- coding: utf-8 -*-
"""Independent human-evaluation sheet for the held-out judge scenarios.

The reviewer marks every reasonable candidate (several may be); an empty
approval means none is reasonable. `human-eval-template.json` is the
machine-readable twin to fill in.
"""
import json
from collections import defaultdict
from pathlib import Path

PUB = Path('D:/others/Jity/artifacts/goal/micro-workflow')
HELD = {'caesar', 'lin', 'qin', 'tomiyama'}


def main():
    rows = [json.loads(line) for line in open(PUB / 'judge-data.jsonl', encoding='utf8')]
    scenarios = defaultdict(list)
    for row in rows:
        if row['actor'] in HELD:
            scenarios[row['scenario']].append(row)
    lines = ['# NPC 行为人工评价表', '',
             '对每个场景，在认为合理的行为前打 `[x]`；同一场景可以有多个合理行为。',
             '全部不合理就留空并在备注里说明。评价只看“这个角色此刻做这件事是否合理”，不看措辞。', '']
    template = []
    for scenario, items in sorted(scenarios.items()):
        context = items[0]['context']
        lines.append(f'## {scenario}')
        lines.append('')
        lines.append(context)
        lines.append('')
        for index, row in enumerate(items, start=1):
            lines.append(f'- [ ] {index}. {row["candidate"]}（{row["category"]}）')
        lines.append('')
        lines.append('备注：')
        lines.append('')
        template.append({
            'scenario': scenario, 'context': context,
            'candidates': [row['candidate'] for row in items],
            'approved': [], 'notes': '',
        })
    (PUB / 'human-eval-sheet.md').write_text('\n'.join(lines), encoding='utf8')
    (PUB / 'human-eval-template.json').write_text(json.dumps(template, ensure_ascii=False, indent=1), encoding='utf8')
    print('scenarios', len(template))


if __name__ == '__main__':
    main()
