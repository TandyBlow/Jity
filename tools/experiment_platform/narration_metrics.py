#!/usr/bin/env python3
"""Frozen narration metrics (E58/E61 definitions) over any eval set.

Metrics: per-fact bigram coverage, outcome-label coverage per actor, negation
loss, invented names/numbers, 8-gram repetition, sentence shape. Character F1
is deliberately absent.

Arms:
  current      recorded system prose stored with the case
  rules-e55    artifacts/goal/narration-standalone/compose_rules.py
  cluster-e57  artifacts/goal/narration-standalone/cluster_events.py

Definitions are copied from E58 evaluate_narration.py / E61 check_failures.py
so the platform can score sets those scripts never see; keep them in sync.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

NAMES = ['路明非', '诺诺', '芬格尔', '秦越', '阿豹', '林亦舟', '楚子航', '凯撒', '顾岚', '唐骁', '夏弥', '绘梨衣']
OUTCOMES = ['达到目的', '没有成功', '只完成一部分', '无法完成', '部分成功', '失败']
NEG = re.compile(r'没有|没|未|不|无法|没能')
FAIL_CUE = re.compile(r'没有成功|没能|失败|未成功|无法|不成功|落空')
PART_CUE = re.compile(r'只完成|一部分|部分完成|半途|未竟')
NUM = re.compile(r'\d{2,}(?:[:：]\d{2})?')
CJK = re.compile(r'[^一-鿿]')
NARR_DIR = Path(__file__).resolve().parents[2] / 'artifacts/goal/narration-standalone'


def clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r'[。；]', text or '') if c.strip()]


def parse_result(line: str):
    match = re.match(r'^([^：:]{1,8})[：:](.+)$', (line or '').strip())
    if not match:
        return None
    actor, body = match.group(1).strip(), match.group(2).strip()
    outcome = next((o for o in OUTCOMES if o in body), None)
    action = re.sub(r'[（(][^）)]*[）)]', '', body).strip('。 ')
    return {'actor': actor, 'action': action, 'outcome': outcome}


def bigrams(text: str) -> set[str]:
    text = CJK.sub('', text or '')
    return {text[i:i + 2] for i in range(len(text) - 1)}


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r'[。！？\n]+', text or '') if s.strip()]


def coverage(fact: str, cand_grams: set[str]) -> float:
    grams = bigrams(fact)
    return 1.0 if not grams else len(grams & cand_grams) / len(grams)


def repetition(text: str, n: int = 8) -> float:
    chars = CJK.sub('', text or '')
    if len(chars) < n:
        return 0.0
    grams = [chars[i:i + n] for i in range(len(chars) - n + 1)]
    counts = Counter(grams)
    return sum(v - 1 for v in counts.values() if v > 1) / len(grams)


def evaluate(row: dict, text: str) -> dict:
    cand = bigrams(text)
    facts = [c for c in clauses(row['factsText'])
             if len(c) > 4 and '做的事' not in c and '玩家这回合' not in c]
    covered = [c for c in facts if coverage(c, cand) >= 0.5]
    sents = sentences(text)
    fact_text = row['factsText'] + row.get('settlementText', '') + ' '.join(row.get('resultLines') or [])
    invented_names = [n for n in NAMES if n in text and n not in fact_text]
    invented_nums = sorted(set(NUM.findall(text)) - set(NUM.findall(fact_text)))
    neg_total = neg_lost = 0
    for clause in facts:
        if not NEG.search(clause):
            continue
        best_ov = 0.0
        best = ''
        for sent in sents:
            ov = len(bigrams(clause) & bigrams(sent)) / max(1, len(bigrams(clause)))
            if ov > best_ov:
                best, best_ov = sent, ov
        if best_ov >= 0.5:
            neg_total += 1
            if not NEG.search(best):
                neg_lost += 1
    results = [r for r in (parse_result(x) for x in (row.get('resultLines') or [])) if r]
    out_total = out_hit = 0
    for res in results:
        cue = FAIL_CUE if res['outcome'] in ('没有成功', '无法完成', '失败') else (
            PART_CUE if res['outcome'] in ('只完成一部分', '部分成功') else None)
        if not cue:
            continue
        out_total += 1
        if any(cue.search(s) for s in sents if res['actor'] in s):
            out_hit += 1
    return {
        'facts': len(facts), 'covered': len(covered),
        'coverRate': round(len(covered) / max(1, len(facts)), 3),
        'negTotal': neg_total, 'negLost': neg_lost,
        'outTotal': out_total, 'outHit': out_hit,
        'inventedNames': len(invented_names), 'inventedNums': len(invented_nums),
        'sentences': len(sents),
        'meanSentLen': round(statistics.mean([len(s) for s in sents]), 1) if sents else 0,
        'maxSentLen': max((len(s) for s in sents), default=0),
        'repetition': round(repetition(text), 3),
        'chars': len(text),
        'factChars': len(fact_text),
        'lenRatio': round(len(text) / max(1, len(fact_text)), 3),
    }


def summarize(results: list[dict]) -> dict:
    if not results:
        return {}
    keys = ['negTotal', 'negLost', 'outTotal', 'outHit', 'inventedNames', 'inventedNums',
            'sentences', 'meanSentLen', 'maxSentLen', 'repetition', 'chars', 'lenRatio']
    out = {k: round(sum(r[k] for r in results) / len(results), 3) for k in keys}
    out['coverRate'] = round(sum(r['covered'] for r in results) / max(1, sum(r['facts'] for r in results)), 3)
    out['negLossRate'] = round(sum(r['negLost'] for r in results) / max(1, sum(r['negTotal'] for r in results)), 3)
    out['outcomeRate'] = round(sum(r['outHit'] for r in results) / max(1, sum(r['outTotal'] for r in results)), 3)
    out['inventedNameTotal'] = sum(r['inventedNames'] for r in results)
    out['inventedNumTotal'] = sum(r['inventedNums'] for r in results)
    out['points'] = len(results)
    return out


def bundle_row(case: dict) -> dict:
    inp = case['input']
    return {**inp, 'factsText': inp['factsText'], 'settlementText': inp.get('settlementText', ''),
            'resultLines': inp.get('resultLines') or [], 'playerLine': inp.get('playerLine', '')}


def arm_text(arm: str, case: dict) -> str:
    if arm == 'current':
        return (case.get('recorded') or {}).get('systemProse') or ''
    if str(NARR_DIR) not in sys.path:
        sys.path.insert(0, str(NARR_DIR))
    if arm == 'rules-e55':
        import compose_rules
        return compose_rules.compose(bundle_row(case))[0]
    if arm == 'cluster-e57':
        import cluster_events
        return cluster_events.compose(bundle_row(case))[0]
    raise SystemExit(f'unknown arm {arm}')


def load_cases(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding='utf-8-sig').splitlines() if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--set', required=True)
    parser.add_argument('--arms', default='current,rules-e55,cluster-e57')
    parser.add_argument('--group-model', action='store_true',
                        help='also report current-arm metrics per recorded model')
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    cases = load_cases(Path(args.set))
    report = {}
    for arm in [a.strip() for a in args.arms.split(',') if a.strip()]:
        rows = [evaluate(bundle_row(c), arm_text(arm, c)) for c in cases]
        report[arm] = summarize(rows)
    if args.group_model:
        groups = defaultdict(list)
        for case in cases:
            groups[(case.get('recorded') or {}).get('model', 'unknown')].append(case)
        for model, group in sorted(groups.items()):
            report[f'current@{model}'] = summarize(
                [evaluate(bundle_row(c), arm_text('current', c)) for c in group])
    report['cases'] = len(cases)
    report['set'] = args.set.replace('\\', '/')
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
