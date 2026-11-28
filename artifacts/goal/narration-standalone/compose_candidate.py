# -*- coding: utf-8 -*-
"""N07: zero-parameter narration candidate. Opens with the player's declared
action, narrates only fresh facts plus every settlement result, puts the clock
last. No model, no weights."""
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import cluster_events as ce
from role_parse import clauses, parse_result

HERE = Path(__file__).resolve().parent
ACTION = re.compile(r'^玩家这回合让(.{1,4}?)做的事[：:](.+)$')


def fact_list(row):
    out = []
    for c in clauses(row['factsText']):
        c = ce.clean(c)
        if len(c) > 4 and '做的事' not in c and '玩家这回合' not in c:
            out.append(c)
    return out


def opening_of(row, facts):
    m = ACTION.match(row['playerLine'] or '')
    if not m:
        return None
    name, body = m.group(1), m.group(2).strip('。 ')
    # 玩家说了另一个地点而结算没有移动过去：丢掉那一段，避免把意图写成事实
    loc = next((c for c in facts if c.startswith(name) and '现在在' in c), '')
    place = loc.split('现在在')[1].split('，')[0] if '现在在' in loc else ''
    if place:
        body = '，'.join(p for p in body.split('，') if place not in p) or body
    body = body.replace('我', name)
    if body.startswith(name):
        body = body[len(name):]
    if not body:
        return None
    # 结算行已经写了同一动作时不要再开场复述
    grams = {body[i:i + 2] for i in range(len(body) - 1)}
    for x in row['resultLines']:
        p = parse_result(x)
        if not p:
            continue
        a = p['action']
        ag = {a[i:i + 2] for i in range(len(a) - 1)}
        if grams and len(grams & ag) / len(grams) >= 0.5:
            return None
    return f'{name}{body}'


NAME_HEAD = re.compile(r'^(路明非|诺诺|芬格尔|秦越|阿豹|林亦舟|楚子航|凯撒|顾岚|唐骁|夏弥|绘梨衣)')


def polish(text):
    """相邻句同主语时第二句改用代词，避免'路明非……。路明非……'。"""
    paras, last = [], None
    for para in text.split('\n\n'):
        sents = [x.strip().rstrip('。') for x in re.split(r'。', para) if x.strip()]
        fixed = []
        for sent in sents:
            m = NAME_HEAD.match(sent)
            if m and last == m.group(1) and ce.GENDER.get(m.group(1)):
                sent = ce.GENDER[m.group(1)] + sent[len(m.group(1)):]
                m = None
            fixed.append(sent)
            if m:
                last = m.group(1)
        if fixed:
            paras.append('。'.join(fixed) + '。')
    return '\n\n'.join(paras)


def main():
    rows = [json.loads(l) for l in (HERE / 'inputs.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    by = defaultdict(list)
    for r in rows:
        by[r['evidence']].append(r)
    prev_of = {}
    for ev, rs in by.items():
        prev = None
        for r in rs:
            prev_of[id(r)] = set(prev) if prev is not None else set()
            prev = fact_list(r)
    started = time.perf_counter()
    out_rows, total = [], 0
    for r in rows:
        facts = fact_list(r)
        fresh = [c for c in facts if c not in prev_of[id(r)]]
        kept = fresh or [c for c in facts if c.startswith(ce.player_name(r) or '') and '现在在' in c][:1]
        text, stats, _ = ce.compose(r, facts=kept, time_last=True, opening=opening_of(r, facts))
        text = polish(text)
        total += len(text)
        out_rows.append({'id': r['id'], 'chars': len(text), 'fresh': len(fresh), 'text': text})
    elapsed = time.perf_counter() - started
    summary = {
        'points': len(out_rows),
        'chars': total,
        'charsPerPoint': round(total / len(out_rows), 1),
        'msPerPoint': round(elapsed * 1000 / len(out_rows), 3),
        'params': 0,
        'samples': out_rows[:3],
    }
    (HERE / 'compose-candidate-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    (HERE / 'compose-candidate-rows.json').write_text(json.dumps(out_rows, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'samples'}, ensure_ascii=False))
    for s in summary['samples']:
        print('---', s['id'])
        print(s['text'][:300])


if __name__ == '__main__':
    main()
