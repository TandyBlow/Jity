# -*- coding: utf-8 -*-
"""NPC behavior-category dataset from recorded action calls.

Input is the same compact sheet the action head will see in the browser; the
label is the category of the accepted action text, derived with the same rules
as `actions/structure.ts`.
"""
import json
from collections import Counter
from pathlib import Path

PUB = Path('D:/others/Jity/artifacts/goal/micro-workflow')
RULES = [
    ('move', ['走进', '走入', '走到', '走向', '进入', '来到', '回到', '退回', '退到', '跑到', '冲向', '赶到', '爬上', '走下', '钻出', '穿过', '离开', '前往', '让路']),
    ('assist', ['递给', '交给', '塞给', '扶', '帮助', '掩护', '拉开', '托住', '抬起', '包扎']),
    ('guard', ['守住', '挡住', '拦住', '拦下', '护住', '戒备']),
    ('communicate', ['问', '说', '喊', '告诉', '报告', '回答', '解释', '示意', '呼叫', '对讲']),
    ('hide', ['蹲', '躲', '藏', '伏下', '屏住']),
    ('observe', ['看', '检查', '确认', '查看', '望', '观察', '核对', '清点', '找']),
    ('use', ['用', '换', '装', '拿', '举', '按', '推', '拉', '打开', '关闭', '戴上', '摘下']),
]


def category(text):
    for name, words in RULES:
        if any(word in text for word in words):
            return name
    return 'other'


def main():
    rows = [json.loads(line) for line in open(PUB / 'short-inputs.jsonl', encoding='utf8')]
    out = []
    for row in rows:
        if row['task'] != 'act' or not row.get('text'):
            continue
        out.append({'run': row['run'], 'input': row['input'], 'label': category(row['text']), 'text': row['text']})
    (PUB / 'behavior-data.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in out), encoding='utf8')
    print('rows', len(out), 'labels', dict(Counter(r['label'] for r in out)),
          'runs', dict(Counter(r['run'] for r in out)))


if __name__ == '__main__':
    main()
