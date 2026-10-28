"""Isolate expected TS version failures without changing either worktree.

Archived copy note: the original run used an absolute local path; it is
replaced by an env-overridable relative default below (run from this directory).
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(os.environ.get('WORLD_SERVER_WORKTREE', '../world-server-worktree'))
parent = (ROOT / 'frontend/src/lib').resolve()
report_dir = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='world-r1-version-probe-', dir=parent) as folder:
    target = Path(folder).resolve()
    assert target.is_relative_to(parent)
    shutil.copytree(parent / 'world-engine', target, dirs_exist_ok=True)
    protocol = target / 'protocol.ts'
    value = protocol.read_bytes()
    old = b'v.schemaVersion !== 1'
    assert value.count(old) == 1
    protocol.write_bytes(value.replace(old, b'v.schemaVersion !== 2'))
    command = [shutil.which('npm.cmd') or shutil.which('npm'), 'exec', '--', 'vitest', 'run',
               str(target / 'contract.test.ts'), str(target / 'traces.test.ts')]
    result = subprocess.run(command, cwd=ROOT / 'frontend', capture_output=True,
                            encoding='utf-8', errors='replace')
    output = result.stdout + result.stderr
    (report_dir / 'fafc859_ts_probe.log').write_text(output, encoding='utf-8')
    summary = dict(returncode=result.returncode,
                   temporaryChange='Only v.schemaVersion !== 1 -> !== 2 in a temporary consumer copy',
                   sourceWorktreesChanged=False,
                   finalOutput=output[-2200:])
    (report_dir / 'fafc859_ts_probe.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
