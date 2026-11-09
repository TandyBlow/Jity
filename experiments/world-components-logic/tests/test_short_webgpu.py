"""Transport counterexamples use explicit fixtures, never count as model runs."""
import copy
import importlib.util
import json
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from lab import canonical_bytes, sha256_file
from run_pilot import digest
from short_webgpu import (BrowserBridge, WebGPUProvider, validate_response, verified_manifest,
    MODEL_SCHEMA, RUNTIME_SCHEMA, PLACEMENT_POLICY, profiling_policy)
import short_webgpu as webgpu_module


def assets(directory, schema):
    files = ['config.json', 'generation_config.json', 'tokenizer.json', 'tokenizer_config.json', 'onnx/model_q4f16.onnx'] if schema == MODEL_SCHEMA else ['transformers.web.min.js']
    records = []
    for name in files:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}')
        records.append({'path': name, 'size': path.stat().st_size, 'sha256': sha256_file(path)})
    value = {'schema': schema, 'directory': str(directory), 'files': records}
    if schema == MODEL_SCHEMA:
        value.update(modelType='qwen3', dtype='q4f16', device='webgpu', maxContextTokens=1024,
                     eosTokenIds=[99], provenance={'sourceModel': 'test-fixture', 'capability': 'engineering_fixture', 'trainingSteps': 0})
    else:
        value.update(version='3.8.1')
    value['identity'] = digest({k: v for k, v in value.items() if k != 'directory'})
    path = directory / 'manifest.json'
    path.write_bytes(canonical_bytes(value))
    return path


def device_fixture(placement_sha256):
    return {'executionProvider': 'webgpu', 'dtype': 'q4f16', 'lost': False,
        'bindingSource': 'pinned_ort_jsep_readonly_environment', 'runtimeDeviceVerified': True,
        'adapterReferenceVerified': True, 'deviceCreatedBy': 'onnxruntime',
        'deviceSessionId': 'fixture-session',
        'placementPolicySha256': placement_sha256, 'adapterInfo': {'isFallbackAdapter': False},
        'features': ['shader-f16', 'timestamp-query']}


def response(request):
    value = {k: request[k] for k in ('requestId', 'requestSha256', 'generation', 'component',
        'inputSha256', 'messagesSha256', 'bindingSha256', 'codec', 'modelIdentity', 'runtimeIdentity', 'codeIdentity', 'placementPolicySha256', 'profilingMode')}
    value.update(status='result', deviceIdentity=device_fixture(request['placementPolicySha256']),
                 enableThinking=False, inputTokenIds=[1, 2], rawTokenIds=[8, 99], eosReached=True,
                 stopReason='eos', rawText='  试着用钳子松开螺母。\n')
    value['gpuEvidence'] = {k: request[k] for k in ('requestId', 'generation', 'bindingSha256', 'inputSha256', 'modelIdentity', 'placementPolicySha256')}
    value['gpuEvidence'].update(source='ort_webgpu_timestamp_query_v1', timestampUnit='nanoseconds',
        profilingMode='default', invalidCount=0, provesGpuWeightCompute=True, positiveWeightKernelCount=1,
        kernelCount=1, weightKernelCount=1, cpuNodeCount=None, cpuNodeDurationMs=None,
        weightWitnesses=[{'version': 1, 'kernelType': 'MatMulNBits', 'kernelName': 'fixture-weight',
            'programName': 'BlockwiseMatMulNBits32', 'startTime': 10, 'endTime': 20}])
    return value


class WebGPUBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name)
        self.model = assets(path / 'model', MODEL_SCHEMA)
        self.runtime = assets(path / 'runtime', RUNTIME_SCHEMA)
        self.bridge = BrowserBridge(self.model, self.runtime, retain_events=True, tokenizer_cases=path / 'none.json', require_tokenizer_parity=False)

    def tearDown(self):
        self.bridge.close()
        self.temp.cleanup()

    def call_async(self, **kw):
        results = []
        thread = threading.Thread(target=lambda: results.append(self.bridge.request('D02.2.text',
            {'world': {'name': 'full'}, 'fragments': []}, {'version': 1}, timeout_ms=kw.pop('timeout_ms', 500),
            max_input_tokens=128, max_new_tokens=32, **kw)))
        thread.start()
        for _ in range(100):
            if any(job['state'] == 'queued' for job in self.bridge.jobs.values()):
                break
            time.sleep(.001)
        return thread, results

    def claim(self):
        self.bridge.claim('browser', {'userAgent': 'explicit engineering fixture'})

    def rewrite_fixture_provenance(self, **updates):
        value = json.loads(self.model.read_text())
        value['provenance'].update(updates)
        value['identity'] = digest({k: v for k, v in value.items() if k not in ('identity', 'directory')})
        self.model.write_bytes(canonical_bytes(value))
        return value

    def strict_proof_fixture(self):
        """Explicit gate fixture, not actual numerical-model evidence."""
        root = Path(self.temp.name)
        training = root / 'training-plan.json'
        training.write_text('{"engineeringFixture":true}')
        config = {'validateFloatExport': True, 'validationAtol': .0001, 'validationRtol': .00001}
        plan = root / 'export-plan.json'
        plan.write_bytes(canonical_bytes({'model': {'runId': 'fixture-training',
            'planPath': str(training), 'planSha256': sha256_file(training), 'codec': webgpu_module.CODEC,
            'codeSha256': {'short_qwen_codec.py': sha256_file(BASE / 'short_qwen_codec.py')}}, 'config': config}))
        value = self.rewrite_fixture_provenance(trainingRunId='fixture-training',
            export={'planPath': str(plan), 'planSha256': sha256_file(plan), 'config': config})
        proof = {'schema': webgpu_module.STRICT_VALIDATION_SCHEMA, 'status': 'passed',
            'scope': 'float_export_numerical', 'planSha256': sha256_file(plan),
            'sourceTrainingPlanSha256': sha256_file(training),
            'codec': value['provenance']['codec'], 'codecSha256': value['provenance']['codecSha256'],
            'validatedFloatGraph': {'path': 'explicit-engineering-fixture.onnx', 'sha256': 'f' * 64, 'bytes': 2},
            'finalAssets': [{'path': row['path'], 'bytes': row['size'], 'sha256': row['sha256']} for row in value['files']],
            'expectedOutputNames': ['logits', 'present.0.key'],
            'checks': [{'name': name, 'atol': .0001, 'rtol': .00001, 'finite': True,
                'shapesEqual': True, 'valuesClose': True, 'maxAbsError': .00008}
                for name in ('logits', 'present.0.key')], 'engineeringFixture': True}
        return self.write_strict_proof_fixture(proof), proof

    def write_strict_proof_fixture(self, proof):
        path = Path(self.temp.name) / 'strict-proof.json'
        path.write_bytes(canonical_bytes(proof))
        value = self.rewrite_fixture_provenance(strictValidation={
            'schema': webgpu_module.STRICT_VALIDATION_SCHEMA, 'status': 'passed',
            'scope': 'float_export_numerical', 'proofPath': str(path), 'proofSha256': sha256_file(path)})
        return value

    def test_trained_assets_cannot_inherit_current_codec_label_from_old_training(self):
        codec_sha = sha256_file(BASE / 'short_qwen_codec.py')
        self.rewrite_fixture_provenance(trainingSteps=8, codec=webgpu_module.CODEC + '-older', codecSha256=codec_sha)
        with self.assertRaisesRegex(ValueError, 'trained_model_codec_version_mismatch'):
            verified_manifest(self.model, MODEL_SCHEMA)
        self.rewrite_fixture_provenance(codec=webgpu_module.CODEC, codecSha256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'trained_model_codec_source_mismatch'):
            verified_manifest(self.model, MODEL_SCHEMA)
        self.rewrite_fixture_provenance(codecSha256=codec_sha, trainedComponents=['D02.2.text'])
        good, _ = self.strict_proof_fixture()
        self.bridge.model = verified_manifest(self.model, MODEL_SCHEMA)
        identity = WebGPUProvider(self.bridge, binding={'v': 1}).identity
        self.assertEqual(identity['qualification'], 'task_finetuned')
        self.assertEqual(identity['trainingCodecSha256'], codec_sha)
        # The version string is unchanged but the current prompt source changed.
        # Patch only its observed hash; never edit the shared/frozen source file.
        real_sha = webgpu_module.sha256_file
        def changed_prompt(path):
            return 'f' * 64 if Path(path) == BASE / 'short_qwen_codec.py' else real_sha(path)
        with patch.object(webgpu_module, 'sha256_file', changed_prompt):
            with self.assertRaisesRegex(ValueError, 'trained_model_codec_source_mismatch'):
                verified_manifest(self.model, MODEL_SCHEMA)
            with self.assertRaisesRegex(ValueError, 'trained_model_codec_source_mismatch'):
                WebGPUProvider(self.bridge, binding={'v': 1}).identity
            rejected = self.bridge.request('D02.2.text', {'world': 'complete fixture'}, {'v': 1})
            self.assertEqual(rejected.status, 'incomplete')
            self.assertIn('trained_model_codec_source_mismatch', rejected.reason)
            self.assertFalse(self.bridge.jobs)
        self.assertEqual(good['provenance']['codec'], webgpu_module.CODEC)

    def test_r1_style_completed_export_without_strict_evidence_is_rejected(self):
        self.rewrite_fixture_provenance(trainingSteps=32, codec=webgpu_module.CODEC,
            codecSha256=sha256_file(BASE / 'short_qwen_codec.py'),
            export={'status': 'diagnostic_completed', 'config': {'validateFloatExport': True,
                'validationAtol': .0001}}, trainedComponents=['D02.2.text'])
        with self.assertRaisesRegex(ValueError, 'trained_model_missing_strict_validation'):
            verified_manifest(self.model, MODEL_SCHEMA)
        self.bridge.model = json.loads(self.model.read_text())
        with self.assertRaisesRegex(ValueError, 'trained_model_missing_strict_validation'):
            WebGPUProvider(self.bridge, binding={}).identity
        value = self.bridge.request('D02.2.text', {'world': 'complete fixture'}, {})
        self.assertEqual(value.status, 'incomplete')
        self.assertIn('trained_model_missing_strict_validation', value.reason)
        self.assertFalse(self.bridge.jobs)

    def test_registration_does_not_publish_unvalidated_trained_assets(self):
        script = BASE / 'short_webgpu/prepare.py'
        spec = importlib.util.spec_from_file_location('webgpu_prepare_fixture', script)
        prepare = importlib.util.module_from_spec(spec); spec.loader.exec_module(prepare)
        directory = Path(self.temp.name) / 'model'
        (directory / 'config.json').write_text(json.dumps({'model_type': 'qwen3',
            'max_position_embeddings': 1024, 'eos_token_id': 99}))
        (directory / 'generation_config.json').write_text('{"eos_token_id":99}')
        (directory / 'tokenizer_config.json').write_text('{"chat_template":"explicit fixture"}')
        (directory / 'special_tokens_map.json').write_text('{}')
        output = Path(self.temp.name) / 'must-not-publish.json'
        with self.assertRaisesRegex(ValueError, 'trained_model_missing_strict_validation'):
            prepare.register_local(directory, provenance={'sourceModel': 'fixture',
                'capability': 'explicit_engineering_fixture', 'trainingSteps': 8,
                'codec': webgpu_module.CODEC, 'codecSha256': sha256_file(BASE / 'short_qwen_codec.py')}, out=output)
        self.assertFalse(output.exists())

    def test_strict_validation_proof_requires_all_checks_and_exact_assets(self):
        self.rewrite_fixture_provenance(trainingSteps=8, codec=webgpu_module.CODEC,
            codecSha256=sha256_file(BASE / 'short_qwen_codec.py'))
        _, proof = self.strict_proof_fixture()
        self.assertEqual(verified_manifest(self.model, MODEL_SCHEMA)['provenance']['strictValidation']['status'], 'passed')
        mutations = [
            ('strict_validation_proof_claim_mismatch', lambda p: p.update(status='failed')),
            ('strict_validation_check_not_passed', lambda p: p['checks'][0].update(valuesClose=False, maxAbsError=.00082)),
            ('strict_validation_check_not_passed', lambda p: p['checks'][0].update(finite=1)),
            ('strict_validation_check_threshold_mismatch', lambda p: p['checks'][0].update(atol=.001)),
            ('strict_validation_check_threshold_mismatch', lambda p: p['checks'][0].update(rtol=.01)),
            ('strict_validation_invalid_observation', lambda p: p['checks'][0].update(maxAbsError=True)),
            ('strict_validation_output_coverage_missing', lambda p: p.update(checks=[])),
            ('strict_validation_output_coverage_mismatch', lambda p: p['checks'].pop()),
            ('strict_validation_output_coverage_mismatch', lambda p: p['checks'].append(copy.deepcopy(p['checks'][0]))),
            ('strict_validation_asset_binding_mismatch', lambda p: p['finalAssets'][0].update(sha256='0' * 64)),
            ('strict_validation_asset_binding_mismatch', lambda p: p['finalAssets'].pop()),
            ('strict_validation_training_source_mismatch', lambda p: p.update(sourceTrainingPlanSha256='0' * 64)),
            ('strict_validation_codec_mismatch', lambda p: p.update(codecSha256='0' * 64)),
            ('strict_validation_export_plan_mismatch', lambda p: p.update(planSha256='0' * 64)),
        ]
        for reason, mutate in mutations:
            with self.subTest(reason=reason):
                candidate = copy.deepcopy(proof); mutate(candidate)
                self.write_strict_proof_fixture(candidate)
                with self.assertRaisesRegex(ValueError, reason):
                    verified_manifest(self.model, MODEL_SCHEMA)
        self.write_strict_proof_fixture(proof)
        (Path(self.temp.name) / 'strict-proof.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'strict_validation_evidence_mismatch:proof'):
            verified_manifest(self.model, MODEL_SCHEMA)
        self.write_strict_proof_fixture(proof)
        (Path(self.temp.name) / 'export-plan.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'strict_validation_evidence_mismatch:export_plan'):
            verified_manifest(self.model, MODEL_SCHEMA)

    def test_zero_step_base_is_explicit_diagnostic_and_boolean_training_steps_are_rejected(self):
        self.rewrite_fixture_provenance(trainingSteps=0, codec='old-base-note', codecSha256='old-base-note',
                                       trainedComponents=[])
        self.bridge.model = verified_manifest(self.model, MODEL_SCHEMA)
        identity = WebGPUProvider(self.bridge, binding={'v': 1}).identity
        self.assertEqual(identity['qualification'], 'base_zero_shot')
        self.assertEqual(identity['trainedComponents'], [])
        self.assertIsNone(identity['trainingCodec'])
        self.rewrite_fixture_provenance(trainingSteps=True)
        with self.assertRaisesRegex(ValueError, 'invalid_training_step_identity'):
            verified_manifest(self.model, MODEL_SCHEMA)

    def test_zero_step_nonempty_training_claim_is_rejected_not_silently_cleared(self):
        for claimed in (['D02.2.text'], ['D08.1.amount'], 'D02.2.text'):
            self.rewrite_fixture_provenance(trainingSteps=0, trainedComponents=claimed)
            with self.assertRaisesRegex(ValueError, 'zero_step_model_cannot_claim_trained_components'):
                verified_manifest(self.model, MODEL_SCHEMA)
        self.rewrite_fixture_provenance(trainingSteps=0, trainedComponents=[])
        self.assertEqual(webgpu_module.validate_model_qualification(verified_manifest(self.model, MODEL_SCHEMA)), 0)

    def test_complete_output_preserves_exact_text_and_full_payload(self):
        self.claim(); thread, answers = self.call_async()
        job = self.bridge.poll('browser')['job']
        self.assertEqual(json.loads(job['inputJson'])['world'], {'name': 'full'})
        self.bridge.submit('browser', response(job)); thread.join()
        self.assertEqual(answers[0].value, '  试着用钳子松开螺母。\n')

    def test_off_is_opt_in_and_requires_same_input_session_calibration(self):
        self.claim()
        value = self.bridge.request('D02.2.text', {}, {'version': 1}, profiling_mode='off')
        self.assertIn('not_registered', value.reason)
        self.bridge.allow_profiling_comparison = True
        value = self.bridge.request('D02.2.text', {}, {'version': 1}, profiling_mode='off')
        self.assertIn('missing_same_input', value.reason)
        thread, answers = self.call_async()
        on = self.bridge.poll('browser')['job']; self.bridge.submit('browser', response(on)); thread.join()
        self.assertEqual(answers[0].status, 'result')
        thread, answers = self.call_async(profiling_mode='off')
        off = self.bridge.poll('browser')['job']
        self.assertEqual(off['calibration']['requestId'], on['requestId'])
        self.assertEqual(off['placementPolicySha256'], digest(profiling_policy('off')))
        reply = response(off)
        reply['gpuEvidence'] = {k: off[k] for k in ('requestId', 'generation', 'bindingSha256',
            'inputSha256', 'modelIdentity', 'placementPolicySha256')}
        reply['gpuEvidence'].update(source='same_session_same_input_prior_gpu_calibration_v1',
            calibration=off['calibration'], perRequestGpuProof=False, kernelCount=None,
            totalKernelDurationNs=None, cpuNodeCount=None, cpuNodeDurationMs=None,
            unexpectedProfileKernelCount=0)
        changed = copy.deepcopy(reply); changed['deviceIdentity']['deviceSessionId'] = 'other-device'
        self.assertEqual(validate_response(off, changed, self.bridge.model).status, 'incomplete')
        fabricated = copy.deepcopy(reply); fabricated['gpuEvidence']['kernelCount'] = 0
        self.assertEqual(validate_response(off, fabricated, self.bridge.model).status, 'incomplete')
        self.bridge.submit('browser', reply); thread.join()
        self.assertEqual(answers[0].status, 'result')
        self.assertFalse(reply['gpuEvidence']['perRequestGpuProof'])
        changed_timeout = self.bridge.request('D02.2.text', {'world': {'name': 'full'}, 'fragments': []},
            {'version': 1}, timeout_ms=120000, max_input_tokens=128, max_new_tokens=32, profiling_mode='off')
        self.assertIn('missing_same_input', changed_timeout.reason)
        changed_input = self.bridge.request('D02.2.text', {'world': {'name': 'changed'}},
            {'version': 1}, max_input_tokens=128, max_new_tokens=32, profiling_mode='off')
        self.assertIn('missing_same_input', changed_input.reason)
        self.bridge.cancel()
        self.assertFalse(self.bridge.calibrations)

    def test_identity_and_completion_counterexamples(self):
        self.claim(); thread, answers = self.call_async()
        job = self.bridge.poll('browser')['job']; good = response(job)
        patches = [{'generation': True}, {'modelIdentity': 'stale'}, {'bindingSha256': 'old'},
                   {'eosReached': False}, {'rawTokenIds': [1, 2]}, {'rawTokenIds': [99, 8, 99]},
                   {'rawTokenIds': [True, 99]}, {'enableThinking': True}, {'rawText': '<think>补写</think>答案'},
                   {'deviceIdentity': {'executionProvider': 'wasm', 'dtype': 'q4f16', 'lost': False}},
                   {'deviceIdentity': {'executionProvider': 'webgpu', 'dtype': 'q4f16', 'lost': True}}]
        for patch in patches:
            with self.subTest(patch=patch):
                self.assertEqual(validate_response(job, {**good, **patch}, self.bridge.model).status, 'incomplete')
        self.bridge.submit('browser', good); thread.join()

    def test_webgpu_option_without_weight_kernel_proof_is_incomplete(self):
        self.claim(); thread, answers = self.call_async()
        job = self.bridge.poll('browser')['job']; good = response(job)
        mutations = [None,
            {**good['gpuEvidence'], 'positiveWeightKernelCount': 0},
            {**good['gpuEvidence'], 'requestId': 'other-request'},
            {**good['gpuEvidence'], 'cpuNodeCount': 0},
            {**good['gpuEvidence'], 'invalidCount': True},
            {**good['gpuEvidence'], 'kernelCount': 0},
            {**good['gpuEvidence'], 'weightWitnesses': [{'version': 1, 'kernelType': 'Cast', 'kernelName': 'not-weight',
                'programName': 'Cast', 'startTime': 10, 'endTime': 20}]},
            {**good['gpuEvidence'], 'weightWitnesses': [{**good['gpuEvidence']['weightWitnesses'][0], 'endTime': 10}]},
        ]
        for evidence in mutations:
            with self.subTest(evidence=evidence):
                self.assertEqual(validate_response(job, {**good, 'gpuEvidence': evidence}, self.bridge.model).status, 'incomplete')
        self.bridge.submit('browser', good); thread.join()

    def test_timeout_and_late_output_kept_but_not_accepted(self):
        self.claim(); thread, answers = self.call_async(timeout_ms=20)
        job = self.bridge.poll('browser')['job']; thread.join()
        self.assertEqual(answers[0].reason, 'webgpu:timeout')
        receipt = self.bridge.submit('browser', response(job))
        self.assertFalse(receipt['accepted'])
        self.assertTrue(any(e.get('response', {}).get('rawTokenIds') == [8, 99] for e in self.bridge.events))

    def test_cancel_generation_and_foreign_browser_rejected(self):
        self.claim(); thread, answers = self.call_async()
        job = self.bridge.poll('browser')['job']
        self.assertFalse(self.bridge.submit('other', response(job))['accepted'])
        self.bridge.cancel(); thread.join()
        self.assertEqual(answers[0].reason, 'webgpu:cancelled')
        self.assertFalse(self.bridge.submit('browser', response(job))['accepted'])

    def test_binding_change_and_model_session_cancellation_callbacks(self):
        self.claim(); binding = {'version': 1}
        thread, answers = self.call_async(binding_now=lambda: binding)
        self.bridge.poll('browser'); binding['version'] = 2; thread.join()
        self.assertIn('binding_changed', answers[0].reason)

    def test_missing_browser_does_not_return_empty_or_skip(self):
        thread, answers = self.call_async(timeout_ms=10); thread.join()
        self.assertEqual(answers[0].status, 'incomplete')
        self.assertIsNone(answers[0].value)

    def test_registered_asset_corruption_rejected(self):
        (Path(self.temp.name) / 'model/config.json').write_text('modified')
        with self.assertRaisesRegex(ValueError, 'asset_bytes_mismatch'):
            verified_manifest(self.model, MODEL_SCHEMA)

    def test_base_identity_does_not_claim_trained_tasks(self):
        provider = WebGPUProvider(self.bridge, binding={'version': 1})
        self.assertEqual(provider.identity['qualification'], 'base_zero_shot')
        self.assertEqual(provider.identity['trainedComponents'], [])
        self.assertEqual(provider.identity['precision'], 'q4f16')

    def test_finished_jobs_release_full_payload_and_retention_is_bounded(self):
        self.claim(); thread, answers = self.call_async()
        job = self.bridge.poll('browser')['job']
        self.bridge.submit('browser', response(job)); thread.join()
        self.assertNotIn('inputJson', self.bridge.jobs[job['requestId']]['request'])
        self.assertNotIn('response', self.bridge.jobs[job['requestId']])
        for i in range(200):
            self.bridge.record('fixture', {'index': i})
        self.assertEqual(len(self.bridge.events), 128)

    def test_late_prior_request_cannot_enter_new_case_forward_journal(self):
        self.claim(); scoped = []; result_box = []
        provider = WebGPUProvider(self.bridge, binding={'version': 1}, timeout_ms=500)
        provider.checkpoint = lambda kind, event: scoped.append((kind, event))
        thread = threading.Thread(target=lambda: result_box.append(provider('D02.2.text', {'world': {}})))
        thread.start()
        while not self.bridge.jobs:
            time.sleep(.001)
        job = self.bridge.poll('browser')['job']
        old = {'kind': 'generator_forward_settled', 'requestId': 'old-case', 'generation': 0,
               'bindingSha256': job['bindingSha256'], 'inputSha256': job['inputSha256'], 'elapsedMs': 999}
        self.bridge.browser_event({'clientId': 'browser', 'event': old})
        good = {**old, 'requestId': job['requestId'], 'elapsedMs': 10}
        self.bridge.browser_event({'clientId': 'browser', 'event': good})
        self.bridge.submit('browser', response(job)); thread.join()
        forwards = [e for k, e in scoped if k == 'generator_forward_settled']
        self.assertEqual(len(forwards), 1)
        self.assertEqual(forwards[0]['elapsedMs'], 10)

    def test_parity_report_cannot_claim_success_for_wrong_token(self):
        self.claim()
        self.bridge.parity = {'cases': [{'exampleId': 'case', 'expectedInputIds': [1, 2]}]}
        self.bridge.parity_sha256 = 'frozen-parity'
        self.bridge.browser_event({'clientId': 'browser', 'event': {
            'kind': 'tokenizer_parity_finished', 'sourceSha256': 'frozen-parity',
            'cases': [{'exampleId': 'case', 'actualInputIds': [1, 3], 'exactMatch': True}]}})
        self.assertEqual(self.bridge.readiness['tokenizerParityPassed'], False)
        self.assertEqual(self.bridge.wait_ready(.001)['reason'], 'tokenizer_parity_mismatch')

    def test_loaded_ready_requires_valid_worker_and_model_events(self):
        self.claim()
        self.assertEqual(self.bridge.wait_ready(.001)['status'], 'incomplete')
        self.bridge.browser_event({'clientId': 'browser', 'event': {'kind': 'webgpu_worker_bound',
            'modelIdentity': self.bridge.model['identity'], 'runtimeIdentity': self.bridge.runtime['identity']}})
        self.assertEqual(self.bridge.wait_ready(.001, require_model=False)['status'], 'ready')
        self.bridge.browser_event({'clientId': 'browser', 'event': {'kind': 'request_model_load',
            'modelIdentity': self.bridge.model['identity'], 'deviceIdentity': device_fixture(digest(PLACEMENT_POLICY)), 'elapsedMs': 20}})
        self.assertEqual(self.bridge.wait_ready(.001)['status'], 'ready')
        self.bridge.browser_event({'clientId': 'browser', 'event': {'kind': 'webgpu_device_lost', 'reason': 'lost'}})
        self.assertEqual(self.bridge.wait_ready(.001)['status'], 'incomplete')

    def test_probe_device_cannot_claim_model_readiness(self):
        self.claim()
        device = device_fixture(digest(PLACEMENT_POLICY))
        device.pop('runtimeDeviceVerified')
        with self.assertRaisesRegex(ValueError, 'actual_runtime_device_unverified'):
            self.bridge.browser_event({'clientId': 'browser', 'event': {'kind': 'request_model_load',
                'modelIdentity': self.bridge.model['identity'], 'deviceIdentity': device, 'elapsedMs': 20}})
        self.assertFalse(self.bridge.readiness['modelLoaded'])

    def test_local_http_token_host_and_asset_allowlist(self):
        url = self.bridge.start(); origin = url.split('/#')[0]
        with urllib.request.urlopen(origin + '/') as r:
            self.assertIn(b'Qwen3', r.read())
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(origin + '/api/status')
        request = urllib.request.Request(origin + '/api/status', headers={'X-Jity-Token': self.bridge.token})
        with urllib.request.urlopen(request) as r:
            self.assertFalse(json.load(r)['connected'])
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(origin + '/../../AGENTS.md')
        request = urllib.request.Request(origin + '/', headers={'Host': 'untrusted.example'})
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(request)


if __name__ == '__main__':
    unittest.main()
