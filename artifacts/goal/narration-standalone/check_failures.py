# -*- coding: utf-8 -*-
"""E61: failure taxonomy for a narration arm. Attribution (does a fact about X
land in a sentence whose subject is Y?), repeated sentence heads, unmatched
openings, outcome phrasing, and sentence shape."""
import json
import re
from collections import Counter
from pathlib import Path

import cluster_events as ce
import evaluate_narration as ev
from role_parse import NAMES, clauses, parse_result

HERE = Path(__file__).resolve().parent
CUE = re.compile(r'没有成功|没能|失败|未成功|无法|不成功|落空|只完成|一部分|部分完成')
HEAD = re.compile(r'^(路明非|诺诺|芬格尔|楚子航|凯撒|顾岚|林亦舟|秦越|唐骁|夏弥|绘梨衣)')


def bigrams(text):
    return ev.bigrams(text)


def best_sentence(fact, sents, cache):
    if fact in cache:
        return cache[fact]
    fg = bigrams(fact)
    best, ov = '', 0.0
    for s in sents:
        o = len(fg & bigrams(s)) / max(1, len(fg))
        if o > ov:
            best, ov = s, o
    cache[fact] = (best, ov)
    return best, ov


def check_row(row, text):
    sents = ev.sentences(text)
    cache = {}
    out = Counter()
    # 归属：事实主语 X 的最佳句子里出现别人、没有 X
    for c in clauses(row['factsText']):
        c = ce.clean(c)
        if len(c) < 6 or '做的事' in c or '玩家这回合' in c:
            continue
        subject = next((n for n in NAMES if c.startswith(n)), None)
        if not subject:
            subject = next((n for n in NAMES if re.match(r'^.{0,8}' + n + '的', c)), None)
        if not subject:
            continue
        best, ov = best_sentence(c, sents, cache)
        if ov < 0.4:
            continue
        out['attributed'] += 1
        others = [n for n in NAMES if n != subject and n in best]
        if others and subject not in best:
            out['misattributed'] += 1
            out.setdefault('examples', 0)
    # 同头句：相邻句以同一人名开头
    heads = [HEAD.match(s).group(1) if HEAD.match(s) else '' for s in sents]
    for a, b in zip(heads, heads[1:]):
        if a and a == b:
            out['sameHeadPairs'] += 1
    # 结果行：每条有结果的结算，是否在含该角色的句子里带线索
    for x in row['resultLines']:
        p = parse_result(x)
        if not p or not p['outcome']:
            continue
        actor_sents = [s for s in sents if p['actor'] in s]
        if p['outcome'] in ('没有成功', '无法完成', '失败'):
            out['failPartial'] += 1
            if any(CUE.search(s) for s in actor_sents):
                out['failPartialHit'] += 1
        elif p['outcome'] in ('只完成一部分', '部分成功'):
            out['failPartial'] += 1
            if any(CUE.search(s) for s in actor_sents):
                out['failPartialHit'] += 1
        else:
            out['success'] += 1
            ag = bigrams(p['action'])
            if any(len(ag & bigrams(s)) / max(1, len(ag)) >= 0.5 for s in actor_sents):
                out['successHit'] += 1
    # 开场：玩家行动句是否有对应的结果线索
    m = re.match(r'^玩家这回合让(.{1,4}?)做的事', row['playerLine'] or '')
    if m and sents and sents[0].startswith(m.group(1)):
        out['openings'] += 1
        if CUE.search(''.join(sents[:2])):
            out['openingWithOutcome'] += 1
    out['sentences'] += len(sents)
    out['chars'] += len(text)
    return out


def run(name, rows, texts):
    total = Counter()
    for row in rows:
        total.update(check_row(row, texts[row['id']]))
    total['points'] = len(rows)
    total['misattrRate'] = round(total['misattributed'] / max(1, total['attributed']), 3)
    total['failPartialRate'] = round(total['failPartialHit'] / max(1, total['failPartial']), 3)
    total['successRate'] = round(total['successHit'] / max(1, total['success']), 3)
    total['openingOutcomeRate'] = round(total['openingWithOutcome'] / max(1, total['openings']), 3)
    print(name, json.dumps({k: v for k, v in total.items() if k != 'examples'}, ensure_ascii=False))
    return dict(total)


def main():
    rows = [json.loads(l) for l in (HERE / 'inputs.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    cand = {r['id']: r['text'] for r in json.load(open(HERE / 'compose-candidate-rows.json', encoding='utf8'))}
    report = {}
    report['candidate-e60'] = run('candidate-e60', rows, cand)
    report['current-1.7b'] = run('current-1.7b', rows, {r['id']: r['systemProse'] or '' for r in rows})
    (HERE / 'check-failures.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    main()
