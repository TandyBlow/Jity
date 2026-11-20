"""Demonstrate gate, bytes, response and digest failures in temporary copies.

The source worktree is read-only. Temporary frontend files live at the same
import depth as the consumer, so Vitest runs the actual consumer gate test.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from export_world_protocol import ROOT, json_bytes, run_export


def main():
    baseline = ROOT / 'design/world-protocol/v2'
    with tempfile.TemporaryDirectory(prefix='jity-world-mutants-') as temporary:
        root = Path(temporary)
        for mutation in ('generated_crlf', 'response_field', 'dynamic_digest'):
            target = root / mutation
            shutil.copytree(baseline, target)
            if mutation == 'generated_crlf':
                path = target / 'world-protocol.schema.json'
                path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
            elif mutation == 'response_field':
                path = target / 'fixtures/api/checkpoint_resume/success.json'
                value = json.loads(path.read_bytes()); del value['control']
                path.write_bytes(json_bytes(value))
            else:
                path = target / 'traces/T07.json'
                value = json.loads(path.read_bytes())
                key = next(iter(value['samples'][1]['expectedDigests']))
                value['samples'][1]['expectedDigests'][key] = '0' * 64
                path.write_bytes(json_bytes(value))
            try:
                run_export('v2', target, check=True)
            except ValueError as error:
                print(f'REJECTED {mutation}: {error}', flush=True)
            else:
                raise SystemExit(f'Mutation unexpectedly passed: {mutation}')
    parent = (ROOT / 'frontend/src/lib').resolve()
    with tempfile.TemporaryDirectory(prefix='world-interface-mutation-', dir=parent) as temporary:
        target = Path(temporary).resolve()
        if not target.is_relative_to(parent): raise SystemExit('Unsafe mutation workspace')
        shutil.copytree(parent / 'world-engine', target, dirs_exist_ok=True)
        protocol = target / 'protocol.ts'
        text = protocol.read_text(encoding='utf-8')
        before = 'return control.canCompute;'
        if text.count(before) != 1: raise SystemExit('Gate probe needs updating for changed source')
        protocol.write_bytes(text.replace(before, 'return !control.canCompute;').encode('utf-8'))
        npm = shutil.which('npm.cmd') or shutil.which('npm')
        if not npm: raise SystemExit('npm is required for the gate mutation probe')
        result = subprocess.run([npm, 'exec', '--', 'vitest', 'run', str(target / 'contract.test.ts'),
            '-t', 'handles resume-blocked'], cwd=ROOT / 'frontend', capture_output=True, encoding='utf-8', errors='replace')
        output = result.stdout + result.stderr
        if result.returncode == 0 or 'expected true to be false' not in output:
            print(output)
            raise SystemExit('Gate mutation did not fail for the expected assertion')
        print('REJECTED gate_handling: real resume-blocked consumer assertion failed', flush=True)
    print('PASS: all four mutations rejected; source artifacts were not modified.')


if __name__ == '__main__': main()
