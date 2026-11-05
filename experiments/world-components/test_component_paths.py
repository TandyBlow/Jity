import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from component_paths import ComponentPaths


class PathsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'branch'
        self.root.mkdir()
        self.paths = ComponentPaths(self.root, 'inputs', 'outputs')
        self.paths.inputs.mkdir()
        (self.paths.inputs / 'round.json').write_bytes(b'{"value": 1}\r\n')
        self.digest = hashlib.sha256((self.paths.inputs / 'round.json').read_bytes()).hexdigest()
        (self.paths.inputs / 'pin.json').write_text(json.dumps({'files': {
            'round.json': {'sha256': self.digest}}}))

    def test_missing_or_changed_input_fails_instead_of_reading_another_worktree(self):
        self.assertEqual(self.paths.verify_inputs()['files'], 1)
        (self.paths.inputs / 'round.json').write_bytes(b'{"value": 1}\n')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            self.paths.input('round.json')
        with self.assertRaises(FileNotFoundError):
            self.paths.input('missing.json')

    def test_output_escape_and_input_overwrite_are_rejected(self):
        for path in ('../../outside.json', self.paths.inputs / 'round.json', self.root.parent / 'other/result.json'):
            with self.assertRaises(ValueError):
                self.paths.output(path)
        self.assertFalse(self.paths.outputs.exists())

    def test_historical_copy_is_immutable_and_drift_is_detected(self):
        archive = self.root / 'archive/round.json'
        archive.parent.mkdir()
        archive.write_bytes((self.paths.inputs / 'round.json').read_bytes())
        pin = self.paths.inputs / 'pin.json'
        records = json.loads(pin.read_text())
        records['files']['round.json']['historicalCopies'] = [{'path': 'archive/round.json'}]
        pin.write_text(json.dumps(records))
        self.assertEqual(self.paths.verify_inputs()['historicalCopiesVerified'], 1)
        redirected = ComponentPaths(self.root, 'inputs', 'archive')
        with self.assertRaisesRegex(ValueError, 'historical evidence'):
            redirected.output('round.json')
        archive.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Historical evidence drifted'):
            self.paths.input('round.json')
        archive.unlink()
        with self.assertRaises(FileNotFoundError):
            self.paths.verify_inputs()

    def test_symlink_output_escape_is_rejected(self):
        self.paths.outputs.mkdir()
        outside = self.root.parent / 'other'
        outside.mkdir()
        try:
            (self.paths.outputs / 'link').symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f'Symlinks unavailable: {exc}')
        with self.assertRaises(ValueError):
            self.paths.output('link/result.json')

    def test_model_is_explicit_and_checkpoint_is_separate(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'N4_MODEL_DIR'):
                self.paths.model()
            model = self.root.parent / 'shared-model'
            model.mkdir()
            for name in ('config.json', 'spiece.model', 'model.safetensors'):
                (model / name).write_bytes(b'fixture')
            os.environ['N4_MODEL_DIR'] = str(model)
            self.assertEqual(self.paths.model(), model.resolve())
            self.assertEqual(self.paths.model(model), model.resolve())
            with self.assertRaises(ValueError):
                self.paths.checkpoint(model)
            self.assertEqual(self.paths.checkpoint('training/run1'), self.paths.outputs / 'training/run1')


if __name__ == '__main__':
    unittest.main()
