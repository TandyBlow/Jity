"""Local Qwen3 browser bridge, injectable as a ModelSession provider.

This is a D experiment transport, not a production A/B/C endpoint. It serves
only frozen local assets. Browser generation is never replaced by Python text.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import mimetypes
import secrets
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

from lab import canonical_bytes, sha256_file
from run_pilot import digest
from short_contracts import ModelIdentity, incomplete, result
from short_qwen_codec import prompt_packet, CODEC

BASE = Path(__file__).resolve().parent
PAGE = BASE / 'short_webgpu'
MODEL_SCHEMA = 'jity-d-webgpu-model-v1'
RUNTIME_SCHEMA = 'jity-d-webgpu-runtime-v1'
STRICT_VALIDATION_SCHEMA = 'jity-qwen-onnx-strict-validation-v1'
PLACEMENT_POLICY = {
    'id': 'webgpu_preferred_cpu_nodes_allowed_profiled_v1',
    'executionProviders': ['webgpu'], 'disableCpuEpFallback': '0',
    'requiredDeviceFeatures': ['shader-f16', 'timestamp-query'],
    'profilingMode': 'default', 'profilingScope': 'every_real_generate',
    'kernelBatchSize': 64, 'requiredPositiveGpuKernelType': 'MatMulNBits',
    'drain': 'queue_onSubmittedWorkDone_before_and_after_generate',
    'cpuPlacementMeasured': False, 'profilingCostIncludedInWall': True,
}
OFF_COMPARISON_POLICY = {**PLACEMENT_POLICY,
    'id': 'webgpu_cpu_nodes_allowed_profiling_off_comparison_v1',
    'profilingMode': 'off', 'profilingScope': 'not_measured_this_request',
    'requiredPositiveGpuKernelType': None,
    'requiredCalibration': 'prior_successful_audit_same_input_binding_device_session',
}
CALIBRATION_FIELDS = ('generation', 'component', 'inputSha256', 'messagesSha256', 'bindingSha256',
    'codec', 'modelIdentity', 'runtimeIdentity', 'codeIdentity', 'maxInputTokens', 'maxNewTokens', 'timeoutMs', 'decoding')


def profiling_policy(mode):
    if mode not in ('default', 'off'):
        raise ValueError('invalid_profiling_mode')
    return copy.deepcopy(PLACEMENT_POLICY if mode == 'default' else OFF_COMPARISON_POLICY)


def calibration_scope(request):
    return {k: request[k] for k in CALIBRATION_FIELDS}


def validate_training_provenance(provenance):
    """A current prompt label must not requalify weights trained on old text."""
    if not isinstance(provenance, dict):
        raise ValueError('missing_model_provenance')
    steps = provenance.get('trainingSteps', 0)
    if type(steps) is not int or steps < 0:
        raise ValueError('invalid_training_step_identity')
    if steps == 0 and provenance.get('trainedComponents'):
        raise ValueError('zero_step_model_cannot_claim_trained_components')
    if steps > 0:
        if provenance.get('codec') != CODEC:
            raise ValueError('trained_model_codec_version_mismatch')
        if provenance.get('codecSha256') != sha256_file(BASE / 'short_qwen_codec.py'):
            raise ValueError('trained_model_codec_source_mismatch')
    return steps


def _evidence_json(path, expected_sha, label):
    if not isinstance(path, str) or not path or not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError('invalid_strict_validation_reference:' + label)
    file = Path(path)
    if not file.is_absolute():
        file = BASE.parents[1] / file
    try:
        raw = file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_sha:
            raise ValueError('strict_validation_evidence_mismatch:' + label)
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError('strict_validation_evidence_unavailable:' + label) from error
    if not isinstance(value, dict):
        raise ValueError('invalid_strict_validation_evidence:' + label)
    return value


def validate_model_qualification(model):
    """Bind trained assets to explicit strict float-export evidence.

    This does not certify quantized-model numerics, browser quality, or semantics.
    The exporter owns actual comparisons; this boundary verifies their complete,
    immutable evidence and its identity against the assets we will serve.
    """
    provenance = model.get('provenance')
    steps = validate_training_provenance(provenance)
    if not steps:
        return steps
    validation = provenance.get('strictValidation')
    if not isinstance(validation, dict):
        raise ValueError('trained_model_missing_strict_validation')
    for key, expected in (('schema', STRICT_VALIDATION_SCHEMA), ('status', 'passed'),
                          ('scope', 'float_export_numerical')):
        if validation.get(key) != expected:
            raise ValueError('trained_model_strict_validation_not_passed:' + key)
    proof = _evidence_json(validation.get('proofPath'), validation.get('proofSha256'), 'proof')
    for key in ('schema', 'status', 'scope'):
        if proof.get(key) != validation[key]:
            raise ValueError('strict_validation_proof_claim_mismatch:' + key)
    export = provenance.get('export', {})
    if not isinstance(export, dict) or proof.get('planSha256') != export.get('planSha256'):
        raise ValueError('strict_validation_export_plan_mismatch')
    plan = _evidence_json(export.get('planPath'), export.get('planSha256'), 'export_plan')
    source = plan.get('model', {})
    if (not isinstance(source, dict) or proof.get('sourceTrainingPlanSha256') != source.get('planSha256')
            or source.get('runId') != provenance.get('trainingRunId')):
        raise ValueError('strict_validation_training_source_mismatch')
    _evidence_json(source.get('planPath'), source.get('planSha256'), 'training_plan')
    source_code = source.get('codeSha256', {})
    if (any(proof.get(key) != provenance.get(key) for key in ('codec', 'codecSha256'))
            or source.get('codec') != provenance['codec'] or not isinstance(source_code, dict)
            or source_code.get('short_qwen_codec.py') != provenance['codecSha256']):
        raise ValueError('strict_validation_codec_mismatch')
    graph = proof.get('validatedFloatGraph')
    if (not isinstance(graph, dict) or not isinstance(graph.get('path'), str) or not graph['path']
            or not isinstance(graph.get('sha256'), str) or len(graph['sha256']) != 64
            or type(graph.get('bytes')) is not int or graph['bytes'] <= 0):
        raise ValueError('strict_validation_float_graph_identity_missing')
    assets = proof.get('finalAssets')
    if not isinstance(assets, list) or not assets:
        raise ValueError('strict_validation_asset_binding_missing')
    normalized = []
    for row in assets:
        if (not isinstance(row, dict) or not isinstance(row.get('path'), str)
                or type(row.get('bytes')) is not int or row['bytes'] <= 0
                or not isinstance(row.get('sha256'), str) or len(row['sha256']) != 64):
            raise ValueError('strict_validation_invalid_asset_binding')
        normalized.append({'path': row['path'], 'size': row['bytes'], 'sha256': row['sha256']})
    actual = [{key: row.get(key) for key in ('path', 'size', 'sha256')} for row in model.get('files', [])]
    if (len({row['path'] for row in normalized}) != len(normalized)
            or digest(sorted(normalized, key=lambda r: r['path'])) != digest(sorted(actual, key=lambda r: r['path']))):
        raise ValueError('strict_validation_asset_binding_mismatch')
    checks, expected_names = proof.get('checks'), proof.get('expectedOutputNames')
    if (not isinstance(checks, list) or not checks or not isinstance(expected_names, list) or not expected_names
            or any(not isinstance(name, str) or not name for name in expected_names)
            or len(set(expected_names)) != len(expected_names)):
        raise ValueError('strict_validation_output_coverage_missing')
    config = plan.get('config', {})
    if not isinstance(config, dict):
        raise ValueError('strict_validation_export_configuration_mismatch')
    atol, rtol = config.get('validationAtol'), config.get('validationRtol', 1e-5)
    for value, ceiling in ((atol, 1e-4), (rtol, 1e-5)):
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= ceiling:
            raise ValueError('strict_validation_threshold_not_registered')
    if config.get('validateFloatExport') is not True or digest(config) != digest(export.get('config')):
        raise ValueError('strict_validation_export_configuration_mismatch')
    names = []
    for row in checks:
        if not isinstance(row, dict) or not isinstance(row.get('name'), str) or not row['name']:
            raise ValueError('strict_validation_invalid_check')
        names.append(row.get('name'))
        if any(row.get(key) is not True for key in ('finite', 'shapesEqual', 'valuesClose')):
            raise ValueError('strict_validation_check_not_passed')
        if (type(row.get('atol')) not in (int, float) or type(row.get('rtol')) not in (int, float)
                or row['atol'] != atol or row['rtol'] != rtol):
            raise ValueError('strict_validation_check_threshold_mismatch')
        observed = row.get('maxAbsError')
        if type(observed) not in (int, float) or not math.isfinite(observed) or observed < 0:
            raise ValueError('strict_validation_invalid_observation')
        # np.allclose includes a relative term. maxAbsError alone is not its
        # pass criterion and must not silently replace the frozen comparison.
    if sorted(names) != sorted(expected_names):
        raise ValueError('strict_validation_output_coverage_mismatch')
    return steps


def verified_manifest(path, schema):
    value = json.loads(Path(path).read_text())
    if value.get('schema') != schema:
        raise ValueError('invalid_asset_manifest_schema')
    if value.get('identity') != digest({k: v for k, v in value.items() if k not in ('identity', 'directory')}):
        raise ValueError('asset_manifest_identity_mismatch')
    if schema == MODEL_SCHEMA:
        validate_model_qualification(value)
    directory = Path(value['directory']).resolve()
    if not directory.is_dir() or not value.get('files'):
        raise ValueError('missing_local_assets')
    seen = set()
    for row in value['files']:
        name = row['path']
        file = (directory / name).resolve()
        if name in seen or not file.is_relative_to(directory) or file == directory:
            raise ValueError('invalid_asset_path')
        seen.add(name)
        if file.stat().st_size != row['size'] or sha256_file(file) != row['sha256']:
            raise ValueError('asset_bytes_mismatch:' + name)
    if schema == MODEL_SCHEMA:
        if value.get('modelType') != 'qwen3' or value.get('dtype') != 'q4f16' or value.get('device') != 'webgpu':
            raise ValueError('unsupported_model_format')
        required = {'config.json', 'generation_config.json', 'tokenizer.json',
                    'tokenizer_config.json', 'onnx/model_q4f16.onnx'}
        if not required <= seen:
            raise ValueError('incomplete_model_assets')
        if type(value.get('maxContextTokens')) is not int or value['maxContextTokens'] < 1:
            raise ValueError('invalid_model_context_limit')
    elif value.get('version') != '3.8.1':
        raise ValueError('unregistered_runtime_version')
    return value


class BrowserBridge:
    """One browser worker, sequential jobs, generation-scoped late isolation.

    checkpoint receives full input/output events. Caller should use the existing
    append-only experiment journal; no answer is lost when a deadline rejects it.
    """
    def __init__(self, model_manifest, runtime_manifest, *, checkpoint=None, tokenizer_cases=None,
                 retain_events=False, require_tokenizer_parity=True, allow_profiling_comparison=False):
        self.model = verified_manifest(model_manifest, MODEL_SCHEMA)
        self.runtime = verified_manifest(runtime_manifest, RUNTIME_SCHEMA)
        self.checkpoint = checkpoint or (lambda *_: None)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.jobs, self.events, self.client, self.browser = {}, deque(maxlen=128), None, None
        self.retain_events = retain_events
        self.allow_profiling_comparison = allow_profiling_comparison is True
        self.calibrations = {}
        self.readiness = {'connected': False, 'workerBound': False, 'modelLoaded': False,
                          'deviceIdentity': None, 'initializationElapsedMs': None,
                          'tokenizerParityPassed': None, 'error': None}
        codec_version = CODEC.rsplit('-', 1)[-1]
        if not codec_version.startswith('v') or not codec_version[1:].isdigit():
            raise ValueError('codec_has_no_registered_parity_version')
        parity_path = Path(tokenizer_cases) if tokenizer_cases else BASE.parents[1] / (
            'artifacts/world-components-logic/qwen-short/tokenizer-parity-cases-' + codec_version + '.json')
        self.parity = json.loads(parity_path.read_text()) if parity_path.exists() else None
        if require_tokenizer_parity and self.parity is None:
            raise ValueError('missing_tokenizer_parity_material')
        self.parity_sha256 = sha256_file(parity_path) if self.parity else None
        if self.parity:
            if (self.parity.get('schema') != 'jity-qwen-tokenizer-parity-v1' or self.parity.get('codec') != CODEC
                    or self.parity.get('codecSha256') != sha256_file(BASE / 'short_qwen_codec.py')):
                raise ValueError('tokenizer_parity_codec_identity_mismatch')
            for case in self.parity['cases']:
                packet = prompt_packet(case['component'], case['payload'])
                if packet['messages'] != case['messages'] or packet['inputSha256'] != case['inputSha256'] or packet['messagesSha256'] != case['messagesSha256']:
                    raise ValueError('tokenizer_parity_input_identity_mismatch')
        self.generation, self.stopped = 0, False
        self.server = None
        self.assets = {}
        for prefix, manifest in (('/model/qwen/', self.model), ('/runtime/', self.runtime)):
            for row in manifest['files']:
                path = (Path(manifest['directory']) / row['path']).resolve()
                self.assets[prefix + row['path']] = (path, row['sha256'], path.stat().st_mtime_ns, row['size'])
        for name in ('index.html', 'page.mjs', 'worker.mjs', 'core.mjs'):
            path = PAGE / name
            if path.exists():
                self.assets['/' if name == 'index.html' else '/' + name] = (path, sha256_file(path), path.stat().st_mtime_ns, path.stat().st_size)
        self.code_identity = digest({k: v[1] for k, v in self.assets.items() if k in ('/', '/page.mjs', '/worker.mjs', '/core.mjs')})

    def record(self, kind, value):
        event = {'event': kind, 'wallTimeMs': time.time() * 1000, **copy.deepcopy(value)}
        with self.lock:
            self.events.append(event if self.retain_events else {
                'eventKind': kind, 'wallTimeMs': event['wallTimeMs'],
                'requestId': event.get('requestId', event.get('request', {}).get('requestId'))})
        self.checkpoint(kind, event)

    def browser_event(self, data):
        with self.condition:
            if data['clientId'] != self.client:
                raise ValueError('browser_owner_mismatch')
            event = data['event']
            if event.get('kind') == 'webgpu_worker_bound':
                if event.get('modelIdentity') != self.model['identity'] or event.get('runtimeIdentity') != self.runtime['identity']:
                    raise ValueError('worker_asset_identity_mismatch')
                self.readiness['workerBound'] = True
                self.calibrations.clear()
            if event.get('kind') == 'request_model_load':
                if event.get('modelIdentity') != self.model['identity'] or event.get('deviceIdentity', {}).get('executionProvider') != 'webgpu':
                    raise ValueError('loaded_model_identity_mismatch')
                validate_runtime_device(event['deviceIdentity'], digest(PLACEMENT_POLICY))
                self.readiness.update(modelLoaded=True, deviceIdentity=copy.deepcopy(event['deviceIdentity']),
                                      initializationElapsedMs=event['elapsedMs'], error=None)
            if event.get('kind') == 'tokenizer_parity_finished':
                rows = event.get('cases', [])
                expected = {c['exampleId']: c['expectedInputIds'] for c in self.parity['cases']} if self.parity else {}
                actual = {c['exampleId']: c['actualInputIds'] for c in rows}
                passed = (bool(expected) and event.get('sourceSha256') == self.parity_sha256
                          and len(rows) == len(expected) and digest(actual) == digest(expected))
                self.readiness['tokenizerParityPassed'] = passed
                if not passed:
                    self.readiness['error'] = 'tokenizer_parity_mismatch'
            if event.get('kind') in ('webgpu_device_lost', 'webgpu_load_failed', 'webgpu_worker_terminated'):
                self.readiness.update(modelLoaded=False, error=event.get('reason', event['kind']))
            self.record('webgpu_browser_event', data)
            self.condition.notify_all()

    def wait_ready(self, timeout_seconds=120, *, require_model=True):
        deadline = time.monotonic() + timeout_seconds
        with self.condition:
            while True:
                state = copy.deepcopy(self.readiness)
                if state['error']:
                    return {'status': 'incomplete', 'reason': state['error'], **state}
                if (state['connected'] and state['workerBound'] and (not require_model or
                        (state['modelLoaded'] and (self.parity is None or state['tokenizerParityPassed'] is True)))):
                    return {'status': 'ready', **state}
                if self.stopped or time.monotonic() >= deadline:
                    return {'status': 'incomplete', 'reason': 'bridge_stopped' if self.stopped else 'browser_ready_timeout', **state}
                self.condition.wait(min(0.1, max(0.001, deadline - time.monotonic())))

    def configuration(self):
        return {'modelIdentity': self.model['identity'], 'runtimeIdentity': self.runtime['identity'],
                'codeIdentity': self.code_identity, 'modelPath': 'qwen', 'dtype': 'q4f16',
                'device': 'webgpu', 'maxContextTokens': self.model['maxContextTokens'],
                'eosTokenIds': self.model['eosTokenIds'], 'generation': self.generation,
                'initializationTimeoutMs': 120000,
                'placementPolicy': copy.deepcopy(PLACEMENT_POLICY),
                'placementPolicySha256': digest(PLACEMENT_POLICY),
                'allowProfilingComparison': self.allow_profiling_comparison,
                'placementPolicies': {mode: {'policy': profiling_policy(mode), 'sha256': digest(profiling_policy(mode))}
                    for mode in (('default', 'off') if self.allow_profiling_comparison else ('default',))},
                'tokenizerParitySha256': self.parity_sha256,
                'source': copy.deepcopy(self.model['provenance'])}

    def claim(self, client, browser):
        with self.condition:
            if not isinstance(client, str) or not client or not isinstance(browser, dict):
                raise ValueError('missing_browser_identity')
            if self.client is not None and client != self.client:
                raise ValueError('another_browser_owns_bridge')
            self.client, self.browser = client, copy.deepcopy(browser)
            self.readiness['connected'] = True
            self.record('webgpu_browser_connected', {'clientId': client, 'browser': browser})
            self.condition.notify_all()
            return self.configuration()

    def poll(self, client):
        with self.condition:
            if client != self.client or self.stopped:
                raise ValueError('browser_owner_mismatch_or_stopped')
            controls = [{'requestId': k, 'generation': v['request']['generation'], 'type': 'cancel'}
                        for k, v in self.jobs.items() if v['state'] == 'cancelled' and not v.get('cancelSent')]
            for c in controls:
                self.jobs[c['requestId']]['cancelSent'] = True
            job = next((v for v in self.jobs.values() if v['state'] == 'queued'), None)
            if job:
                job['state'] = 'claimed'
                job['client'] = client
            return {'controls': controls, 'job': copy.deepcopy(job['request']) if job else None,
                    'generation': self.generation}

    def submit(self, client, response):
        # Record before validation so even stale/error/token-bearing output survives.
        self.record('webgpu_browser_response', {'clientId': client, 'response': response})
        with self.condition:
            request_id = response.get('requestId') if isinstance(response, dict) else None
            job = self.jobs.get(request_id)
            if client != self.client or not job or job.get('client') != client:
                return {'accepted': False, 'reason': 'unknown_request_or_browser'}
            if job['state'] != 'claimed' or job['request']['generation'] != self.generation:
                return {'accepted': False, 'reason': 'late_or_cancelled_output'}
            job['response'], job['state'] = copy.deepcopy(response), 'returned'
            self.condition.notify_all()
            return {'accepted': True}

    def request(self, component, payload, binding, *, timeout_ms=120000,
                max_input_tokens=32768, max_new_tokens=128, cancelled=None, binding_now=None,
                profiling_mode='default'):
        try:
            validate_model_qualification(self.model)
        except ValueError as error:
            return incomplete('webgpu:' + str(error))
        if profiling_mode not in ('default', 'off') or (profiling_mode == 'off' and not self.allow_profiling_comparison):
            return incomplete('webgpu:profiling_comparison_not_registered')
        if (type(timeout_ms) is not int or not 0 < timeout_ms <= 2 ** 53 - 1
                or type(max_input_tokens) is not int or max_input_tokens < 1
                or type(max_new_tokens) is not int or max_new_tokens < 1):
            return incomplete('webgpu:invalid_resource_policy')
        start = time.perf_counter()
        try:
            packet = prompt_packet(component, payload)
            payload_json = canonical_bytes(payload).decode()
            messages_json = canonical_bytes(packet['messages']).decode()
            binding_json = canonical_bytes(binding).decode()
        except Exception as error:
            return incomplete('webgpu:prompt:' + str(error))
        with self.condition:
            if self.stopped:
                return incomplete('webgpu:bridge_stopped')
            if any(v['state'] in ('queued', 'claimed') for v in self.jobs.values()):
                return incomplete('webgpu:concurrent_call_rejected')
            request = {'requestId': uuid.uuid4().hex, 'generation': self.generation,
                       'component': component, 'inputJson': payload_json, 'inputSha256': packet['inputSha256'],
                       'messagesJson': messages_json, 'messagesSha256': packet['messagesSha256'],
                       'bindingJson': binding_json, 'bindingSha256': digest(binding), 'codec': CODEC,
                       'enableThinking': False, 'modelIdentity': self.model['identity'],
                       'runtimeIdentity': self.runtime['identity'], 'codeIdentity': self.code_identity,
                       'placementPolicySha256': digest(profiling_policy(profiling_mode)),
                       'profilingMode': profiling_mode, 'calibration': None,
                       'deadlineUnixMs': time.time() * 1000 + timeout_ms, 'timeoutMs': timeout_ms,
                       'maxInputTokens': max_input_tokens, 'maxNewTokens': max_new_tokens,
                       'decoding': {'do_sample': False, 'num_beams': 1},
                       'contextPolicy': 'complete_input_reject_overlimit_no_truncation'}
            scope_sha = digest(calibration_scope(request))
            if profiling_mode == 'off':
                calibration = self.calibrations.get(scope_sha)
                if not calibration:
                    return incomplete('webgpu:profiling_off_missing_same_input_session_calibration')
                request['calibration'] = copy.deepcopy(calibration)
            request['requestSha256'] = digest(request)
            self.jobs[request['requestId']] = {'request': request, 'state': 'queued'}
            self.record('webgpu_request_started', {'request': request})
            job = self.jobs[request['requestId']]
            while job['state'] not in ('returned', 'cancelled'):
                reason = None
                if cancelled and cancelled():
                    reason = 'cancelled'
                elif binding_now and digest(binding_now()) != request['bindingSha256']:
                    reason = 'binding_changed_during_call'
                elif (time.perf_counter() - start) * 1000 >= timeout_ms:
                    reason = 'timeout'
                if reason:
                    job.update(state='cancelled', reason=reason)
                    break
                self.condition.wait(timeout=min(0.05, max(0.001, timeout_ms / 1000)))
            if job['state'] == 'cancelled':
                answer = incomplete('webgpu:' + job.get('reason', 'cancelled'))
            elif cancelled and cancelled():
                answer = incomplete('webgpu:cancelled')
            elif binding_now and digest(binding_now()) != request['bindingSha256']:
                answer = incomplete('webgpu:binding_changed_during_call')
            elif (time.perf_counter() - start) * 1000 >= timeout_ms:
                answer = incomplete('webgpu:timeout')
            else:
                answer = validate_response(request, job['response'], self.model)
                if answer.status == 'result' and profiling_mode == 'default':
                    self.calibrations[scope_sha] = {
                        'requestId': request['requestId'], 'requestSha256': request['requestSha256'],
                        'scopeSha256': scope_sha,
                        'deviceSessionId': job['response']['deviceIdentity']['deviceSessionId'],
                        'positiveWeightKernelCount': job['response']['gpuEvidence']['positiveWeightKernelCount']}
                    while len(self.calibrations) > 16:
                        del self.calibrations[next(iter(self.calibrations))]
            self.record('webgpu_request_finished', {'requestId': request['requestId'], 'completion': answer.__dict__,
                        'bridgeElapsedMs': (time.perf_counter() - start) * 1000})
            # Keep only finite transport tombstones after the complete raw event
            # has reached the owning journal. A tombstone cannot replay semantics.
            self.jobs[request['requestId']] = {'request': {k: request[k] for k in ('requestId', 'generation')},
                'state': job['state'], 'client': job.get('client'), 'reason': job.get('reason'),
                'cancelSent': job.get('cancelSent', False)}
            if len(self.jobs) > 128:
                for key in list(self.jobs):
                    if len(self.jobs) <= 128:
                        break
                    if self.jobs[key]['state'] not in ('queued', 'claimed'):
                        del self.jobs[key]
            return answer

    def cancel(self, reason='cancelled'):
        with self.condition:
            self.generation += 1
            self.calibrations.clear()
            for job in self.jobs.values():
                if job['state'] in ('queued', 'claimed'):
                    job.update(state='cancelled', reason=reason)
            self.condition.notify_all()
        self.record('webgpu_cancelled', {'reason': reason, 'generation': self.generation})

    def start(self, port=0):
        bridge = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def headers_common(self):
                self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
                self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self'; style-src 'self'")

            def reply(self, status, value):
                data = canonical_bytes(value)
                self.send_response(status); self.headers_common()
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(data))); self.end_headers()
                self.wfile.write(data)

            def allowed(self, api=False):
                host = f'127.0.0.1:{self.server.server_address[1]}'
                if self.headers.get('Host') != host:
                    return False
                origin = self.headers.get('Origin')
                if origin and origin != 'http://' + host:
                    return False
                return not api or secrets.compare_digest(self.headers.get('X-Jity-Token', ''), bridge.token)

            def do_GET(self):
                path = unquote(urlparse(self.path).path)
                if not self.allowed(api=path.startswith('/api/')):
                    return self.reply(403, {'error': 'unauthorized_local_request'})
                if path == '/api/status':
                    return self.reply(200, {'connected': bridge.client is not None, 'browser': bridge.browser,
                        'readiness': bridge.readiness,
                        'configuration': bridge.configuration(), 'jobs': {k: v['state'] for k, v in bridge.jobs.items()}})
                asset = bridge.assets.get(path)
                if asset is None:
                    return self.reply(404, {'error': 'unregistered_asset'})
                file, expected, mtime, size = asset
                stat = file.stat()
                if stat.st_mtime_ns != mtime or stat.st_size != size:
                    return self.reply(409, {'error': 'frozen_asset_changed_restart_with_new_identity'})
                kind = 'text/javascript' if file.suffix in ('.js', '.mjs') else 'application/wasm' if file.suffix == '.wasm' else mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
                self.send_response(200); self.headers_common()
                self.send_header('Content-Type', kind); self.send_header('Content-Length', str(size))
                self.send_header('X-Content-SHA256', expected); self.end_headers()
                with file.open('rb') as stream:
                    while chunk := stream.read(1024 * 1024):
                        self.wfile.write(chunk)
                bridge.record('webgpu_asset_served', {'path': path, 'sha256': expected, 'bytes': size})

            def do_POST(self):
                if not self.allowed(api=True):
                    return self.reply(403, {'error': 'unauthorized_local_request'})
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 64 * 1024 * 1024:
                        raise ValueError('transport_body_overlimit')
                    data = json.loads(self.rfile.read(size))
                    path = urlparse(self.path).path
                    if path == '/api/claim':
                        value = bridge.claim(data['clientId'], data['browser'])
                    elif path == '/api/poll':
                        value = bridge.poll(data['clientId'])
                    elif path == '/api/result':
                        value = bridge.submit(data['clientId'], data['response'])
                    elif path == '/api/event':
                        bridge.browser_event(data)
                        value = {'accepted': True}
                    elif path == '/api/tokenizer-cases':
                        if data['clientId'] != bridge.client or bridge.parity is None:
                            raise ValueError('tokenizer_cases_unavailable')
                        value = {'sourceSha256': bridge.parity_sha256, 'cases': [{
                            'exampleId': c['exampleId'], 'component': c['component'],
                            'messagesJson': canonical_bytes(c['messages']).decode(),
                            'messagesSha256': c['messagesSha256'], 'inputSha256': c['inputSha256'],
                            'expectedInputIds': c['expectedInputIds']} for c in bridge.parity['cases']]}
                    else:
                        return self.reply(404, {'error': 'unknown_endpoint'})
                    self.reply(200, value)
                except (ValueError, KeyError, TypeError) as error:
                    self.reply(400, {'error': str(error)})
        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return f'http://127.0.0.1:{self.server.server_address[1]}/#{self.token}'

    def close(self):
        self.cancel('bridge_stopped')
        self.stopped = True
        if self.server:
            self.server.shutdown(); self.server.server_close()


def validate_runtime_device(device, placement_sha256):
    if (not isinstance(device, dict) or device.get('executionProvider') != 'webgpu'
            or device.get('dtype') != 'q4f16' or device.get('lost') is not False):
        raise ValueError('invalid_or_lost_device')
    if (device.get('bindingSource') != 'pinned_ort_jsep_readonly_environment'
            or device.get('runtimeDeviceVerified') is not True
            or device.get('adapterReferenceVerified') is not True
            or device.get('deviceCreatedBy') != 'onnxruntime'):
        raise ValueError('actual_runtime_device_unverified')
    if (device.get('placementPolicySha256') != placement_sha256
            or device.get('adapterInfo', {}).get('isFallbackAdapter') is not False
            or not {'shader-f16', 'timestamp-query'} <= set(device.get('features', []))):
        raise ValueError('gpu_placement_or_feature_identity_mismatch')


def validate_response(request, response, model):
    """Validate completion evidence, never infer semantic correctness from it."""
    try:
        if not isinstance(response, dict):
            raise ValueError('response_not_object')
        for name in ('requestId', 'requestSha256', 'generation', 'component', 'inputSha256',
                     'messagesSha256', 'bindingSha256', 'codec', 'modelIdentity', 'runtimeIdentity', 'codeIdentity', 'profilingMode'):
            if digest(response.get(name)) != digest(request[name]):
                raise ValueError('response_identity_mismatch:' + name)
        if response.get('placementPolicySha256') != request['placementPolicySha256']:
            raise ValueError('response_identity_mismatch:placementPolicySha256')
        if response.get('status') == 'incomplete':
            reason = response.get('reason')
            if not isinstance(reason, str) or not reason:
                raise ValueError('missing_incomplete_reason')
            return incomplete('webgpu:' + reason)
        if response.get('status') != 'result':
            raise ValueError('invalid_completion_status')
        device = response['deviceIdentity']
        validate_runtime_device(device, request['placementPolicySha256'])
        if request['profilingMode'] == 'off' and device.get('deviceSessionId') != request.get('calibration', {}).get('deviceSessionId'):
            raise ValueError('profiling_off_device_session_changed')
        if response.get('enableThinking') is not False:
            raise ValueError('thinking_mode_changed')
        inputs, tokens = response['inputTokenIds'], response['rawTokenIds']
        if (not isinstance(inputs, list) or not inputs or not isinstance(tokens, list)
                or any(type(t) is not int or t < 0 for t in inputs + tokens)):
            raise ValueError('invalid_token_evidence')
        if len(inputs) > request['maxInputTokens'] or len(inputs) + request['maxNewTokens'] > model['maxContextTokens']:
            raise ValueError('complete_context_exceeds_frozen_token_limit')
        if not 1 <= len(tokens) <= request['maxNewTokens']:
            raise ValueError('output_token_limit')
        if response.get('eosReached') is not True or tokens[-1] not in model['eosTokenIds']:
            raise ValueError('truncated_no_eos')
        if any(t in model['eosTokenIds'] for t in tokens[:-1]):
            raise ValueError('tokens_after_eos')
        raw = response['rawText']
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError('empty_generation')
        if '<think>' in raw or '</think>' in raw:
            raise ValueError('unexpected_thinking_tokens')
        if response.get('stopReason') != 'eos':
            raise ValueError('non_eos_stop')
        validate_gpu_evidence(request, response.get('gpuEvidence'))
        return result(raw)  # No strip, rewrite, entity replacement or JSON repair.
    except (KeyError, TypeError, ValueError) as error:
        return incomplete('webgpu:' + str(error))


def validate_gpu_evidence(request, evidence):
    if request.get('profilingMode') == 'off':
        calibration = request.get('calibration')
        if (not isinstance(calibration, dict) or not isinstance(evidence, dict)
                or evidence.get('source') != 'same_session_same_input_prior_gpu_calibration_v1'
                or evidence.get('perRequestGpuProof') is not False
                or evidence.get('unexpectedProfileKernelCount') != 0
                or digest(evidence.get('calibration')) != digest(calibration)
                or calibration.get('scopeSha256') != digest(calibration_scope(request))
                or evidence.get('kernelCount') is not None or evidence.get('totalKernelDurationNs') is not None
                or evidence.get('cpuNodeCount') is not None or evidence.get('cpuNodeDurationMs') is not None):
            raise ValueError('invalid_profiling_off_calibration_evidence')
        for name in ('requestId', 'generation', 'bindingSha256', 'inputSha256', 'modelIdentity', 'placementPolicySha256'):
            if digest(evidence.get(name)) != digest(request[name]):
                raise ValueError('gpu_profile_request_identity_mismatch:' + name)
        return
    if not isinstance(evidence, dict) or evidence.get('source') != 'ort_webgpu_timestamp_query_v1':
        raise ValueError('gpu_weight_compute_unproven')
    for name in ('requestId', 'generation', 'bindingSha256', 'inputSha256', 'modelIdentity', 'placementPolicySha256'):
        if digest(evidence.get(name)) != digest(request[name]):
            raise ValueError('gpu_profile_request_identity_mismatch:' + name)
    if (evidence.get('timestampUnit') != 'nanoseconds' or evidence.get('profilingMode') != 'default'
            or evidence.get('invalidCount') != 0 or type(evidence.get('invalidCount')) is not int
            or evidence.get('provesGpuWeightCompute') is not True):
        raise ValueError('invalid_gpu_profile_evidence')
    count = evidence.get('positiveWeightKernelCount')
    if type(count) is not int or count < 1:
        raise ValueError('gpu_weight_compute_unproven')
    witnesses = evidence.get('weightWitnesses')
    if not isinstance(witnesses, list) or not witnesses:
        raise ValueError('gpu_weight_compute_unproven')
    for row in witnesses:
        if not isinstance(row, dict):
            raise ValueError('invalid_gpu_weight_kernel_witness')
        start, end = row.get('startTime'), row.get('endTime')
        if (row.get('kernelType') != 'MatMulNBits' or row.get('version') != 1
                or type(start) is not int or type(end) is not int or not 0 <= start < end <= 2 ** 53 - 1
                or not isinstance(row.get('kernelName'), str) or not isinstance(row.get('programName'), str)):
            raise ValueError('invalid_gpu_weight_kernel_witness')
    total, weight = evidence.get('kernelCount'), evidence.get('weightKernelCount')
    if (type(total) is not int or type(weight) is not int or not len(witnesses) <= count <= weight <= total
            or total < 1):
        raise ValueError('gpu_profile_count_mismatch')
    if evidence.get('cpuNodeCount') is not None or evidence.get('cpuNodeDurationMs') is not None:
        raise ValueError('unsupported_cpu_placement_claim')


class WebGPUProvider:
    """Text-only callable; compositional task routing remains in shared provider."""
    def __init__(self, bridge, *, binding, timeout_ms=120000, max_input_tokens=32768,
                 max_new_tokens=128, cancelled=None, binding_now=None, profiling_mode='default'):
        self.bridge, self.binding = bridge, copy.deepcopy(binding)
        self.checkpoint = lambda *_: None
        self.profiling_mode = profiling_mode
        self.policy = dict(timeout_ms=timeout_ms, max_input_tokens=max_input_tokens,
                           max_new_tokens=max_new_tokens, cancelled=cancelled, binding_now=binding_now,
                           profiling_mode=profiling_mode)

    @property
    def identity(self):
        provenance = self.bridge.model['provenance']
        steps = validate_model_qualification(self.bridge.model)
        return {'modelId': provenance.get('originalModel', provenance['sourceModel']),
                'device': 'webgpu', 'revision': provenance.get('sourceRevision'),
                'modelIdentity': self.bridge.model['identity'],
                'runtime': copy.deepcopy(self.bridge.runtime), 'codeIdentity': self.bridge.code_identity,
                'placementPolicy': profiling_policy(self.profiling_mode),
                'placementPolicySha256': digest(profiling_policy(self.profiling_mode)),
                'profilingMode': self.profiling_mode,
                'assetHashes': {r['path']: r['sha256'] for r in self.bridge.model['files']},
                'adapter': copy.deepcopy(provenance), 'precision': 'q4f16',
                'tokenizer': digest([r for r in self.bridge.model['files'] if 'token' in r['path'] or 'template' in r['path']]),
                'codec': CODEC, 'codecSha256': sha256_file(BASE / 'short_qwen_codec.py'),
                'trainingCodec': provenance.get('codec') if steps else None,
                'trainingCodecSha256': provenance.get('codecSha256') if steps else None,
                'strictValidation': copy.deepcopy(provenance.get('strictValidation')) if steps else None,
                'trainedComponents': provenance.get('trainedComponents', []) if steps else [],
                'qualification': 'task_finetuned' if steps > 0 else 'base_zero_shot',
                'trainingSteps': steps}

    @property
    def model_identity(self):
        validate_model_qualification(self.bridge.model)
        return ModelIdentity(model='Qwen3-0.6B-WebGPU', weights=self.bridge.model['identity'],
            adapter=digest(self.bridge.model['provenance']),
            tokenizer=digest([r for r in self.bridge.model['files'] if 'token' in r['path'] or 'template' in r['path']]),
            precision='q4f16', implementation=self.bridge.runtime['identity'] + ':' + self.bridge.code_identity
                + ':' + digest(profiling_policy(self.profiling_mode)),
            capability=self.bridge.model['provenance']['capability'])

    def __call__(self, component, payload):
        original = self.bridge.checkpoint
        expected = {}
        def relay(kind, event):
            original(kind, event)
            if kind == 'webgpu_request_started':
                expected.update(event['request'])
                self.checkpoint(kind, event)
                return
            nested = event.get('event') if kind == 'webgpu_browser_event' else None
            candidate = nested if isinstance(nested, dict) else event.get('response', event)
            if expected and candidate.get('requestId') == expected['requestId']:
                if isinstance(nested, dict):
                    if any(digest(nested.get(k)) != digest(expected[k]) for k in ('generation', 'bindingSha256', 'inputSha256')):
                        return
                self.checkpoint(kind, event)
                if isinstance(nested, dict) and nested.get('kind'):
                    self.checkpoint(nested['kind'], {k: v for k, v in nested.items() if k != 'kind'})
        self.bridge.checkpoint = relay
        try:
            return self.bridge.request(component, payload, self.binding, **self.policy)
        finally:
            self.bridge.checkpoint = original

    def cancel(self):
        self.bridge.cancel()


def serve(model_manifest, runtime_manifest, *, port=0, journal_path=None):
    lock = threading.Lock()
    def checkpoint(kind, value):
        if journal_path:
            with lock, Path(journal_path).open('ab') as stream:
                stream.write(canonical_bytes({'kind': kind, 'value': value}) + b'\n')
                stream.flush()
    bridge = BrowserBridge(model_manifest, runtime_manifest, checkpoint=checkpoint)
    url = bridge.start(port)
    return bridge, url


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-manifest', required=True)
    parser.add_argument('--runtime-manifest', required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--journal', required=True)
    args = parser.parse_args()
    if Path(args.journal).exists():
        raise FileExistsError('new_append_only_journal_required')
    Path(args.journal).parent.mkdir(parents=True, exist_ok=True)
    bridge, url = serve(args.model_manifest, args.runtime_manifest, port=args.port, journal_path=args.journal)
    print(json.dumps({'url': url, 'scope': 'D browser worker; no production A/B/C'}), flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        bridge.close()
