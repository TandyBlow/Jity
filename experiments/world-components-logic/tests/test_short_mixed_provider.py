import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from short_contracts import result, incomplete, empty
from short_mixed_provider import MixedSemanticProvider, verify_backend_artifacts
from short_qwen_codec import CODEC


class Backend:
    """Engineering routing fixture, never model-quality evidence."""
    def __init__(self, answer):
        self.identity = {'modelId': 'Qwen/Qwen3-0.6B', 'device': 'webgpu', 'codec': CODEC,
                         'trainedComponents': ['D02.2.text'], 'trainingSteps': 1,
                         'qualification': 'task_finetuned'}
        self.calls = []
        self.answer = answer
    def __call__(self, component, payload):
        self.calls.append((component, payload))
        return self.answer


class RoutingTests(unittest.TestCase):
    def manifest(self):
        return {'schema': 'jity-d-short-trained-provider-v1', 'datasetSha256': 'fixture',
                'codeSha256': {'fixture': 'fixture'}, 'config': {},
                'models': {'encoder': {}, 'generator': {'retired': True}},
                'tasks': {'D02.2.text': {'kind': 'text', 'outputCodec': 'text'}}}
    def test_only_webgpu_receives_original_complete_payload_and_returns_original_text(self):
        backend = Backend(result(' 甲尝试开门。\n'))
        provider = MixedSemanticProvider(self.manifest(), backend)
        payload = {'world': {'offscene': 'kept'}, 'fragments': []}
        with patch.object(provider, '_load', side_effect=AssertionError('old generator cannot load')):
            self.assertEqual(provider('D02.2.text', payload).value, ' 甲尝试开门。\n')
        self.assertEqual(backend.calls, [('D02.2.text', payload)])
        self.assertNotIn('generator', provider.manifest['models'])
    def test_failure_and_empty_never_fall_back(self):
        for answer in (incomplete('device_lost'), empty()):
            provider = MixedSemanticProvider(self.manifest(), Backend(answer))
            with patch.object(provider, '_load', side_effect=AssertionError('no fallback')):
                self.assertEqual(provider('D02.2.text', {}).status, 'incomplete')
    def test_untrained_baseline_requires_explicit_experimental_mode(self):
        backend = Backend(result('fixture')); backend.identity['trainedComponents'] = []
        provider = MixedSemanticProvider(self.manifest(), backend)
        self.assertIn('untrained_qwen', provider('D02.2.text', {}).reason)
        self.assertEqual(backend.calls, [])
        self.assertEqual(MixedSemanticProvider(self.manifest(), backend, require_trained=False)('D02.2.text', {}).value, 'fixture')

    def test_old_focus_dataset_needs_explicit_verified_migration(self):
        from lab import sha256_file
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def artifact(name, value):
                p = root / name; p.write_text(json.dumps(value))
                return {'path': str(p), 'sha256': sha256_file(p)}
            file = artifact('asset.json', {})
            focus = artifact('focus.json', {'datasetSha256': 'old-data'})
            manifest = {'datasetSha256': 'new-data', 'sourceEncoderProvider': file,
                'focusBackend': focus, 'textBackend': {'modelManifest': file, 'runtimeManifest': file,
                    'tokenizerParity': file}}
            with patch('short_webgpu.verified_manifest', return_value={}):
                with self.assertRaisesRegex(ValueError, 'dataset_identity_mismatch'):
                    verify_backend_artifacts(manifest)
                proof = artifact('proof.json', {'fixture': True})
                checked = {'verifiedUnchangedComponents': ['D02.1'], 'semanticApproval': False}
                manifest['focusDataMigration'] = {'proof': proof, 'verified': checked}
                with patch('short_encoder_repair.FocusSemanticProvider') as provider, \
                        patch('short_data_migration.verify_migration', return_value=checked) as verify:
                    provider.return_value.identity = {'components': ['D02.1']}
                    verify_backend_artifacts(manifest)
                    verify.assert_called_once_with(proof['path'], source_sha='old-data', target_sha='new-data',
                                                   unchanged_components=['D02.1'])
                with patch('short_encoder_repair.FocusSemanticProvider') as provider, \
                        patch('short_data_migration.verify_migration', return_value={'changed': True}):
                    provider.return_value.identity = {'components': ['D02.1']}
                    with self.assertRaisesRegex(ValueError, 'migration_identity_changed'):
                        verify_backend_artifacts(manifest)
    def test_cpu_or_identity_change_rejected(self):
        backend = Backend(result('fixture')); backend.identity['device'] = 'cpu'
        with self.assertRaisesRegex(ValueError, 'WebGPU'): MixedSemanticProvider(self.manifest(), backend)
        backend.identity['device'] = 'webgpu'
        provider = MixedSemanticProvider(self.manifest(), backend)
        backend.identity['codec'] = 'changed'
        self.assertIn('identity_changed', provider('D02.2.text', {}).reason)

    def test_declared_component_list_does_not_replace_real_training_qualification(self):
        for steps, qualification in ((0, 'task_finetuned'), (1, 'base_zero_shot')):
            backend = Backend(result('fixture'))
            backend.identity.update(trainingSteps=steps, qualification=qualification)
            provider = MixedSemanticProvider(self.manifest(), backend)
            self.assertEqual(provider('D02.2.text', {}).status, 'incomplete')
            self.assertEqual(backend.calls, [])

    def test_admission_rejection_never_counts_or_calls_model(self):
        backend = Backend(result('fixture'))
        def reject(name, value):
            if name == 'semantic_call_started': raise RuntimeError('before_primitive_deadline')
        provider = MixedSemanticProvider(self.manifest(), backend, checkpoint=reject)
        with self.assertRaisesRegex(RuntimeError, 'before_primitive_deadline'):
            provider('D02.2.text', {})
        self.assertEqual(provider.primitive_calls, 0)
        self.assertEqual(backend.calls, [])

    def test_focus_nested_log_keeps_logits_without_duplicate_primitive_count(self):
        class Focus:
            identity = {'components': ['D02.1'], 'model': 'fixture_only'}
            def __call__(self, component, payload):
                self.checkpoint('semantic_call_started', {'component': component, 'input': payload})
                self.checkpoint('encoder_forward_started', {'component': component})
                self.checkpoint('encoder_forward_settled', {'component': component, 'elapsedMs': 2.})
                self.checkpoint('semantic_call_finished', {'component': component, 'rawLogits': [1., 2., 3.],
                                                          'value': 'incomplete', 'elapsedMs': 3.})
                return result('incomplete')
        from short_evaluation import CaseCheckpoints, CONFIG
        events = []
        checkpoint = CaseCheckpoints(lambda name, payload: events.append((name, payload)), CONFIG,
                                     'diagnostic', started_ns=0, clock=lambda: 1)
        provider = MixedSemanticProvider(self.manifest(), Backend(result('unused')),
                                         focus_backend=Focus(), checkpoint=checkpoint)
        with patch.object(provider, '_load', side_effect=AssertionError('no fallback')):
            answer = provider('D02.1', {'world': {'all': 'facts'}})
        self.assertEqual(answer.status, 'incomplete')
        self.assertEqual(answer.reason, 'semantic_incomplete:D02.1')
        self.assertEqual(checkpoint.counters['primitiveCalls'], 1)
        self.assertEqual(checkpoint.counters['encoderForwards'], 1)
        self.assertEqual(sum(name == 'semantic_call_finished' for name, _ in events), 1)
        nested = next(value for name, value in events if name == 'focus_semantic_call_finished')
        self.assertEqual(nested['rawLogits'], [1., 2., 3.])

    def test_focus_failure_never_uses_historical_head(self):
        class Focus:
            identity = {'components': ['D02.1'], 'model': 'fixture_only'}
            def __call__(self, component, payload): return incomplete('new_head_failed')
        provider = MixedSemanticProvider(self.manifest(), Backend(result('unused')), focus_backend=Focus())
        with patch.object(provider, '_load', side_effect=AssertionError('no fallback')):
            self.assertEqual(provider('D02.1', {}).reason, 'new_head_failed')

    def test_late_text_is_logged_before_deadline_rejection(self):
        from short_evaluation import CaseCheckpoints, CaseBudgetExceeded, CONFIG
        now = [0]; events = []
        class Slow(Backend):
            def __call__(self, component, payload):
                now[0] = 31_000_000_000
                return result('迟到的原始句子。')
        checkpoint = CaseCheckpoints(lambda name, payload: events.append((name, payload)), CONFIG,
                                     'diagnostic', started_ns=0, clock=lambda: now[0])
        provider = MixedSemanticProvider(self.manifest(), Slow(result('unused')), checkpoint=checkpoint)
        with self.assertRaises(CaseBudgetExceeded): provider('D02.2.text', {})
        raw = next(value for name, value in events if name == 'semantic_call_finished')
        self.assertEqual(raw['value'], '迟到的原始句子。')
        self.assertEqual(events[-1][0], 'case_late_output_rejected')


if __name__ == '__main__': unittest.main()
