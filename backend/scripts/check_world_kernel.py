"""A-owned local gate for the world kernel.

Deliberately separate from check_world_interface_baseline.py: the common
interface check must stay byte-identical on both development branches and
cannot learn about kernel modules (B's branch has no kernel). This script is
not part of the manifest and never runs inside the common entry. The CI
backend job runs the full backend suite, which includes these modules.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GLOB = 'test_world_kernel_*.py'


def main():
    tests = sorted((ROOT / 'backend/tests').glob(GLOB))
    if not tests:
        raise SystemExit(f'No kernel test modules found for {GLOB}')
    commands = [
        [sys.executable, '-X', 'utf8', '-m', 'pytest', '-q',
         *[str(path.relative_to(ROOT)) for path in tests]],
    ]
    for command in commands:
        print('> ' + subprocess.list2cmdline(command), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)
    print(f'PASS: world kernel ({len(tests)} modules)')


if __name__ == '__main__':
    main()
