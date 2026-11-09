"""Isolated four-head MiniRBT experiment, using the shared D supervisor.

Every original fact reaches the global branch. The additional focus branch is
only a structural projection of the actual request, never a semantic answer or
retrieved training example. No generator model is loaded or called here.
"""
from __future__ import annotations

import argparse
import collections
import copy
import importlib.metadata
import inspect
import json
import math
import os
from pathlib import Path
import platform
import re
import sys
import time

import experiment as common
from lab import sha256_file
from run_pilot import digest, exclusive, save, timestamp
from short_contracts import incomplete, result
from short_training import encode_complete, load_neural, task_specs, training_schedule, validate_rows

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
ART = ROOT / 'artifacts/world-components-logic/short-semantics'
LOCAL = ROOT / '.local/world-components-logic'
COMPONENTS = ('D02.1', 'D02.2.next', 'D04.1.next', 'D05.3.next')
ARMS = ('full_mean_control', 'global_plus_focus')
CODE = ('short_encoder_repair.py', 'short_training.py', 'short_experiment.py',
        'short_contracts.py', 'experiment.py', 'fact_windows.py', 'pilot_codec.py',
        'lab.py', 'run_pilot.py', 'm01_probe.py', 'generate_dev_drafts.py',
        'prepare_run_batch.py', 'action_plan.py')
CONFIG = {'device': 'cpu', 'threads': 1, 'concurrency': 1, 'precision': 'float32',
          'seed': 1729, 'steps': 512, 'batchSize': 8, 'learningRate': 0.003,
          'weightDecay': 0.01, 'maxGradNorm': 1.0, 'hiddenSize': 64,
          'standardDeviationFloor': 0.02, 'encoderLayers': [0, 1],
          'encoderPooling': False, 'encoderTokenLimit': 512,
          'promptCodec': 'complete_json_executor_binding_v2',
          'processWallSeconds': 1200, 'maxResidentMiB': 3072,
          'attemptsPerCase': 1, 'retries': 0, 'earlyStopping': False,
          'focusCodec': 'explicit_request_plus_executor_v1',
          'representation': 'all_fact_mean_plus_explicit_query_mean_v1'}


def representation_hashes():
    return {fn.__name__: digest(inspect.getsource(fn)) for fn in
            (focus_payload, representation, feature, build_model, encode_complete, load_neural)}


def paths(run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}', run_id):
        raise ValueError('invalid run identity')
    return ART / (run_id + '.plan.json'), ART / (run_id + '.record.json')


def focus_payload(component, payload):
    """Structural projection; the unmodified payload is still globally encoded.

    All non-world request fields are copied, including complete group/attempt
    judgments and all current candidate facts. Executor selection uses memberId
    for reaction requests and actorId otherwise; it makes no action judgment.
    """
    if component not in COMPONENTS or not isinstance(payload, dict):
        raise ValueError('unregistered focus task/input')
    context = payload.get('context')
    if not isinstance(context, dict) or not isinstance(context.get('world'), dict):
        raise ValueError('complete context world required')
    world = context['world']
    projected = {k: copy.deepcopy(v) for k, v in payload.items() if k not in ('context', 'world')}
    projected['context'] = {k: copy.deepcopy(v) for k, v in context.items() if k != 'world'}
    actor = payload.get('memberId') if component == 'D04.1.next' else context.get('actorId')
    projected['executorBinding'] = {'id': actor, 'identitySource': 'memberId' if component == 'D04.1.next' else 'context.actorId'}
    if actor is not None:
        current = world.get('characters', {}).get(actor)
        initial = world.get('initial', {}).get('characters', {}).get(actor)
        if not isinstance(current, dict) or not isinstance(initial, dict):
            raise ValueError('executor missing from complete actual world')
        projected['executorBinding'].update(current=copy.deepcopy(current), initial=copy.deepcopy(initial))
    # This is a second view, not an input rewrite. World/time are fully retained
    # in the separately encoded original payload, even for D05 with no executor.
    return projected


