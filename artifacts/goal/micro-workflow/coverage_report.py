# -*- coding: utf-8 -*-
"""Per-task micro-model coverage from one turn's semantic call log.

micro_share = micro / (micro + model): the share of semantic decisions taken by
a micro model rather than the LLM. Program rules are reported separately so
rule savings are not counted as model coverage.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def main():
    data = json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
    turn = data['turns'][0]
    calls = (turn.get('product') or {}).get('semanticCalls') or []
    per = defaultdict(Counter)
    ms = defaultdict(float)
    for call in calls:
        source = call.get('source') or 'attempt'
        per[call['task']][source] += 1
        ms[call['task']] += call.get('ms') or 0
    overall = Counter()
    for task in sorted(per):
        counts = per[task]
        total = sum(counts.values())
        micro = counts.get('micro', 0)
        model = counts.get('model', 0)
        share = micro / (micro + model) if micro + model else 0
        overall.update(counts)
        print(f"{task:12s} calls={total:3d} {dict(counts)} micro_share={share:.2f} ms={round(ms[task])}")
    micro = overall.get('micro', 0)
    model = overall.get('model', 0)
    print(f"overall      micro={micro} model={model} program={overall.get('program', 0)} "
          f"attempts={overall.get('attempt', 0)} micro_share={micro / (micro + model) if micro + model else 0:.2f}")


if __name__ == '__main__':
    main()
