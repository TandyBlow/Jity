# -*- coding: utf-8 -*-
"""N16 negative controls: the grounding checker must reject a clause that
cites another actor's result and a result whose failure cue was dropped."""
import copy
import json
from pathlib import Path

import check_natural as cn

HERE = Path(__file__).resolve().parent


def main():
    rows = {r['id']: r for r in (json.loads(l) for l in open(HERE / 'pairs.jsonl', encoding='utf8'))}
    refs = json.load(open(HERE / 'natural-reference.json', encoding='utf8'))
    base = next(d for d in refs if d['id'].endswith('s03-act-talk:point_round_45_2'))
    cases = []
    wrong_actor = copy.deepcopy(base)
    wrong_actor['clauses'][1] = {'text': '凯撒留在红方集结点等待，没有成功。', 'sources': [1, 2]}
    cases.append(('wrong_actor', wrong_actor, 'result_not_in_its_clause:1'))
    dropped_cue = copy.deepcopy(base)
    dropped_cue['clauses'][0] = {'text': '凯撒留在红方集结点等待。', 'sources': [0]}
    cases.append(('dropped_cue', dropped_cue, 'result_not_in_its_clause:0'))
    ok = True
    for name, ref, expected in cases:
        problems = cn.check_ref(ref, rows)['problems']
        caught = any(problem.startswith(expected) for problem in problems)
        ok = ok and caught
        print(json.dumps({'case': name, 'caught': caught, 'problems': problems}, ensure_ascii=False))
    print('all-caught', ok)


if __name__ == '__main__':
    main()