def selected_rows(dataset):
    from short_experiment import load_rows
    rows = [r for r in load_rows(dataset) if r['component'] in COMPONENTS]
    validate_rows(rows)
    if set(r['component'] for r in rows) != set(COMPONENTS):
        raise ValueError('four registered tasks must all be present')
    for component in COMPONENTS:
        spec = task_specs(rows)[component]
        if spec['kind'] != 'label': raise ValueError('only trained label heads accepted')
        for split in ('train', 'development', 'test'):
            present = {r['target'] for r in rows if r['component'] == component and r['split'] == split}
            if present != set(spec['labels']): raise ValueError('missing label/split coverage:' + component + ':' + split)
    return rows


def inventory(rows, schedule):
    seen = collections.Counter(schedule['exampleIds'])
    result = {}
    for component in COMPONENTS:
        subset = [r for r in rows if r['component'] == component]
        result[component] = {'labels': task_specs(subset)[component]['labels'], 'splits': {}}
        for split in ('train', 'development', 'test'):
            part = [r for r in subset if r['split'] == split]
            result[component]['splits'][split] = {
                'rows': len(part), 'sourceGroups': sorted({r['sourceGroup'] for r in part}),
                'labels': dict(collections.Counter(r['target'] for r in part))}
        train = [r for r in subset if r['split'] == 'train']
        result[component]['scheduledExposures'] = sum(seen[r['exampleId']] for r in train)
        result[component]['minimumRowExposure'] = min(seen[r['exampleId']] for r in train)
        if result[component]['minimumRowExposure'] < 1: raise ValueError('training schedule misses a complete source row')
    return result


def encoder_identity(source_provider):
    source = common.read_json(source_provider)
    if source.get('schema') != 'jity-d-short-trained-provider-v1': raise ValueError('source registry required')
    encoder = copy.deepcopy(source['models']['encoder'])
    for file in encoder['files']:
        if sha256_file(Path(encoder['directory']) / file['path']) != file['observedSha256']:
            raise ValueError('source encoder file mismatch')
    if sha256_file(encoder['checkpoint']['path']) != encoder['checkpoint']['sha256']:
        raise ValueError('historical encoder checkpoint mismatch')
    for component in COMPONENTS:
        if component not in encoder['trainedComponents']: raise ValueError('historical four-head comparator incomplete')
    return encoder


def freeze(run_id, *, dataset=None, source_provider):
    from short_experiment import snapshot_code, snapshot_data
    dataset = Path(dataset) if dataset else BASE / 'data/short-semantics/supervision.jsonl.gz'
    source_provider = Path(source_provider)
    plan_path, out = paths(run_id)
    if plan_path.exists() or out.exists(): raise FileExistsError('run identity already used')
    rows = selected_rows(dataset)
    schedule = training_schedule(rows, CONFIG)
    encoder = encoder_identity(source_provider)
    inv = inventory(rows, schedule)
    # Inspect every full/focus token workload before any neural call. No caps
    # truncate input; impossible atomic windows fail this frozen batch.
    from transformers import AutoTokenizer
    from fact_windows import make_windows
    tokenizer = AutoTokenizer.from_pretrained(encoder['directory'], local_files_only=True, trust_remote_code=False)
    tokenization = {}
    for row in rows:
        _, full = make_windows(row['input'], tokenizer, row['component'], CONFIG['encoderTokenLimit'])
        _, focused = make_windows(focus_payload(row['component'], row['input']), tokenizer,
                                  row['component'] + ':focus', CONFIG['encoderTokenLimit'])
        tokenization[row['exampleId']] = {'fullWindows': len(full), 'focusWindows': len(focused),
                                         'fullPayloadTokens': sum(w['payloadTokens'] for w in full),
                                         'focusPayloadTokens': sum(w['payloadTokens'] for w in focused)}
    snapshot = snapshot_code(run_id, CODE)
    data = snapshot_data(run_id, dataset)
    source_snapshot = ART / 'providers' / (run_id + '.source-encoder.json')
    source_snapshot.parent.mkdir(parents=True, exist_ok=True)
    exclusive(source_snapshot, {'encoder': encoder, 'sourceProviderSha256': sha256_file(source_provider),
                                'sourceProviderPath': str(source_provider)})
    plan = {'schema': 'jity-d-focus-encoder-plan-v1', 'runId': run_id, 'preparedAt': timestamp(),
            'config': copy.deepcopy(CONFIG), 'arms': list(ARMS), 'cases': [{'caseId': 'four-heads-training-and-heldout'}],
            'components': list(COMPONENTS), 'tasks': task_specs(rows), 'trainingSchedule': schedule,
            'inventory': inv, 'tokenization': tokenization, 'dataset': data['supervision.jsonl.gz'],
            'dataSnapshot': data, 'sourceEncoder': encoder,
            'sourceProvider': {'path': str(source_provider), 'sha256': sha256_file(source_provider),
                               'snapshot': str(source_snapshot), 'snapshotSha256': sha256_file(source_snapshot)},
            'codeSnapshot': snapshot, 'codeSha256': snapshot['files'],
            'representationFunctionHashes': representation_hashes(),
            'environment': {'venvExecutableRelativePath': str(Path(sys.executable).relative_to(ROOT)),
                            'python': sys.version, 'platform': platform.platform(),
                            'versions': {n: importlib.metadata.version(n) for n in ('torch', 'transformers', 'numpy')}},
            'thresholds': {'draftAccuracyExploratory': 0.9, 'eachLabelRecallExploratory': 0.8,
                           'humanReviewRequiredForPromotion': True, 'allClassesActualDataGradient': True},
            'comparison': {'trainingExamplesAndScheduleIdentical': True,
                           'bothArmsMLP': 'Linear(512,64),GELU,Linear(64,class_count)',
                           'normalization': 'train-only mean/std with registered floor',
                           'control': 'concat(global,global)', 'focus': 'concat(global,focus)',
                           'historicalHeadComparator': 'same full input, existing head, no generator',
                           'inputCoverage': 'all original facts plus extra structural focus, no truncation',
                           'trainingFeatureReuse': 'same frozen base/model/tokenizer/input per run only',
                           'heldoutInference': 'each arm re-encodes every full input; no fit feature cache'},
            'readiness': 'ready_exploratory', 'formalEvaluationAllowed': False,
            'semanticQualityApproved': False, 'humanReviewCount': 0, 'sourceVerification': 'unverified',
            'testUse': 'same open source groups previously evaluated, not fresh generalization',
            'generatorCallsAuthorized': False, 'productionIntegration': False,
            'unaffectedHeads': {'count': len(encoder['trainedComponents']) - len(COMPONENTS),
                                'policy': 'not loaded into new representation; external routing keeps original registry'}}
    exclusive(plan_path, plan)
    return plan_path


