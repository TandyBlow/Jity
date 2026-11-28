#!/usr/bin/env python3
"""Unified experiment entry: manifest, raw logs, result record, resumable.

Heavy browser jobs should be submitted through frontend/scripts/lab/expctl.ps1
(Job Object + memory gate); this runner is for component tests, offline replay
and metric jobs. Every attempt keeps its own logs; a completed run is never
silently redone, a failed run keeps its evidence on retry.

  python -m tools.experiment_platform.run_experiment \
    --name narration-eval --command "python eval.py" --inputs a.jsonl,b.jsonl \
    --model qwen3-1.7b --seed 11
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'jity-run/1'


def git_head() -> str | None:
    try:
        return subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True).stdout.strip() or None
    except OSError:
        return None


def file_digest(path: Path) -> dict:
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as fh:
        while chunk := fh.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return {'path': str(path), 'bytes': size, 'sha256': digest.hexdigest()}


def next_attempt(out_dir: Path) -> int:
    return 1 + sum(1 for p in out_dir.glob('result.attempt*.json'))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--name', required=True)
    parser.add_argument('--command', required=True)
    parser.add_argument('--cwd', default=str(ROOT))
    parser.add_argument('--inputs', default='', help='comma-separated files to hash')
    parser.add_argument('--model', default=None)
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--notes', default='')
    parser.add_argument('--timeout', type=float, default=None)
    parser.add_argument('--out-root', default='artifacts/goal/platform/runs')
    parser.add_argument('--out-dir', default=None, help='explicit run directory')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args(argv)

    slug = re.sub(r'[^a-z0-9]+', '-', args.name.lower()).strip('-') or 'run'
    out_dir = Path(args.out_dir) if args.out_dir else (
        ROOT / args.out_root / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slug}")
    result_path = out_dir / 'result.json'
    if args.resume and result_path.exists():
        previous = json.loads(result_path.read_text(encoding='utf-8'))
        if previous.get('status') == 'done':
            print(json.dumps({'status': 'already-done', 'outDir': str(out_dir)}, ensure_ascii=False))
            return 0
        shutil.copyfile(result_path, out_dir / f"result.attempt{previous.get('attempt', 1)}.json")
    out_dir.mkdir(parents=True, exist_ok=True)
    attempt = next_attempt(out_dir)
    manifest = {
        'schema': SCHEMA, 'name': args.name, 'command': args.command, 'cwd': args.cwd,
        'model': args.model, 'seed': args.seed, 'notes': args.notes, 'attempt': attempt,
        'headCommit': git_head(), 'startedAt': datetime.now(tz=timezone.utc).isoformat(),
        'inputs': [file_digest(ROOT / p if not Path(p).is_absolute() else Path(p))
                   for p in [x.strip() for x in args.inputs.split(',') if x.strip()]],
        'environment': {'python': sys.version.split()[0], 'platform': platform.platform()},
    }
    (out_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n',
                                            encoding='utf-8')
    stdout_path, stderr_path = out_dir / f'attempt{attempt}.out.log', out_dir / f'attempt{attempt}.err.log'
    started = time.time()
    status, exit_code = 'done', 0
    with stdout_path.open('wb') as out, stderr_path.open('wb') as err:
        try:
            proc = subprocess.run(args.command, shell=True, cwd=args.cwd, stdout=out, stderr=err,
                                  timeout=args.timeout)
            exit_code = proc.returncode
            status = 'done' if exit_code == 0 else 'failed'
        except subprocess.TimeoutExpired:
            status, exit_code = 'timeout', None
    result = {'schema': SCHEMA, 'name': args.name, 'status': status, 'exitCode': exit_code,
              'attempt': attempt, 'startedAt': manifest['startedAt'],
              'endedAt': datetime.now(tz=timezone.utc).isoformat(),
              'durationMs': round((time.time() - started) * 1000),
              'stdout': stdout_path.name, 'stderr': stderr_path.name,
              'manifest': 'manifest.json'}
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'status': status, 'exitCode': exit_code, 'outDir': str(out_dir),
                      'durationMs': result['durationMs']}, ensure_ascii=False))
    return 0 if status == 'done' else (124 if status == 'timeout' else 1)


if __name__ == '__main__':
    sys.exit(main())
