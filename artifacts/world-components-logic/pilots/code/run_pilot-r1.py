"""Bounded, offline M02 development diagnostic on the already-reviewed 42 set.

Preparation freezes identities and configuration. Execution uses one CPU thread
in an isolated child with a supervising wall/RSS limit. Every attempt, including
invalid output and token overflow, is retained. No training or production writes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import resource
import signal
import statistics
import subprocess
import sys
import time

from lab import canonical_bytes, sha256_file, build_model_input, guard_case, decode_output
import review_io
from runtime_smoke import _publish_exclusive, _replace_content, import_stack, generation_attempt
from prepare_run_batch import observe_environment, observe_m02

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
ART = ROOT / 'artifacts/world-components-logic/pilots'
LOCAL = ROOT / '.local/world-components-logic'
REVIEW = ROOT / 'artifacts/world-components-logic/reviews/l3-review-5db17d61-2026-10-30T19-04-59-780Z.json'
CASES = ('dev-d02-01', 'dev-d03-01', 'dev-d04-01', 'dev-d05-01')
INSTRUCTIONS = {
    'D02': '根据完整世界、任务和个性判断当前人物行动。pending输入需重新判断可行性；consumed/expired不重复消费。只输出JSON {"kind":"act","text":"尝试的动作"}或{"kind":"skip"}，不宣布动作已经成功。',
    'D03': '分析当前已冻结源行动会牵连完整名册中的谁，已行动者仍可被牵连。只输出JSON {"targets":[{"targetId":"人物ID"}]}，允许空集。不生成骰点、准入或未来行动。',
    'D04': '结合全部已冻结威胁和实际判定、任务与个性，生成当前已准入人物的一次反应尝试。只输出反应正文；不改写已冻结动作，不保证成功，不自行分配目标或骰点。',
    'D05': '统一推导已闭合全组的自洽后果，考虑全部动作和骰点；骰点用于反应准入，不机械决定胜负。只输出JSON {"results":{"组成员ID":"后果正文"}}，results键恰好覆盖memberIds，不补新行动。',
}


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def save(path, value):
    _replace_content(path, canonical_bytes(value) + b'\n')


def exclusive(path, value):
    if not _publish_exclusive(path, canonical_bytes(value) + b'\n'):
        raise FileExistsError(f'已有证据不能覆盖：{path}')


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def paths(run_id):
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', run_id):
        raise ValueError('invalid run id')
    return ART / f'{run_id}.plan.json', ART / f'{run_id}.record.json'


def select_cases():
    packet = review_io.build_packet()
    claims = review_io._parse_json(REVIEW.read_text(encoding='utf-8'))
    result = review_io.reconcile_claims(claims, packet)
    opinions = {r['caseId']: r for r in claims['decisions']}
    rows = {c['caseId']: c for c in packet['cases']}
    selected = []
    for cid in CASES:
        c = rows[cid]
        if c['split'] != 'development' or opinions[cid]['decision'] != 'agree' or not guard_case({k: c[k] for k in (
                'caseId', 'sourceGroup', 'anchorCase', 'derivedFrom', 'split', 'purpose', 'task', 'stageCut', 'input')})['shouldCall']:
            raise ValueError(f'not an approved development callable input: {cid}')
        selected.append({k: c[k] for k in ('caseId', 'sourceGroup', 'anchorCase', 'derivedFrom', 'split', 'purpose', 'task', 'stageCut', 'input')})
    return selected, {'reviewerClaim': claims['reviewer'], 'reviewExportSha256': sha256_file(REVIEW),
                      'recorded': result['summary']['recorded'], 'agree': result['summary']['agree'],
                      'inputFileSha256': packet['inputSha256'], 'reviewFileSha256': packet['reviewDraftSha256'],
                      'provenanceFileSha256': packet['provenanceSha256'],
                      'reviewerIdentityAuthenticated': False, 'scope': 'user_initial_review_from_conversation_not_formal_double_blind'}


def prepare(run_id, max_input_tokens=512):
    plan_path, record_path = paths(run_id)
    if plan_path.exists() or record_path.exists():
        raise FileExistsError('use a new run id; prior evidence is immutable')
    cases, review = select_cases()
    environment, model = observe_environment(ROOT), observe_m02(ROOT)
    if not environment['registeredVersionsMatch'] or not model['allSixFilesFullyRehashedAndVerified']:
        raise ValueError('isolated environment or M02 identity mismatch')
    config = {'device': 'cpu', 'threads': 1, 'concurrency': 1, 'seed': 42,
              'attemptsPerCase': 5, 'maxInputTokens': max_input_tokens,
              'maxNewTokens': {'D02': 128, 'D03': 96, 'D04': 128, 'D05': 256},
              'softGenerationSeconds': 3, 'processWallSeconds': 120, 'maxResidentMiB': 2048,
              'doSample': False, 'truncation': False, 'serialization': 'complete_canonical_json',
              'tokenizerExtraIds': 0, 'resizeEmbeddings': False,
              'iterationOrder': 'repeat_outer_then_D02_D03_D04_D05', 'networkAllowed': False}
    code = {str(p.relative_to(ROOT)): sha256_file(p) for p in
            (Path(__file__), BASE/'lab.py', BASE/'runtime_smoke.py', BASE/'review_io.py', BASE/'prepare_run_batch.py')}
    plan = {'schema': 'jity-d-exploratory-pilot-plan-v1', 'runId': run_id, 'preparedAt': timestamp(),
            'sourceHead': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'code': code, 'config': config, 'configSha256': digest(config),
            'authorization': {'status': 'explicit_user_instruction', 'recordedAt': timestamp(),
                'instruction': '对啊那进行运行适配并安排小批实测啊，你在这让我审批啥呢，你给我总结，每次提交的进度，我要查看你的工作',
                'scope': 'restore_bounded_local_CPU_development_diagnostic_and_adaptation',
                'resourceWindow': 'this_user_requested_turn_one_process_one_CPU_thread_no_GPU_no_BC_services'},
            'environment': environment, 'model': model, 'review': review,
            'cases': cases, 'caseSha256': {c['caseId']: digest(c) for c in cases},
            'instructions': INSTRUCTIONS, 'instructionSha256': digest(INSTRUCTIONS),
            'sourceIndependence': 'unverified_BC_receipts_pending_explicit_exploration_only',
            'formalEvaluationAllowed': False, 'fullRequestClaimAllowed': False,
            'performanceTarget': {'localEngineeringMs': 50, 'fullRequestMs': 500,
                                  'scope': 'independent_component_calls_not_full_request'},
            'trainingPerformed': False, 'sealedCandidatesExposed': False}
    exclusive(plan_path, plan)
    return plan_path


def verify_plan(plan):
    if plan['authorization']['status'] != 'explicit_user_instruction' or plan['formalEvaluationAllowed'] is not False:
        raise ValueError('invalid exploratory execution scope')
    if plan['configSha256'] != digest(plan['config']) or plan['instructionSha256'] != digest(plan['instructions']):
        raise ValueError('configuration/instruction changed')
    config = plan['config']
    if (config['device'] != 'cpu' or config['threads'] != 1 or config['concurrency'] != 1
            or config['truncation'] is not False or config['doSample'] is not False
            or not 1 <= config['attemptsPerCase'] <= 5
            or not 0 < config['processWallSeconds'] <= 120
            or not 0 < config['maxResidentMiB'] <= 2048):
        raise ValueError('bounded diagnostic policy changed')
    for name, expected in plan['code'].items():
        if sha256_file(ROOT / name) != expected:
            raise ValueError(f'code changed after preparation: {name}')
    current, review = select_cases()
    if review != plan['review'] or current != plan['cases']:
        raise ValueError('reviewed inputs changed')
    for c in plan['cases']:
        if digest(c) != plan['caseSha256'][c['caseId']] or c['split'] != 'development':
            raise ValueError('case identity/split changed')
    current_model = observe_m02(ROOT)
    if current_model != plan['model'] or not current_model['allSixFilesFullyRehashedAndVerified']:
        raise ValueError('model identity changed')


def peak_rss_mib():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024 if sys.platform == 'darwin' else 1024)


def run_attempt(case, plan, ns, tokenizer, model, repeat):
    started = time.perf_counter()
    config = plan['config']
    record = {'caseId': case['caseId'], 'sourceGroup': case['sourceGroup'], 'task': case['task'],
              'repeat': repeat, 'stage': case['stageCut'], 'arm': 'M02-direct-zero-shot',
              'modelId': plan['model']['modelId'], 'configSha256': plan['configSha256'],
              'modelRevision': plan['model']['revision'], 'deviceId': platform.machine()+'-cpu-1thread',
              'runId': plan['runId'], 'epoch': 1, 'status': 'started', 'raw': '',
              'semanticReview': 'pending_not_automatically_approved'}
    try:
        guard = guard_case(case)
        if not guard['shouldCall']:
            record.update(status='guarded', guard=guard, generationPerformed=False)
            return record
        projected = build_model_input(case)
        record['modelInputSha256'] = digest(projected)
        record['prompt'] = plan['instructions'][case['task']] + '\n完整当前阶段资料：\n' + canonical_bytes(projected).decode('utf-8')
        record['promptSha256'] = hashlib.sha256(record['prompt'].encode()).hexdigest()
        encode_start = time.perf_counter()
        encoded = tokenizer(record['prompt'], return_tensors='pt', truncation=False)
        record['encodeMs'] = (time.perf_counter() - encode_start) * 1000
        record['inputTokens'] = int(encoded['input_ids'].shape[-1])
        if record['inputTokens'] > config['maxInputTokens']:
            record.update(status='input_overflow', structureStatus='not_evaluated', generationPerformed=False)
            return record
        generation_start = time.perf_counter()
        criteria = ns['StoppingCriteriaList']([ns['MaxTimeCriteria'](max_time=config['softGenerationSeconds'])])
        with ns['torch'].inference_mode():
            output = model.generate(**encoded, max_new_tokens=config['maxNewTokens'][case['task']],
                                    do_sample=False, use_cache=True, stopping_criteria=criteria)
        record['generateMs'] = (time.perf_counter() - generation_start) * 1000
        record['generationPerformed'] = True
        ids = output[0].tolist()
        record['outputTokenIds'] = ids
        record['outputTokensExcludingDecoderStart'] = max(0, len(ids)-1)
        record['finishedWithEos'] = bool(ids) and ids[-1] == model.generation_config.eos_token_id
        decode_start = time.perf_counter()
        record['raw'] = tokenizer.decode(output[0], skip_special_tokens=True)
        record['rawUtf8Sha256'] = hashlib.sha256(record['raw'].encode()).hexdigest()
        if not record['finishedWithEos']:
            record.update(status='incomplete', structureStatus='not_evaluated')
        else:
            try:
                record['parsed'] = decode_output(case['task'], record['raw'], case)
                record.update(status='complete', structureStatus='valid')
            except (ValueError, TypeError) as error:
                record.update(status='invalid_output', structureStatus='invalid',
                              parseError={'type': type(error).__name__, 'message': str(error)})
        record['decodeAndValidateMs'] = (time.perf_counter() - decode_start) * 1000
    except Exception as error:
        record.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
    finally:
        record['elapsedMs'] = (time.perf_counter() - started) * 1000
        record['settledElapsedMs'] = record['elapsedMs']
        record['peakResidentMiB'] = peak_rss_mib()
        record['fullRequestMeasured'] = False
    return record


def worker(plan_path):
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    _, out = paths(plan['runId'])
    report = {'schema': 'jity-d-exploratory-pilot-record-v1', 'runId': plan['runId'],
              'planSha256': sha256_file(plan_path), 'startedAt': timestamp(), 'status': 'running',
              'stages': [], 'attempts': [], 'plannedAttempts': len(plan['cases'])*plan['config']['attemptsPerCase'],
              'sourceIndependence': plan['sourceIndependence'], 'formalEvaluationAllowed': False,
              'fullRequestLatencyStatus': 'not_measured', 'semanticQualityStatus': 'not_approved',
              'modelsLoaded': False, 'generationCalls': 0}
    exclusive(out, report)
    def stage(name, fn):
        start = time.perf_counter()
        entry = {'stage': name, 'status': 'running'}
        report['stages'].append(entry); save(out, report)
        try:
            result = fn(); entry['status'] = 'complete'; return result
        except Exception as error:
            entry.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
            raise
        finally:
            entry['elapsedMs'] = (time.perf_counter()-start)*1000
            save(out, report)
    try:
        stage('verify_plan_and_model_files', lambda: verify_plan(plan))
        ns = stage('dependency_import', import_stack)
        directory = ROOT / plan['model']['directory']
        tokenizer = stage('tokenizer_load', lambda: ns['T5Tokenizer'].from_pretrained(directory, local_files_only=True, extra_ids=0, legacy=True))
        model = stage('model_load', lambda: ns['T5ForConditionalGeneration'].from_pretrained(directory, local_files_only=True, use_safetensors=True).to('cpu').eval())
        report.update(modelsLoaded=True, parameterCount=sum(p.numel() for p in model.parameters()),
                      tokenizerLength=len(tokenizer), embeddingRows=model.get_input_embeddings().num_embeddings)
        report['smoke'] = stage('nonbusiness_smoke', lambda: generation_attempt(ns, tokenizer, model))
        for repeat in range(plan['config']['attemptsPerCase']):
            for case in plan['cases']:
                report['activeAttempt'] = {'caseId': case['caseId'], 'repeat': repeat}
                save(out, report)
                attempt = run_attempt(case, plan, ns, tokenizer, model, repeat)
                report['attempts'].append(attempt)
                report['generationCalls'] += bool(attempt.get('generationPerformed'))
                save(out, report)
        report['status'] = 'diagnostic_completed'
    except Exception as error:
        report.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
    finally:
        report['finishedAt'] = timestamp()
        report['peakResidentMiB'] = peak_rss_mib()
        report['unexecutedAttempts'] = report['plannedAttempts']-len(report['attempts'])
        save(out, report)
    print(json.dumps({'record': str(out), 'status': report['status'], 'attempts': len(report['attempts'])}))
    return 0 if report['status'] == 'diagnostic_completed' else 1


def execute(plan_path):
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    _, record_path = paths(plan['runId'])
    if record_path.exists():
        raise FileExistsError('record exists; choose a new run id')
    try:
        verify_plan(plan)
    except Exception as error:
        exclusive(record_path, {'schema': 'jity-d-exploratory-pilot-record-v1', 'runId': plan['runId'],
            'planSha256': sha256_file(plan_path), 'status': 'failed_preflight', 'attempts': [],
            'generationCalls': 0, 'formalEvaluationAllowed': False, 'fullRequestLatencyStatus': 'not_measured',
            'error': {'type': type(error).__name__, 'message': str(error)}})
        raise
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1', TOKENIZERS_PARALLELISM='false', HF_HUB_OFFLINE='1',
               TRANSFORMERS_OFFLINE='1', HF_HOME=str(LOCAL/'hf-cache'))
    python = ROOT / plan['environment']['venvExecutableRelativePath']
    started = time.monotonic(); peak = 0.; stopped = None; supervisor_error = None
    log_path = record_path.with_suffix('.process.log')
    with log_path.open('x', encoding='utf-8') as log:
        child = subprocess.Popen([str(python), str(Path(__file__)), '--worker', str(plan_path)],
                                 cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while child.poll() is None:
                rss = subprocess.run(['ps', '-o', 'rss=', '-p', str(child.pid)], capture_output=True, text=True)
                if rss.returncode or not rss.stdout.strip():
                    if child.poll() is not None: break
                    raise RuntimeError('cannot monitor child RSS; stopping bounded diagnostic')
                peak = max(peak, float(rss.stdout.strip())/1024)
                if peak > plan['config']['maxResidentMiB']:
                    stopped = 'resident_memory_limit'
                if time.monotonic()-started > plan['config']['processWallSeconds']:
                    stopped = 'process_wall_limit'
                if stopped:
                    os.killpg(child.pid, signal.SIGTERM)
                    try: child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL); child.wait()
                    break
                time.sleep(0.25)
        except Exception as error:
            stopped = 'supervisor_failure'
            supervisor_error = {'type': type(error).__name__, 'message': str(error)}
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL); child.wait()
    if record_path.exists():
        report = json.loads(record_path.read_text(encoding='utf-8'))
    else:
        report = {'schema': 'jity-d-exploratory-pilot-record-v1', 'runId': plan['runId'],
                  'planSha256': sha256_file(plan_path), 'attempts': [], 'status': 'failed_before_worker_journal'}
    report['supervisor'] = {'exitCode': child.returncode, 'stopReason': stopped,
                            'wallMs': (time.monotonic()-started)*1000, 'observedPeakResidentMiB': peak,
                            'rssMeasurement': 'ps_child_rss_every_250ms', 'processLog': str(log_path.relative_to(ROOT))}
    if supervisor_error:
        report['supervisor']['error'] = supervisor_error
    if stopped:
        report['status'] = 'stopped_incomplete'
    report['unexecutedAttempts'] = len(plan['cases'])*plan['config']['attemptsPerCase']-len(report['attempts'])
    if record_path.exists(): save(record_path, report)
    else: exclusive(record_path, report)
    print(json.dumps({'runId': plan['runId'], 'status': report['status'], 'attempts': len(report['attempts']),
                      'generationCalls': report.get('generationCalls', 0), 'record': str(record_path)}, ensure_ascii=False))
    return 0 if report['status'] == 'diagnostic_completed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', metavar='RUN_ID')
    mode.add_argument('--execute', type=Path, metavar='PLAN')
    mode.add_argument('--worker', type=Path, metavar='PLAN')
    parser.add_argument('--max-input-tokens', type=int, choices=(512, 1024, 2048), default=512)
    args = parser.parse_args()
    if args.prepare:
        print(prepare(args.prepare, args.max_input_tokens)); return 0
    if args.execute:
        return execute(args.execute)
    return worker(args.worker)


if __name__ == '__main__':
    raise SystemExit(main())