def verify(plan):
    if plan.get('schema') != 'jity-d-focus-encoder-plan-v1': raise ValueError('unknown plan')
    if plan['components'] != list(COMPONENTS) or plan['config'] != CONFIG: raise ValueError('frozen configuration drift')
    if plan['representationFunctionHashes'] != representation_hashes(): raise ValueError('representation drift')
    for name, expected in plan['codeSha256'].items():
        if sha256_file(BASE / name) != expected: raise ValueError('source drift:' + name)
        if sha256_file(Path(plan['codeSnapshot']['directory']) / name) != expected: raise ValueError('code snapshot drift')
    for file in plan['dataSnapshot'].values():
        if sha256_file(file['path']) != file['sha256']: raise ValueError('data snapshot drift')
    if sha256_file(plan['sourceProvider']['snapshot']) != plan['sourceProvider']['snapshotSha256']:
        raise ValueError('source registry snapshot drift')
    observed = encoder_identity(plan['sourceProvider']['path'])
    if observed != plan['sourceEncoder']: raise ValueError('source encoder identity drift')
    rows = selected_rows(plan['dataset']['path'])
    if training_schedule(rows, plan['config']) != plan['trainingSchedule']: raise ValueError('schedule drift')
    return rows


def build_model(torch, width, labels, config):
    return torch.nn.Sequential(torch.nn.Linear(width * 2, config['hiddenSize']), torch.nn.GELU(),
                               torch.nn.Linear(config['hiddenSize'], len(labels)))


def representation(torch, global_value, focused_value, arm):
    if arm not in ARMS: raise ValueError('unknown representation arm')
    return torch.cat((global_value, global_value if arm == ARMS[0] else focused_value))


def feature(torch, model, tokenizer, component, payload, config, checkpoint, arm):
    global_value = encode_complete(torch, model, tokenizer, component, payload, config, checkpoint)
    focused_value = (encode_complete(torch, model, tokenizer, component + ':focus', focus_payload(component, payload),
                                    config, checkpoint) if arm == ARMS[1] else global_value)
    return representation(torch, global_value, focused_value, arm), global_value, focused_value


