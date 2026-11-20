import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from component_paths import ComponentPaths

sys.path.insert(0, str(Path(__file__).resolve().parent / 'n4_narrative_dev'))
import narration_service as service


class RoundLookupTests(unittest.TestCase):
    def test_unknown_and_traversal_round_ids_are_not_read(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = ComponentPaths(temp, 'inputs', 'outputs')
            directory = paths.inputs / 'rounds'
            directory.mkdir(parents=True)
            data = b'{"worldId":"fixed","units":[]}'
            (directory / 'example-authorized.json').write_bytes(data)
            (paths.inputs / 'pin.json').write_text(json.dumps({'files': {
                'rounds/example-authorized.json': {'sha256': hashlib.sha256(data).hexdigest()}}}))
            engine = service.Engine.__new__(service.Engine)
            engine.rounds_dir = directory
            with patch.object(service, 'PATHS', paths):
                self.assertEqual(engine.load_round('example')['worldId'], 'fixed')
                for invalid in ('missing', '../example', '..\\example', 'C:/example'):
                    with self.assertRaises(KeyError, msg=invalid):
                        engine.load_round(invalid)
                (directory / 'example-authorized.json').write_bytes(data + b'\n')
                with self.assertRaisesRegex(ValueError, 'bytes changed'):
                    engine.load_round('example')


if __name__ == '__main__':
    unittest.main()
