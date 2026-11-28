# -*- coding: utf-8 -*-
"""Replacement pairs with context: each (src -> dst) pair also carries the
fact clause it came from and the previous target sentence. The split for the
context experiment is by passage id, not by phrase, so an unseen phrasing is
not required; choosing the right rewrite for the same phrase is."""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import jieba

HERE = Path(__file__).resolve().parent
PLAN = HERE / 'planning-examples-v2.jsonl'
SRC = Path('D:/others/Jity/.local/narr-train/sft-v13.jsonl')
OUT = HERE / 'replace-pairs-ctx.jsonl'


def strip_prefix(clause: str) -> str:
    body = re.sub(r'^玩家这回合.*?做的事：', '', clause)
    body = re.sub(r'^这一回合的结算结果：', '', body)
    body = re.sub(r'^[\u4e00-\u9fa5]{1,4}[：:]', '', body)
    return body.strip()


def tokens(text: str):
    return [w for w in jieba.lcut(text) if w.strip()]


def sentences_with_spans(tokens):
    spans, start = [], 0
    for i, tok in enumerate(tokens):
        if tok in '。；！？':
            spans.append((start, i + 1))
            start = i + 1
    if start < len(tokens):
        spans.append((start, len(tokens)))
    return spans


def main():
    plans = {str(json.loads(l)['id']): json.loads(l) for l in PLAN.read_text(encoding='utf8').splitlines() if l.strip()}
    rows = {}
    for line in SRC.read_text(encoding='utf8').splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row['id'])] = row
    pairs = []
    for rid, plan in plans.items():
        row = rows.get(rid)
        if not row:
            continue
        target = row['target']
        b = tokens(target)
        spans = sentences_with_spans(b)
        for index in plan['selected']:
            clause = strip_prefix(plan['clauses'][index])
            a = tokens(clause)
            if not a or not b:
                continue
            for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
                if tag != 'replace':
                    continue
                src, dst = ''.join(a[i1:i2]), ''.join(b[j1:j2])
                if not src or not dst:
                    continue
                sent_index = next((k for k, (s, e) in enumerate(spans) if s <= j1 < e), 0)
                prev = ''.join(b[spans[sent_index - 1][0]:spans[sent_index - 1][1]]) if sent_index > 0 else ''
                pairs.append({'id': rid, 'src': src, 'dst': dst, 'clause': clause,
                              'prev': prev, 'sent': sent_index})
    OUT.write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in pairs), encoding='utf8')
    print(json.dumps({'pairs': len(pairs), 'rows': len({p['id'] for p in pairs}),
                      'withPrev': sum(1 for p in pairs if p['prev'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