def fit(torch, model, tokenizer, rows, plan, arm, checkpoint, directory):
    from m01_probe import tensor_hash
    config = plan['config']; specs = plan['tasks']; width = model.config.hidden_size
    model.eval()
    for param in model.parameters(): param.requires_grad_(False)
    base_hash = tensor_hash(model.state_dict())
    train = [r for r in rows if r['split'] == 'train']
    features = {}
    for row in train:
        checkpoint('training_feature_started', {'exampleId': row['exampleId'], 'input': row['input'],
                                               'inputHash': digest(row['input']), 'component': row['component']})
        values = feature(torch, model, tokenizer, row['component'], row['input'], config, checkpoint, arm)[0]
        features[row['exampleId']] = values
    torch.manual_seed(config['seed'])
    heads = {c: build_model(torch, width, specs[c]['labels'], config) for c in COMPONENTS}
    initial = {c: tensor_hash(h.state_dict()) for c, h in heads.items()}
    normalization = {}
    for component in COMPONENTS:
        values = torch.stack([features[r['exampleId']] for r in train if r['component'] == component])
        normalization[component] = {'mean': values.mean(0),
                                    'std': values.std(0, unbiased=False).clamp_min(config['standardDeviationFloor'])}
    parameters = [p for h in heads.values() for p in h.parameters()]
    optimizer = torch.optim.AdamW(parameters, lr=config['learningRate'], weight_decay=config['weightDecay'])
    by_id = {r['exampleId']: r for r in train}
    gradients = {c: 0 for c in COMPONENTS}; labels = {c: collections.Counter() for c in COMPONENTS}; losses = []
    for step in range(config['steps']):
        batch = [by_id[i] for i in plan['trainingSchedule']['exampleIds'][step*config['batchSize']:(step+1)*config['batchSize']]]
        checkpoint('training_step_started', {'step': step + 1, 'exampleIds': [r['exampleId'] for r in batch]})
        optimizer.zero_grad(set_to_none=True)
        terms = []
        for row in batch:
            c = row['component']; stats = normalization[c]
            logits = heads[c]((features[row['exampleId']] - stats['mean']) / stats['std']).unsqueeze(0)
            terms.append(torch.nn.functional.cross_entropy(logits, torch.tensor([specs[c]['labels'].index(row['target'])])))
        loss = sum(terms) / len(terms)
        if not torch.isfinite(loss): raise ValueError('nonfinite data loss')
        loss.backward()
        active = {r['component'] for r in batch}
        nonzero = [c for c in active if any(p.grad is not None and bool(torch.any(p.grad != 0)) for p in heads[c].parameters())]
        for c in nonzero: gradients[c] += 1
        for row in batch:
            if row['component'] in nonzero: labels[row['component']][row['target']] += 1
        norm = torch.nn.utils.clip_grad_norm_(parameters, config['maxGradNorm'])
        if not torch.isfinite(norm): raise ValueError('nonfinite data gradient')
        optimizer.step(); losses.append(float(loss.detach()))
        checkpoint('training_step_settled', {'step': step + 1, 'loss': losses[-1], 'gradientNorm': float(norm),
                                            'nonzeroDataGradientComponents': sorted(nonzero)})
    if tensor_hash(model.state_dict()) != base_hash: raise ValueError('frozen base modified')
    trained = [c for c in COMPONENTS if gradients[c] > 0 and tensor_hash(heads[c].state_dict()) != initial[c]
               and all(labels[c][label] > 0 for label in specs[c]['labels'])]
    if set(trained) != set(COMPONENTS): raise ValueError('some head or positive class had no actual training gradient')
    state = {'heads': {c: heads[c].state_dict() for c in COMPONENTS}, 'normalization': normalization}
    directory.mkdir(parents=True, exist_ok=False); path = directory / 'heads.pt'
    with path.open('xb') as stream: torch.save(state, stream); stream.flush(); os.fsync(stream.fileno())
    restored = torch.load(path, map_location='cpu', weights_only=True)
    for c in COMPONENTS:
        heads[c].load_state_dict(restored['heads'][c], strict=True); heads[c].eval()
        if tensor_hash(restored['heads'][c]) != tensor_hash(state['heads'][c]): raise ValueError('head reload mismatch')
        if not all(torch.equal(restored['normalization'][c][k], state['normalization'][c][k]) for k in ('mean', 'std')):
            raise ValueError('normalization reload mismatch')
    checkpoint('head_checkpoint_reloaded', {'path': str(path), 'sha256': sha256_file(path), 'trainedComponents': trained})
    # Existing four historical heads are read only to diagnose collapse. Their
    # predictions do not initialize, route, select, or overwrite new predictions.
    historical = torch.load(plan['sourceEncoder']['checkpoint']['path'], map_location='cpu', weights_only=True)
    predictions = []; probes = []
    for row in (r for r in rows if r['split'] != 'train'):
        begin = time.perf_counter(); c = row['component']
        checkpoint('head_prediction_started', {'exampleId': row['exampleId'], 'component': c,
                                               'input': row['input'], 'inputHash': digest(row['input'])})
        vector, global_value, focused = feature(torch, model, tokenizer, c, row['input'], config, checkpoint, arm)
        stats = normalization[c]
        with torch.no_grad():
            logits = heads[c]((vector - stats['mean']) / stats['std'])
            old_logits = torch.nn.functional.linear(global_value, historical[c]['weight'], historical[c]['bias'])
        values = logits.tolist()
        if not all(math.isfinite(v) for v in values): raise ValueError('nonfinite inference logits')
        value = specs[c]['labels'][int(logits.argmax())]
        old_labels = plan['sourceEncoder']['taskSpecs'][c]['labels']
        old = old_labels[int(old_logits.argmax())]
        event = {'exampleId': row['exampleId'], 'sourceGroup': row['sourceGroup'], 'split': row['split'],
                 'component': c, 'input': row['input'], 'inputHash': digest(row['input']),
                 'output': value, 'rawLogits': values, 'draftTarget': row['target'], 'exactDraftMatch': value == row['target'],
                 'historicalOutput': old, 'historicalRawLogits': old_logits.tolist(),
                 'elapsedMs': (time.perf_counter() - begin) * 1000, 'completion': 'result',
                 'semanticQualityApproved': False}
        ref = checkpoint('head_prediction', event)
        predictions.append({k: v for k, v in event.items() if k not in ('input', 'rawLogits', 'historicalRawLogits')} | {'rawCheckpoint': ref})
        probes.append((row, global_value, focused))
    contrasts = []
    for i, (left, global_a, focus_a) in enumerate(probes):
        for right, global_b, focus_b in probes[i+1:]:
            if (left['sourceGroup'], left['component']) != (right['sourceGroup'], right['component']) or left['target'] == right['target']: continue
            if digest(left['input']['context']['world']) != digest(right['input']['context']['world']): continue
            contrasts.append({'left': left['exampleId'], 'right': right['exampleId'], 'component': left['component'],
                              'globalCosine': float(torch.nn.functional.cosine_similarity(global_a, global_b, dim=0)),
                              'focusCosine': float(torch.nn.functional.cosine_similarity(focus_a, focus_b, dim=0))})
    checkpoint('same_world_different_label_representation_diagnostic', {'pairs': contrasts,
                 'interpretation': 'descriptive geometry after predictions; not semantic causality proof'})
    return {'steps': len(losses), 'losses': losses, 'checkpoint': {'path': str(path), 'sha256': sha256_file(path)},
            'trainedComponents': trained, 'componentNonzeroDataGradientSteps': gradients,
            'componentLabelDataGradientExposures': {c: dict(v) for c, v in labels.items()},
            'sourceWeightsUnchanged': True, 'baseTensorHash': base_hash,
            'predictions': predictions, 'contrastPairs': contrasts, 'semanticQualityApproved': False}


