"""Frozen, supervised local evaluation; no teacher output enters live inference.

Diagnostic targets are read only after inference for draft exact-match scoring.
Live cases use authored initial contexts, then actual model outputs exclusively.
This offline D scope does not commit a world, narrate, or measure a full request.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import replace
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import time
import threading

import experiment as common
from lab import sha256_file
from run_pilot import exclusive, save, timestamp
from short_contracts import Completion, ModelIdentity, ModelSession, digest, incomplete, json_value, result
from short_training import END, LocalSemanticProvider
import short_experiment as training

BASE = Path(__file__).resolve().parent
ART = training.ART
ARMS = ('short_evaluation',)
CONFIG = {'processWallSeconds': 1800, 'maxResidentMiB': 4096, 'attemptsPerCase': 1,
          'retries': 0, 'seed': 1729, 'maxCallsPerCase': 512,
          'maxPrimitiveCallsPerCase': 4096, 'callTimeoutMs': 120000,
          'maxFragments': 8, 'maxSources': 16, 'maxFacts': 32, 'maxNewTasks': 32,
          'cache': False, 'concurrency': 1, 'representationSubarms': ['natural', 'references'],
          'caseDeadlineSeconds': {'live_upstream': 60, 'live_initialization': 120,
                                  'live_pure_time': 90, 'diagnostic': 30}}
CONTRACT_SELECTION = r'^(D0[1-8]\.[1-6]|U[1-6]\.[12]|D06\.P\.(mapping|review))$'


def configuration(scope='contracts'):
    if scope not in ('contracts', 'all', 'webgpu', 'webgpu_text'):
        raise ValueError('unknown frozen evaluation scope')
    value = {**copy.deepcopy(CONFIG), 'diagnosticScope': scope}
    if scope in ('webgpu', 'webgpu_text'):
        value.update(processWallSeconds=2400, browserAttachSeconds=300)
        value['caseDeadlineSeconds']['diagnostic'] = 60
    if scope == 'webgpu_text': value['processWallSeconds'] = 1200
    return value


def paths(run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}', run_id):
        raise ValueError('invalid evaluation identity')
    return ART / ('evaluation-' + run_id + '.plan.json'), ART / ('evaluation-' + run_id + '.record.json')


def _code_files(webgpu=False):
    # Authorship is offline preparation and is never imported by this worker.
    # A new independently versioned packet may be authored during inference.
    names = {name for name in training.CODE if not name.startswith('data/')} | {'short_evaluation.py', 'short_preview.py'}
    if webgpu:
        names |= {'short_mixed_provider.py', 'short_qwen_codec.py', 'short_webgpu.py',
                  'short_encoder_repair.py', 'short_webgpu/index.html', 'short_webgpu/page.mjs',
                  'short_webgpu/worker.mjs', 'short_webgpu/core.mjs'}
    return sorted(names)


def _preview_authority(scope):
    if scope == 'webgpu_text':
        return {'mode': 'unused_for_direct_text_only', 'sourceCommit': None, 'sourceFiles': {},
                'serviceOrDatabaseAccess': False, 'productionIntegration': False}
    from short_preview import authority_identity
    return authority_identity()


def _highest_sequence(value):
    if isinstance(value, dict):
        own = value.get('sourceSequence', 0)
        return max([own if type(own) is int else 0] + [_highest_sequence(v) for v in value.values()])
    if isinstance(value, list):
        return max([0] + [_highest_sequence(v) for v in value])
    return 0


def _point_metadata(case_id, world):
    tag = digest({'case': case_id, 'seed': CONFIG['seed']})
    return {'worldId': world['worldId'], 'id': 'eval-point:' + tag,
            'sequence': max(2, _highest_sequence(world) + 1),
            'previousPointId': 'eval-predecessor:' + tag, 'roundId': 'eval-round:' + tag,
            'advanceId': 'eval-advance:' + tag, 'trigger': 'player'}


def live_input_kind(row):
    """Evaluation provenance only; never added to the semantic payload."""
    if row.get('abstentionControl') == 'act':
        return 'provided_complete_attempt_control'
    if row.get('abstentionControl') == 'skip':
        return 'explicit_skip_control'
    if row.get('semanticAbstention'):
        return 'missing_material_abstention_control'
    context = row['input']['context']
    actor = 'player' if context['actorId'] == context['protagonistId'] else 'npc'
    return actor + '_' + context['advance']['intentStatus']


def register_cases(rows, scope='contracts'):
    """Register all held-out diagnostics and every distinct starting context.

    Never inspect target, scenario steps, authored facts, or result candidates to
    select a live case. NPC/consumed variants retain their original source group.
    """
    configuration(scope)
    cases, seen, text_seen = [], set(), set()
    for row in rows:
        if row['split'] not in ('development', 'test'):
            continue
        if scope == 'webgpu_text':
            if row['kind'] != 'text' or row['component'] in text_seen:
                continue
            text_seen.add(row['component'])
        if scope == 'contracts' and not re.fullmatch(CONTRACT_SELECTION, row['component']):
            continue
        if scope == 'webgpu' and not re.fullmatch(CONTRACT_SELECTION, row['component']):
            key = (row['component'], row['sourceGroup'])
            if row['kind'] != 'text' or key in text_seen:
                continue
            text_seen.add(key)
        cases.append({'caseId': 'diagnostic:' + row['exampleId'], 'scope': 'diagnostic',
                      'exampleId': row['exampleId'], 'component': row['component'],
                      'kind': row['kind'], 'sourceGroup': row['sourceGroup'], 'split': row['split'],
                      'inputHash': digest(row['input'])})
    if scope == 'webgpu_text':
        return cases
    for row in rows:
        if row['split'] not in ('development', 'test') or row['component'] != 'D02.1':
            continue
        context = row['input']['context']
        key = (row['sourceGroup'], digest(context))
        if key in seen:
            continue
        seen.add(key)
        for representation in CONFIG['representationSubarms']:
            case_id = 'live:' + row['exampleId'] + ':' + representation
            point = _point_metadata(case_id, context['world'])
            point.update(kind='instant', linkedFromPointId=point['previousPointId'],
                         timeAdvance={'boundary': 'instant', 'duration': {'amount': 0, 'unit': 'second'}})
            cases.append({'caseId': case_id,
                          'scope': 'live_upstream', 'exampleId': row['exampleId'],
                          'sourceGroup': row['sourceGroup'], 'split': row['split'],
                          'inputKind': live_input_kind(row),
                          'representation': representation, 'inputHash': digest(context), 'offlinePoint': point})
    # Source-file order is part of the frozen packet. Choose one initial world
    # per held-out source, never an authored later-state or expected result.
    source_worlds, source_briefs = {}, {}
    for row in rows:
        if row['split'] not in ('development', 'test'):
            continue
        if row['component'] == 'D02.1':
            source_worlds.setdefault(row['sourceGroup'], row)
        if row['component'] == 'D01.1':
            source_briefs.setdefault(row['sourceGroup'], row)
    for group, row in source_briefs.items():
        source = source_worlds.get(group)
        initial_time = copy.deepcopy(source['input']['context']['world']['initial'].get('initialTime')) if source else None
        actual_input = {'brief': row['input'].get('brief'), 'initialTime': initial_time}
        cases.append({'caseId': 'initialization:' + row['exampleId'], 'scope': 'live_initialization',
                      'exampleId': row['exampleId'], 'sourceExampleId': source['exampleId'] if source else None,
                      'sourceGroup': group, 'split': row['split'], 'inputHash': digest(actual_input)})
    for group, row in source_worlds.items():
        world = row['input']['context']['world']
        case_id = 'pure-time:' + row['exampleId']
        cases.append({'caseId': case_id, 'scope': 'live_pure_time', 'exampleId': row['exampleId'],
                      'sourceGroup': group, 'split': row['split'], 'inputHash': digest(world),
                      'offlinePointMetadata': _point_metadata(case_id, world)})
    # Exercise actual upstream before the larger supplied-intermediate workload.
    return sorted(cases, key=lambda case: case['scope'] == 'diagnostic')


def freeze(run_id, provider_path, *, dataset=None, scope='contracts'):
    path, out = paths(run_id)
    if path.exists() or out.exists():
        raise FileExistsError('preserve original evaluation; use a new identity')
    dataset = Path(dataset or training.DATA / 'supervision.jsonl.gz').resolve()
    rows = training.load_rows(dataset)
    provider_path = Path(provider_path).resolve()
    manifest = common.read_json(provider_path)
    webgpu = bool(manifest.get('textBackend'))
    if webgpu and scope == 'contracts':
        scope = 'webgpu'
    LocalSemanticProvider(manifest)  # Registry validation only; no neural import.
    if webgpu:
        from short_mixed_provider import verify_backend_artifacts
        verify_backend_artifacts(manifest)
    if manifest['datasetSha256'] != sha256_file(dataset):
        raise ValueError('evaluation packet differs from this trained provider; freeze a separately specified holdout protocol')
    files = _code_files(webgpu)
    missing = [name for name in files if not (BASE / name).is_file()]
    if missing:
        raise ValueError('evaluation code not ready: ' + ','.join(missing))
    snapshot_id = 'evaluation-' + run_id
    code_snapshot = training.snapshot_code(snapshot_id, files)
    if dataset.parent == training.DATA.resolve():
        data_snapshot = training.snapshot_data(snapshot_id, dataset)
    else:
        # A trained provider may point at an earlier immutable source packet.
        # Bind its companion provenance rather than a subsequently authored
        # active manifest or sources file. These exact bytes already persist.
        data_snapshot = {name: {'path': str(source), 'sha256': sha256_file(source)}
                         for name, source in (('supervision.jsonl.gz', dataset),
                                              ('manifest.json', dataset.parent / 'manifest.json'),
                                              ('sources.jsonl', dataset.parent / 'sources.jsonl'))}
    provider_snapshot = Path(code_snapshot['directory']).parent.parent / 'data' / snapshot_id / 'provider.json'
    provider_snapshot.parent.mkdir(parents=True, exist_ok=True)
    with provider_snapshot.open('xb') as stream:
        stream.write(provider_path.read_bytes())
    authority = _preview_authority(scope)
    authority_files = {}
    for source, expected in (authority['sourceFiles'] if scope != 'webgpu_text' else {}).items():
        from short_preview import read_authority_source
        raw = read_authority_source(source, expected_sha256=expected)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('pinned A authority source mismatch: ' + source)
        destination = Path(code_snapshot['directory']) / 'authority' / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(raw)
        authority_files[source] = {'path': str(destination), 'sha256': expected}
    cases = register_cases(rows, scope)
    all_case_count = len(register_cases(rows, 'all'))
    representation_counts = {name: sum(r['split'] == 'train' and r['component'] == 'D02.2' and
                                      r['input'].get('representation') == name for r in rows)
                             for name in CONFIG['representationSubarms']}
    plan = {'schema': 'jity-d-short-evaluation-plan-v1', 'runId': run_id,
            'backendMode': 'qwen_webgpu' if webgpu else 'historical_local_encoder',
            'preparedAt': timestamp(), 'config': configuration(scope),
            'provider': {'path': str(provider_path), 'sha256': sha256_file(provider_path),
                         'identity': digest(manifest), 'trainingRunId': manifest['runId']},
            'dataset': {'path': str(dataset), 'sha256': sha256_file(dataset),
                        'inventory': training.validate_rows(rows)},
            'codeSha256': {name: sha256_file(BASE / name) for name in files},
            'codeSnapshot': code_snapshot, 'dataSnapshot': data_snapshot,
            'providerSnapshot': {'path': str(provider_snapshot), 'sha256': sha256_file(provider_snapshot)},
            'previewAuthority': authority, 'authoritySnapshot': authority_files,
            'environment': {'venvExecutableRelativePath': sys.executable, 'pythonVersion': sys.version,
                            'versions': {name: importlib.metadata.version(name) for name in ('torch', 'transformers', 'sentencepiece', 'numpy', 'pydantic')}},
            'cases': cases, 'arms': list(ARMS),
            'selection': {'scope': scope, 'literalComponentRegex': CONTRACT_SELECTION if scope in ('contracts', 'webgpu') else 'all',
                          'webgpuAdditionalText': ('first_row_per_primitive_text_task_in_file_order' if scope == 'webgpu_text' else
                                                   'first_row_per_primitive_text_task_and_heldout_source_in_file_order' if webgpu else None),
                          'literalSplits': ['development', 'test'], 'liveSelection': 'every_distinct_D02.1_input.context; never_target',
                          'initializationSelection': 'first_D01.1_brief_per_source_in_frozen_file_order; initial_time_from_first_same_source_D02.1_initial_world',
                          'pureTimeSelection': 'first_D02.1_world_per_source_in_frozen_file_order; no_actions_or_teacher_outcomes',
                          'registeredCaseCount': len(cases), 'allAvailableCaseCount': all_case_count,
                          'caseCountsByScope': {key: sum(c['scope'] == key for c in cases)
                                               for key in CONFIG['caseDeadlineSeconds']},
                          'liveInputKinds': {key: sum(c.get('inputKind') == key for c in cases)
                                             for key in dict.fromkeys(c['inputKind'] for c in cases if c['scope'] == 'live_upstream')},
                          'primitiveDiagnosticRowsNotRepeated': all_case_count - len(cases),
                          'primitiveEvidenceRecord': manifest.get('recordPath'),
                          'selectionBasis': 'component_contract_names_before_reading_model_results'},
            'comparisonArms': (['diagnostic_correct_intermediate'] if scope == 'webgpu_text' else
                               ['diagnostic_correct_intermediate', 'live_upstream', 'live_initialization', 'live_pure_time']),
            'referenceDefaultPromoted': False,
            'representationTrainingExamples': representation_counts,
            'untrainedRepresentationInputs': [name for name, count in representation_counts.items() if count == 0],
            'rollPolicy': {'mode': 'offline_actual_sample_not_production_receipt',
                           'ruleVersion': 'reaction-d20-v1', 'target': 11, 'sides': 20,
                           'eligibility': 'not_in_confirmed_prefix', 'seed': CONFIG['seed'],
                           'streamBinding': 'sourceGroup_and_full_initial_context_shared_across_representations'},
            'previewPolicy': {'scope': authority['mode'], 'committed': False,
                              'usedByRegisteredWorkload': scope != 'webgpu_text',
                              'actionChainTime': {'boundary': 'instant', 'duration': {'amount': 0, 'unit': 'second'}},
                              'pureTime': 'D08.1_actual_model_output_locked_once_then_all_U1_U6',
                              'initialization': 'pinned_A_WorldInitialState_validation_offline_candidate_only'},
            'thresholds': {'structure': 1.0, 'requiredCoverage': 1.0, 'criticalSemanticErrors': 0,
                           'fullRequestWallMs': 500, 'humanSemanticReviewRequired': True},
            'scoring': {'targets': 'assistant_draft_exact_match_only', 'humanReview': 'pending',
                        'providedAttemptControls': 'classification_and_transmission_only_not_autonomous_planning',
                        'inputKindMetadata': 'plan_and_summary_only_never_provider_input',
                        'missingHeadsExcludedFromTrainedAccuracy': True, 'semanticPass': 'not_established'},
            'retryPolicy': {'maxRetries': 0, 'retainFirstOutput': True, 'upstreamFailure': 'downstream_not_started_no_gold'},
            'deadlinePolicy': {'mode': 'cooperative_at_primitive_start_and_finished',
                               'lateOutput': 'retain_raw_then_reject_as_incomplete',
                               'blockedPrimitive': 'record_full_input_and_modelCalled_false',
                               'inFlightPrimitive': 'not_interrupted; common_process_supervisor_enforces_total_wall',
                               'unstartedSlots': 'retain_all; continuation_requires_new_frozen_remaining_case_list',
                               'budgetBasis': (str(configuration(scope)['processWallSeconds']) + '_seconds_including_browser_attach_load_and_registered_cases; not_full_game_request' if webgpu else
                                               'r1_894_seconds_for_333_cases; 1800_seconds_total_including_new_D01_and_pure_time_workloads')},
            'workload': {'scope': 'fourteen_direct_text_tasks_only' if scope == 'webgpu_text' else 'offline_D01_D02_D06_and_D08_D06_plus_component_diagnostics',
                         'CGeneration': 'not_connected', 'readyWait': 'not_measured',
                         'ABCommit': 'not_connected', 'automaticFollowups': 'diagnostic_only',
                         'fullRequestMeasured': False, 'fullRequest500ms': 'unmeasured'},
            'formalEvaluationAllowed': False, 'semanticQualityApproved': False}
    ART.mkdir(parents=True, exist_ok=True)
    exclusive(path, plan)
    return path


def verify(plan):
    if plan.get('schema') != 'jity-d-short-evaluation-plan-v1' or plan['config'] != configuration(plan['config'].get('diagnosticScope', 'contracts')) or plan['arms'] != list(ARMS):
        raise ValueError('evaluation policy drift; freeze a new plan')
    if set(plan['codeSha256']) != set(_code_files(plan.get('backendMode') == 'qwen_webgpu')):
        raise ValueError('incomplete evaluation code identity')
    for name, expected in plan['codeSha256'].items():
        if sha256_file(BASE / name) != expected:
            raise ValueError('evaluation code drift: ' + name)
        if plan['codeSnapshot']['files'].get(name) != expected or sha256_file(Path(plan['codeSnapshot']['directory']) / name) != expected:
            raise ValueError('evaluation source snapshot drift: ' + name)
    for snapshot in [*plan['dataSnapshot'].values(), plan['providerSnapshot']]:
        if sha256_file(Path(snapshot['path'])) != snapshot['sha256']:
            raise ValueError('evaluation immutable snapshot drift')
    if plan['providerSnapshot']['sha256'] != plan['provider']['sha256']:
        raise ValueError('provider snapshot identity mismatch')
    if _preview_authority(plan['config']['diagnosticScope']) != plan['previewAuthority'] or set(plan['authoritySnapshot']) != set(plan['previewAuthority']['sourceFiles']):
        raise ValueError('preview authority registration drift')
    for source, snapshot in plan['authoritySnapshot'].items():
        if snapshot['sha256'] != plan['previewAuthority']['sourceFiles'][source] or sha256_file(Path(snapshot['path'])) != snapshot['sha256']:
            raise ValueError('pinned A source snapshot drift')
    if sha256_file(Path(plan['provider']['path'])) != plan['provider']['sha256']:
        raise ValueError('provider manifest drift')
    manifest = common.read_json(plan['provider']['path'])
    if digest(manifest) != plan['provider']['identity']:
        raise ValueError('provider identity drift')
    if manifest['datasetSha256'] != plan['dataset']['sha256']:
        raise ValueError('training/evaluation packet identity mismatch')
    LocalSemanticProvider(manifest)
    if plan.get('backendMode') == 'qwen_webgpu':
        from short_mixed_provider import verify_backend_artifacts
        verify_backend_artifacts(manifest)
    for spec in manifest['models'].values():
        checkpoint = Path(spec['checkpoint']['path'])
        if not checkpoint.is_absolute():
            checkpoint = training.ROOT / checkpoint
        if sha256_file(checkpoint) != spec['checkpoint']['sha256']:
            raise ValueError('trained checkpoint drift')
        for item in spec['files']:
            if sha256_file(Path(spec['directory']) / item['path']) != item['observedSha256']:
                raise ValueError('base model/tokenizer drift')
    if sha256_file(Path(plan['dataset']['path'])) != plan['dataset']['sha256']:
        raise ValueError('evaluation data drift')
    rows = training.load_rows(plan['dataset']['path'])
    if training.validate_rows(rows) != plan['dataset']['inventory'] or register_cases(rows, plan['config']['diagnosticScope']) != plan['cases']:
        raise ValueError('case or source split drift')
    if sys.version != plan['environment']['pythonVersion']:
        raise ValueError('Python environment drift')
    for name, version in plan['environment']['versions'].items():
        if importlib.metadata.version(name) != version:
            raise ValueError('dependency drift: ' + name)
    return rows, manifest


def _expected(row):
    """Scoring only; called after the provider settles and never passed to it."""
    target = row['target']
    if row['kind'] == 'annotation_only':
        return json.loads(target)
    if row.get('outputCodec') in ('fragment_or_end', 'fact_or_end'):
        return {'kind': 'end'} if target == END else {
            'kind': 'fragment' if row['outputCodec'] == 'fragment_or_end' else 'fact', 'text': target}
    return target


def diagnostic_case(session, row, manifest):
    payload = copy.deepcopy(row['input'])
    answer = session.call(row['component'], payload)
    direct = any(row['component'] in model.get('trainedComponents', []) for model in manifest['models'].values())
    # This is scoring after actual inference, never an inference-time adapter.
    # Only a precise semantic refusal can match these labels. Missing heads,
    # parser errors, timeouts, and arbitrary incomplete reasons cannot match.
    expected = _expected(row)
    abstention_reason, abstention_ids = None, []
    if row['component'] == 'D02.1' and expected == 'incomplete':
        abstention_reason = 'semantic_incomplete:D02.1'
    elif row['component'] == 'D05.2' and isinstance(expected, dict):
        judgments = expected.get('judgments', [])
        attempts = [a['attemptId'] for a in payload.get('attempts', [])]
        indexed = {j.get('attemptId'): j for j in judgments if isinstance(j, dict)}
        if (len(indexed) == len(judgments) == len(attempts) and set(indexed) == set(attempts)
                and all(j.get('label') in ('achieved', 'partial', 'not_achieved', 'incomplete') for j in indexed.values())):
            abstention_ids = [key for key in attempts if indexed[key]['label'] == 'incomplete']
            if abstention_ids:
                abstention_reason = 'semantic_incomplete:D05.2:' + ','.join(abstention_ids)
    return {'scope': 'diagnostic_correct_intermediate', 'component': row['component'],
            'sourceGroup': row['sourceGroup'], 'split': row['split'], 'inputHash': digest(payload),
            'trainedDirectTask': direct, 'compositeAnnotation': row['kind'] == 'annotation_only',
            'completion': json_value(answer),
            'draftComparisonEligible': abstention_reason is None,
            'draftExactMatch': abstention_reason is None and answer.status == 'result' and digest(answer.value) == digest(expected),
            'expectedSemanticIncomplete': abstention_reason is not None,
            'expectedSemanticIncompleteReason': abstention_reason,
            'expectedSemanticIncompleteAttemptIds': abstention_ids,
            'semanticAbstentionMatches': abstention_reason is not None and answer.status == 'incomplete' and answer.reason == abstention_reason,
            'targetHash': digest(row['target']), 'semanticReview': 'pending',
            'autonomousPlanningEvidence': False}


def offline_roller(context, group_id, seed, checkpoint):
    """Frozen offline RNG is a program rule; receipt is never an outcome label."""
    rng, receipts = random.Random(seed), []
    acted = {r['memberId'] for r in context['confirmedPrefix']}
    def roll(source, targets):
        added = []
        for target in targets:
            value = rng.randint(1, 20)
            eligible = target not in acted
            row = {'rollId': group_id + ':roll:' + str(len(receipts) + 1),
                   'sourceId': source.actor_id, 'targetId': target, 'groupId': group_id,
                   'triggerKey': group_id + ':' + source.actor_id + ':' + target,
                   'ruleVersion': 'reaction-d20-v1', 'result': value, 'target': 11,
                   'eligible': eligible, 'admitted': eligible and value >= 11,
                   'eligibilityBaselineDigest': digest({'world': context['world'], 'confirmedPrefix': context['confirmedPrefix']})}
            receipts.append(copy.deepcopy(row)); added.append(row)
            checkpoint('offline_actual_roll', {'receipt': row, 'productionReceipt': False})
        return added
    return roll, receipts


def candidate_id(case_tag, kind, slot):
    """Bind both identities inside one digest; A Id permits at most 128 chars."""
    return 'eval-' + kind + ':' + digest({'case': case_tag, 'slot': slot})


def _measured_preview(preview, checkpoint):
    def call(request):
        before = len(getattr(preview, 'events', []))
        answer = preview(request)
        for event in getattr(preview, 'events', [])[before:]:
            checkpoint('offline_A_preview', json_value(event))
        return answer
    return call


def initialization_case(session, case, row, source_row, config, checkpoint):
    """Autonomous D01 from brief; the initial-world reference provides time only."""
    from short_lifecycle import InitialDraft
    initial_time = copy.deepcopy(source_row['input']['context']['world']['initial'].get('initialTime')) if source_row else None
    actual_input = {'brief': row['input'].get('brief'), 'initialTime': initial_time}
    if digest(actual_input) != case['inputHash']:
        raise ValueError('initialization input differs from registration')
    stages = [{'stage': name, 'status': 'not_started'} for name in ('D01_generate', 'offline_A_initial_validation', 'offline_candidate_seal')]
    common_out = {'scope': 'live_initialization', 'stages': stages, 'committed': False,
                  'worldCreated': False, 'formalAuthority': False, 'CConnected': False,
                  'fullRequestMeasured': False}
    if initial_time is None or not isinstance(actual_input['brief'], str) or not actual_input['brief'].strip():
        answer = incomplete('initialization_missing_source_brief_or_time')
        stages[0].update(status='incomplete', completion=json_value(answer))
        return {**common_out, 'completion': json_value(answer)}
    tag = digest({'case': case['caseId'], 'seed': config['seed']})
    # D01 nests draft IDs within task IDs twice, so use a bounded program ID.
    draft = InitialDraft('ed' + tag[:24], actual_input['brief'], initial_time)
    generated = draft.generate(session, max_tasks_per_character=config['maxNewTasks'])
    stages[0].update(status=generated.status, completion=json_value(generated))
    checkpoint('live_stage_settled', stages[0])
    if generated.status != 'result':
        for stage in stages[1:]:
            stage['reason'] = 'upstream_' + generated.status
        return {**common_out, 'completion': json_value(generated)}
    world_id = 'eval-world:' + tag
    def validate(candidate):
        from short_preview import _load_kernel, authority_identity
        event = {'candidate': {**copy.deepcopy(candidate), 'worldId': world_id},
                 'authority': authority_identity(), 'formalAuthority': False, 'worldCreated': False}
        begin = time.perf_counter()
        try:
            parsed = _load_kernel().contracts.WorldInitialState.model_validate(event['candidate'])
            event.update(status='result', parsedHash=digest(parsed.model_dump(mode='json')))
            return True
        except Exception as error:
            event.update(status='incomplete', error={'type': type(error).__name__, 'message': str(error)})
            raise
        finally:
            event['elapsedMs'] = (time.perf_counter() - begin) * 1000
            stages[1].update(status=event['status'], source='pinned_A_WorldInitialState',
                             candidateHash=digest(event['candidate']))
            checkpoint('offline_A_initial_validation', event)
    sealed = draft.seal(validate)
    stages[2].update(status=sealed.status, completion=json_value(sealed))
    checkpoint('live_stage_settled', stages[2])
    answer = result({**sealed.value, 'worldId': world_id}) if sealed.status == 'result' else sealed
    return {**common_out, 'completion': json_value(answer),
            'validationScope': 'offline_initial_candidate_validity_not_world_creation'}


def pure_time_case(session, case, row, config, checkpoint, preview_factory=None):
    """Actual D08 time proposal → complete U1–U6 scan, with no D05 facts."""
    from short_lifecycle import propose_time
    from short_settlement import run_updates
    world = copy.deepcopy(row['input']['context']['world'])
    if digest(world) != case['inputHash']:
        raise ValueError('pure-time world differs from registration')
    metadata = copy.deepcopy(case['offlinePointMetadata'])
    binding = {'pointId': metadata['id'], 'version': 1, 'epoch': 1}
    time_input = {'world': world, 'pointId': metadata['id'], 'timeLocked': False,
                  'timeAdvance': None, 'frozenActions': [], 'time_scan': True}
    stages = [{'stage': name, 'status': 'not_started'} for name in ('D08_time', 'D06')]
    common_out = {'scope': 'live_pure_time', 'stages': stages, 'committed': False,
                  'D05Executed': False, 'CConnected': False, 'fullRequestMeasured': False}
    proposed = propose_time(session, time_input)
    stages[0].update(status=proposed.status, completion=json_value(proposed))
    checkpoint('live_stage_settled', stages[0])
    if proposed.status != 'result':
        stages[1]['reason'] = 'upstream_' + proposed.status
        return {**common_out, 'completion': json_value(proposed)}
    point = {**metadata, 'timeAdvance': copy.deepcopy(proposed.value),
             'kind': 'normal' if proposed.value['boundary'] == 'elapsed' else 'instant',
             'linkedFromPointId': None if proposed.value['boundary'] == 'elapsed' else metadata['previousPointId']}
    checkpoint('offline_time_locked', {'point': point, 'inputHash': digest(time_input),
                                       'source': 'D08.1_actual_output', 'committed': False})
    tag = digest({'case': case['caseId'], 'seed': config['seed']})
    context = {'world': world, 'binding': binding, 'time_scan': True,
               'timeAdvance': copy.deepcopy(proposed.value),
               'timeFact': {'id': candidate_id(tag, 'time', 'D08.1'),
                            'timeAdvance': copy.deepcopy(proposed.value),
                            'source': {'component': 'D08.1', 'inputHash': digest(time_input)}}}
    try:
        if preview_factory is None:
            from short_preview import offline_preview
            preview_factory = offline_preview
        preview = preview_factory(world, binding, point=point, group_id=None, actor_ids=[])
        updates = run_updates(session, context, None, _measured_preview(preview, checkpoint),
                              lambda kind, slot: candidate_id(tag, kind, slot),
                              max_new_tasks=config['maxNewTasks'],
                              progress_sink=lambda progress: checkpoint('D06_progress', json_value(progress)))
    except Exception as error:
        updates = incomplete('offline_time_preview_or_update:' + type(error).__name__ + ':' + str(error))
    stages[1].update(status=updates.status, completion=json_value(updates))
    checkpoint('live_stage_settled', stages[1])
    return {**common_out, 'completion': json_value(updates), 'timeAdvance': proposed.value,
            'previewScope': 'offline_pinned_A_preview_point'}


def live_case(session, case, row, config, checkpoint, preview_factory=None):
    from short_intent import run_action_chain
    from short_settlement import settlement_context, settle_joint, run_updates
    context = copy.deepcopy(row['input']['context'])
    if digest(context) != case['inputHash']:
        raise ValueError('live context differs from registration')
    tag = digest({'case': case['caseId'], 'seed': config['seed']})
    binding = {'pointId': 'eval-point:' + tag, 'version': 1, 'epoch': 1}
    group_id = 'eval-group:' + tag
    # Natural-name and reference representations share the same RNG stream for
    # the same registered initial input. Only identities differ between arms.
    roll_seed = digest({'inputHash': case['inputHash'], 'sourceGroup': case['sourceGroup'], 'seed': config['seed']})
    roll, receipts = offline_roller(context, group_id, int(roll_seed[:16], 16), checkpoint)
    stages = [{'stage': name, 'status': 'not_started'} for name in ('D02_D03_D04', 'D05', 'D06')]
    chain = run_action_chain(session, context, 'eval-op:' + tag, roll_targets=roll,
                             max_sources=config['maxSources'], max_fragments=config['maxFragments'],
                             representation=case['representation'])
    stages[0].update(status=chain.status, completion=json_value(chain))
    checkpoint('live_stage_settled', stages[0])
    if chain.status != 'result':
        for stage in stages[1:]:
            stage['reason'] = 'upstream_' + chain.status
        return {'scope': 'live_upstream', 'stages': stages, 'completion': json_value(chain),
                'rolls': receipts, 'committed': False}
    try:
        context = settlement_context(context, chain, group_id=group_id, binding=binding)
        settlement = settle_joint(session, context, max_facts=config['maxFacts'])
    except Exception as error:
        settlement = incomplete('joint_input_or_call:' + type(error).__name__ + ':' + str(error))
    stages[1].update(status=settlement.status, completion=json_value(settlement))
    checkpoint('live_stage_settled', stages[1])
    if settlement.status != 'result':
        stages[2]['reason'] = 'upstream_' + settlement.status
        return {'scope': 'live_upstream', 'stages': stages, 'completion': json_value(settlement),
                'rolls': receipts, 'committed': False}
    try:
        if preview_factory is None:
            from short_preview import offline_preview
            preview_factory = offline_preview
        # Registered fixed point is only a D02-D06 offline workload boundary.
        point = copy.deepcopy(case['offlinePoint'])
        preview = preview_factory(context['world'], binding, point=point,
                                  group_id=context['group']['groupId'], actor_ids=context['group']['memberIds'])
        updates = run_updates(session, context, settlement.value, _measured_preview(preview, checkpoint),
                              lambda kind, slot: candidate_id(tag, kind, slot),
                              max_new_tasks=config['maxNewTasks'],
                              progress_sink=lambda progress: checkpoint('D06_progress', json_value(progress)))
    except Exception as error:
        updates = incomplete('offline_preview_or_update:' + type(error).__name__ + ':' + str(error))
    stages[2].update(status=updates.status, completion=json_value(updates))
    checkpoint('live_stage_settled', stages[2])
    return {'scope': 'live_upstream', 'stages': stages, 'completion': json_value(updates),
            'rolls': receipts, 'committed': False, 'previewScope': 'offline_pinned_A_preview_point',
            'CConnected': False, 'fullRequestMeasured': False}


class CaseBudgetExceeded(RuntimeError):
    pass


class CaseCheckpoints:
    """Bound a case at real primitive boundaries without fabricating outputs.

    The sink always persists a finished model event before a late value is
    rejected. One in-flight neural call cannot be interrupted cooperatively;
    the existing process supervisor remains the total-wall backstop.
    """
    def __init__(self, sink, config, scope, *, started_ns=None, clock=None):
        self.sink, self.config = sink, config
        self.clock = clock or time.monotonic_ns
        self.started_ns = self.clock() if started_ns is None else started_ns
        self.deadline_seconds = config['caseDeadlineSeconds'][scope]
        self.deadline_ns = self.started_ns + int(self.deadline_seconds * 1e9)
        self.failure_reason = None
        self.counters = {'primitiveCalls': 0, 'primitiveBlockedBeforeCall': 0,
                         'encoderForwards': 0, 'generatorInvocations': 0,
                         'providerCallInclusiveMs': 0., 'DModelComputeMs': 0.,
                         'coldLoadMs': 0., 'requestLoadMs': 0.,
                         'AOfflinePreviewCalls': 0, 'AOfflinePreviewMs': 0.,
                         'AOfflineInitialValidationMs': 0.}

    def __call__(self, name, payload):
        if name == 'semantic_call_started':
            reason = ('case_deadline_before_primitive' if self.clock() >= self.deadline_ns else
                      'frozen_primitive_call_budget' if self.counters['primitiveCalls'] >= self.config['maxPrimitiveCallsPerCase'] else None)
            if reason is not None:
                self.failure_reason = reason
                self.counters['primitiveBlockedBeforeCall'] += 1
                self.sink('primitive_not_started', {'reason': reason, 'modelCalled': False,
                                                   'deadlineSeconds': self.deadline_seconds,
                                                   'attemptedCall': json_value(payload)})
                raise CaseBudgetExceeded(reason)
            self.counters['primitiveCalls'] += 1
        if name == 'encoder_forward_started': self.counters['encoderForwards'] += 1
        if name == 'generator_forward_started': self.counters['generatorInvocations'] += 1
        if name in ('encoder_forward_settled', 'generator_forward_settled'):
            self.counters['DModelComputeMs'] += payload['elapsedMs']
        if name == 'semantic_call_finished': self.counters['providerCallInclusiveMs'] += payload['elapsedMs']
        if name == 'request_model_load':
            self.counters['requestLoadMs'] += payload['elapsedMs']
            self.counters['coldLoadMs'] += payload['elapsedMs']
        if name == 'offline_A_preview':
            self.counters['AOfflinePreviewCalls'] += 1
            self.counters['AOfflinePreviewMs'] += payload['elapsedMs']
        if name == 'offline_A_initial_validation':
            self.counters['AOfflineInitialValidationMs'] += payload['elapsedMs']
        reference = self.sink(name, payload)
        if name == 'semantic_call_finished' and self.clock() >= self.deadline_ns:
            self.failure_reason = 'case_deadline_late_primitive_output'
            self.sink('case_late_output_rejected', {'reason': self.failure_reason,
                                                   'rawCheckpoint': reference,
                                                   'component': payload.get('component'),
                                                   'deadlineSeconds': self.deadline_seconds,
                                                   'modelCalled': True})
            raise CaseBudgetExceeded(self.failure_reason)
        return reference

    def finish(self, outcome):
        if self.clock() >= self.deadline_ns:
            self.failure_reason = self.failure_reason or 'case_deadline_after_program_work'
        if self.failure_reason:
            self.sink('case_budget_incomplete', {'reason': self.failure_reason,
                                               'originalCompletion': outcome.get('completion')})
            outcome = {**outcome, 'completion': json_value(incomplete(self.failure_reason)),
                       'budgetFailure': self.failure_reason}
            if outcome.get('scope') == 'diagnostic_correct_intermediate':
                outcome['draftExactMatch'] = False
                outcome['semanticAbstentionMatches'] = False
        return outcome


def summarize(attempts):
    components, live = {}, []
    for attempt in attempts:
        outcome = attempt.get('outcome', {})
        if outcome.get('scope') == 'diagnostic_correct_intermediate':
            key = outcome['component']
            counts = components.setdefault(key, {'registered': 0, 'result': 0, 'empty': 0, 'incomplete': 0,
                                                 'draftMatches': 0, 'trainedDirect': 0, 'trainedDirectResults': 0,
                                                 'trainedDirectDraftMatches': 0, 'incompleteReasons': {},
                                                 'draftComparisonCases': 0, 'semanticAbstentionsExpected': 0,
                                                 'semanticAbstentionMatches': 0, 'semanticPassed': False})
            counts['registered'] += 1
            counts[outcome['completion']['status']] += 1
            counts['draftMatches'] += int(outcome['draftExactMatch'])
            counts['draftComparisonCases'] += int(outcome.get('draftComparisonEligible', True))
            counts['semanticAbstentionsExpected'] += int(outcome.get('expectedSemanticIncomplete', False))
            counts['semanticAbstentionMatches'] += int(outcome.get('semanticAbstentionMatches', False))
            counts['trainedDirect'] += int(outcome['trainedDirectTask'])
            counts['trainedDirectResults'] += int(outcome['trainedDirectTask'] and outcome['completion']['status'] == 'result')
            counts['trainedDirectDraftMatches'] += int(outcome['trainedDirectTask'] and outcome['draftExactMatch'])
            if outcome['completion']['status'] == 'incomplete':
                reason = outcome['completion'].get('reason') or 'unspecified_incomplete'
                counts['incompleteReasons'][reason] = counts['incompleteReasons'].get(reason, 0) + 1
        elif outcome.get('scope') in ('live_upstream', 'live_initialization', 'live_pure_time'):
            live.append({'caseId': attempt['caseId'], 'scope': outcome['scope'], 'completion': outcome['completion']['status'],
                         'reason': outcome['completion'].get('reason'),
                         'stages': [{k: v for k, v in stage.items() if k != 'completion'} for stage in outcome['stages']]})
    return {'components': components, 'liveCases': live, 'semanticQualityApproved': False,
            'humanReview': 'pending', 'fullRequest500ms': 'unmeasured'}


def worker(path):
    plan = common.read_json(path)
    rows, manifest = verify(plan)
    by_id = {r['exampleId']: r for r in rows}
    by_case = {c['caseId']: c for c in plan['cases']}
    _, out = paths(plan['runId'])
    slots = common.planned_slots(plan, ARMS)
    report = {'schema': 'jity-d-short-evaluation-record-v1', 'runId': plan['runId'],
              'planSha256': sha256_file(path), 'status': 'running', 'stages': [], 'attempts': [],
              'attemptSlots': slots, 'activeAttempt': None, 'formalEvaluationAllowed': False,
              'semanticQualityApproved': False, 'fullRequestMeasured': False,
              'checkpointStorage': common.CHECKPOINT_STORAGE}
    exclusive(out, report)
    identity = ModelIdentity(model=digest(manifest['models']), weights=digest({k: v['checkpoint'] for k, v in manifest['models'].items()}),
                             adapter=digest(manifest['tasks']), tokenizer=digest({k: v['files'] for k, v in manifest['models'].items()}),
                             precision=manifest['config']['precision'], implementation=digest(plan['codeSha256']))
    bridge, browser_journal = None, None
    try:
        with common.AppendJournal(out.with_suffix('.journal.jsonl'), report['planSha256']) as journal:
            journal.append('begin', {'runId': plan['runId'], 'slots': slots,
                                     'checkpointStorage': common.CHECKPOINT_STORAGE})
            if plan.get('backendMode') == 'qwen_webgpu':
                from short_mixed_provider import create_provider
                browser_journal_path = out.with_suffix('.webgpu.jsonl')
                browser_journal = common.AppendJournal(browser_journal_path, report['planSha256'])
                browser_lock = threading.RLock()
                def browser_evidence(kind, value):
                    with browser_lock:
                        return browser_journal.append('browser_event', {'name': kind, 'payload': json_value(value)})
                provider, bridge = create_provider(manifest, global_checkpoint=browser_evidence)
                identity = replace(provider.model_identity(), implementation=digest(plan['codeSha256']))
                def initialize_browser():
                    url = bridge.start()
                    print(json.dumps({'browserUrl': url, 'runId': plan['runId'], 'waitingForActualBrowser': True}), flush=True)
                    ready = bridge.wait_ready(plan['config']['browserAttachSeconds'], require_model=True)
                    report['browserBootstrap'] = ready
                    save(out, report)
                    if ready['status'] != 'ready':
                        raise ValueError('browser_initialization_incomplete:' + str(ready.get('reason')))
                    return ready
                common.record_stage(report, out, 'browser_initialization_and_ready_wait', initialize_browser)
            else:
                provider = LocalSemanticProvider(manifest, retain_observations=False)
            for slot in slots:
                attempt = {**slot, 'status': 'started', 'startedMonotonicNs': time.monotonic_ns(), 'checkpoints': []}
                report['activeAttempt'] = attempt
                journal.append('attempt_start', attempt)
                def persist(name, payload):
                    event = {k: attempt[k] for k in ('arm', 'caseId', 'repeat')}
                    event.update(name=name, payload=json_value(payload))
                    reference = common.append_checkpoint(journal, event)
                    attempt['checkpoints'].append(reference)
                    return reference
                case = by_case[slot['caseId']]
                checkpoint = CaseCheckpoints(persist, plan['config'], case['scope'],
                                             started_ns=attempt['startedMonotonicNs'])
                provider.checkpoint = checkpoint
                session = ModelSession(provider, binding={'runId': plan['runId'], 'caseId': slot['caseId'], 'provider': plan['provider']['identity']},
                                       identity=identity, retries=0, max_calls=plan['config']['maxCallsPerCase'],
                                       timeout_ms=plan['config']['callTimeoutMs'], cache=False, journal=checkpoint)
                if bridge is not None:
                    provider.text_backend.binding = copy.deepcopy(session.binding)
                    provider.text_backend.policy.update(cancelled=lambda current=session: current.cancelled,
                        binding_now=lambda current=session: copy.deepcopy(current.binding))
                try:
                    row = by_id[case['exampleId']]
                    if case['scope'] == 'diagnostic':
                        outcome = diagnostic_case(session, row, manifest)
                    elif case['scope'] == 'live_upstream':
                        outcome = live_case(session, case, row, plan['config'], checkpoint)
                    elif case['scope'] == 'live_initialization':
                        outcome = initialization_case(session, case, row, by_id.get(case['sourceExampleId']), plan['config'], checkpoint)
                    elif case['scope'] == 'live_pure_time':
                        outcome = pure_time_case(session, case, row, plan['config'], checkpoint)
                    else:
                        raise ValueError('unregistered evaluation scope')
                    attempt.update(status='complete', outcome=checkpoint.finish(outcome))
                except Exception as error:
                    attempt.update(status='failed', completion='incomplete', error={'type': type(error).__name__, 'message': str(error)})
                elapsed = (time.monotonic_ns() - attempt['startedMonotonicNs']) / 1e6
                attempt['timing'] = {**checkpoint.counters, 'caseWallMs': elapsed,
                                     'caseDeadlineSeconds': checkpoint.deadline_seconds,
                                     'budgetFailure': checkpoint.failure_reason,
                                     'modelCalled': bool(checkpoint.counters['encoderForwards'] or checkpoint.counters['generatorInvocations']),
                                     'programAndEvidenceMs': None,
                                     'programMeasurement': 'included_in_case_wall_not_separately_instrumented',
                                     'bucketOverlap': 'provider_call_includes_load_tokenization_forwards_and_nested_logging',
                                     'neuralComputeCoverage': 'encoder_windows_and_generator_generate; small_linear_heads_not_separately_timed',
                                     'counterSemantics': {'encoderForwards': 'one_complete_encoder_window_forward',
                                                          'generatorInvocations': 'one_model.generate_call; not_decoder_token_forward_count',
                                                          'primitiveCalls': 'admitted_semantic_primitives; excludes_budget_refusals_before_model'},
                                     'serviceMs': None, 'CGenerationMs': None, 'readyWaitMs': None,
                                     'fullRequestMs': None, 'loadPolicy': 'lazy_cold_once_then_shared_immutable_weights'}
                attempt['highLevelCalls'] = len(session.attempts)
                journal.append('attempt_result', attempt)
                timing = {k: attempt[k] for k in ('arm', 'caseId', 'repeat')}
                timing.update(resultJournalMs=0., snapshotEndMs=0., elapsedThroughResultMs=(time.monotonic_ns() - attempt['startedMonotonicNs']) / 1e6)
                journal.append('attempt_settled', timing)
                attempt.update(timing)
                report['attempts'].append(attempt); report['activeAttempt'] = None
                # Complete raw observations already reside in append-only
                # checkpoints; release the provider's duplicate in-memory list.
                provider.observations.clear()
                if bridge is not None:
                    # Cancel this request identity without changing model state;
                    # bridge/job IDs quarantine any already-running late output.
                    session.cancel()
                save(out, report)
            report.update(status='diagnostic_completed', unexecutedAttempts=0, summary=summarize(report['attempts']))
    except Exception as error:
        report.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
    finally:
        if bridge is not None:
            bridge.close()
        if browser_journal is not None:
            browser_journal.__exit__(None, None, None)
            report['browserRawJournal'] = {'path': str(browser_journal_path),
                'sha256': sha256_file(browser_journal_path), 'events': browser_journal.seq,
                'retention': 'local_full_raw_append_only',
                'memoryMeasurement': 'Python_supervisor_RSS_only; browser_GPU_and_process_memory_not_measured'}
        save(out, report)
    return 0 if report['status'] == 'diagnostic_completed' else 1


def execute(path):
    return common.execute_plan(Path(path), paths=paths, verify=verify, worker_script=Path(__file__),
                               settle_stages=lambda report, reason: None, arms=ARMS)


def report(path):
    path = Path(path)
    plan = common.read_json(path)
    _, out = paths(plan['runId'])
    stored = out if out.exists() else out.with_suffix(out.suffix + '.gz')
    record = common.read_json(stored) if stored.exists() else None
    if record is not None and record.get('planSha256') != sha256_file(path):
        raise ValueError('historical plan/record identity mismatch')
    for name, expected in plan['codeSha256'].items():
        if sha256_file(Path(plan['codeSnapshot']['directory']) / name) != expected:
            raise ValueError('historical code snapshot drift: ' + name)
    for snapshot in [*plan['dataSnapshot'].values(), plan['providerSnapshot'], *plan['authoritySnapshot'].values()]:
        if sha256_file(Path(snapshot['path'])) != snapshot['sha256']:
            raise ValueError('historical frozen snapshot drift')
    drift = [name for name, expected in plan['codeSha256'].items()
             if not (BASE / name).is_file() or sha256_file(BASE / name) != expected]
    for key in ('dataset', 'provider'):
        current = Path(plan[key]['path'])
        if not current.is_file() or sha256_file(current) != plan[key]['sha256']:
            drift.append(key)
    attempted = {item['caseId'] for item in (record or {}).get('attempts', [])}
    active = (record or {}).get('activeAttempt')
    if active is not None:
        attempted.add(active['caseId'])
    unstarted = [case['caseId'] for case in plan['cases'] if case['caseId'] not in attempted]
    return {'runId': plan['runId'], 'registeredCases': len(plan['cases']),
            'unstartedCaseIds': unstarted, 'unstartedCaseCount': len(unstarted),
            'status': record['status'] if record else 'not_started',
            'summary': summarize(record['attempts']) if record else None,
            'supervisor': record.get('supervisor') if record else None,
            'frozenEvidenceVerified': True, 'currentSourceDrift': drift,
            'rerunStatus': 'new_freeze_required' if drift else 'original_identity_current',
            'formalEvaluationAllowed': False, 'fullRequest500ms': 'unmeasured'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=Path, required=True)
    raise SystemExit(worker(parser.parse_args().worker))
