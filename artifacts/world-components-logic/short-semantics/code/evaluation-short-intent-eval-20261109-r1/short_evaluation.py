"""Frozen, supervised local evaluation; no teacher output enters live inference.

Diagnostic targets are read only after inference for draft exact-match scoring.
Live cases use authored initial contexts, then actual model outputs exclusively.
This offline D scope does not commit a world, narrate, or measure a full request.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import time

import experiment as common
from lab import sha256_file
from run_pilot import exclusive, save, timestamp
from short_contracts import Completion, ModelIdentity, ModelSession, digest, incomplete, json_value
from short_training import END, LocalSemanticProvider
import short_experiment as training

BASE = Path(__file__).resolve().parent
ART = training.ART
ARMS = ('short_evaluation',)
CONFIG = {'processWallSeconds': 900, 'maxResidentMiB': 4096, 'attemptsPerCase': 1,
          'retries': 0, 'seed': 1729, 'maxCallsPerCase': 512,
          'maxPrimitiveCallsPerCase': 4096, 'callTimeoutMs': 120000,
          'maxFragments': 8, 'maxSources': 16, 'maxFacts': 32, 'maxNewTasks': 32,
          'cache': False, 'concurrency': 1, 'representationSubarms': ['natural', 'references']}
CONTRACT_SELECTION = r'^(D0[1-8]\.[1-6]|U[1-6]\.[12]|D06\.P\.(mapping|review))$'


def configuration(scope='contracts'):
    if scope not in ('contracts', 'all'):
        raise ValueError('unknown frozen evaluation scope')
    return {**copy.deepcopy(CONFIG), 'diagnosticScope': scope}


def paths(run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}', run_id):
        raise ValueError('invalid evaluation identity')
    return ART / ('evaluation-' + run_id + '.plan.json'), ART / ('evaluation-' + run_id + '.record.json')


def _code_files():
    # Authorship is offline preparation and is never imported by this worker.
    # A new independently versioned packet may be authored during inference.
    return sorted({name for name in training.CODE if not name.startswith('data/')} |
                  {'short_evaluation.py', 'short_preview.py'})


def register_cases(rows, scope='contracts'):
    """Register all held-out diagnostics and every distinct starting context.

    Never inspect target, scenario steps, authored facts, or result candidates to
    select a live case. NPC/consumed variants retain their original source group.
    """
    configuration(scope)
    cases, seen = [], set()
    for row in rows:
        if row['split'] not in ('development', 'test'):
            continue
        if scope == 'contracts' and not re.fullmatch(CONTRACT_SELECTION, row['component']):
            continue
        cases.append({'caseId': 'diagnostic:' + row['exampleId'], 'scope': 'diagnostic',
                      'exampleId': row['exampleId'], 'component': row['component'],
                      'kind': row['kind'], 'sourceGroup': row['sourceGroup'], 'split': row['split'],
                      'inputHash': digest(row['input'])})
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
            tag = digest({'case': case_id, 'seed': CONFIG['seed']})
            def highest_sequence(value):
                if isinstance(value, dict):
                    own = value.get('sourceSequence', 0)
                    return max([own if type(own) is int else 0] + [highest_sequence(v) for v in value.values()])
                if isinstance(value, list):
                    return max([0] + [highest_sequence(v) for v in value])
                return 0
            point = {'worldId': context['world']['worldId'], 'id': 'eval-point:' + tag,
                     'sequence': max(2, highest_sequence(context['world']) + 1), 'kind': 'instant',
                     'previousPointId': 'eval-predecessor:' + tag, 'roundId': 'eval-round:' + tag,
                     'advanceId': 'eval-advance:' + tag, 'trigger': 'player',
                     'linkedFromPointId': 'eval-predecessor:' + tag,
                     'timeAdvance': {'boundary': 'instant', 'duration': {'amount': 0, 'unit': 'second'}}}
            cases.append({'caseId': case_id,
                          'scope': 'live_upstream', 'exampleId': row['exampleId'],
                          'sourceGroup': row['sourceGroup'], 'split': row['split'],
                          'representation': representation, 'inputHash': digest(context), 'offlinePoint': point})
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
    LocalSemanticProvider(manifest)  # Registry validation only; no neural import.
    if manifest['datasetSha256'] != sha256_file(dataset):
        raise ValueError('evaluation packet differs from this trained provider; freeze a separately specified holdout protocol')
    files = _code_files()
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
    from short_preview import authority_identity
    authority = authority_identity()
    authority_files = {}
    for source, expected in authority['sourceFiles'].items():
        raw = subprocess.check_output(['git', 'show', authority['sourceCommit'] + ':' + source], cwd=training.ROOT)
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
            'selection': {'scope': scope, 'literalComponentRegex': CONTRACT_SELECTION if scope == 'contracts' else 'all',
                          'literalSplits': ['development', 'test'], 'liveSelection': 'every_distinct_D02.1_input.context; never_target',
                          'registeredCaseCount': len(cases), 'allAvailableCaseCount': all_case_count,
                          'primitiveDiagnosticRowsNotRepeated': all_case_count - len(cases),
                          'primitiveEvidenceRecord': manifest.get('recordPath'),
                          'selectionBasis': 'component_contract_names_before_reading_model_results'},
            'comparisonArms': ['diagnostic_correct_intermediate', 'live_upstream'],
            'referenceDefaultPromoted': False,
            'representationTrainingExamples': representation_counts,
            'untrainedRepresentationInputs': [name for name, count in representation_counts.items() if count == 0],
            'rollPolicy': {'mode': 'offline_actual_sample_not_production_receipt',
                           'ruleVersion': 'reaction-d20-v1', 'target': 11, 'sides': 20,
                           'eligibility': 'not_in_confirmed_prefix', 'seed': CONFIG['seed'],
                           'streamBinding': 'sourceGroup_and_full_initial_context_shared_across_representations'},
            'previewPolicy': {'scope': authority['mode'], 'committed': False,
                              'timeAdvance': {'boundary': 'instant', 'duration': {'amount': 0, 'unit': 'second'}},
                              'D08Executed': False},
            'thresholds': {'structure': 1.0, 'requiredCoverage': 1.0, 'criticalSemanticErrors': 0,
                           'fullRequestWallMs': 500, 'humanSemanticReviewRequired': True},
            'scoring': {'targets': 'assistant_draft_exact_match_only', 'humanReview': 'pending',
                        'missingHeadsExcludedFromTrainedAccuracy': True, 'semanticPass': 'not_established'},
            'retryPolicy': {'maxRetries': 0, 'retainFirstOutput': True, 'upstreamFailure': 'downstream_not_started_no_gold'},
            'workload': {'scope': 'offline_D02_D06_plus_component_diagnostics',
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
    if set(plan['codeSha256']) != set(_code_files()):
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
    from short_preview import authority_identity
    if authority_identity() != plan['previewAuthority'] or set(plan['authoritySnapshot']) != set(plan['previewAuthority']['sourceFiles']):
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
    return {'scope': 'diagnostic_correct_intermediate', 'component': row['component'],
            'sourceGroup': row['sourceGroup'], 'split': row['split'], 'inputHash': digest(payload),
            'trainedDirectTask': direct, 'compositeAnnotation': row['kind'] == 'annotation_only',
            'completion': json_value(answer),
            'draftExactMatch': answer.status == 'result' and digest(answer.value) == digest(_expected(row)),
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
        def measured_preview(request):
            before = len(getattr(preview, 'events', []))
            answer = preview(request)
            for event in getattr(preview, 'events', [])[before:]:
                checkpoint('offline_A_preview', json_value(event))
            return answer
        updates = run_updates(session, context, settlement.value, measured_preview,
                              lambda kind, slot: 'eval-' + kind + ':' + tag + ':' + slot,
                              max_new_tasks=config['maxNewTasks'],
                              progress_sink=lambda progress: checkpoint('D06_progress', json_value(progress)))
    except Exception as error:
        updates = incomplete('offline_preview_or_update:' + type(error).__name__ + ':' + str(error))
    stages[2].update(status=updates.status, completion=json_value(updates))
    checkpoint('live_stage_settled', stages[2])
    return {'scope': 'live_upstream', 'stages': stages, 'completion': json_value(updates),
            'rolls': receipts, 'committed': False, 'previewScope': 'offline_pinned_A_preview_point',
            'CConnected': False, 'fullRequestMeasured': False}


def summarize(attempts):
    components, live = {}, []
    for attempt in attempts:
        outcome = attempt.get('outcome', {})
        if outcome.get('scope') == 'diagnostic_correct_intermediate':
            key = outcome['component']
            counts = components.setdefault(key, {'registered': 0, 'result': 0, 'empty': 0, 'incomplete': 0,
                                                 'draftMatches': 0, 'trainedDirect': 0, 'trainedDirectResults': 0,
                                                 'trainedDirectDraftMatches': 0, 'incompleteReasons': {}, 'semanticPassed': False})
            counts['registered'] += 1
            counts[outcome['completion']['status']] += 1
            counts['draftMatches'] += int(outcome['draftExactMatch'])
            counts['trainedDirect'] += int(outcome['trainedDirectTask'])
            counts['trainedDirectResults'] += int(outcome['trainedDirectTask'] and outcome['completion']['status'] == 'result')
            counts['trainedDirectDraftMatches'] += int(outcome['trainedDirectTask'] and outcome['draftExactMatch'])
            if outcome['completion']['status'] == 'incomplete':
                reason = outcome['completion'].get('reason') or 'unspecified_incomplete'
                counts['incompleteReasons'][reason] = counts['incompleteReasons'].get(reason, 0) + 1
        elif outcome.get('scope') == 'live_upstream':
            live.append({'caseId': attempt['caseId'], 'completion': outcome['completion']['status'],
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
              'semanticQualityApproved': False, 'fullRequestMeasured': False}
    exclusive(out, report)
    identity = ModelIdentity(model=digest(manifest['models']), weights=digest({k: v['checkpoint'] for k, v in manifest['models'].items()}),
                             adapter=digest(manifest['tasks']), tokenizer=digest({k: v['files'] for k, v in manifest['models'].items()}),
                             precision=manifest['config']['precision'], implementation=digest(plan['codeSha256']))
    try:
        with common.AppendJournal(out.with_suffix('.journal.jsonl'), report['planSha256']) as journal:
            journal.append('begin', {'runId': plan['runId'], 'slots': slots})
            provider = LocalSemanticProvider(manifest)
            for slot in slots:
                attempt = {**slot, 'status': 'started', 'startedMonotonicNs': time.monotonic_ns(), 'checkpoints': []}
                report['activeAttempt'] = attempt
                journal.append('attempt_start', attempt)
                counters = {'primitiveCalls': 0, 'encoderForwards': 0, 'generatorForwards': 0,
                            'providerCallInclusiveMs': 0., 'DModelComputeMs': 0., 'coldLoadMs': 0., 'requestLoadMs': 0.,
                            'AOfflinePreviewCalls': 0, 'AOfflinePreviewMs': 0.}
                def checkpoint(name, payload):
                    if name == 'semantic_call_started':
                        counters['primitiveCalls'] += 1
                        if counters['primitiveCalls'] > plan['config']['maxPrimitiveCallsPerCase']:
                            raise ValueError('frozen_primitive_call_budget')
                    if name == 'encoder_forward_started': counters['encoderForwards'] += 1
                    if name == 'generator_forward_started': counters['generatorForwards'] += 1
                    if name in ('encoder_forward_settled', 'generator_forward_settled'):
                        counters['DModelComputeMs'] += payload['elapsedMs']
                    if name == 'semantic_call_finished': counters['providerCallInclusiveMs'] += payload['elapsedMs']
                    if name == 'request_model_load':
                        counters['requestLoadMs'] += payload['elapsedMs']
                        counters['coldLoadMs'] += payload['elapsedMs']
                    if name == 'offline_A_preview':
                        counters['AOfflinePreviewCalls'] += 1
                        counters['AOfflinePreviewMs'] += payload['elapsedMs']
                    event = {k: attempt[k] for k in ('arm', 'caseId', 'repeat')}
                    event.update(name=name, payload=json_value(payload))
                    journal.append('attempt_checkpoint', event)
                    attempt['checkpoints'].append(event)
                provider.checkpoint = checkpoint
                case = by_case[slot['caseId']]
                session = ModelSession(provider, binding={'runId': plan['runId'], 'caseId': slot['caseId'], 'provider': plan['provider']['identity']},
                                       identity=identity, retries=0, max_calls=plan['config']['maxCallsPerCase'],
                                       timeout_ms=plan['config']['callTimeoutMs'], cache=False, journal=checkpoint)
                try:
                    row = by_id[case['exampleId']]
                    if case['scope'] == 'diagnostic':
                        outcome = diagnostic_case(session, row, manifest)
                    else:
                        outcome = live_case(session, case, row, plan['config'], checkpoint)
                    attempt.update(status='complete', outcome=outcome)
                except Exception as error:
                    attempt.update(status='failed', completion='incomplete', error={'type': type(error).__name__, 'message': str(error)})
                elapsed = (time.monotonic_ns() - attempt['startedMonotonicNs']) / 1e6
                attempt['timing'] = {**counters, 'caseWallMs': elapsed,
                                     'programAndEvidenceMs': None,
                                     'programMeasurement': 'included_in_case_wall_not_separately_instrumented',
                                     'bucketOverlap': 'provider_call_includes_load_tokenization_forwards_and_nested_logging',
                                     'neuralComputeCoverage': 'encoder_windows_and_generator_generate; small_linear_heads_not_separately_timed',
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
                save(out, report)
            report.update(status='diagnostic_completed', unexecutedAttempts=0, summary=summarize(report['attempts']))
    except Exception as error:
        report.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
    finally:
        save(out, report)
    return 0 if report['status'] == 'diagnostic_completed' else 1


def execute(path):
    return common.execute_plan(Path(path), paths=paths, verify=verify, worker_script=Path(__file__),
                               settle_stages=lambda report, reason: None, arms=ARMS)


def report(path):
    path = Path(path)
    plan = common.read_json(path)
    _, out = paths(plan['runId'])
    record = common.read_json(out) if out.exists() else None
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
    return {'runId': plan['runId'], 'registeredCases': len(plan['cases']),
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