class FocusSemanticProvider:
    """Independent representation registry: never silently handles other heads."""
    def __init__(self, manifest, *, checkpoint=None):
        self.manifest = copy.deepcopy(manifest); self.manifest_hash = digest(manifest)
        self.identity = {'schema': 'jity-d-focus-encoder-identity-v1', 'components': list(COMPONENTS),
                         'manifestSha256': self.manifest_hash, 'arm': manifest.get('arm'),
                         'representation': manifest.get('config', {}).get('representation'),
                         'checkpoint': copy.deepcopy(manifest.get('checkpoint'))}
        self.identity_hash = digest(self.identity)
        self.checkpoint = checkpoint or (lambda *_: None); self.loaded = None; self.primitive_calls = 0
        if manifest.get('schema') != 'jity-d-focus-encoder-provider-v1': raise ValueError('focus registry required')
        if set(manifest.get('tasks', {})) != set(COMPONENTS): raise ValueError('four-head registry scope mismatch')
        if manifest.get('arm') not in ARMS: raise ValueError('unknown frozen representation')

    def _load(self):
        if self.loaded is not None: return self.loaded
        import torch
        spec = self.manifest; model_spec = spec['encoder']
        if spec.get('representationFunctionHashes') != representation_hashes(): raise ValueError('trained representation identity mismatch')
        if sha256_file(spec['checkpoint']['path']) != spec['checkpoint']['sha256']: raise ValueError('trained head hash mismatch')
        for file in model_spec['files']:
            if sha256_file(Path(model_spec['directory']) / file['path']) != file['observedSha256']: raise ValueError('base model identity mismatch')
        begin = time.perf_counter()
        model, tokenizer = load_neural(torch, 'encoder', model_spec['directory'], spec['config'])
        state = torch.load(spec['checkpoint']['path'], map_location='cpu', weights_only=True)
        if set(state['heads']) != set(COMPONENTS) or set(state['normalization']) != set(COMPONENTS): raise ValueError('checkpoint scope mismatch')
        heads = {c: build_model(torch, model.config.hidden_size, spec['tasks'][c]['labels'], spec['config']) for c in COMPONENTS}
        for c, h in heads.items(): h.load_state_dict(state['heads'][c], strict=True); h.eval()
        for c in COMPONENTS:
            stats = state['normalization'][c]
            if any(stats[k].shape != (model.config.hidden_size * 2,) or not bool(torch.isfinite(stats[k]).all()) for k in ('mean', 'std')):
                raise ValueError('normalization shape/value invalid')
            if not bool((stats['std'] > 0).all()): raise ValueError('normalization divisor invalid')
        self.checkpoint('request_model_load', {'role': 'focus_encoder', 'elapsedMs': (time.perf_counter()-begin)*1000})
        self.loaded = torch, model, tokenizer, heads, state['normalization']
        return self.loaded

    def __call__(self, component, payload):
        if digest(self.manifest) != self.manifest_hash or digest(self.identity) != self.identity_hash:
            return incomplete('focus_provider_identity_changed')
        if component not in COMPONENTS: return incomplete('focus_provider_component_not_registered:' + component)
        spec = self.manifest
        if spec.get('trainingSteps', 0) <= 0 or spec.get('componentNonzeroDataGradientSteps', {}).get(component, 0) <= 0:
            return incomplete('untrained_focus_component:' + component)
        labels = spec['tasks'][component]['labels']
        if any(spec.get('componentLabelDataGradientExposures', {}).get(component, {}).get(label, 0) <= 0 for label in labels):
            return incomplete('untrained_focus_positive_class:' + component)
        event = {'component': component, 'input': copy.deepcopy(payload), 'inputHash': digest(payload), 'role': 'focus_encoder'}
        self.checkpoint('semantic_call_started', event); self.primitive_calls += 1
        begin = time.perf_counter()
        try:
            torch, model, tokenizer, heads, normalization = self._load()
            vector = feature(torch, model, tokenizer, component, payload, spec['config'], self.checkpoint, spec['arm'])[0]
            stats = normalization[component]
            with torch.no_grad(): logits = heads[component]((vector-stats['mean'])/stats['std'])
            values = logits.tolist()
            if not all(math.isfinite(v) for v in values): raise ValueError('nonfinite logits')
            value = labels[int(logits.argmax())]; event.update(rawLogits=values, value=value, completion='result')
            if component == 'D02.1' and value == 'incomplete':
                event.update(completion='incomplete', rawLabel=value, reason='semantic_incomplete:D02.1')
                return incomplete('semantic_incomplete:D02.1')
            return result(value)
        except Exception as error:
            event.update(completion='incomplete', error={'type': type(error).__name__, 'message': str(error)})
            return incomplete('focus_encoder:' + str(error))
        finally:
            event['elapsedMs'] = (time.perf_counter()-begin)*1000; self.checkpoint('semantic_call_finished', event)


