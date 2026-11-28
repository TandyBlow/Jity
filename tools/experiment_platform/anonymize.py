#!/usr/bin/env python3
"""Blind arm comparison: hide model names behind per-case A/B/C labels.

Input JSONL rows: {"id": ..., "arm": ..., "text": ...} (one row per arm/case).
Output: blind.jsonl with variants per case, key.json to unblind after review,
and an optional Markdown review sheet with empty score cells.

  python -m tools.experiment_platform.anonymize --input outputs.jsonl \
    --blind blind.jsonl --key key.json --sheet review.md --seed 7
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

LETTERS = 'ABCDEFGH'


def blind(rows: list[dict], seed: int = 0) -> tuple[list[dict], dict]:
    grouped = defaultdict(dict)
    for row in rows:
        grouped[row['id']][row['arm']] = row.get('text', '')
    blind_rows, key = [], {}
    for identity in sorted(grouped):
        arms = sorted(grouped[identity])
        if len(arms) < 2:
            continue
        rng = random.Random(f'{seed}:{identity}')
        rng.shuffle(arms)
        labels = {LETTERS[i]: arm for i, arm in enumerate(arms)}
        key[identity] = labels
        blind_rows.append({'id': identity,
                           'variants': {label: grouped[identity][arm] for label, arm in labels.items()}})
    return blind_rows, key


def sheet(rows: list[dict]) -> str:
    lines = ['# Blind narration review', '',
             'Read each case, score every variant 0-3 on fact accuracy, naturalness and coherence.',
             'Do not guess the model. Fill the score columns after reading all variants.', '']
    for row in rows:
        lines.append(f"## {row['id']}")
        for label, text in row['variants'].items():
            lines.append(f"**{label}.** {text}")
            lines.append('')
        lines.append('| variant | facts | naturalness | coherence | note |')
        lines.append('|---|---|---|---|---|')
        for label in row['variants']:
            lines.append(f'| {label} |  |  |  |  |')
        lines.append('')
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--input', required=True)
    parser.add_argument('--blind', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--sheet', default=None)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args(argv)
    rows = [json.loads(ln) for ln in Path(args.input).read_text(encoding='utf-8-sig').splitlines() if ln.strip()]
    blind_rows, key = blind(rows, args.seed)
    if not blind_rows:
        print('no case had two or more arms', file=sys.stderr)
        return 2
    Path(args.blind).write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in blind_rows) + '\n',
                                encoding='utf-8')
    Path(args.key).write_text(json.dumps(key, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    if args.sheet:
        Path(args.sheet).write_text(sheet(blind_rows), encoding='utf-8')
    print(json.dumps({'cases': len(blind_rows), 'arms': len(next(iter(key.values())))}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
