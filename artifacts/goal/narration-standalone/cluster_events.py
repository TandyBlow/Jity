# -*- coding: utf-8 -*-
"""E57: cluster settled facts by discourse topic (actor / place / time), then
emit one sentence per topic. Measures whether clustering unlocks the merges,
pronouns and connectives that surface rules could not reach (E56: 29/1601)."""
import json
import re
from collections import Counter, OrderedDict
from pathlib import Path

from role_parse import clauses, parse_result

HERE = Path(__file__).resolve().parent
NAMES = ['路明非', '诺诺', '芬格尔', '秦越', '阿豹', '林亦舟', '楚子航', '凯撒', '顾岚', '唐骁', '夏弥', '绘梨衣']
GENDER = {'路明非': '他', '诺诺': '她', '芬格尔': '他', '楚子航': '他', '凯撒': '他', '夏弥': '她', '绘梨衣': '她'}
PRONOUNS = set(GENDER.values()) | {'它', '他们', '她们'}
PLACES = ['西侧服务巷', '地下检修通道', '跨溪小桥', '器材棚', '领用台', '右墙', '左墙', '墙面', '墙角', '墙根',
          '低墙', '石墙', '巷口', '巷子', '屋里', '庭院', '回廊', '廊柱', '钟楼', '桌上', '地面', '角落',
          '备用', '检修通道', '通道', '门', '柜', '床', '楼', '桌', '巷', '墙', '屋', '院', '廊', '桥', '路']
PLACE_GROUP = {}
for _p in PLACES:
    _g = '巷' if _p == '西侧服务巷' else ('通道' if '通道' in _p else _p)
    PLACE_GROUP.setdefault(_p, _g)
PLACE_SORTED = sorted(PLACES, key=len, reverse=True)
TIME = re.compile(r'^时间到了')
OUTCOME = {
    '没有成功': '，却没有成功',
    '只完成一部分': '，只完成了一部分',
    '无法完成': '，没能完成',
    '部分成功': '，只完成了一部分',
    '失败': '，失败了',
}


def clean(c):
    c = c.strip().lstrip('（(。，；、 ')
    return c.rstrip('（(')


WORLD = HERE.parents[2] / 'data/worlds/dragon-raja-free-day.world.json'


def protagonist():
    """主角名由静态世界的 protagonistId 与其物品名推得。"""
    world = json.loads(WORLD.read_text(encoding='utf8'))
    pid = world['protagonistId']
    for item in (world.get('initial', {}).get('items') or {}).values():
        pos = item.get('initialPosition') or {}
        m = re.match(r'^(.{1,4})的', item.get('name') or '')
        if pos.get('containerId') == pid and m:
            return m.group(1)
    return None


PROTAGONIST = protagonist()


def player_name(row):
    m = re.match(r'^玩家这回合让(.{1,4}?)做的事', row['playerLine'] or '')
    return m.group(1) if m else PROTAGONIST


def place_head(text):
    for p in PLACE_SORTED:
        if text.startswith(p):
            return p
    return None


def starts_subject(text):
    return bool(place_head(text)) or any(text.startswith(n) for n in NAMES) or text[:1] in PRONOUNS


def attribute(c):
    if TIME.match(c):
        return ('time', '时间')
    for n in NAMES:
        if c.startswith(n):
            return ('actor', n)
    for n in NAMES:
        if re.match(r'^.{0,8}' + n + '的', c):
            return ('actor', n)
    p = place_head(c)
    if p:
        return ('place', PLACE_GROUP[p])
    return ('missing', None)


def cluster(row):
    clusters, order, first_at = OrderedDict(), [], {}
    last = None
    seen_time = False
    stats = Counter()
    for idx, c in enumerate(clauses(row['factsText'])):
        c = clean(c)
        if len(c) < 2 or '做的事' in c or '玩家这回合' in c:
            continue
        kind, key = attribute(c)
        if kind == 'time':
            if seen_time:
                continue
            seen_time = True
            stats['timeLines'] += 1
        elif kind == 'missing':
            if last is None:
                stats['dropped'] += 1
                continue
            kind, key = last
            stats['inherited'] += 1
        else:
            last = (kind, key)
            stats['explicit'] += 1
        ck = (kind, key)
        if ck not in clusters:
            clusters[ck] = []
            order.append(ck)
            first_at[ck] = idx
        clusters[ck].append(c)
        stats['clauses'] += 1
    return clusters, order, first_at, stats


def chunks_of(items, name):
    out = []
    for it in items:
        if isinstance(it, tuple):
            r = it[1]
            out.append(r['action'] + OUTCOME.get(r['outcome'] or '', ''))
        elif name and it.startswith(name):
            out.append(it[len(name):])
        else:
            out.append(it)
    return out