def worker(path):
    plan = common.read_json(path); rows = verify(plan); _, out = paths(plan['runId'])
    slots = common.planned_slots(plan, ARMS)
    record = {'schema': 'jity-d-focus-encoder-record-v1', 'runId': plan['runId'], 'planSha256': sha256_file(path),
              'status': 'running', 'stages': [], 'attempts': [], 'attemptSlots': slots, 'activeAttempt': None,
              'checkpointStorage': common.CHECKPOINT_STORAGE, 'formalEvaluationAllowed': False,
              'semanticQualityApproved': False, 'fullRequestMeasured': False}
    exclusive(out, record)
    try:
        import torch
        torch.set_num_threads(1); torch.set_num_interop_threads(1); torch.manual_seed(plan['config']['seed'])
        with common.AppendJournal(out.with_suffix('.journal.jsonl'), record['planSha256']) as journal:
            journal.append('begin', {'runId': plan['runId'], 'slots': slots, 'checkpointStorage': common.CHECKPOINT_STORAGE})
            for slot in slots:
                attempt = {**slot, 'status': 'started', 'startedMonotonicNs': time.monotonic_ns(), 'checkpoints': []}
                record['activeAttempt'] = attempt; journal.append('attempt_start', attempt)
                def checkpoint(name, payload):
                    ref = common.append_checkpoint(journal, {**{k: attempt[k] for k in ('arm', 'caseId', 'repeat')}, 'name': name, 'payload': payload})
                    attempt['checkpoints'].append(ref); return ref
                try:
                    begin = time.perf_counter()
                    model, tokenizer = load_neural(torch, 'encoder', plan['sourceEncoder']['directory'], plan['config'])
                    checkpoint('cold_model_load', {'role': 'encoder', 'elapsedMs': (time.perf_counter()-begin)*1000,
                                                   'parameters': sum(p.numel() for p in model.parameters())})
                    directory = LOCAL / 'focus-encoder-models' / plan['runId'] / attempt['arm']
                    trained = fit(torch, model, tokenizer, rows, plan, attempt['arm'], checkpoint, directory)
                    manifest = {'schema': 'jity-d-focus-encoder-provider-v1', 'runId': plan['runId'], 'arm': attempt['arm'],
                                'config': plan['config'], 'tasks': plan['tasks'], 'encoder': {k: v for k, v in plan['sourceEncoder'].items()
                                    if k not in ('checkpoint', 'taskSpecs', 'trainedComponents', 'trainingSteps', 'componentGradientExposures',
                                                 'componentNonzeroDataGradientSteps', 'componentLabelDataGradientExposures')},
                                'checkpoint': trained['checkpoint'], 'trainingSteps': trained['steps'],
                                'componentNonzeroDataGradientSteps': trained['componentNonzeroDataGradientSteps'],
                                'componentLabelDataGradientExposures': trained['componentLabelDataGradientExposures'],
                                'datasetSha256': plan['dataset']['sha256'], 'codeSha256': plan['codeSha256'],
                                'representationFunctionHashes': plan['representationFunctionHashes'],
                                'planPath': str(path), 'planSha256': sha256_file(path), 'recordPath': str(out),
                                'semanticQualityApproved': False, 'generator': None,
                                'integration': 'route exactly four registered primitive heads; all others retain prior identity'}
                    provider_path = directory / 'provider.json'; exclusive(provider_path, manifest)
                    attempt.update(status='complete', training=trained,
                                   provider={'path': str(provider_path), 'sha256': sha256_file(provider_path)})
                    del model, tokenizer
                except Exception as error:
                    attempt.update(status='failed', completion='incomplete', error={'type': type(error).__name__, 'message': str(error)})
                journal.append('attempt_result', attempt)
                timing = {k: attempt[k] for k in ('arm', 'caseId', 'repeat')}
                timing.update(resultJournalMs=0., snapshotEndMs=0., elapsedThroughResultMs=(time.monotonic_ns()-attempt['startedMonotonicNs'])/1e6)
                journal.append('attempt_settled', timing); attempt.update(timing)
                record['attempts'].append(attempt); record['activeAttempt'] = None; save(out, record)
        record['status'] = 'diagnostic_completed' if all(a['status'] == 'complete' for a in record['attempts']) else 'failed'
    except Exception as error:
        record.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
    finally: save(out, record)
    return 0 if record['status'] == 'diagnostic_completed' else 1


