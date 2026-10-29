"""Bounded, single-CPU, non-business runtime smoke. Never evaluates D cases.

DRAFT / PAUSED CHECKPOINT: import/load failure journaling is not complete.
Do not execute inference mode until that known issue is fixed and re-reviewed.
This only checks the isolated M02 environment, tokenizer and generation path.
It cannot establish semantic quality, component latency or a 500 ms request.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from lab import canonical_bytes, sha256_file

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / '.local/world-components-logic'
REGISTRY = ROOT / 'artifacts/world-components-logic/l2-model-sources-20261029.json'
PROMPT = '运行检查：请写出“模型已载入”。'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true', help='Freeze identity/config without loading or running a model')
    args = parser.parse_args()
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
    out = ROOT / 'artifacts/world-components-logic/l3-1-runtime-smoke.json'
    if out.exists():
        raise FileExistsError('smoke record already exists; preserve it and register a new run')
    plan_path = LOCAL / 'runtime-smoke-plan.json'
    script_files = ('lab.py', 'runtime_smoke.py', 'fetch_model.py', 'requirements-probe.txt',
                    'requirements-probe-macos-arm64-py311.lock.txt')
    report = {
        'schema': 'jity-d-nonbusiness-runtime-smoke-v1',
        'scope': 'synthetic_runtime_smoke_only', 'businessCasesExposed': [],
        'formalVerdict': 'not_evaluated', 'semanticStatus': 'not_evaluated',
        'componentLatencyStatus': 'latency_unverified', 'fullRequestLatencyStatus': 'latency_unverified',
        'humanReview': 'pending_user', 'sourceIsolationReview': 'unverified',
        'device': {'platform': platform.platform(), 'machine': platform.machine(),
                   'logicalCpuCount': os.cpu_count(), 'selectedDevice': 'cpu', 'threads': 1,
                   'gpuUsed': False},
        'python': {'version': platform.python_version(), 'executable': sys.executable},
        'dependencies': {d: importlib.metadata.version(d) for d in
                         ('torch', 'transformers', 'safetensors', 'sentencepiece', 'tokenizers', 'numpy')},
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
    plan_path.write_bytes(canonical_bytes(report) + b'\n')
    if args.prepare_only:
        print(json.dumps({'plan': str(plan_path), 'modelLoaded': False}, ensure_ascii=False))
        return
    # All identity/configuration above is persisted before model loading.
    imported = time.perf_counter()
    import torch
    from transformers import T5ForConditionalGeneration, T5Tokenizer
    from transformers.generation.stopping_criteria import MaxTimeCriteria, StoppingCriteriaList
    report['runtimeImportWallMs'] = (time.perf_counter() - imported) * 1000
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(42)
    loaded = time.perf_counter()
    tokenizer = T5Tokenizer.from_pretrained(model_dir, local_files_only=True, extra_ids=0, legacy=True)
    model = T5ForConditionalGeneration.from_pretrained(model_dir, local_files_only=True,
                                                       use_safetensors=True).to('cpu').eval()
    report['loadWallMs'] = (time.perf_counter() - loaded) * 1000
    report['parameterCount'] = sum(p.numel() for p in model.parameters())
    report['tokenizerLength'] = len(tokenizer)
    report['embeddingRows'] = model.get_input_embeddings().num_embeddings
    started = time.perf_counter()
    record = {'status': 'started', 'raw': '', 'stage': 'encode'}
    try:
        encoded = tokenizer(PROMPT, return_tensors='pt', truncation=False)
        record['inputTokens'] = int(encoded['input_ids'].shape[-1])
        record['stage'] = 'generate'
        criteria = StoppingCriteriaList([MaxTimeCriteria(max_time=3)])
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
        report['attempts'] = [record]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(canonical_bytes(report) + b'\n')
    print(json.dumps({'record': str(out), 'status': record['status'],
                      'elapsedMs': record['elapsedMs'], 'loadWallMs': report['loadWallMs'],
                      'formalVerdict': 'not_evaluated'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
