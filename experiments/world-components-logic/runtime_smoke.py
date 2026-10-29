"""Bounded, single-CPU, non-business runtime smoke. Never evaluates D cases.

Engineering journaling is complete: dependency import, tokenizer load and
model load are journaled stages, the smoke record is written even when a
stage fails, and preparation plans are never silently overwritten (an
identical plan is reused; a differing one refuses and asks for --run-id).
Executing the inference path still awaits the L3 resume decision from the
user/coordinator after re-review. This smoke cannot establish semantic
quality, component latency or a 500 ms request.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from lab import canonical_bytes, sha256_file

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / '.local/world-components-logic'
REGISTRY = ROOT / 'artifacts/world-components-logic/l2-model-sources-20261029.json'
PROMPT = '运行检查：请写出“模型已载入”。'
RUN_ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')


def resolve_run_paths(run_id: str | None) -> tuple[Path, Path]:
    """Map an optional run id to the (plan, record) pair it registers."""
    if run_id is not None and not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError('run id must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}')
    suffix = f'-{run_id}' if run_id else ''
    return (LOCAL / f'runtime-smoke-plan{suffix}.json',
            ROOT / 'artifacts/world-components-logic' / f'l3-1-runtime-smoke{suffix}.json')


def write_plan(plan_path: Path, report: Mapping[str, Any]) -> str:
    """Freeze preparation identity without ever overwriting prior evidence.

    Byte-identical replanning reuses the existing plan; any difference
    refuses so an operator must decide (keep, remove explicitly, or
    register a new run id) instead of the file being replaced silently.
    """
    payload = canonical_bytes(report) + b'\n'
    if plan_path.exists():
        if plan_path.read_bytes() == payload:
            return 'reused'
        raise FileExistsError(f'preparation plan differs at {plan_path}; '
                              'preserve it and register a new run with --run-id')
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_bytes(payload)
    return 'written'


def _dependency_versions() -> dict[str, str]:
    return {d: importlib.metadata.version(d) for d in
            ('torch', 'transformers', 'safetensors', 'sentencepiece', 'tokenizers', 'numpy')}


def import_stack() -> dict[str, Any]:
    """Import the heavy stack single-threaded; journaled as one stage."""
    started = time.perf_counter()
    import torch
    from transformers import T5ForConditionalGeneration, T5Tokenizer
    from transformers.generation.stopping_criteria import MaxTimeCriteria, StoppingCriteriaList
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(42)
    return {'torch': torch, 'T5Tokenizer': T5Tokenizer,
            'T5ForConditionalGeneration': T5ForConditionalGeneration,
            'StoppingCriteriaList': StoppingCriteriaList, 'MaxTimeCriteria': MaxTimeCriteria,
            'importWallMs': (time.perf_counter() - started) * 1000}


def generation_attempt(ns: Mapping[str, Any], tokenizer: Any, model: Any) -> dict[str, Any]:
    """One synthetic non-business generation; captures partials on failure."""
    torch = ns['torch']
    started = time.perf_counter()
    record: dict[str, Any] = {'status': 'started', 'raw': '', 'stage': 'encode'}
    try:
        encoded = tokenizer(PROMPT, return_tensors='pt', truncation=False)
        record['inputTokens'] = int(encoded['input_ids'].shape[-1])
        record['stage'] = 'generate'
        criteria = ns['StoppingCriteriaList']([ns['MaxTimeCriteria'](max_time=3)])
        with torch.inference_mode():
            result = model.generate(**encoded, max_new_tokens=12, do_sample=False,
                                    stopping_criteria=criteria)
        record['outputTokenIds'] = result[0].tolist()
        record['raw'] = tokenizer.decode(result[0], skip_special_tokens=True)
        eos = model.generation_config.eos_token_id
        record['finishedWithEos'] = record['outputTokenIds'][-1] == eos
        record['status'] = 'complete' if record['finishedWithEos'] else 'incomplete'
        record['stage'] = 'decoded'
    except Exception as exc:
        record['status'] = 'failed'
        record['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        record['elapsedMs'] = (time.perf_counter() - started) * 1000
        record['settledElapsedMs'] = record['elapsedMs']
        record['note'] = 'Non-business synthetic request; no D component semantics or timing acceptance.'
    return record


def _journaled(stages: list[dict[str, Any]], stage: str, fn: Callable[[], Any]) -> Any:
    started = time.perf_counter()
    try:
        value = fn()
    except Exception as exc:
        stages.append({'stage': stage, 'status': 'failed',
                       'elapsedMs': (time.perf_counter() - started) * 1000,
                       'error': {'type': type(exc).__name__, 'message': str(exc)}})
        raise
    stages.append({'stage': stage, 'status': 'ok',
                   'elapsedMs': (time.perf_counter() - started) * 1000})
    return value


def run_with_journal(report: dict[str, Any], model_dir: Path, record_path: Path, *,
                     import_stack: Callable[[], Mapping[str, Any]],
                     load_tokenizer: Callable[[Mapping[str, Any], Path], Any],
                     load_model: Callable[[Mapping[str, Any], Path], Any],
                     generation_attempt: Callable[[Mapping[str, Any], Any, Any], dict[str, Any]]) -> dict[str, Any]:
    """Execute the smoke and write the record whatever the outcome.

    Every stage lands in report['stages'] with its elapsed time; on any
    failure the complete report (status, failedStage, error, stages) is
    persisted before the error propagates, so a crash can no longer leave
    the run unrecorded. Existing evidence is only ever appended to disk
    under this run's own record path, never rewritten in place.
    """
    stages: list[dict[str, Any]] = []
    report['stages'] = stages
    status, failed_stage = 'failed', None
    attempt: dict[str, Any] = {'status': 'failed', 'stage': 'unknown', 'raw': ''}
    started = time.perf_counter()
    try:
        ns = _journaled(stages, 'dependency_import', import_stack)
        report['runtimeImportWallMs'] = ns['importWallMs']
        tokenizer = _journaled(stages, 'tokenizer_load', lambda: load_tokenizer(ns, model_dir))
        load_ms = stages[-1]['elapsedMs']
        model = _journaled(stages, 'model_load', lambda: load_model(ns, model_dir))
        report['loadWallMs'] = load_ms + stages[-1]['elapsedMs']
        report['parameterCount'] = sum(p.numel() for p in model.parameters())
        report['tokenizerLength'] = len(tokenizer)
        report['embeddingRows'] = model.get_input_embeddings().num_embeddings
        attempt = generation_attempt(ns, tokenizer, model)
        stages.append({'stage': 'generation_attempt', 'status': attempt['status'],
                       'elapsedMs': attempt['elapsedMs'],
                       **({'error': attempt['error']} if attempt.get('error') else {})})
        status = attempt['status']
        if status == 'failed':
            failed_stage = attempt.get('stage', 'generation')
    except Exception as exc:
        report['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        if failed_stage is None:
            failed_stage = next((entry['stage'] for entry in reversed(stages)
                                 if entry['status'] == 'failed'), 'unknown')
        attempt = {'status': 'failed', 'stage': failed_stage, 'raw': '',
                   'error': report['error']}
    finally:
        report['runWallMs'] = (time.perf_counter() - started) * 1000
        attempt.setdefault('elapsedMs', report['runWallMs'])
        report['attempts'] = [attempt]
        report['status'] = status
        report['failedStage'] = failed_stage
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_bytes(canonical_bytes(report) + b'\n')
    if status == 'failed':
        raise RuntimeError(f'runtime smoke failed at stage {failed_stage}; record kept at {record_path}')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true',
                        help='Freeze identity/config without loading or running a model')
    parser.add_argument('--run-id', default=None,
                        help='Register this run under an explicit id; required when the '
                             'default plan/record names already hold earlier evidence')
    args = parser.parse_args()
    plan_path, out = resolve_run_paths(args.run_id)
    for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
        os.environ[key] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HOME'] = str(LOCAL / 'hf-cache')
    registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
    source = next(m for m in registry['models'] if m['id'].endswith('Randeng-T5-77M-MultiTask-Chinese'))
    model_dir = LOCAL / 'models/M02' / source['revision']
    payload_path = model_dir / 'payload-manifest.json'
    payload = json.loads(payload_path.read_text(encoding='utf-8'))
    expected_files = {f['path']: f for f in source['files']}
    selected = {'README.md', 'config.json', 'tokenizer_config.json',
                'special_tokens_map.json', 'spiece.model', 'model.safetensors'}
    if payload['modelId'] != source['id'] or payload['revision'] != source['revision']:
        raise ValueError('payload model identity differs from registration')
    if {f['path'] for f in payload['files']} != selected or len(payload['files']) != len(selected):
        raise ValueError('unexpected model payload file inventory')
    for item in payload['files']:
        spec = expected_files[item['path']]
        registered = spec.get('lfs_sha256') or spec.get('sha256_of_fetched_bytes')
        if item['sha256'] != registered or sha256_file(model_dir / item['path']) != registered:
            raise ValueError('model payload changed: ' + item['path'])
    if out.exists():
        raise FileExistsError('smoke record already exists; preserve it and register a '
                              'new run with --run-id')
    script_files = ('lab.py', 'runtime_smoke.py', 'fetch_model.py', 'requirements-probe.txt',
                    'requirements-probe-macos-arm64-py311.lock.txt')
    report: dict[str, Any] = {
        'schema': 'jity-d-nonbusiness-runtime-smoke-v1',
        'scope': 'synthetic_runtime_smoke_only', 'businessCasesExposed': [],
        'formalVerdict': 'not_evaluated', 'semanticStatus': 'not_evaluated',
        'componentLatencyStatus': 'latency_unverified', 'fullRequestLatencyStatus': 'latency_unverified',
        'humanReview': 'pending_user', 'sourceIsolationReview': 'unverified',
        'device': {'platform': platform.platform(), 'machine': platform.machine(),
                   'logicalCpuCount': os.cpu_count(), 'selectedDevice': 'cpu', 'threads': 1,
                   'gpuUsed': False},
        'python': {'version': platform.python_version(), 'executable': sys.executable},
        'dependencies': _dependency_versions(),
        'sourceHead': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'sourceFiles': {name: sha256_file(Path(__file__).parent / name) for name in script_files},
        'sourceRegistrySha256': sha256_file(REGISTRY),
        'model': {'id': source['id'], 'revision': source['revision'], 'files': payload['files']},
        'configuration': {'prompt': PROMPT, 'maxNewTokens': 12, 'doSample': False,
                          'seed': 42, 'softGenerationLimitSeconds': 3,
                          'tokenizerExtraIds': 0, 'resizeEmbeddings': False,
                          'attempts': 1, 'expectedUse': 'environment smoke, not task comparison'},
        'preparation': {'modelPayloadVerified': True, 'humanSemanticApproval': False,
                        'protectedSourceAuditComplete': False, 'formalScreeningAllowed': False,
                        'heavyComputeWindow': 'not_requested_or_used; single-core short smoke only'},
    }
    plan_state = write_plan(plan_path, report)
    report['preparationPlan'] = {'path': str(plan_path), 'sha256': sha256_file(plan_path),
                                 'state': plan_state}
    if args.prepare_only:
        print(json.dumps({'plan': str(plan_path), 'planState': plan_state,
                          'modelLoaded': False}, ensure_ascii=False))
        return
    # All identity/configuration above is persisted before model loading.
    run_with_journal(report, model_dir, out,
                     import_stack=import_stack,
                     load_tokenizer=lambda ns, directory: ns['T5Tokenizer'].from_pretrained(
                         directory, local_files_only=True, extra_ids=0, legacy=True),
                     load_model=lambda ns, directory: ns['T5ForConditionalGeneration'].from_pretrained(
                         directory, local_files_only=True, use_safetensors=True).to('cpu').eval(),
                     generation_attempt=generation_attempt)
    record = report['attempts'][0]
    print(json.dumps({'record': str(out), 'status': record['status'],
                      'elapsedMs': record['elapsedMs'],
                      'loadWallMs': report.get('loadWallMs'),
                      'formalVerdict': 'not_evaluated'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
