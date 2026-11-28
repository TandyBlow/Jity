# -*- coding: utf-8 -*-
"""Prompt-token distribution of every recorded generation, per engine.
Reads turns[].generations from artifacts/goal/**/evidence-*.json plus the
acceptance runs, so the semantic context size can be sized on real calls."""
import glob
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path('D:/others/Jity')
OUT = Path(__file__).resolve().parent / 'semantic-token-stats.json'


def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def main():
    by_engine = defaultdict(list)
    files = set()
    for path in glob.glob(str(ROOT / 'artifacts/goal/**/*.json'), recursive=True):
        try:
            doc = json.load(open(path, encoding='utf8'))
        except Exception:
            continue
        turns = doc.get('turns') if isinstance(doc, dict) else None
        if not isinstance(turns, list):
            continue
        for turn in turns:
            for gen in (turn.get('generations') or []):
                if not isinstance(gen, dict):
                    continue
                tokens = gen.get('promptTokens')
                if not isinstance(tokens, int):
                    continue
                by_engine[str(gen.get('engine'))].append({
                    'tokens': tokens,
                    'ctx': gen.get('contextSize'),
                    'maxTokens': gen.get('maxTokens'),
                    'finish': gen.get('finishReason'),
                    'file': path.split('artifacts')[-1].replace('\\', '/'),
                })
                files.add(path)

    summary = {'files': len(files)}
    for engine, records in sorted(by_engine.items()):
        vals = sorted(r['tokens'] for r in records if r['tokens'] > 0)
        summary[engine] = {
            'calls': len(records),
            'min': vals[0] if vals else None,
            'p50': pct(vals, 0.50),
            'p95': pct(vals, 0.95),
            'p99': pct(vals, 0.99),
            'max': vals[-1] if vals else None,
            'over': {str(k): sum(1 for v in vals if v > k) for k in (2048, 4096, 6144, 8192, 12288)},
            'ctxSizes': sorted({r['ctx'] for r in records if isinstance(r['ctx'], int)}),
            'maxCall': max(records, key=lambda r: r['tokens']) if records else None,
        }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
