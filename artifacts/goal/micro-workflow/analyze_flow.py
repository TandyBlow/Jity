# -*- coding: utf-8 -*-
"""Point/round/narration breakdown of a turn: where the wall clock goes after
the player's own point."""
import json
import sys
from collections import Counter
from pathlib import Path


def main():
    for path in sys.argv[1:]:
        data = json.loads(Path(path).read_text(encoding='utf8'))
        turn = data['turns'][0]
        calls = (turn.get('product') or {}).get('semanticCalls') or []
        points = (turn.get('snapshotAfterTurn') or {}).get('transport', {}).get('points') or {}
        kinds = Counter(point.get('kind') for point in points.values())
        triggers = Counter(point.get('trigger') for point in points.values())
        rounds = len({point.get('roundId') for point in points.values()})
        continuations = [c for c in calls if c['task'] == 'continuation']
        narrations = [c for c in calls if c['task'] == 'narration']
        actions = [c.get('value') for c in calls if c['task'] == 'action' and c.get('source') in ('model', 'micro')]
        texts = [str(a.get('text', '')) for a in actions if isinstance(a, dict)]
        repeats = len(texts) - len(set(texts))
        print(Path(path).name)
        print('  points', len(points), dict(kinds), dict(triggers), 'rounds', rounds)
        print('  continuation', len(continuations), round(sum(c.get('ms') or 0 for c in continuations) / 1000, 1), 's',
              'decisions', [str(c.get('raw'))[:60] for c in continuations])
        print('  narration', len(narrations), round(sum(c.get('ms') or 0 for c in narrations) / 1000, 1), 's',
              'prompt_chars', sum(c.get('promptChars') or 0 for c in narrations))
        print('  action texts', len(texts), 'repeats', repeats, 'chars', sum(len(t) for t in texts))


if __name__ == '__main__':
    main()
