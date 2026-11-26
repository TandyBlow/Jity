# -*- coding: utf-8 -*-
"""Run semantic routes sequentially through the real product page.

Usage: python run_semantic_routes.py env-2 env-4 info-4
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / 'frontend'
ART = ROOT / 'artifacts/goal/micro-workflow'
QUERY = 'micro=1&microContinuation=heads&microReaction=1&taskProposer=micro&seed=11'


def main():
    routes = sys.argv[1:]
    if not routes:
        print('usage: run_semantic_routes.py <route>...', file=sys.stderr)
        sys.exit(2)
    for route in routes:
        turns = ART / f'semantic-turns-{route}.json'
        if not turns.exists():
            print(f'missing {turns}', file=sys.stderr)
            sys.exit(2)
        subprocess.run([
            'node', 'scripts/product-acceptance/accept-world-local.mjs',
            '--base', 'http://127.0.0.1:3177',
            '--turns', f'../artifacts/goal/micro-workflow/semantic-turns-{route}.json',
            '--out', f'../artifacts/goal/micro-workflow/evidence-semantic-{route}.json',
            '--query', QUERY,
        ], cwd=FRONTEND, check=False)


if __name__ == '__main__':
    main()
