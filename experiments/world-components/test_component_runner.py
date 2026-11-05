import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from component_paths import ComponentPaths, WORKTREE
import run_component as runner


class RunnerTests(unittest.TestCase):
    def test_repeating_a_task_does_not_overwrite_evidence_or_start_a_child(self):
        local = WORKTREE / '.local'
        local.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local) as temp:
            paths = ComponentPaths(WORKTREE, Path(temp) / 'inputs', Path(temp) / 'runs')
            paths.inputs.mkdir()
            (paths.inputs / 'pin.json').write_text(json.dumps({'files': {}}))
            argv = ['run_component.py', 'smoke', '--run-dir', 'same-run']
            with patch.object(runner, 'PATHS', paths), patch.object(sys, 'argv', argv), \
                    patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as child:
                self.assertEqual(runner.main(), 0)
                manifest = paths.outputs / 'same-run/smoke-run.json'
                before = manifest.read_bytes()
                sentinel = manifest.parent / 'result.json'
                sentinel.write_bytes(b'existing result')
                with self.assertRaises(FileExistsError):
                    runner.main()
                self.assertEqual(child.call_count, 1)
                self.assertEqual(manifest.read_bytes(), before)
                self.assertEqual(sentinel.read_bytes(), b'existing result')


if __name__ == '__main__':
    unittest.main()
