# -*- coding: utf-8 -*-
"""Summarize the semantic-ctx A/B: page-attributed memory per phase per arm."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def summarize(path):
    rows = [json.loads(l) for l in open(path, encoding='utf8') if l.strip()]
    samples = [r for r in rows if r.get('wasmEstimate')]
    by_phase = {}
    for r in samples:
        by_phase.setdefault(r.get('phase'), []).append(r['wasmEstimate'])
    return {
        'file': Path(path).name,
        'samples': len(samples),
        'byPhaseMB': {phase: [round(v / 1e6, 1) for v in vals] for phase, vals in by_phase.items()},
        'maxMB': round(max(v['wasmEstimate'] for v in samples) / 1e6, 1) if samples else None,
        'lastMB': round(samples[-1]['wasmEstimate'] / 1e6, 1) if samples else None,
        'phases': sorted({str(r.get('phase')) for r in rows}),
        'submitted': any(r.get('event') == 'turn-submitted' for r in rows),
    }


def main():
    arms = sys.argv[1:] or [str(HERE / 'ab-ctx12288.jsonl'), str(HERE / 'ab-ctx8192.jsonl')]
    out = {Path(a).stem: summarize(a) for a in arms if Path(a).exists()}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
