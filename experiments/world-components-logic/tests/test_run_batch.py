"""Preparation guards only: no model stack or real inference in these tests."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import prepare_run_batch as prep
from lab import canonical_bytes, load_jsonl


class RunPreparationTests(unittest.TestCase):
    def fixture(self, root):
        relative = prep.BASE + 'data/round1-inputs/development-inputs.jsonl'
        path = root / relative
        path.parent.mkdir(parents=True)
        rows = load_jsonl(prep.ROOT / relative)
        path.write_bytes(b''.join(canonical_bytes(r)+b'\n' for r in rows))
        manifest = path.with_name('input-manifest.json')
        manifest.write_text(json.dumps({'files': {path.name: prep.sha256_file(path)}}))
        return relative, path, manifest

    def test_only_explicit_development_ready_cases_can_be_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative, _, _ = self.fixture(root)
            ids = ['r1-dev-d02-01', 'r1-dev-d03-04', 'r1-dev-d04-01', 'r1-dev-d05-01']
            bound = prep.bind_development(root, relative, ids)
            self.assertEqual(bound['caseIds'], ids)
            self.assertEqual(len(bound['selectedCases']), 4)
            self.assertIsNone(bound['inputReviewEvidence'])
            self.assertIsNone(bound['sourceIsolationEvidence'])
            for bad in ([], ['r1-sealed-d02-01'], ['r1-dev-d04-07'], [ids[0], ids[0]]):
                with self.assertRaises(ValueError):
                    prep.bind_development(root, relative, bad)

    def test_sealed_and_changed_data_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative, path, manifest = self.fixture(root)
            original = path.read_bytes()
            path.write_bytes(original+b'\n')
            with self.assertRaisesRegex(ValueError, 'manifest'):
                prep.bind_development(root, relative, ['r1-dev-d02-01'])
            row = json.loads(original.splitlines()[0]); row['split'] = 'sealed_candidate'
            path.write_bytes(canonical_bytes(row)+b'\n')
            manifest.write_text(json.dumps({'files': {path.name: prep.sha256_file(path)}}))
            with self.assertRaisesRegex(ValueError, 'development-only'):
                prep.bind_development(root, relative, [row['caseId']])

    def test_unknown_and_redirected_paths_are_rejected(self):
        for name in ('../data.jsonl', '/tmp/data.jsonl', prep.BASE+'data/round1-inputs/task-inputs.jsonl'):
            with self.assertRaises(ValueError):
                prep.bind_development(prep.ROOT, name, ['r1-dev-d02-01'])

    def test_no_batch_obtains_authorization_from_preparation(self):
        binding = prep.bind_development(prep.ROOT, None, [])
        value = {'environmentObservation': {'venvExecutableExists': True, 'venvExecutablePermission': True,
                  'lockMatchesHistoricalIdentity': True, 'registeredVersionsMatch': True},
                 'm02Observation': {'allSixFilesFullyRehashedAndVerified': True}}
        for batch in prep.batches(binding):
            blockers = prep.execution_blockers(batch, value)
            self.assertIn('authorizationEvidence', blockers)
            self.assertIn('resourceWindow', blockers)
            self.assertFalse(batch['executionAuthorized'])
            self.assertFalse(batch['formalScreeningAllowed'])
        training = prep.batches(binding)[2]
        self.assertEqual(training['first90TrainingQuota'], 0)
        self.assertEqual(training['protocolDraft']['dataPlan']['sourceGroupsBuilt'], 0)
        self.assertTrue(all(v is None for v in training['protocol'].values()))
        self.assertIn('protocol.labels', prep.execution_blockers(training, value))
        dev = prep.batches(binding)[1]
        self.assertEqual(set(dev['promptAndDecoderConfig']['instructions']), {'D02','D03','D04','D05'})
        self.assertFalse(dev['promptAndDecoderConfig']['truncationAllowed'])
        self.assertEqual(dev['plannedAttemptsPerCase'], 5)
        self.assertIn('tokenCoverageVerified', prep.execution_blockers(dev, value))

    def test_missing_trained_m01_head_blocks_collaboration(self):
        batch = prep.batches(prep.bind_development(prep.ROOT, None, []))[1]
        batch['modelIds'].append('M01')
        value = {'environmentObservation': {'venvExecutableExists': True, 'venvExecutablePermission': True,
                  'lockMatchesHistoricalIdentity': True, 'registeredVersionsMatch': True},
                 'm02Observation': {'allSixFilesFullyRehashedAndVerified': True}}
        self.assertIn('trained_M01_business_head', prep.execution_blockers(batch, value))

    def test_publication_never_overwrites_existing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'snapshot.json'
            prep.write_new(path, b'original\n')
            with self.assertRaises(FileExistsError):
                prep.write_new(path, b'different\n')
            self.assertEqual(path.read_bytes(), b'original\n')

    def test_static_snapshot_rejects_fabricated_authorization_or_performance(self):
        env = {'venvExecutableExists': True, 'venvExecutablePermission': True,
               'lockMatchesHistoricalIdentity': True, 'registeredVersionsMatch': True}
        with mock.patch.object(prep, 'observe_environment', return_value=env), mock.patch.object(
                prep, 'observe_m02', return_value={'allSixFilesFullyRehashedAndVerified': True}):
            snapshot = prep.build_preparation()
        self.assertEqual(prep.validate(snapshot, recheck_files=False), [])
        for field in ('executionAuthorized', 'modelExecutionPerformed', 'executionDispatchImplemented'):
            bad = copy.deepcopy(snapshot); bad[field] = True
            self.assertTrue(prep.validate(bad, recheck_files=False))
        bad = copy.deepcopy(snapshot); bad['performance']['fullRequestTargetMs'] = 1000
        self.assertTrue(prep.validate(bad, recheck_files=False))
        bad = copy.deepcopy(snapshot); bad['batches'][2]['first90TrainingQuota'] = 1
        self.assertTrue(prep.validate(bad, recheck_files=False))


if __name__ == '__main__':
    unittest.main()
