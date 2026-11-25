# -*- coding: utf-8 -*-
"""Blind human-eval sheet for continuation heads (held-out actors).

Labels are not printed. The evaluator judges the four questions directly from
the context and candidate. A second evaluator who did not write the rules is
the intended user; an assistant spot-check is recorded separately and does not
count as independent.
"""
import json
from pathlib import Path

PUB = Path('D:/others/Jity/artifacts/goal/micro-workflow')
KEYS = ('novelty', 'unfinished', 'necessity', 'intervene')


def main():
    rows = [json.loads(line) for line in open(PUB / 'continuation-data.jsonl', encoding='utf8')]
    held = [row for row in rows if row['split'] == 'test']
    picked = []
    for actor in sorted({row['actor'] for row in held}):
        for variant in ('base', 'continuous', 'player_present', 'idle'):
            items = [row for row in held if row['actor'] == actor and row['variant'] == variant][:4]
            picked.extend(items)
    template = {
        'reviewer': None,
        'instructions': '对每一行独立判断，不参考规则或模型输出；overall_continue 表示是否允许游戏自动推进这条候选。',
        'rows': [{
            'id': f'c{index + 1:02d}',
            'scenario': row['scenario'],
            'context': row['context'],
            'candidate': row['candidate'],
            'novelty': None, 'unfinished': None, 'necessity': None, 'intervene': None,
            'overall_continue': None, 'notes': '',
        } for index, row in enumerate(picked)],
    }
    (PUB / 'continuation-human-eval-template.json').write_text(
        json.dumps(template, ensure_ascii=False, indent=1), encoding='utf8')
    lines = ['# Continuation 盲评表（held-out 人物）', '',
             '判断每题四个问题，再给一个总体结论。不要参考训练标签或模型输出。',
             '- 新颖性：这条候选是否带来本轮尚未发生的新事件（不是原句重放）。',
             '- 未完成交互：它是否推进一个未完成的待办或尚未收束的互动。',
             '- 必要性：这个 NPC 是否“必须现在行动”，而不只是“可以行动”。',
             '- 玩家介入：是否应由玩家先决定（涉及主角、主角物品或关键选择）。',
             '- 总体：是否允许自动推进这条候选。', '']
    for index, row in enumerate(template['rows']):
        lines.extend([
            f"## {row['id']}", '',
            f"- 情境：{row['context']}",
            f"- 候选：{row['candidate']}",
            '- 新颖性：☐ 是 ☐ 否；未完成交互：☐ 是 ☐ 否；必要性：☐ 是 ☐ 否；玩家介入：☐ 是 ☐ 否',
            '- 总体：☐ 允许自动推进 ☐ 交还玩家', '',
        ])
    (PUB / 'continuation-human-eval-sheet.md').write_text('\n'.join(lines), encoding='utf8')
    print('rows', len(template['rows']), 'scenarios', len({row['scenario'] for row in picked}))


if __name__ == '__main__':
    main()
