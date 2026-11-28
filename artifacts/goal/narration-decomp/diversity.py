# -*- coding: utf-8 -*-
"""Expression diversity for the same settled facts: how far apart are the
acceptable hand-written targets, and how does their operation mix vary."""
import importlib.util
import json
import statistics
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path('D:/others/Jity')
ALT = ROOT / '.local/narr-train/alt-targets-all.jsonl'
OUT = Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location('d2', OUT / 'decompose2.py')
d2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d2)


def facts_of(prompt: str) -> str:
    marker = prompt.find('事实：')
    return prompt[marker + 3:] if marker >= 0 else prompt


def main():
    rows = [json.loads(line) for line in ALT.read_text(encoding='utf8').splitlines() if line.strip()]
    groups = defaultdict(list)
    for row in rows:
        groups[str(row['baseId'])].append(row)
    pair_sims = []
    share_rows = []
    for base, variants in groups.items():
        targets = [row['target'] for row in variants]
        for i in range(len(targets)):
            for j in range(i + 1, len(targets)):
                pair_sims.append(SequenceMatcher(None, targets[i], targets[j]).ratio())
        for row in variants:
            result = d2.decompose(row['target'], facts_of(row['prompt']))
            share_rows.append((base, result['openRatio'], result['paraphraseRatio'],
                               len(row['target'])))
    open_by_base = defaultdict(list)
    for base, open_ratio, para_ratio, _ in share_rows:
        open_by_base[base].append(open_ratio)
    spreads = [max(values) - min(values) for values in open_by_base.values() if len(values) > 1]
    summary = {
        'variants': len(rows),
        'groups': len(groups),
        'variantsPerGroup': dict(sorted((k, len(v)) for k, v in groups.items())),
        'pairwiseSimilarityMean': round(statistics.mean(pair_sims), 3) if pair_sims else None,
        'pairwiseSimilarityMin': round(min(pair_sims), 3) if pair_sims else None,
        'meanOpenShare': round(statistics.mean(r[1] for r in share_rows), 3),
        'meanParaphraseShare': round(statistics.mean(r[2] for r in share_rows), 3),
        'openShareSpreadMean': round(statistics.mean(spreads), 3) if spreads else None,
        'openShareSpreadMax': round(max(spreads), 3) if spreads else None,
    }
    (OUT / 'diversity-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'variantsPerGroup'}, ensure_ascii=False))
    print('groups detail sample', json.dumps(dict(list(summary['variantsPerGroup'].items())[:10]), ensure_ascii=False))


if __name__ == '__main__':
    main()
