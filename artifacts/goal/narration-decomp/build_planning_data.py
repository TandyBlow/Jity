# -*- coding: utf-8 -*-
"""Planning examples: which fact clauses enter the narration, and in what order.

For every sft-v13 row the settled facts are split into clause units; a clause is
'expressed' when any of its content words appears in the hand-written target.
The output order is the first appearance of a matched word in the target."""
import json
import re
from collections import Counter
from pathlib import Path

import jieba

ROOT = Path('D:/others/Jity')
SRC = ROOT / '.local/narr-train/sft-v13.jsonl'
OUT = Path(__file__).resolve().parent / 'planning-examples.jsonl'
STOP = set('的 了 着 过 地 得 是 在 把 被 将 让 给 向 从 对 与 和 及 而 却 便 就 都 也 还 很 更 最 又 再 才 只 分 他 她 它 他们 她们 它们 自己 对方 这 那 其 我 你 我们 你们 一个 一 二 三 两 之 于 为 以 所 但 然 后 里 上 下 中 前 后 边 面 头 了 的 着'.split())
PUNCT = re.compile(r'^[，。！？；：、"' + "'" + r'（）\n…—\s]+$')


def facts_of(prompt: str) -> str:
    marker = prompt.find('事实：')
    return prompt[marker + 3:] if marker >= 0 else prompt


def content_words(text: str):
    return [w for w in jieba.lcut(text) if len(w) >= 1 and not PUNCT.match(w) and w not in STOP]


def clauses_of(facts: str):
    parts = re.split(r'[。；]', facts)
    return [part.strip() for part in parts if len(part.strip()) >= 4]


def main():
    rows = [json.loads(line) for line in SRC.read_text(encoding='utf8').splitlines() if line.strip()]
    rows.sort(key=lambda row: str(row['id']))
    examples = []
    stats = Counter()
    for row in rows:
        target = row['target']
        clauses = clauses_of(facts_of(row['prompt']))
        expressed = []
        for index, clause in enumerate(clauses):
            words = [w for w in content_words(clause) if len(w) >= 2]
            positions = [target.find(w) for w in words if target.find(w) >= 0]
            if positions:
                expressed.append((index, min(positions)))
            stats['clauses'] += 1
        if not clauses:
            continue
        expressed.sort(key=lambda pair: pair[1])
        order = [index for index, _ in expressed]
        stats['expressed'] += len(order)
        examples.append({
            'id': str(row['id']),
            'clauses': clauses,
            'selected': order,
            'selectionRate': round(len(order) / len(clauses), 3),
            'targetChars': len(target),
        })
    OUT.write_text(''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in examples), encoding='utf8')
    summary = {
        'passages': len(examples),
        'clauseCount': stats['clauses'],
        'expressed': stats['expressed'],
        'selectionRate': round(stats['expressed'] / max(1, stats['clauses']), 3),
        'meanSelectionRate': round(sum(item['selectionRate'] for item in examples) / max(1, len(examples)), 3),
    }
    (Path(__file__).resolve().parent / 'planning-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
