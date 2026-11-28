# -*- coding: utf-8 -*-
"""Build the standalone narration bundle from real settlement records.

Input: acceptance evidence files (turns[].product.pointPrompts[].prompt).
Output: inputs.jsonl — one row per point with the fact block, the player line,
the settlement result lines, and the turn's produced prose (current system).

No model is loaded; this only re-serializes records already on disk.
"""
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent
FACT_MARK = '事实：'
BODY_MARK = '\n正文：'


def split_prompt(prompt):
    i = prompt.find(FACT_MARK)
    if i < 0:
        return None
    facts = prompt[i + len(FACT_MARK):]
    j = facts.find(BODY_MARK)
    if j >= 0:
        facts = facts[:j]
    return facts.strip()


def section(facts, start, ends):
    i = facts.find(start)
    if i < 0:
        return ''
    i += len(start)
    stop = len(facts)
    for e in ends:
        k = facts.find(e, i)
        if 0 <= k < stop:
            stop = k
    return facts[i:stop].strip()


def main():
    rows = []
    for path in sorted(glob.glob(str(ROOT / 'results/product/evidence/*.json'))):
        try:
            doc = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        except Exception:
            continue
        for turn in doc.get('turns') or []:
            product = turn.get('product') or {}
            prompts = product.get('pointPrompts') or []
            for idx, item in enumerate(prompts):
                prompt = item.get('prompt') or ''
                facts = split_prompt(prompt)
                if not facts:
                    continue
                marker = facts.find('这一回合的结算结果：')
                head = facts[:marker] if marker >= 0 else facts
                player = head.split('。')[0].strip()
                results = facts[marker + len('这一回合的结算结果：'):] if marker >= 0 else ''
                rows.append({
                    'id': f"{Path(path).stem}:{turn.get('id')}:{idx}",
                    'evidence': Path(path).name,
                    'turnId': turn.get('id'),
                    'pointId': item.get('pointId'),
                    'playerLine': player,
                    'resultLines': [line.strip(' 。') for line in re.split(r'[；]', results) if line.strip(' 。')],
                    'factsText': facts,
                    'systemProse': turn.get('text') or '',
                    'humanRef': None,
                })
    with (OUT_DIR / 'inputs.jsonl').open('w', encoding='utf-8') as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(json.dumps({'points': len(rows),
                      'withResultLines': sum(1 for r in rows if r['resultLines']),
                      'withProse': sum(1 for r in rows if r['systemProse'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
