"""Explicit profiling diagnostic using the existing D supervisor and journal.

No automatic production route is enabled. Each workload is on/off/on/off in one
browser session; repeats are registered measurements, never answer selection.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import json
from pathlib import Path
import re
import sys
import threading
import time

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import experiment as common
from lab import sha256_file
from run_pilot import digest, exclusive, save, timestamp
from short_contracts import ModelSession, json_value
from short_experiment import snapshot_code
from short_webgpu import BrowserBridge, WebGPUProvider

ROOT = BASE.parents[1]
ART = ROOT / 'artifacts/world-components-logic/qwen-short'
ARMS = ('profiling_comparison',)
COMPONENTS = ('D01.1.slot_label', 'U4.2')
MODES = ('default', 'off', 'default', 'off')
QUALIFICATIONS = ('task_trained', 'base_zero_shot_diagnostic')
BASE_DIAGNOSTIC_IDENTITY = '31fb901fe876af0b3fff2c6a519dd8fe75fab495ccf1875908b2d6a8ac125c81'
CODE = ('experiment.py', 'lab.py', 'run_pilot.py', 'runtime_smoke.py', 'review_io.py',
    'prepare_run_batch.py', 'pilot_codec.py', 'm01_probe.py', 'short_experiment.py',
    'short_training.py', 'short_data_migration.py', 'plan_training.py',
    'short_contracts.py', 'short_qwen_codec.py', 'short_webgpu.py',
    'short_webgpu/profile_comparison.py', 'short_webgpu/core.mjs', 'short_webgpu/worker.mjs',
    'short_webgpu/page.mjs', 'short_webgpu/index.html')
CONFIG = {'attemptsPerCase': 1, 'retries': 0, 'concurrency': 1, 'callTimeoutMs': 120000,
    'browserAttachSeconds': 180, 'processWallSeconds': 1200, 'maxResidentMiB': 1024,
    'maxInputTokens': 8192, 'maxNewTokens': 128, 'cache': False, 'threads': 1,
    'measurementOrder': list(MODES), 'sameDeviceSessionRequired': True,
    'repeatMeaning': 'pre_registered_repeated_measurement_not_retry_or_best_of',
    'scope': 'profiling_kernel_scheduling_readback_and_full_logging_cost_together',
    'browserAndGpuPeakMemoryMeasured': False}


def paths(run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}', run_id): raise ValueError('invalid_run_id')
    return ART / (run_id + '.plan.json'), ART / (run_id + '.record.json')


def workloads(source_plan):
    source_plan = Path(source_plan).resolve()
    plan = common.read_json(source_plan)
    source = plan['dataSnapshot']['supervision.jsonl.gz']
    if sha256_file(source['path']) != source['sha256']: raise ValueError('source_data_drift')
    chosen = [next(c for c in plan['cases'] if c['component'] == component) for component in COMPONENTS]
    ids = {c['exampleId'] for c in chosen}
    with gzip.open(source['path'], 'rt') as stream:
        rows = {row['exampleId']: row for line in stream if (row := json.loads(line))['exampleId'] in ids}
    result = []
    for index, case in enumerate(chosen):
        row = rows[case['exampleId']]
        if digest(row['input']) != case['inputHash']: raise ValueError('source_input_drift')
        result.append({'workloadId': 'short' if index == 0 else 'long', 'component': case['component'],
            'exampleId': case['exampleId'], 'sourceGroup': case['sourceGroup'], 'split': case['split'],
            'input': row['input'], 'inputHash': case['inputHash'], 'completeInput': True})
    return {'sourcePlan': {'path': str(source_plan), 'sha256': sha256_file(source_plan)},
        'sourceData': copy.deepcopy(source), 'workloads': result,
        'scope': 'two_actual_complete_inputs_not_full_chain', 'semanticQualityApproval': False}


def registered_cases(registered):
    return [{'caseId': f"{workload['workloadId']}:{index + 1}:{mode}",
        'workloadId': workload['workloadId'], 'component': workload['component'],
        'inputHash': workload['inputHash'], 'profilingMode': mode,
        'measurementIndex': index + 1, 'repeatedMeasurement': index > 0,
        'retry': False, 'orderBias': 'fixed_on_off_on_off_not_counterbalanced'}
        for workload in registered for index, mode in enumerate(MODES)]


def bridge_for(plan, checkpoint=None):
    return BrowserBridge(plan['assets']['model']['path'], plan['assets']['runtime']['path'],
        tokenizer_cases=plan['assets']['parity']['path'], checkpoint=checkpoint,
        allow_profiling_comparison=True)


def qualification_metadata(model, qualification='task_trained', trained_export_failure=None):
    """An explicit baseline diagnostic never requalifies rejected trained bytes."""
    if qualification not in QUALIFICATIONS:
        raise ValueError('unregistered_asset_qualification')
    provenance = model['provenance']; steps = provenance.get('trainingSteps', 0)
    if type(steps) is not int or steps < 0:
        raise ValueError('invalid_training_step_identity')
    if qualification == 'task_trained':
        if steps <= 0 or not set(COMPONENTS) <= set(provenance.get('trainedComponents', [])):
            raise ValueError('this_registered_comparison_requires_task_trained_assets')
        # BrowserBridge has already verified the complete strict export proof.
        return {'mode': qualification, 'trainingEffectEvidence': False,
            'scope': 'profiling_cost_of_one_qualified_trained_asset_not_a_training_ablation'}
    if (steps != 0 or model.get('identity') != BASE_DIAGNOSTIC_IDENTITY
            or provenance.get('sourceModel') != 'onnx-community/Qwen3-0.6B-ONNX'
            or provenance.get('sourceRevision') != '58ca03a5e7b354b480b1a82b34bde8dc7b854cc0'):
        raise ValueError('base_diagnostic_requires_exact_registered_zero_step_community_asset')
    if not trained_export_failure:
        raise ValueError('base_diagnostic_requires_explicit_trained_export_disposition')
    path = Path(trained_export_failure).resolve(); failure = common.read_json(path)
    if (failure.get('status') not in ('failed', 'incomplete', 'failed_validation', 'not_qualified')
            and failure.get('effectiveQualification') != 'failed_numerical_validation'):
        raise ValueError('trained_export_failure_evidence_not_final_or_not_failed')
    return {'mode': qualification, 'trainingEffectEvidence': False,
        'scope': 'unfinetuned_community_base_profiling_only', 'trainedWeightsExportQualified': False,
        'trainedExportDisposition': {'path': str(path), 'sha256': sha256_file(path),
            'runId': failure.get('runId'), 'status': failure.get('status'),
            'effectiveQualification': failure.get('effectiveQualification')}}


def freeze(run_id, source_plan, model_manifest, runtime_manifest, parity, venv, *,
           qualification='task_trained', trained_export_failure=None):
    plan_path, out = paths(run_id)
    if plan_path.exists() or out.exists(): raise FileExistsError('new_run_id_required')
    packet = workloads(source_plan)
    assets = {key: {'path': str(Path(path).resolve()), 'sha256': sha256_file(path)}
        for key, path in [('model', model_manifest), ('runtime', runtime_manifest), ('parity', parity)]}
    plan = {'schema': 'jity-webgpu-profiling-comparison-plan-v1', 'runId': run_id,
        'preparedAt': timestamp(), 'assets': assets, **packet, 'config': copy.deepcopy(CONFIG),
        'arms': list(ARMS), 'cases': registered_cases(packet['workloads']),
        'environment': {'venvExecutableRelativePath': str(Path(venv).resolve())},
        'paidServices': False, 'formalEvaluationAllowed': False, 'semanticQualityApproved': False,
        'fullRequestMeasured': False, 'productionIntegration': False}
    bridge = bridge_for(plan)
    plan['qualification'] = qualification_metadata(bridge.model, qualification, trained_export_failure)
    plan['browserConfiguration'] = bridge.configuration()
    plan['modelIdentity'] = bridge.model['identity']; plan['runtimeIdentity'] = bridge.runtime['identity']
    plan['codeSnapshot'] = snapshot_code(run_id, CODE)
    plan['codeSha256'] = plan['codeSnapshot']['files']
    exclusive(plan_path, plan)
    return plan_path


def verify(plan):
    if plan['config'] != CONFIG or plan['cases'] != registered_cases(plan['workloads']):
        raise ValueError('unregistered_comparison_schedule_or_resources')
    for name, expected in plan['codeSha256'].items():
        if sha256_file(BASE / name) != expected or sha256_file(Path(plan['codeSnapshot']['directory']) / name) != expected:
            raise ValueError('frozen_code_drift:' + name)
    for item in [*plan['assets'].values(), plan['sourcePlan'], plan['sourceData']]:
        if sha256_file(item['path']) != item['sha256']: raise ValueError('frozen_asset_or_source_drift:' + item['path'])
    if workloads(plan['sourcePlan']['path'])['workloads'] != plan['workloads']:
        raise ValueError('complete_workload_changed')
    bridge = bridge_for(plan)
    registered = plan.get('qualification', {'mode': 'task_trained'})
    failure = registered.get('trainedExportDisposition')
    if failure and sha256_file(failure['path']) != failure['sha256']:
        raise ValueError('trained_export_disposition_drift')
    expected = qualification_metadata(bridge.model, registered['mode'], failure['path'] if failure else None)
    if plan.get('qualification') != expected:
        raise ValueError('registered_asset_qualification_drift')
    if bridge.configuration() != plan['browserConfiguration']:
        raise ValueError('browser_configuration_drift')
    return True


def comparisons(attempts):
    result = []
    for workload in ('short', 'long'):
        rows = [a for a in attempts if a['caseId'].startswith(workload + ':')]
        for a, b in zip(rows[::2], rows[1::2]):
            av, bv = a.get('nativeOutput', {}), b.get('nativeOutput', {})
            result.append({'workloadId': workload, 'onCase': a['caseId'], 'offCase': b['caseId'],
                'bothComponentResults': a['completion']['status'] == b['completion']['status'] == 'result',
                'tokensIdentical': av.get('rawTokenIds') == bv.get('rawTokenIds')
                    if isinstance(av.get('rawTokenIds'), list) and isinstance(bv.get('rawTokenIds'), list) else None,
                'textIdentical': av.get('rawText') == bv.get('rawText')
                    if isinstance(av.get('rawText'), str) and isinstance(bv.get('rawText'), str) else None,
                'numericHeadComparison': 'not_applicable_two_registered_text_components',
                'onWallMs': a.get('elapsedIncludingTelemetryMs', a.get('elapsedThroughResultMs', a.get('callAndCheckpointWallMs'))),
                'offWallMs': b.get('elapsedIncludingTelemetryMs', b.get('elapsedThroughResultMs', b.get('callAndCheckpointWallMs'))),
                'wallScope': 'through_result_snapshot_and_settled_journal; final_metadata_save_in_supervisor_wall',
                'onGenerateMs': av.get('timings', {}).get('forwardMs'),
                'offGenerateMs': bv.get('timings', {}).get('forwardMs'),
                'sameDeviceSession': bool(av.get('deviceSessionId') and av.get('deviceSessionId') == bv.get('deviceSessionId')) if av and bv else None,
                'offPerRequestGpuProof': False, 'semanticQualityApproved': False})
    return result


def worker(plan_path):
    plan = common.read_json(plan_path); verify(plan)
    _, out = paths(plan['runId']); plan_sha = sha256_file(plan_path)
    slots = common.planned_slots(plan, ARMS)
    report = {'schema': 'jity-webgpu-profiling-comparison-record-v1', 'runId': plan['runId'],
        'planSha256': plan_sha, 'status': 'running', 'stages': [], 'attempts': [],
        'attemptSlots': slots, 'activeAttempt': None, 'checkpointStorage': common.CHECKPOINT_STORAGE,
        'formalEvaluationAllowed': False, 'semanticQualityApproved': False, 'fullRequestMeasured': False,
        'qualification': copy.deepcopy(plan.get('qualification'))}
    work = {w['workloadId']: w for w in plan['workloads']}
    cases = {c['caseId']: c for c in plan['cases']}
    browser_log = None; bridge = None; lock = threading.Lock()
    try:
        browser_log = common.AppendJournal(out.with_suffix('.webgpu.jsonl'), plan_sha)
        def global_event(name, payload):
            with lock: browser_log.append('browser_event', {'name': name, 'payload': json_value(payload)})
        bridge = bridge_for(plan, global_event)
        with common.AppendJournal(out.with_suffix('.journal.jsonl'), plan_sha) as journal:
            journal.append('begin', {'runId': plan['runId'], 'slots': slots,
                'checkpointStorage': common.CHECKPOINT_STORAGE, 'config': plan['config']})
            def initialize():
                url = bridge.start(); print(json.dumps({'browserUrl': url, 'runId': plan['runId']}), flush=True)
                ready = bridge.wait_ready(CONFIG['browserAttachSeconds'])
                report['browserBootstrap'] = ready
                if ready['status'] != 'ready': raise ValueError('browser_initialization_incomplete:' + str(ready.get('reason')))
            common.record_stage(report, out, 'browser_initialization_and_ready_wait', initialize)
            for slot in slots:
                case = cases[slot['caseId']]; workload = work[case['workloadId']]
                attempt = {**slot, 'status': 'started', 'startedMonotonicNs': time.monotonic_ns(),
                    'checkpoints': [], 'profilingMode': case['profilingMode'], 'measurementIndex': case['measurementIndex'],
                    'repeatedMeasurement': case['repeatedMeasurement'], 'retry': False}
                report['activeAttempt'] = attempt; journal.append('attempt_start', attempt)
                def persist(name, payload):
                    event = {k: attempt[k] for k in ('arm', 'caseId', 'repeat')}
                    event.update(name=name, payload=json_value(payload))
                    attempt['checkpoints'].append(common.append_checkpoint(journal, event))
                    if name == 'webgpu_browser_response':
                        native = payload['response']
                        attempt['nativeOutput'] = {k: native.get(k) for k in ('status', 'reason', 'rawText', 'rawTokenIds', 'eosReached', 'timings')}
                        attempt['nativeOutput']['deviceSessionId'] = native.get('deviceIdentity', {}).get('deviceSessionId')
                        attempt['nativeOutput']['gpuEvidence'] = native.get('gpuEvidence')
                binding = {'runId': plan['runId'], 'workloadId': case['workloadId'], 'planSha256': plan_sha}
                provider = WebGPUProvider(bridge, binding=binding, timeout_ms=CONFIG['callTimeoutMs'],
                    max_input_tokens=CONFIG['maxInputTokens'], max_new_tokens=CONFIG['maxNewTokens'],
                    profiling_mode=case['profilingMode'])
                provider.checkpoint = persist
                session = ModelSession(provider, binding=binding, identity=provider.model_identity,
                    retries=0, max_calls=1, timeout_ms=CONFIG['callTimeoutMs'], cache=False, journal=persist)
                answer = session.call(workload['component'], workload['input'])
                attempt.update(status='complete', completion=json_value(answer),
                    callAndCheckpointWallMs=(time.monotonic_ns() - attempt['startedMonotonicNs']) / 1e6)
                result_start = time.monotonic_ns()
                journal.append('attempt_result', attempt)
                result_ms = (time.monotonic_ns() - result_start) / 1e6
                report['attempts'].append(attempt); report['activeAttempt'] = None
                snapshot_start = time.monotonic_ns(); save(out, report)
                snapshot_ms = (time.monotonic_ns() - snapshot_start) / 1e6
                settled = {k: attempt[k] for k in ('arm', 'caseId', 'repeat')}
                settled.update(resultJournalMs=result_ms, snapshotEndMs=snapshot_ms,
                    elapsedThroughResultMs=(time.monotonic_ns() - attempt['startedMonotonicNs']) / 1e6)
                telemetry_start = time.monotonic_ns(); journal.append('attempt_settled', settled)
                telemetry_ms = (time.monotonic_ns() - telemetry_start) / 1e6
                attempt.update(settled, telemetryJournalMs=telemetry_ms,
                    elapsedIncludingTelemetryMs=(time.monotonic_ns() - attempt['startedMonotonicNs']) / 1e6)
                save(out, report)
            report.update(status='diagnostic_completed', comparisons=comparisons(report['attempts']), unexecutedAttempts=0)
    except Exception as error:
        report.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
    finally:
        if bridge: bridge.close()
        if browser_log:
            browser_log.close()
            report['browserRawJournal'] = {'path': str(out.with_suffix('.webgpu.jsonl')),
                'sha256': sha256_file(out.with_suffix('.webgpu.jsonl')), 'events': browser_log.seq}
        save(out, report)
    return 0 if report['status'] == 'diagnostic_completed' else 1


def execute(plan_path):
    return common.execute_plan(Path(plan_path), paths=paths, verify=verify,
        worker_script=Path(__file__), settle_stages=lambda report, reason: None, arms=ARMS)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--worker': return worker(Path(sys.argv[2]))
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    f = sub.add_parser('freeze')
    for key in ('run-id', 'source-plan', 'model-manifest', 'runtime-manifest', 'parity', 'venv'): f.add_argument('--' + key, required=True)
    f.add_argument('--qualification', choices=QUALIFICATIONS, default='task_trained')
    f.add_argument('--trained-export-failure', type=Path)
    e = sub.add_parser('execute'); e.add_argument('plan', type=Path)
    args = parser.parse_args()
    if args.command == 'execute': return execute(args.plan)
    print(freeze(args.run_id, args.source_plan, args.model_manifest, args.runtime_manifest, args.parity, args.venv,
        qualification=args.qualification, trained_export_failure=args.trained_export_failure))
    return 0


if __name__ == '__main__': raise SystemExit(main())
