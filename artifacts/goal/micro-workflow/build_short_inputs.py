# -*- coding: utf-8 -*-
"""Build short structured inputs for the task heads from recorded prompts.

The long LLM prompts are parsed once; the heads see a compact state summary,
not the prompt. Labels come from the accepted raw answers of the same calls.
"""
import json
import re
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
ACTOR = re.compile(r'- ([^（(]+)（id=([^）)]+)）位置=([^；]+)；精神=[^；]+；个性=(.*?)；待办=([^\n]+)', re.S)
MEMBER = re.compile(r'^- ([^（(]+)（id=([^）)]+)）行动：(.+)')
JUDGE = re.compile(r'^判定：(?:目标([^(（]+)\(([^)]+)\) 骰点=(\d+) 资格=(\w+) 准入=(\w+)|无判定)')


def main():
    rows = [json.loads(line) for line in open(PUB / 'records.jsonl', encoding='utf8')]
    out = []
    for row in rows:
        try:
            raw = json.loads(row['raw'])
        except json.JSONDecodeError:
            continue
        if row['task'] == 'action':
            match = ACTOR.search(row['prompt'])
            if not match:
                continue
            name, _id, position, personality, tasks = match.groups()
            out.append({'run': row['run'], 'task': 'act', 'label': raw.get('kind'),
                        'input': f'角色：{name}；位置：{position}；个性：{personality[:40]}；待办：{tasks[:120]}',
                        'text': (raw.get('text') or '')[:120]})
        elif row['task'] == 'results':
            members, judges = [], []
            for line in row['prompt'].split('\n'):
                stripped = line.strip()
                member = MEMBER.match(stripped)
                if member:
                    members.append(member.groups())
                    continue
                judge = JUDGE.match(stripped)
                if judge:
                    judges.append(judge.groups())
            judgments = {j.get('memberId'): j for j in raw.get('judgments') or []}
            for (name, mid, action), judge in zip(members, judges):
                judgment = judgments.get(mid)
                if not judgment or judgment.get('label') not in ('achieved', 'partial', 'not_achieved', 'blocked', 'no_change'):
                    continue
                if judge[0] is None:
                    roll, qual, admitted = '?', '?', '?'
                else:
                    _tname, _tid, roll, qual, admitted = judge
                out.append({'run': row['run'], 'task': 'result', 'label': judgment['label'],
                            'input': f'角色：{name}；行动：{action[:80]}；骰点：{roll}；资格：{qual}；准入：{admitted}',
                            'text': (judgment.get('reason') or '')[:120]})
    (PUB / 'short-inputs.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in out), encoding='utf8')
    from collections import Counter
    counts = Counter((r['task'], r['label']) for r in out)
    runs = Counter(r['run'] for r in out)
    print('samples', len(out), dict(counts), 'runs', dict(runs))


if __name__ == '__main__':
    main()
