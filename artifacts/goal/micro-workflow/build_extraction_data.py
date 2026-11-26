# -*- coding: utf-8 -*-
"""Extraction pairs from settled 信息= facts.

Each pair is (player action, entity appearance) -> the clause the program
extracted. The clause is a verbatim slice of the committed appearance, so the
span offsets are exact; pairs whose clause is not in the base appearance are
skipped rather than guessed."""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DATASET = HERE / 'real-semantic.jsonl'
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'
OUT = HERE / 'semantic-extraction.jsonl'
TAG = re.compile('信息[=＝]([^:：；\s]+)[:：]([^；。\n]+)')


def main():
    rows = [json.loads(line) for line in DATASET.read_text(encoding='utf8').splitlines() if line.strip()]
    initial = json.loads(WORLD.read_text(encoding='utf8'))['initial']
    entities = {**initial.get('items', {}), **initial.get('characters', {})}
    pairs = []
    seen = set()
    for row in rows:
        if row.get('source') != 'semantic':
            continue
        for index, fact in enumerate(row.get('settled') or []):
            if fact.get('task') != 'results' or not fact.get('text'):
                continue
            for match in TAG.finditer(str(fact['text'])):
                entity_id = match.group(1).strip('<>')
                clause = match.group(2).strip()
                appearance = (entities.get(entity_id) or {}).get('initialAppearance') or ''
                start = appearance.find(clause)
                if start < 0:
                    continue
                key = (row.get('input') or '', entity_id, clause)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append({'id': f"{row['id']}#e{index}", 'rowId': row['id'], 'entityId': entity_id,
                              'action': row.get('input') or '', 'appearance': appearance, 'clause': clause,
                              'start': start, 'end': start + len(clause)})
    OUT.write_text(''.join(json.dumps(pair, ensure_ascii=False) + '\n' for pair in pairs), encoding='utf8')
    print(json.dumps({'pairs': len(pairs), 'routes': len({pair['rowId'] for pair in pairs})}, ensure_ascii=False))


if __name__ == '__main__':
    main()
