# -*- coding: utf-8 -*-
"""Program-only reconstruction baselines before any small generator.

A: program plan - every clause ordered by a fixed type heuristic.
B: oracle plan - the clauses the human selected, in the human order.
Both strip fact-side boilerplate and join with periods; overlap with the
hand-written target is measured (SequenceMatcher ratio and char-set F1)."""
import json
import re
import statistics
from pathlib import Path

ROOT = Path('D:/others/Jity')
SRC = ROOT / '.local/narr-train/sft-v13.jsonl'
PLAN = Path(__file__).resolve().parent / 'planning-examples-v2.jsonl'

RANK = {'player_action': 0, 'location_state': 1, 'actor_result': 2, 'scene': 3, 'appearance': 4, 'time': 5}


def strip_prefix(clause: str) -> str:
    body = re.sub(r'^玩家这回合.*?做的事：', '', clause)
    body = re.sub(r'^这一回合的结算结果：', '', body)
    body = re.sub(r'^[\u4e00-\u9fa5]{1,4}[：:]', '', body)
    return body.strip()


def char_f1(a: str, b: str) -> float:
    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    common = sum((ca & cb).values())
    if not common:
        return 0.0
    precision = common / max(1, len(a))
    recall = common / max(1, len(b))
    return round(2 * precision * recall / (precision + recall), 3)


def ratio(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return round(SequenceMatcher(None, a, b).ratio(), 3)


def main():
    plans = {}
    for line in PLAN.read_text(encoding='utf8').splitlines():
        if line.strip():
            row = json.loads(line)
            plans[row['id']] = row
    rows = [json.loads(line) for line in SRC.read_text(encoding='utf8').splitlines() if line.strip()]
    rows.sort(key=lambda row: str(row['id']))
    a_scores, b_scores = [], []
    for row in rows:
        rid = str(row['id'])
        plan = plans.get(rid)
        if not plan:
            continue
        clauses = plan['clauses']
        types = plan['types']
        ordered = sorted(range(len(clauses)), key=lambda i: (RANK.get(types[i], 3), i))
        text_a = '。'.join(strip_prefix(clauses[i]) for i in ordered if types[i] != 'time')
        selected = plan['selected']
        text_b = '。'.join(strip_prefix(clauses[i]) for i in selected)
        target = row['target']
        a_scores.append((ratio(text_a, target), char_f1(text_a, target)))
        b_scores.append((ratio(text_b, target), char_f1(text_b, target)))
    summary = {
        'passages': len(a_scores),
        'programPlan': {'ratioMean': round(statistics.mean(s[0] for s in a_scores), 3),
                        'charF1Mean': round(statistics.mean(s[1] for s in a_scores), 3)},
        'oraclePlan': {'ratioMean': round(statistics.mean(s[0] for s in b_scores), 3),
                       'charF1Mean': round(statistics.mean(s[1] for s in b_scores), 3)},
    }
    (Path(__file__).resolve().parent / 'reconstruct-summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
