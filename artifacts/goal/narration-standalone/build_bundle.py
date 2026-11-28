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
SETTLE_MARK = '这一回合的结算结果：'
TIME_HEAD = '时间到了'


def split_prompt(prompt):
    i = prompt.find(FACT_MARK)
    if i < 0:
        return None
    facts = prompt[i + len(FACT_MARK):]
    j = facts.find(BODY_MARK)
    if j >= 0:
        facts = facts[:j]
    return facts.strip()


def split_settlement(rest):
    """结算块在下一个世界事实块（以“时间到了”开头）之前结束。"""
    k = rest.find(TIME_HEAD)
    if k < 0:
        return rest, ''
    cut = rest.rfind('。', 0, k)
    if cut < 0:
        return rest, ''
    return rest[:cut + 1].rstrip('（'), rest[cut + 1:]


def main():
    rows, pairs = [], []
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
                marker = facts.find(SETTLE_MARK)
                if marker >= 0:
                    head = facts[:marker]
                    results, world = split_settlement(facts[marker + len(SETTLE_MARK):])
                    facts_text = (head + world).strip()
                else:
                    results, facts_text = '', facts
                player = next((c.strip() for c in re.split(r'[。；]', facts_text) if '玩家这回合' in c), '')
                rows.append({
                    'id': f"{Path(path).stem}:{turn.get('id')}:{idx}",
                    'evidence': Path(path).name,
                    'turnId': turn.get('id'),
                    'pointId': item.get('pointId'),
                    'playerLine': player,
                    'resultLines': [line.strip(' 。（') for line in re.split(r'[；]', results) if line.strip(' 。（')],
                    'settlementText': results.strip(),
                    'factsText': facts_text,
                    'systemProse': turn.get('text') or '',
                    'humanRef': None,
                })
            # 逐 point 的精确输入/输出对：只有最后一个 point 的输出被记录
            narr = product.get('narration') or {}
            if narr.get('text') and narr.get('prompt'):
                facts = split_prompt(narr['prompt'])
                if facts:
                    marker = facts.find(SETTLE_MARK)
                    if marker >= 0:
                        head = facts[:marker]
                        results, world = split_settlement(facts[marker + len(SETTLE_MARK):])
                        facts_text = (head + world).strip()
                    else:
                        results, facts_text = '', facts
                    player = next((c.strip() for c in re.split(r'[。；]', facts_text) if '玩家这回合' in c), '')
                    pairs.append({
                        'id': f"{Path(path).stem}:{turn.get('id')}:{narr.get('pointId')}",
                        'evidence': Path(path).name,
                        'turnId': turn.get('id'),
                        'pointId': narr.get('pointId'),
                        'playerLine': player,
                        'resultLines': [line.strip(' 。（') for line in re.split(r'[；]', results) if line.strip(' 。（')],
                        'settlementText': results.strip(),
                        'factsText': facts_text,
                        'systemProse': narr.get('text') or '',
                        'pointProse': narr.get('text') or '',
                        'humanRef': None,
                    })
    with (OUT_DIR / 'inputs.jsonl').open('w', encoding='utf-8') as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    with (OUT_DIR / 'pairs.jsonl').open('w', encoding='utf-8') as fh:
        for row in pairs:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(json.dumps({'points': len(rows),
                      'withResultLines': sum(1 for r in rows if r['resultLines']),
                      'withProse': sum(1 for r in rows if r['systemProse']),
                      'exactPairs': len(pairs)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
