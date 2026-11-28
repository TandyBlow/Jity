# -*- coding: utf-8 -*-
"""E55 rule composer: emit one sentence per settled fact / event, keep polarity
and outcome, never add content. This is the program baseline the micro models
must beat on naturalness, not on fidelity."""
import json
import re
from collections import Counter
from pathlib import Path

from role_parse import classify, clauses, parse_result

HERE = Path(__file__).resolve().parent
OUTCOME_PHRASE = {
    '达到目的': '',
    '没有成功': '，但没有成功',
    '只完成一部分': '，只完成了一部分',
    '无法完成': '，没能完成',
    '部分成功': '，只完成了一部分',
    '失败': '，失败了',
}


def compose(row):
    results = [r for r in (parse_result(x) for x in row['resultLines']) if r]
    out = []
    used_actions = []
    for r in results:
        phrase = OUTCOME_PHRASE.get(r['outcome'] or '', '')
        out.append(f"{r['actor']}{r['action']}{phrase}。")
        used_actions.append(r['action'])
    world = row['factsText'].split('这一回合的结算结果：')[0]
    for c in clauses(world):
        info = classify(c)
        if '做的事' in c or '玩家这回合' in c:
            continue
        if info['subjectKind'] == 'missing':
            continue
        out.append(c.rstrip('。') + '。')
    return ''.join(out), results


def main():
    rows = [json.loads(l) for l in (HERE / 'inputs.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    totals = Counter()
    ratios = []
    outcome_rate = []
    samples = []
    for row in rows:
        text, results = compose(row)
        sys_text = row['systemProse'] or ''
        totals['points'] += 1
        totals['events'] += len(results)
        totals['eventsWithOutcome'] += sum(1 for r in results if r['outcome'])
        totals['ruleChars'] += len(text)
        totals['sysChars'] += len(sys_text)
        if sys_text:
            ratios.append(len(text) / max(1, len(sys_text)))
        if results:
            outcome_rate.append(sum(1 for r in results if r['outcome']) / len(results))
        if len(samples) < 5 and results:
            samples.append({'id': row['id'], 'rule': text[:300], 'system': sys_text[:200]})
    summary = {
        'points': totals['points'],
        'events': totals['events'],
        'eventsWithOutcome': totals['eventsWithOutcome'],
        'outcomeRate': round(totals['eventsWithOutcome'] / max(1, totals['events']), 3),
        'ruleChars': totals['ruleChars'],
        'systemChars': totals['sysChars'],
        'lenRatioMean': round(sum(ratios) / max(1, len(ratios)), 3),
        'samples': samples,
    }
    (HERE / 'compose-rules-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'samples'}, ensure_ascii=False))
    for s in samples[:2]:
        print('---', s['id'])
        print('RULE:', s['rule'][:200])
        print('SYS :', s['system'][:160])


if __name__ == '__main__':
    main()
