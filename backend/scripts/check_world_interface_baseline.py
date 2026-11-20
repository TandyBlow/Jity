"""Common A0/B0 check; run from any directory on Windows or Linux.

Requires installed backend requirements and frontend npm ci. Does not export,
repair snapshots, install dependencies, start services, or skip missing tests.
The full frontend suite is a separate CI step.
"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
    if not npm:
        raise SystemExit('npm is required for the common interface check')
    v1 = sorted((ROOT / 'backend/tests').glob('test_world_protocol_*.py'))
    v2 = sorted((ROOT / 'backend/tests').glob('test_world_protocol_v2_*.py'))
    v1 = [p for p in v1 if p not in v2]
    required_v1 = {'test_world_protocol_contract.py', 'test_world_protocol_storage_contract.py'}
    required_v2 = {f'test_world_protocol_v2_{name}.py' for name in ('contract', 'revision', 'storage_contract', 'canonical', 'trace_schema', 'traces', 'export')}
    if not required_v1.issubset({p.name for p in v1}) or not required_v2.issubset({p.name for p in v2}):
        raise SystemExit('Required contract test modules are missing')
    commands = [
        [sys.executable, '-X', 'utf8', 'backend/scripts/export_world_protocol.py', '--version', v, '--check'] for v in ('v1', 'v2')
    ]
    commands += [[sys.executable, '-X', 'utf8', '-m', 'pytest', '-q', *[str(p.relative_to(ROOT)) for p in v1]],
                 [sys.executable, '-X', 'utf8', '-m', 'pytest', '-q', *[str(p.relative_to(ROOT)) for p in v2]]]
    commands += [[npm, '--prefix', 'frontend', 'run', name] for name in ('typecheck:world', 'test:world-contract', 'test:world-traces')]
    commands += [[sys.executable, '-X', 'utf8', 'backend/scripts/probe_world_interface_mutations.py']]
    for command in commands:
        print('> ' + subprocess.list2cmdline(command), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)
    print('PASS: shared world interface baseline (services/A3/H1/H2 remain separate).')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode)