def execute(path):
    return common.execute_plan(path, paths=paths, verify=verify, worker_script=Path(__file__),
                               settle_stages=lambda *_: None, arms=ARMS)


def report(path):
    plan = common.read_json(path); _, out = paths(plan['runId'])
    for name, expected in plan['codeSnapshot']['files'].items():
        if sha256_file(Path(plan['codeSnapshot']['directory']) / name) != expected: raise ValueError('historical code snapshot mismatch')
    rows = selected_rows(plan['dataset']['path'])
    if sha256_file(plan['dataset']['path']) != plan['dataset']['sha256']: raise ValueError('historical dataset mismatch')
    record = common.read_json(out) if out.exists() else None
    if record and record['planSha256'] != sha256_file(path): raise ValueError('plan/record mismatch')
    slots = {(arm, r['exampleId']): {'arm': arm, 'exampleId': r['exampleId'], 'component': r['component'], 'split': r['split'], 'status': 'not_started'}
             for arm in ARMS for r in rows if r['split'] != 'train'}
    events = common.iter_checkpoint_events(record, out.with_suffix('.journal.jsonl')) if record and out.with_suffix('.journal.jsonl').exists() else ()
    predictions = []; counters = collections.Counter(); compute_ms = 0.
    for event in events:
        body = event['payload']; key = event['arm'], body.get('exampleId')
        counters[event['name']] += 1
        if event['name'] == 'encoder_forward_settled': compute_ms += body['elapsedMs']
        if key in slots and event['name'] == 'head_prediction_started': slots[key]['status'] = 'incomplete'
        if key in slots and event['name'] == 'head_prediction':
            slots[key].update(status='result', output=body['output'], draftTarget=body['draftTarget'], exactDraftMatch=body['exactDraftMatch'])
            predictions.append({k: v for k, v in body.items() if k not in ('input', 'rawLogits', 'historicalRawLogits') } | {'arm': event['arm']})
    by_arm = {}
    for arm in ARMS:
        by_arm[arm] = {}
        for component in COMPONENTS:
            part = [p for p in predictions if p['arm'] == arm and p['component'] == component]
            labels = plan['tasks'][component]['labels']
            recall = {label: {'correct': sum(p['output'] == label for p in part if p['draftTarget'] == label),
                              'count': sum(p['draftTarget'] == label for p in part)} for label in labels}
            by_arm[arm][component] = {'count': len(part), 'draftMatches': sum(p['exactDraftMatch'] for p in part),
                                      'historicalDraftMatches': sum(p['historicalOutput'] == p['draftTarget'] for p in part),
                                      'confusion': {target: dict(collections.Counter(p['output'] for p in part if p['draftTarget'] == target)) for target in labels},
                                      'perLabelRecall': recall,
                                      'splits': {split: {'count': sum(p['split'] == split for p in part),
                                                        'draftMatches': sum(p['exactDraftMatch'] for p in part if p['split'] == split)} for split in ('development','test')}}
    return {'schema': 'jity-d-focus-encoder-summary-v1', 'runId': plan['runId'], 'planSha256': sha256_file(path),
            'status': record['status'] if record else 'not_run', 'cases': list(slots.values()), 'metrics': by_arm,
            'unstarted': sum(s['status'] == 'not_started' for s in slots.values()),
            'incomplete': sum(s['status'] == 'incomplete' for s in slots.values()), 'firstOutputs': len(predictions),
            'counters': dict(counters), 'encoderForwardMs': compute_ms, 'supervisor': record.get('supervisor') if record else None,
            'providers': [a['provider'] for a in record['attempts'] if 'provider' in a] if record else [],
            'semanticQualityApproved': False, 'humanReviewCount': 0, 'sourceVerification': 'unverified',
            'fullRequest500ms': 'unmeasured', 'generatorCalls': 0,
            'comparisonLimit': 'previously inspected open source groups; training budget, MLP and normalization differ from historical linear heads',
            'outOfScope': ['D05.2 partial/incomplete head repair', 'autonomous generated action quality', 'other 58 head representations', 'formal AB/C/WebGPU chain']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--worker', type=Path, required=True)
    raise SystemExit(worker(parser.parse_args().worker))
