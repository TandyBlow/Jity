# -*- coding: utf-8 -*-
"""Add per-world and entity/open field summaries to the v2 report."""
import json
from pathlib import Path

PATH = Path('artifacts/goal/micro-workflow/micro-generative/v2-report.json')
report = json.loads(PATH.read_text(encoding='utf8'))
ENTITY = {'loc', 'item', 'target', 'dest'}


def recall(predictions, keys):
    hits = total = 0
    for row in predictions:
        for key, value in row['want'].items():
            if keys is None or key in keys:
                total += 1
                hits += row['got'].get(key) == value
    return round(hits / total, 3) if total else None


for arm, metrics in report['arms'].items():
    predictions = metrics['predictions']
    open_keys = {key for row in predictions for key in row['want'] if key not in ENTITY}
    metrics['entityFieldRecall'] = recall(predictions, ENTITY)
    metrics['openFieldRecall'] = recall(predictions, open_keys)
    by_world = {}
    for world in ('dragon', 'mistport'):
        subset = [row for row in predictions if row['world'] == world]
        by_world[world] = {
            'rows': len(subset),
            'fieldRecall': recall(subset, None),
            'entityFieldRecall': recall(subset, ENTITY),
        }
    metrics['byWorld'] = by_world
PATH.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
print(json.dumps({arm: {key: metrics[key] for key in ('fieldRecall', 'entityFieldRecall', 'byWorld')}
                  for arm, metrics in report['arms'].items()}, ensure_ascii=False, indent=1))
