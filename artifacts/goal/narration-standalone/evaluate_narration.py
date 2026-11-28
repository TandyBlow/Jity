# -*- coding: utf-8 -*-
"""E58: fact-grounded evaluation of narration arms. No char F1: per-fact
coverage, unsupported entities, negation loss, outcome-label coverage,
repetition and sentence shape. Runs on the 161 real inputs."""
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

import cluster_events as ce
import compose_rules as cr
from role_parse import NAMES, clauses, parse_result

HERE = Path(__file__).resolve().parent
NEG = re.compile(r'没有|没|未|不|无法|没能')
FAIL_CUE = re.compile(r'没有成功|没能|失败|未成功|无法|不成功|落空')
PART_CUE = re.compile(r'只完成|一部分|部分完成|半途|未竟')
NUM = re.compile(r'\d{2,}(?:[:：]\d{2})?')
CJK = re.compile(r'[^一-鿿]')


def bigrams(text):
    text = CJK.sub('', text)
    return {text[i:i + 2] for i in range(len(text) - 1)}


def sentences(text):
    return [s.strip() for s in re.split(r'[。！？\n]+', text) if s.strip()]


def coverage(fact, cand_grams):
    g = bigrams(fact)
    if not g:
        return 1.0
    return len(g & cand_grams) / len(g)


def repetition(text, n=8):
    chars = CJK.sub('', text)
    if len(chars) < n:
        return 0.0
    grams = [chars[i:i + n] for i in range(len(chars) - n + 1)]
    c = Counter(grams)
    return sum(v - 1 for v in c.values() if v > 1) / len(grams)


def evaluate(row, text):
    cand = bigrams(text)
    facts = [ce.clean(c) for c in clauses(row['factsText'])]
    facts = [c for c in facts if len(c) > 4 and '做的事' not in c and '玩家这回合' not in c]
    covered = [c for c in facts if coverage(c, cand) >= 0.5]
    partial = [c for c in facts if 0.25 <= coverage(c, cand) < 0.5]
    sents = sentences(text)
    # unsupported entities
    fact_text = row['factsText'] + row.get('settlementText', '') + ' '.join(row['resultLines'])
    invented_names = [n for n in NAMES if n in text and n not in fact_text]
    cand_nums = set(NUM.findall(text))
    fact_nums = set(NUM.findall(fact_text))
    invented_nums = sorted(cand_nums - fact_nums)
    # negation loss: negated fact covered, but its best sentence has no negation
    neg_total = neg_lost = 0
    for c in facts:
        if not NEG.search(c):
            continue
        best, best_ov = '', 0.0
        for s in sents:
            ov = len(bigrams(c) & bigrams(s)) / max(1, len(bigrams(c)))
            if ov > best_ov:
                best, best_ov = s, ov
        if best_ov >= 0.5:
            neg_total += 1
            if not NEG.search(best):
                neg_lost += 1
    # outcome coverage per actor
    results = [r for r in (parse_result(x) for x in row['resultLines']) if r]
    out_total = out_hit = 0
    for r in results:
        cue = FAIL_CUE if r['outcome'] in ('没有成功', '无法完成', '失败') else (
            PART_CUE if r['outcome'] in ('只完成一部分', '部分成功') else None)
        if not cue:
            continue
        out_total += 1
        actor_sents = [s for s in sents if r['actor'] in s]
        if any(cue.search(s) for s in actor_sents):
            out_hit += 1
    return {
        'facts': len(facts),
        'covered': len(covered),
        'partial': len(partial),
        'coverRate': round(len(covered) / max(1, len(facts)), 3),
        'negTotal': neg_total,
        'negLost': neg_lost,
        'outTotal': out_total,
        'outHit': out_hit,
        'inventedNames': len(invented_names),
        'inventedNums': len(invented_nums),
        'sentences': len(sents),
        'meanSentLen': round(statistics.mean([len(s) for s in sents]), 1) if sents else 0,
        'maxSentLen': max((len(s) for s in sents), default=0),
        'repetition': round(repetition(text), 3),
        'chars': len(text),
        'factChars': len(fact_text),
        'lenRatio': round(len(text) / max(1, len(fact_text)), 3),
    }


ARMS = {
    'system-1.7b': lambda row: row.get('pointProse') or row['systemProse'] or '',
    'rules-e55': lambda row: cr.compose(row)[0],
    'cluster-e57': lambda row: ce.compose(row)[0],
}


def summarize(results):
    n = len(results)
    keys = ['coverRate', 'negTotal', 'negLost', 'outTotal', 'outHit',
            'inventedNames', 'inventedNums', 'sentences', 'meanSentLen',
            'maxSentLen', 'repetition', 'chars', 'lenRatio']
    out = {k: round(sum(r[k] for r in results) / n, 3) for k in keys}
    out['coverRate'] = round(sum(r['covered'] for r in results) / max(1, sum(r['facts'] for r in results)), 3)
    out['negLossRate'] = round(sum(r['negLost'] for r in results) / max(1, sum(r['negTotal'] for r in results)), 3)
    out['outcomeRate'] = round(sum(r['outHit'] for r in results) / max(1, sum(r['outTotal'] for r in results)), 3)
    out['inventedNameTotal'] = sum(r['inventedNames'] for r in results)
    out['inventedNumTotal'] = sum(r['inventedNums'] for r in results)
    return out


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else 'inputs.jsonl'
    rows = [json.loads(l) for l in (HERE / src).read_text(encoding='utf8').splitlines() if l.strip()]
    report = {}
    for name, fn in ARMS.items():
        report[name] = summarize([evaluate(row, fn(row)) for row in rows])
    out = HERE / (src.replace('.jsonl', '') + '-eval.json')
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    for name, r in report.items():
        print(name, json.dumps(r, ensure_ascii=False))


if __name__ == '__main__':
    main()
