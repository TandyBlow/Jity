"""Explicit MiniRBT + Qwen WebGPU routing for the new D architecture.

There is one generator route and no generator fallback. Aggregate components
reuse the existing narrow orchestration by calling this provider recursively.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import time

from run_pilot import digest
from lab import sha256_file
from short_contracts import Completion, ModelIdentity, incomplete
from short_qwen_codec import CODEC, TASKS
from short_training import LocalSemanticProvider


class MixedSemanticProvider(LocalSemanticProvider):
    def __init__(self, encoder_manifest, text_backend, *, focus_backend=None,
                 require_trained=True, checkpoint=None, retain_observations=False):
        if type(require_trained) is not bool:
            raise ValueError('explicit_training_qualification_required')
        identity = copy.deepcopy(text_backend.identity)
        if identity.get('modelId') != 'Qwen/Qwen3-0.6B' or identity.get('device') != 'webgpu':
            raise ValueError('Qwen_WebGPU_backend_required')
        if identity.get('codec') != CODEC:
            raise ValueError('training_inference_prompt_codec_mismatch')
        current = copy.deepcopy(encoder_manifest)
        # The old generator's identity remains in its historical manifest only.
        current['models'] = {'encoder': current['models']['encoder']}
        current['activeTextIdentity'] = identity
        current['activeFocusIdentity'] = copy.deepcopy(focus_backend.identity) if focus_backend else None
        current['requireTrainedTextTasks'] = require_trained
        super().__init__(current, checkpoint=checkpoint, retain_observations=retain_observations)
        self.text_backend = text_backend
        self.focus_backend = focus_backend
        self.require_trained = require_trained
        self.text_identity_hash = digest(identity)
        self.focus_identity_hash = digest(focus_backend.identity) if focus_backend else None

    def model_identity(self):
        encoder = self.manifest['models']['encoder']
        return ModelIdentity(model=digest(self.manifest),
            weights=digest({'encoder': encoder['checkpoint'], 'text': self.text_backend.identity,
                            'focus': self.manifest['activeFocusIdentity']}),
            adapter=digest(self.manifest['tasks']),
            tokenizer=digest({'encoder': encoder['files'], 'text': self.text_backend.identity}),
            precision='explicit_per_backend_manifest', implementation=digest(self.manifest['codeSha256']),
            capability='experiment_unvalidated')

    def __call__(self, component, payload):
        if digest(self.manifest) != self.manifest_hash:
            return incomplete('provider_identity_changed_recreate_required')
        if digest(self.text_backend.identity) != self.text_identity_hash:
            return incomplete('text_backend_identity_changed_recreate_required')
        if self.focus_backend and digest(self.focus_backend.identity) != self.focus_identity_hash:
            return incomplete('focus_backend_identity_changed_recreate_required')
        task = self.manifest.get('tasks', {}).get(component)
        backend = None
        if task and task['kind'] == 'text':
            if component not in TASKS:
                return incomplete('unregistered_qwen_task:' + component)
            if task.get('outputCodec') != 'text':
                return incomplete('qwen_requires_narrow_text_codec')
            if self.require_trained and component not in self.text_backend.identity.get('trainedComponents', []):
                return incomplete('untrained_qwen_component:' + component)
            if self.require_trained and (self.text_backend.identity.get('trainingSteps', 0) <= 0
                                        or self.text_backend.identity.get('qualification') != 'task_finetuned'):
                return incomplete('unqualified_qwen_training_identity:' + component)
            backend, role = self.text_backend, 'generator'
        elif self.focus_backend and component in self.focus_backend.identity.get('components', []):
            backend, role = self.focus_backend, 'encoder'
        if backend is None:
            return super().__call__(component, payload)
        start = time.perf_counter()
        event = {'component': component, 'input': copy.deepcopy(payload), 'inputSha256': digest(payload),
                 'role': role, 'backendIdentity': digest(backend.identity)}
        self.checkpoint('semantic_call_started', event)
        self.primitive_calls += 1
        answer = None
        try:
            # The router owns the primitive call count; keep the focus backend's
            # raw logits without counting its nested call as a second primitive.
            def relay(name, value):
                if role == 'encoder' and name in ('semantic_call_started', 'semantic_call_finished'):
                    name = 'focus_' + name
                return self.checkpoint(name, value)
            backend.checkpoint = relay
            answer = backend(component, copy.deepcopy(payload))
            if not isinstance(answer, Completion):
                raise ValueError('backend_completion_contract_required')
            if role == 'generator' and answer.status == 'empty':
                answer = incomplete('text_generation_cannot_be_semantic_empty')
            if role == 'generator' and answer.status == 'result' and (not isinstance(answer.value, str) or not answer.value.strip()):
                answer = incomplete('empty_or_nontext_generation')
            if component == 'D02.1' and answer.status == 'result' and answer.value == 'incomplete':
                answer = incomplete('semantic_incomplete:D02.1')
            return answer
        except Exception as error:
            answer = incomplete('active_backend:' + type(error).__name__ + ':' + str(error))
            return answer
        finally:
            event.update(completion=answer.status if answer else 'incomplete',
                         elapsedMs=(time.perf_counter() - start) * 1000)
            if answer and answer.status == 'result': event['value'] = answer.value
            if answer and answer.reason: event['error'] = answer.reason
            if self.retain_observations: self.observations.append(copy.deepcopy(event))
            self.checkpoint('semantic_call_finished', event)


def publish_manifest(destination, *, encoder_provider, model_manifest, runtime_manifest,
                     focus_provider=None, require_trained=True, max_input_tokens=8192,
                     max_new_tokens=128):
    """Freeze explicit routes and all source artifacts; does not load a model."""
    from short_webgpu import BrowserBridge, WebGPUProvider
    from short_encoder_repair import FocusSemanticProvider
    from run_pilot import exclusive
    destination = Path(destination)
    if destination.exists(): raise FileExistsError('new_provider_identity_required')
    parent = json.loads(Path(encoder_provider).read_text())
    LocalSemanticProvider(parent)
    bridge = BrowserBridge(model_manifest, runtime_manifest)
    text = WebGPUProvider(bridge, binding={'preflight': True}, max_input_tokens=max_input_tokens,
                         max_new_tokens=max_new_tokens)
    provenance = bridge.model['provenance']
    if require_trained and (provenance.get('trainingSteps', 0) <= 0
                           or set(provenance.get('trainedComponents', [])) != set(TASKS)
                           or provenance.get('datasetSha256') != parent['datasetSha256']):
        raise ValueError('new_generator_training_or_dataset_identity_missing')
    focus = None
    if focus_provider:
        focus_manifest = json.loads(Path(focus_provider).read_text())
        if focus_manifest['datasetSha256'] != parent['datasetSha256']:
            raise ValueError('focus_training_dataset_identity_mismatch')
        focus = FocusSemanticProvider(focus_manifest)
    MixedSemanticProvider(parent, text, focus_backend=focus, require_trained=require_trained)
    value = copy.deepcopy(parent)
    value.update(runId=destination.stem, activeArchitecture='short_semantics_qwen_webgpu',
                 semanticQualityApproved=False)
    def artifact(path):
        path = Path(path).resolve()
        return {'path': str(path), 'sha256': sha256_file(path)}
    value['sourceEncoderProvider'] = artifact(encoder_provider)
    value['textBackend'] = {'modelManifest': artifact(model_manifest),
        'runtimeManifest': artifact(runtime_manifest), 'identity': text.identity,
        'tokenizerParity': artifact(Path(__file__).resolve().parents[2] / 'artifacts/world-components-logic/qwen-short/tokenizer-parity-cases-v2.json'),
        'requireTrained': require_trained, 'maxInputTokens': max_input_tokens,
        'maxNewTokens': max_new_tokens, 'timeoutMs': 120000,
        'execution': 'webgpu_preferred_cpu_nodes_allowed_profiled_no_randeng_fallback'}
    value['focusBackend'] = artifact(focus_provider) if focus_provider else None
    value['models'] = {'encoder': copy.deepcopy(parent['models']['encoder']),
        'generator': {'modelId': 'Qwen/Qwen3-0.6B', 'revision': provenance.get('sourceRevision'),
            'directory': bridge.model['directory'], 'checkpoint': artifact(model_manifest),
            'trainingSteps': provenance.get('trainingSteps', 0),
            'trainedComponents': provenance.get('trainedComponents', []),
            'taskSpecs': {c: value['tasks'][c] for c in provenance.get('trainedComponents', [])},
            'files': [{'path': r['path'], 'expectedBytes': r['size'], 'observedSha256': r['sha256']}
                      for r in bridge.model['files']]}}
    exclusive(destination, value)
    return destination


def verify_backend_artifacts(manifest):
    from short_webgpu import verified_manifest, MODEL_SCHEMA, RUNTIME_SCHEMA
    spec = manifest.get('textBackend')
    if not spec: raise ValueError('active_webgpu_backend_required')
    sources = [spec['modelManifest'], spec['runtimeManifest'], spec['tokenizerParity'], manifest['sourceEncoderProvider']]
    if manifest.get('focusBackend'): sources.append(manifest['focusBackend'])
    for source in sources:
        if sha256_file(source['path']) != source['sha256']:
            raise ValueError('backend_artifact_identity_drift')
    verified_manifest(spec['modelManifest']['path'], MODEL_SCHEMA)
    verified_manifest(spec['runtimeManifest']['path'], RUNTIME_SCHEMA)


def create_provider(manifest, *, global_checkpoint=None):
    """Prepare the in-process bridge; caller owns its start, ready gate and close."""
    from short_webgpu import BrowserBridge, WebGPUProvider
    from short_encoder_repair import FocusSemanticProvider
    verify_backend_artifacts(manifest)
    spec = manifest['textBackend']
    bridge = BrowserBridge(spec['modelManifest']['path'], spec['runtimeManifest']['path'], checkpoint=global_checkpoint,
                           tokenizer_cases=spec['tokenizerParity']['path'])
    backend = WebGPUProvider(bridge, binding={'provider': digest(manifest)},
        timeout_ms=spec['timeoutMs'], max_input_tokens=spec['maxInputTokens'],
        max_new_tokens=spec['maxNewTokens'])
    if digest(backend.identity) != digest(spec['identity']):
        raise ValueError('frozen_text_backend_identity_drift')
    focus = FocusSemanticProvider(json.loads(Path(manifest['focusBackend']['path']).read_text())) if manifest.get('focusBackend') else None
    provider = MixedSemanticProvider(manifest, backend, focus_backend=focus,
                                    require_trained=spec['requireTrained'])
    return provider, bridge
