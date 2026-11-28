# -*- coding: utf-8 -*-
"""E54: parse settled facts into semantic-role fragments and measure how many
subject-less facts can be grounded from the settlement's actor record."""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = ['路明非', '诺诺', '芬格尔', '秦越', '阿豹', '林亦舟', '楚子航', '凯撒', '顾岚', '唐骁', '夏弥', '绘梨衣']
OUTCOMES = ['达到目的', '没有成功', '只完成一部分', '无法完成', '部分成功', '失败']
NEG = re.compile(r'没有|没|未|不|无法')
CONTRAST = re.compile(r'却|但|反而|然而|虽然')
CAUSE = re.compile(r'因为|所以|于是|便|才|结果')
DIALOGUE = re.compile(r'[‘“]')


def grams(text):
    text = re.sub(r'[^一-鿿]', '', text)
    return {text[i:i + 2] for i in range(len(text) - 1)}


def clauses(text):
    return [c.strip() for c in re.split(r'[。；]', text) if c.strip()]


def parse_result(line):
    m = re.match(r'^([^：:]{1,8})[：:](.+)$', line.strip())
    if not m:
        return None
    actor, body = m.group(1).strip(), m.group(2).strip()
    outcome = next((o for o in OUTCOMES if o in body), None)
    action = re.sub(r'[（(][^）)]*[）)]', '', body).strip('。 ')
    return {'actor': actor, 'action': action, 'outcome': outcome}


def classify(clause):
    person = next((n for n in NAMES if clause.startswith(n)), None)
    role = {
        'clause': clause,
        'subject': person,
        'subjectKind': 'person' if person else None,
        'negated': bool(NEG.search(clause)),
        'contrast': bool(CONTRAST.search(clause)),
        'cause': bool(CAUSE.search(clause)),
        'dialogue': bool(DIALOGUE.search(clause)),
    }
    if not person:
        if re.match(r'^(屋|墙|桌|门|柜|房间|走廊|楼|院|巷|地面|角落|领用台|器材|备用|黄色|口径|时间|演习)', clause):
            role['subjectKind'] = 'object_or_place'
        else:
            role['subjectKind'] = 'missing'
    return role


def main():
    rows = [json.loads(l) for l in (HERE / 'inputs.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    totals = Counter()
    kinds = Counter()
    recoverable = 0
    missing = 0
    per_row = []
    outcome_counts = Counter()
    for row in rows:
        results = [parse_result(x) for x in row['resultLines']]
        results = [r for r in results if r]
        actors = {r['actor'] for r in results}
        for r in results:
            outcome_counts[r['outcome'] or 'none'] += 1
        parsed = [classify(c) for c in clauses(row['factsText'])]
        miss = [p for p in parsed if p['subjectKind'] == 'missing']
        rec = 0
        for p in miss:
            g = grams(p['clause'])
            for r in results:
                ov = len(g & grams(r['action'])) / max(1, len(g))
                if ov >= 0.5:
                    rec += 1
                    break
        recoverable += rec
        missing += len(miss)
        totals['points'] += 1
        totals['resultLines'] += len(results)
        totals['clauses'] += len(parsed)
        totals['missingSubject'] += len(miss)
        totals['withActorRecord'] += 1 if actors else 0
        totals['negated'] += sum(1 for p in parsed if p['negated'])
        totals['contrast'] += sum(1 for p in parsed if p['contrast'])
        totals['cause'] += sum(1 for p in parsed if p['cause'])
        totals['dialogue'] += sum(1 for p in parsed if p['dialogue'])
        for p in parsed:
            kinds[p['subjectKind']] += 1
        per_row.append({'id': row['id'], 'actors': sorted(actors), 'missing': len(miss), 'recoverable': rec})
    summary = {
        'totals': dict(totals),
        'subjectKinds': dict(kinds),
        'outcomes': dict(outcome_counts),
        'missingRecoverable': recoverable,
        'missingRecoverableRate': round(recoverable / max(1, missing), 3),
        'missingRate': round(missing / max(1, totals['clauses']), 3),
        'rows': per_row[:20],
    }
    (HERE / 'role-parse-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
