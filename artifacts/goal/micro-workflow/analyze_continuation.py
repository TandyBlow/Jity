# -*- coding: utf-8 -*-
"""Continuation calls per turn: candidate texts, duplicates across rounds,
characters proposed, and time. A repeated text is only flagged, not judged
invalid: continuous watch/guard can be reasonable."""
import json
import re
import sys
from collections import Counter
from pathlib import Path


def norm(text):
    return re.sub(r'[^一-龥A-Za-z0-9]', '', text or '')


def main():
    for path in sys.argv[1:]:
        data = json.loads(Path(path).read_text(encoding='utf8'))
        calls = [c for c in (data['turns'][0].get('product') or {}).get('semanticCalls') or [] if c['task'] == 'continuation']
        texts, chars = [], Counter()
        for call in calls:
            try:
                raw = json.loads(call.get('raw') or '')
            except (json.JSONDecodeError, TypeError):
                continue
            for cand in raw.get('candidates') or []:
                if isinstance(cand, dict) and cand.get('text'):
                    texts.append(norm(cand['text']))
                    chars[cand.get('characterId')] += 1
        duplicates = len(texts) - len(set(texts))
        print(Path(path).name)
        print('  calls', len(calls), 'ms', round(sum(c.get('ms') or 0 for c in calls) / 1000, 1),
              'candidates', len(texts), 'duplicate_texts', duplicates, 'characters', dict(chars))


if __name__ == '__main__':
    main()
