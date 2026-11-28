# -*- coding: utf-8 -*-
"""Word-level edit profile between the oracle-plan concatenation and the
hand-written target: how much of the gap is keep / replace / insert / delete.
This defines the action space for an edit-based decoder."""
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import jieba

HERE = Path(__file__).resolve().parent
PLAN = HERE / 'planning-examples-v2.jsonl'
SRC = Path('D:/others/Jity/.local/narr-train/sft-v13.jsonl')


def strip_prefix(clause: str) -> str:
    body = re.sub(r'^玩家这回合.*?做的事：', '', clause)
    body = re.sub(r'^这一回合的结算结果：', '', body)
    body = re.sub(r'^[\u4e00-\u9fa5]{1,4}[：:]', '', body)
    return body.strip()


def words(text: str):
    return [w for w in jieba.lcut(text) if w.strip()]


def main():
    plans = {str(json.loads(l)['id']): json.loads(l) for l in PLAN.read_text(encoding='utf8').splitlines() if l.strip()}
    targets = {}
    for line in SRC.read_text(encoding='utf8').splitlines():
        if line.strip():
            row = json.loads(line)
            targets[str(row['id'])] = row['target']
    ops = Counter()
    per_passage = []
    for rid, plan in plans.items():
        target = targets.get(rid)
        if not target:
            continue
        source = '。'.join(strip_prefix(plan['clauses'][i]) for i in plan['selected'])
        a, b = words(source), words(target)
        matcher = SequenceMatcher(None, a, b, autojunk=False)
        counts = Counter()
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            counts[tag] += max(i2 - i1, j2 - j1)
        ops.update(counts)
        total = sum(counts.values())
        per_passage.append((rid, counts, total))
    total = sum(ops.values())
    summary = {
        'passages': len(per_passage),
        'tokens': total,
        'keep': round(ops['equal'] / total, 3),
        'replace': round(ops['replace'] / total, 3),
        'insert': round(ops['insert'] / total, 3),
        'delete': round(ops['delete'] / total, 3),
    }
    (HERE / 'edit-profile.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
