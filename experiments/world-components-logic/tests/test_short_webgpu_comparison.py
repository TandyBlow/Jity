import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import ExitStack

SCRIPT = Path(__file__).resolve().parents[1] / 'short_webgpu/profile_comparison.py'
SPEC = importlib.util.spec_from_file_location('profile_comparison_fixture', SCRIPT)
M = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(M)


class ComparisonTests(unittest.TestCase):
    def test_base_diagnostic_is_explicit_and_cannot_admit_rejected_trained_assets(self):
        base = {'identity': M.BASE_DIAGNOSTIC_IDENTITY, 'provenance': {'trainingSteps': 0,
            'sourceModel': 'onnx-community/Qwen3-0.6B-ONNX',
            'sourceRevision': '58ca03a5e7b354b480b1a82b34bde8dc7b854cc0'}}
        with self.assertRaisesRegex(ValueError, 'requires_task_trained_assets'):
            M.qualification_metadata(base)
        with self.assertRaisesRegex(ValueError, 'requires_explicit_trained_export_disposition'):
            M.qualification_metadata(base, 'base_zero_shot_diagnostic')
        with tempfile.TemporaryDirectory() as temp:
            failure = Path(temp) / 'failed.export-record.json'
            failure.write_text('{"runId":"fixture-failed-export","status":"failed"}')
            result = M.qualification_metadata(base, 'base_zero_shot_diagnostic', failure)
            self.assertFalse(result['trainingEffectEvidence'])
            self.assertFalse(result['trainedWeightsExportQualified'])
            self.assertEqual(result['trainedExportDisposition']['sha256'], M.sha256_file(failure))
            for changed in ({**base, 'identity': 'different-assets'},
                            {**base, 'provenance': {**base['provenance'], 'trainingSteps': 32}},
                            {**base, 'provenance': {**base['provenance'], 'trainingSteps': False}}):
                with self.assertRaises(ValueError):
                    M.qualification_metadata(changed, 'base_zero_shot_diagnostic', failure)
            failure.write_text('{"status":"running"}')
            with self.assertRaisesRegex(ValueError, 'not_final_or_not_failed'):
                M.qualification_metadata(base, 'base_zero_shot_diagnostic', failure)

    def test_base_freeze_records_qualification_without_changing_default_resources(self):
        # Frozen-plan engineering fixture only; BrowserBridge's actual byte and
        # strict-validation gates have separate tests and are not simulated GPU.
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp).resolve(); source = root / 'source.json'; source.write_text('{}')
            data = root / 'data.json'; data.write_text('{}')
            failure = root / 'failed.export-record.json'; failure.write_text('{"runId":"fixture","status":"failed"}')
            assets = []
            for name in ('model', 'runtime', 'parity'):
                file = root / (name + '.json'); file.write_text('{}'); assets.append(file)
            work = [{'workloadId': label, 'component': component, 'input': {'full': 'fixture'},
                'inputHash': M.digest({'full': 'fixture'})} for label, component in zip(('short', 'long'), M.COMPONENTS)]
            packet = {'workloads': work, 'sourcePlan': {'path': str(source), 'sha256': M.sha256_file(source)},
                'sourceData': {'path': str(data), 'sha256': M.sha256_file(data)}}
            class FixtureBridge:
                model = {'identity': M.BASE_DIAGNOSTIC_IDENTITY, 'provenance': {'trainingSteps': 0,
                    'sourceModel': 'onnx-community/Qwen3-0.6B-ONNX',
                    'sourceRevision': '58ca03a5e7b354b480b1a82b34bde8dc7b854cc0'}}
                runtime = {'identity': 'explicit-runtime-fixture'}
                def configuration(self): return {'engineeringFixture': True}
            for name, value in [('paths', lambda name: (root / (name + '.plan.json'), root / (name + '.record.json'))),
                                ('workloads', lambda *args: packet), ('bridge_for', lambda *args: FixtureBridge()),
                                ('snapshot_code', lambda *args: {'files': {}, 'directory': str(root)})]:
                stack.enter_context(patch.object(M, name, value))
            with self.assertRaisesRegex(ValueError, 'requires_task_trained_assets'):
                M.freeze('default', source, *assets, '/explicit/unused/python')
            self.assertFalse((root / 'default.plan.json').exists())
            path = M.freeze('explicit-base', source, *assets, '/explicit/unused/python',
                qualification='base_zero_shot_diagnostic', trained_export_failure=failure)
            plan = json.loads(path.read_text())
            self.assertEqual(plan['qualification']['mode'], 'base_zero_shot_diagnostic')
            self.assertEqual(plan['config'], M.CONFIG)
            self.assertTrue(M.verify(plan))
            failure.write_text('{"runId":"fixture","status":"failed","changed":true}')
            with self.assertRaisesRegex(ValueError, 'trained_export_disposition_drift'):
                M.verify(plan)

    def test_registered_complete_workloads_have_fixed_repetitions_not_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); data = root / 'rows.jsonl.gz'; source = root / 'source.plan.json'
            rows = [{'exampleId': 'x' + str(i), 'component': component,
                     'input': {'world': {'distant': 'all facts remain'}, 'step': i}}
                    for i, component in enumerate(M.COMPONENTS)]
            with gzip.open(data, 'wt') as f:
                for row in rows: f.write(json.dumps(row) + '\n')
            plan = {'cases': [{'component': row['component'], 'exampleId': row['exampleId'],
                'inputHash': M.digest(row['input']), 'sourceGroup': 'same-original-source', 'split': 'test'} for row in rows],
                'dataSnapshot': {'supervision.jsonl.gz': {'path': str(data), 'sha256': M.sha256_file(data)}}}
            source.write_text(json.dumps(plan))
            packet = M.workloads(source)
            self.assertEqual([w['input'] for w in packet['workloads']], [r['input'] for r in rows])
            cases = M.registered_cases(packet['workloads'])
            self.assertEqual([c['profilingMode'] for c in cases], list(M.MODES) * 2)
            self.assertEqual(len({c['caseId'] for c in cases}), 8)
            self.assertTrue(all(c['retry'] is False for c in cases))
            data.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'source_data_drift'): M.workloads(source)

    def test_failed_measurements_never_create_agreement_or_success(self):
        attempts = [{'caseId': 'short:1:default', 'completion': {'status': 'incomplete'}, 'caseWallMs': 1},
                    {'caseId': 'short:2:off', 'completion': {'status': 'incomplete'}, 'caseWallMs': 2}]
        comparison = M.comparisons(attempts)[0]
        self.assertFalse(comparison['bothComponentResults'])
        self.assertIsNone(comparison['tokensIdentical'])
        self.assertIsNone(comparison['textIdentical'])
        self.assertIsNone(comparison['sameDeviceSession'])
        self.assertFalse(comparison['offPerRequestGpuProof'])

    def test_actual_common_journal_recovery_accepts_eight_fixture_slots_and_measured_timing(self):
        # Explicit orchestration fixture. No browser, GPU, or model executes.
        from short_contracts import ModelIdentity, result
        class FixtureBridge:
            def start(self): return 'http://127.0.0.1:0/#engineering-fixture'
            def wait_ready(self, timeout): return {'status': 'ready', 'engineeringFixture': True}
            def close(self): pass
        class FixtureProvider:
            def __init__(self, *args, **kwargs):
                self.model_identity = ModelIdentity('fixture', 'fixture', 'fixture', 'fixture', 'fixture', 'fixture')
            def __call__(self, component, payload):
                self.checkpoint('explicit_engineering_fixture', {'modelCalled': False, 'component': component})
                return result('explicit fixture text, no model inference')
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp); plan_path = root / 'fixture.plan.json'; out = root / 'fixture.record.json'
            work = [{'workloadId': label, 'component': component, 'input': {'full': 'fixture'},
                'inputHash': M.digest({'full': 'fixture'})} for label, component in zip(('short', 'long'), M.COMPONENTS)]
            plan = {'runId': 'engineering-fixture', 'config': M.CONFIG, 'workloads': work, 'cases': M.registered_cases(work)}
            plan_path.write_text(json.dumps(plan))
            for name, value in [('verify', lambda p: True), ('paths', lambda name: (plan_path, out)),
                                ('bridge_for', lambda *a: FixtureBridge()), ('WebGPUProvider', FixtureProvider)]:
                stack.enter_context(patch.object(M, name, value))
            self.assertEqual(M.worker(plan_path), 0)
            report = json.loads(out.read_text())
            M.common.reconcile_journal(report, out.with_suffix('.journal.jsonl'), 'fixture_complete')
            self.assertEqual(report['status'], 'diagnostic_completed')
            self.assertEqual(len(report['attempts']), 8)
            for attempt in report['attempts']:
                self.assertGreater(attempt['resultJournalMs'], 0)
                self.assertGreater(attempt['snapshotEndMs'], 0)
                self.assertGreater(attempt['telemetryJournalMs'], 0)
                self.assertGreaterEqual(attempt['elapsedIncludingTelemetryMs'], attempt['elapsedThroughResultMs'])
            self.assertEqual(report['journalRecovery']['modelCallsDuringReplay'], 0)


if __name__ == '__main__': unittest.main()
