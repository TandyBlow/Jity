# -*- coding: utf-8 -*-
"""Extract phrase-rewrite pairs from the oracle-plan alignment: each difflib
'replace' opcode becomes (source phrase -> target phrase). These pairs are the
training data for the replacement layer that E36 showed to be missing."""
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


def tokens(text: str):
    return [w for w in jieba.lcut(text) if w.strip()]


def main():
    plans = {str(json.loads(l)['id']): json.loads(l) for l in PLAN.read_text(encoding='utf8').splitlines() if l.strip()}
    targets = {}
    for line in SRC.read_text(encoding='utf8').splitlines():
        if line.strip():
            row = json.loads(line)
            targets[str(row['id'])] = row['target']
    pairs = []
    stats = Counter()
    for rid, plan in plans.items():
        target = targets.get(rid)
        if not target:
            continue
        source = '。'.join(strip_prefix(plan['clauses'][i]) for i in plan['selected'])
        a, b = tokens(source), tokens(target)
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag != 'replace':
                continue
            src_phrase = ''.join(a[i1:i2])
            dst_phrase = ''.join(b[j1:j2])
            if not src_phrase or not dst_phrase:
                continue
            pairs.append({'id': rid, 'src': src_phrase, 'dst': dst_phrase})
            stats['pairs'] += 1
            if len(src_phrase) <= 2 and len(dst_phrase) <= 2:
                stats['short'] += 1
    (HERE / 'replace-pairs.jsonl').write_text(
        ''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in pairs), encoding='utf8')
    summary = {'pairs': stats['pairs'], 'shortPairs': stats['short'],
               'srcLenMean': round(sum(len(p['src']) for p in pairs) / max(1, len(pairs)), 1),
               'dstLenMean': round(sum(len(p['dst']) for p in pairs) / max(1, len(pairs)), 1)}
    (HERE / 'replace-pairs-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))
    for p in pairs[:12]:
        print(p['src'], '=>', p['dst'])


if __name__ == '__main__':
    main()
