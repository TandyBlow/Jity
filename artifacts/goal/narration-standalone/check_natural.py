# -*- coding: utf-8 -*-
"""N16: grounding checks for a hand-written natural reference. Every clause
cites source fragments; entities, numbers and result labels must come from
those sources, and every result fragment must be used."""
import json
import re
from collections import Counter
from pathlib import Path

import evaluate_narration as ev
import renderer_dataset as rd
from role_parse import NAMES, parse_result

HERE = Path(__file__).resolve().parent
CUE = re.compile(r'没有成功|没能|失败|未成功|无法|不成功|落空|只完成|一部分|部分完成')
NUM = re.compile(r'\d{2,}(?:[:：]\d{2})?')


def main():
    rows = {r['id']: r for r in (json.loads(l) for l in open(HERE / 'pairs.jsonl', encoding='utf8'))}
    refs = json.load(open(HERE / 'natural-reference.json', encoding='utf8'))
    for ref in refs:
        point = rows[ref['id']]
        frag = {i: {'i': i, 'kind': k, 'text': t} for i, (k, t) in enumerate(rd.fragments(point))}
        text_by_i = {i: f['text'] for i, f in frag.items()}
        problems = []
        used = set()
        cue_text = ''
        for clause in ref['clauses']:
            source_text = '，'.join(text_by_i[i] for i in clause['sources'])
            used.update(clause['sources'])
            cue_text += clause['text']
            for name in NAMES:
                if name in clause['text'] and name not in source_text:
                    problems.append(f'invented_name:{name}:{clause["text"][:20]}')
            for num in NUM.findall(clause['text']):
                if num not in source_text:
                    problems.append(f'invented_number:{num}')
            cover = ev.coverage(clause['text'], ev.bigrams(source_text))
            if cover < 0.5:
                problems.append(f'low_grounding:{cover}:{clause["text"][:20]}')
        for i, f in frag.items():
            if f['kind'] != 'result':
                continue
            result = parse_result(f['text'])
            if not result or not result['outcome']:
                continue
            if i not in used:
                problems.append(f'result_missing:{i}')
            else:
                cue = CUE if result['outcome'] in ('没有成功', '无法完成', '失败', '只完成一部分', '部分成功') else None
                if cue and not CUE.search(cue_text):
                    problems.append(f'outcome_cue_missing:{i}')
        omitted = sorted(set(text_by_i) - used)
        print(json.dumps({
            'id': ref['id'],
            'clauses': len(ref['clauses']),
            'used': sorted(used),
            'omitted': omitted,
            'problems': problems,
        }, ensure_ascii=False))
        print('TEXT:', ''.join(c['text'] for c in ref['clauses']))


if __name__ == '__main__':
    main()
