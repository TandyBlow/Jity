# -*- coding: utf-8 -*-
"""Extract (fact clause, human sentence) pairs for hand-labelling sentence frames.
Each target sentence is matched to the selected clause with the largest
character overlap; rows without a plan are skipped."""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = HERE / 'planning-examples-v14.jsonl'
SRC = Path('D:/others/Jity/.local/narr-train/sft-v14.jsonl')


def strip_prefix(clause):
    clause = re.sub(r'^玩家这回合.*?做的事：', '', clause)
    clause = re.sub(r'^这一回合的结算结果：', '', clause)
    clause = re.sub(r'^[\u4e00-\u9fa5]{1,4}[：:]', '', clause)
    return clause.strip()


def overlap(a, b):
    return len({c for c in a if '\u4e00' <= c <= '\u9fff'} & {c for c in b if '\u4e00' <= c <= '\u9fff'})


def main():
    plans = {str(json.loads(l)['id']): json.loads(l) for l in PLAN.read_text(encoding='utf8').splitlines() if l.strip()}
    rows = [json.loads(l) for l in SRC.read_text(encoding='utf8').splitlines() if l.strip()]
    out = []
    for row in rows:
        plan = plans.get(str(row['id']))
        if not plan:
            continue
        clauses = [strip_prefix(plan['clauses'][i]) for i in plan['selected']]
        sentences = [s.strip() for s in re.split(r'(?<=[。！？])', row['target']) if s.strip()]
        for sentence in sentences:
            if len(sentence) < 6:
                continue
            best = max(clauses, key=lambda c: overlap(c, sentence)) if clauses else ''
            out.append({'id': str(row['id']), 'sentence': sentence, 'clause': best,
                        'overlap': overlap(best, sentence)})
    (HERE / 'frame-pairs.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in out), encoding='utf8')
    print(json.dumps({'pairs': len(out), 'rows': len(rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
