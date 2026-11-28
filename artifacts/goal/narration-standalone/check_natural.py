# -*- coding: utf-8 -*-
"""N16: grounding checks for a hand-written natural reference. Every clause
cites source fragments; entities, numbers and result labels must come from
those sources, and every result must appear in its own clause."""
import json
import re
from pathlib import Path

import evaluate_narration as ev
import renderer_dataset as rd
from role_parse import NAMES

HERE = Path(__file__).resolve().parent
CUE = re.compile(r'没有成功|没能|失败|未成功|无法|不成功|落空|只完成|一部分|部分完成')
NUM = re.compile(r'\d{2,}(?:[:：]\d{2})?')
OUTCOME_PHRASE = {
    '没有成功': '没有成功', '只完成一部分': '只完成了一部分', '无法完成': '没能完成',
    '部分成功': '只完成了一部分', '失败': '失败了', '达到目的': '',
}


def parse_fragment_result(text):
    """片段格式：角色 + 动作 + 结果短语（没有冒号）。"""
    actor = next((n for n in NAMES if text.startswith(n)), None)
    if not actor:
        return None
    action = text[len(actor):]
    outcome = '达到目的'
    for key, phrase in OUTCOME_PHRASE.items():
        if phrase and phrase in action:
            outcome = key
            action = action.replace(phrase, '')
    return {'actor': actor, 'action': action, 'outcome': outcome}


def check_ref(ref, rows):
    point = rows[ref['id']]
    frag = {i: {'i': i, 'kind': k, 'text': t} for i, (k, t) in enumerate(rd.fragments(point))}
    text_by_i = {i: f['text'] for i, f in frag.items()}
    problems = []
    used = set()
    for clause in ref['clauses']:
        source_text = '，'.join(text_by_i[i] for i in clause['sources'])
        used.update(clause['sources'])
        for name in NAMES:
            if name in clause['text'] and name not in source_text:
                problems.append(f'invented_name:{name}:{clause["text"][:20]}')
        for num in NUM.findall(clause['text']):
            if num not in source_text:
                problems.append(f'invented_number:{num}')
        cover = ev.coverage(clause['text'], ev.bigrams(source_text))
        if cover < 0.5:
            problems.append(f'low_grounding:{cover}:{clause["text"][:20]}')
    clauses_of = {}
    for clause in ref['clauses']:
        for i in clause['sources']:
            clauses_of.setdefault(i, []).append(clause)
    for i, f in frag.items():
        if f['kind'] != 'result':
            continue
        result = parse_fragment_result(f['text'])
        if not result:
            continue
        own = clauses_of.get(i) or []
        if not own:
            problems.append(f'result_missing:{i}')
            continue
        cue = CUE if result['outcome'] in ('没有成功', '无法完成', '失败', '只完成一部分', '部分成功') else None
        for clause in own:
            text = clause['text']
            source_text = '，'.join(text_by_i[s] for s in clause['sources'])
            actor_ok = result['actor'] in text or (('他' in text or '她' in text) and result['actor'] in source_text)
            action_ok = ev.coverage(result['action'], ev.bigrams(text)) >= 0.35
            cue_ok = (not cue) or bool(cue.search(text))
            if not (actor_ok and action_ok and cue_ok):
                problems.append(
                    f'result_not_in_its_clause:{i}:actor={actor_ok}:action={action_ok}:cue={cue_ok}')
    omitted = sorted(set(text_by_i) - used)
    return {'id': ref['id'], 'clauses': len(ref['clauses']), 'used': sorted(used),
            'omitted': omitted, 'problems': problems}


def main():
    rows = {r['id']: r for r in (json.loads(l) for l in open(HERE / 'pairs.jsonl', encoding='utf8'))}
    refs = json.load(open(HERE / 'natural-reference.json', encoding='utf8'))
    for ref in refs:
        result = check_ref(ref, rows)
        print(json.dumps(result, ensure_ascii=False))
        print('TEXT:', ''.join(c['text'] for c in ref['clauses']))


if __name__ == '__main__':
    main()