def sentences_of(chunks, prefix=None, pronoun=None):
    sents, cur = [], []
    for ch in chunks:
        if cur and starts_subject(ch):
            sents.append(cur)
            cur = []
        cur.append(ch)
    if cur:
        sents.append(cur)
    out, used = [], 0
    for i, s in enumerate(sents):
        txt = '，'.join(s)
        if i == 0 and prefix and not starts_subject(txt):
            txt = prefix + txt
        elif i > 0 and pronoun and not starts_subject(txt):
            txt = pronoun + txt
            used += 1
        out.append(txt)
    return out, used


def compose(row):
    results = [r for r in (parse_result(x) for x in row['resultLines']) if r]
    player = player_name(row)
    clusters, order, first_at, stats = cluster(row)
    for r in results:
        ck = ('actor', r['actor'])
        if ck not in clusters:
            clusters[ck] = []
            order.append(ck)
            first_at[ck] = -1
        clusters[ck].insert(0, ('event', r))

    def sort_key(ck):
        kind, key = ck
        if kind == 'time':
            return (0, 0, 0)
        if kind == 'actor':
            return (1, 0 if key == player else 1, first_at[ck])
        return (2, 0, first_at[ck])

    order = sorted(order, key=sort_key)
    blocks = {0: [], 1: [], 2: []}
    merges = pronouns = 0
    for ck in order:
        kind, key = ck
        name = key if kind == 'actor' else None
        chunks = chunks_of(clusters[ck], name)
        if kind == 'actor':
            sents, used = sentences_of(chunks, prefix=key, pronoun=GENDER.get(key))
            pronouns += used
        else:
            sents, _ = sentences_of(chunks)
        merges += max(0, len(chunks) - len(sents))
        blocks[sort_key(ck)[0]].append((sents, clusters[ck][0] if clusters[ck] else ''))
    paras = []
    for g in (0, 1, 2):
        sents = [s for block in blocks[g] for s in block[0]]
        if sents:
            paras.append(''.join(s if s.endswith('。') else s + '。' for s in sents))
    text = '\n\n'.join(paras)
    stats['sentences'] = sum(len(b[0]) for g in blocks.values() for b in g)
    stats['merges'] = merges
    stats['pronouns'] = pronouns
    stats['clusters'] = sum(1 for ck in order if clusters[ck])
    return text, stats, order


def main():
    rows = [json.loads(l) for l in (HERE / 'inputs.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    totals = Counter()
    ratios = []
    switches = pairs = 0
    samples = []
    fidelity_fail = 0
    per_point = []
    for row in rows:
        text, stats, order = compose(row)
        totals.update(stats)
        sys_text = row['systemProse'] or ''
        if sys_text:
            ratios.append(len(text) / len(sys_text))
        totals['chars'] += len(text)
        totals['sysChars'] += len(sys_text)
        totals['points'] += 1
        cl = [clean(c) for c in clauses(row['factsText'])]
        cl = [c for c in cl if len(c) > 1 and '做的事' not in c and '玩家这回合' not in c]
        keys, last = [], None
        for c in cl:
            k, v = attribute(c)
            if k == 'missing' and last:
                k, v = last
            keys.append(f'{k}:{v}')
            if k != 'missing':
                last = (k, v)
        for a, b in zip(keys, keys[1:]):
            pairs += 1
            switches += a != b
        for c in cl:
            stripped = next((c[len(n):] for n in NAMES if c.startswith(n)), c)
            if c not in text and stripped not in text:
                fidelity_fail += 1
        per_point.append({'id': row['id'], 'clauses': len(cl), 'clusters': stats['clusters'],
                          'sentences': stats['sentences'], 'chars': len(text), 'sys': len(sys_text)})
        if len(samples) < 4:
            samples.append({'id': row['id'], 'out': text[:460]})
    summary = {
        'points': totals['points'],
        'clauses': totals['clauses'],
        'explicit': totals['explicit'],
        'inherited': totals['inherited'],
        'inheritedRate': round(totals['inherited'] / max(1, totals['clauses']), 3),
        'timeLines': totals['timeLines'],
        'clusters': totals['clusters'],
        'meanClusterSize': round(totals['clauses'] / max(1, totals['clusters']), 2),
        'sentences': totals['sentences'],
        'merges': totals['merges'],
        'pronouns': totals['pronouns'],
        'chars': totals['chars'],
        'sysChars': totals['sysChars'],
        'lenRatioMean': round(sum(ratios) / max(1, len(ratios)), 3),
        'lenRatioAgg': round(totals['chars'] / max(1, totals['sysChars']), 3),
        'inputTopicSwitchRate': round(switches / max(1, pairs), 3),
        'fidelityFail': fidelity_fail,
        'samples': samples,
    }
    (HERE / 'cluster-events-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    (HERE / 'cluster-events-per-point.json').write_text(json.dumps(per_point, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'samples'}, ensure_ascii=False))
    for s in samples[:2]:
        print('---', s['id'])
        print(s['out'])


if __name__ == '__main__':
    main()
