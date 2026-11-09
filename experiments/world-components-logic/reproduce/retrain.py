"""Portable fresh training using Jity's existing loss, LoRA and encoder kernels.

This creates new candidates, not a byte-identical replay of historical r4/r5.
No historical checkpoint or author-machine path is required.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import sys
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE))
import short_training as heads
import short_qwen_training as qwen
from lab import sha256_file

DATASET = BASE / 'data/short-semantics/time-choice-v2/supervision.jsonl.gz'


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def audit(dataset, split_file):
    raw = Path(dataset).read_bytes()
    rows = [json.loads(line) for line in gzip.decompress(raw).splitlines() if line.strip()]
    heads.validate_rows(rows)
    split = json.loads(Path(split_file).read_text())
    if hashlib.sha256(raw).hexdigest() != split['datasetSha256']:
        raise ValueError('Dataset differs from frozen split manifest; register a new dataset explicitly.')
    actual = {s: [{'exampleId': r['exampleId'], 'sourceGroup': r['sourceGroup']} for r in rows if r['split'] == s]
              for s in ('train', 'development', 'test')}
    if actual != split['splits']:
        raise ValueError('Frozen example IDs, ordering or source-group splits changed.')
    return rows, {'sha256': split['datasetSha256'], 'rows': len(rows),
                  'splitCounts': {s: len(v) for s, v in actual.items()},
                  'sourceGroups': {s: sorted({r['sourceGroup'] for r in v}) for s, v in actual.items()},
                  'humanReviewed': 0, 'independentGeneralizationEstablished': False}


def source_spec(kind):
    return json.loads((HERE / 'model-sources.json').read_text())[kind]


def verify_model(kind, directory):
    spec = source_spec(kind)
    for item in spec['files']:
        p = Path(directory) / item['path']
        if not p.is_file() or p.stat().st_size != item['size_bytes']:
            raise ValueError(f'Missing/wrong-size pinned model file: {p}')
        expected = item.get('lfs_sha256') or item.get('sha256_of_fetched_bytes')
        if expected:
            valid = sha256_file(p) == expected
        else:
            b = p.read_bytes()
            valid = hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest() == item['git_blob_sha1']
        if not valid:
            raise ValueError(f'Pinned model identity mismatch: {p}')
    return {'modelId': spec.get('modelId', spec.get('id')), 'revision': spec['revision']}


def download(kind, directory):
    from fetch_model import fetch_verified
    Path(directory).mkdir(parents=True, exist_ok=True)
    for item in source_spec(kind)['files']:
        p = Path(directory) / item['path']
        p.parent.mkdir(parents=True, exist_ok=True)
        fetch_verified(item, p)
    print(json.dumps(verify_model(kind, directory)))


def configure(args):
    if args.model == 'encoder':
        if args.device != 'cpu' or args.dtype != 'float32':
            raise ValueError('The existing MiniRBT feature/head kernels are CPU float32 only.')
        from short_experiment import CONFIG
        value = copy.deepcopy(CONFIG)
    else:
        value = {k: qwen.CONFIG[k] for k in ('seed', 'steps', 'batchSize', 'rank', 'alpha',
                 'learningRate', 'weightDecay', 'maxGradNorm', 'maxInputTokens', 'maxTargetTokens',
                 'maxNewTokens', 'gradientCheckpointing', 'gradientCheckpointingReentrant',
                 'trainingDropout', 'threads', 'evaluationSplits')}
    value.update(device=args.device, basePrecision=args.dtype, seed=args.seed,
                 steps=args.steps if args.steps is not None else (112 if args.model == 'qwen' else 160))
    if value['steps'] < 1:
        raise ValueError('steps must be positive')
    return value


def device_check(torch, device, dtype):
    if device == 'mps' and not torch.backends.mps.is_available():
        raise ValueError('MPS is unavailable; choose a device present on this machine.')
    if device == 'cuda' and not torch.cuda.is_available():
        raise ValueError('CUDA is unavailable in this PyTorch installation.')
    if device == 'cuda' and dtype == 'bfloat16' and not torch.cuda.is_bf16_supported():
        raise ValueError('This CUDA device does not support bfloat16; use float32.')
    if device == 'cpu' and dtype != 'float32':
        raise ValueError('The portable CPU entry uses float32.')


def sync(torch, device):
    if device == 'mps': torch.mps.synchronize()
    elif device == 'cuda': torch.cuda.synchronize()


def release(torch, device):
    if device == 'mps': torch.mps.empty_cache()
    elif device == 'cuda': torch.cuda.empty_cache()


def qwen_predictions(torch, model, tokenizer, rows, encoded, config, output):
    model.eval()
    results = []
    with output.open('x', encoding='utf-8') as stream:
        for row in rows:
            if row['split'] == 'train': continue
            x = encoded[row['exampleId']]
            ids = torch.tensor([x['promptIds']], dtype=torch.long, device=config['device'])
            started = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(input_ids=ids, attention_mask=torch.ones_like(ids),
                    max_new_tokens=config['maxNewTokens'], do_sample=False, temperature=None,
                    top_p=None, top_k=None, pad_token_id=tokenizer.eos_token_id)
            sync(torch, config['device'])
            tokens = generated[0, len(x['promptIds']):].tolist()
            text = tokenizer.decode(tokens, skip_special_tokens=True)
            complete = bool(tokens and tokens[-1] in qwen.legal_eos_ids(model, tokenizer) and text.strip()
                            and '<think>' not in text and '</think>' not in text)
            item = {'exampleId': row['exampleId'], 'sourceGroup': row['sourceGroup'], 'split': row['split'],
                    'component': row['component'], 'output': text, 'rawTokenIds': tokens,
                    'status': 'result' if complete else 'incomplete', 'exactDraftMatch': text == row['target'],
                    'elapsedMs': (time.perf_counter() - started) * 1000, 'semanticQualityApproved': False}
            stream.write(json.dumps(item, ensure_ascii=False) + '\n'); stream.flush(); results.append(item)
            del ids, generated
            release(torch, config['device'])
    return results


def fit_qwen(torch, model, tokenizer, rows, config, output, event):
    from plan_training import adapter_state
    encoded = {r['exampleId']: qwen.tokenize_row(tokenizer, r, config) for r in rows}
    schedule = heads.training_schedule(rows, config)
    write_json(output / 'schedule.json', schedule)
    baseline = qwen_predictions(torch, model, tokenizer, rows, encoded, config, output / 'before.jsonl')
    qwen.install_lora(torch, model, config)
    parameters = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(parameters, lr=config['learningRate'], weight_decay=config['weightDecay'])
    model.train()  # Enables gradient checkpointing; Qwen attention dropout stays zero.
    if getattr(model.config, 'attention_dropout', 0) != 0:
        raise ValueError('This recipe requires zero attention dropout')
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.enable_input_require_grads()
    counts = {}
    for step, key in enumerate(schedule['exampleIds'], 1):
        example = encoded[key]
        if example['split'] != 'train': raise ValueError('Held-out row reached gradient path')
        optimizer.zero_grad(set_to_none=True)
        loss = qwen.response_loss(torch, model, example, config['device'])
        if not torch.isfinite(loss): raise ValueError('Non-finite loss')
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(parameters, config['maxGradNorm'])
        if not torch.isfinite(norm): raise ValueError('Non-finite gradient')
        optimizer.step()
        counts[example['component']] = counts.get(example['component'], 0) + int(float(norm) > 0)
        event('optimizer_step', {'step': step, 'exampleId': key, 'loss': float(loss.detach().cpu())})
        del loss
        release(torch, config['device'])
    if not all(counts.get(task) for task in qwen.TASKS):
        raise ValueError('At least one text task received no nonzero training gradient')
    model.gradient_checkpointing_disable(); model.disable_input_require_grads(); model.config.use_cache = True
    path = output / 'adapter.pt'
    torch.save({'adapter': adapter_state(model), 'optimizer': qwen.cpu_tree(torch, optimizer.state_dict())}, path)
    saved = torch.load(path, map_location='cpu', weights_only=True)
    qwen.restore_adapter(torch, model, saved['adapter'])
    after = qwen_predictions(torch, model, tokenizer, rows, encoded, config, output / 'after.jsonl')
    return {'checkpoint': path.name, 'checkpointSha256': sha256_file(path),
            'before': metrics(baseline), 'after': metrics(after), 'nonzeroGradientSteps': counts}


def metrics(rows):
    return {'examples': len(rows), 'exactDraftMatches': sum(bool(r.get('exactDraftMatch')) for r in rows),
            'incomplete': sum(r.get('status', 'result') != 'result' for r in rows),
            'semanticQualityApproved': False, 'meaning': 'Draft exact-match is not semantic acceptance.'}


def run(args):
    rows, data = audit(args.dataset, args.splits)
    identity = verify_model(args.model, args.model_dir)
    config = configure(args)
    if args.command == 'evaluate':
        previous = json.loads((args.checkpoint_dir / 'run.json').read_text())
        if previous.get('status') != 'complete' or previous.get('command') != 'train':
            raise ValueError('Evaluation requires a completed training run')
        if previous.get('result', {}).get('untrainedComponents'):
            raise ValueError('Some encoder heads remain untrained; do not report a complete evaluation')
        if previous['model'] != identity or previous['data']['sha256'] != data['sha256']:
            raise ValueError('Checkpoint base model or dataset mismatch')
        config = previous['config'] | {'device': args.device, 'basePrecision': args.dtype}
    else:
        previous = None
    import torch
    device_check(torch, config['device'], config['basePrecision'])
    random.seed(config['seed']); torch.manual_seed(config['seed']); torch.set_num_threads(config['threads'])
    import numpy as np
    np.random.seed(config['seed'])
    if config['device'] == 'cuda': torch.cuda.manual_seed_all(config['seed'])
    if config['device'] == 'mps': torch.mps.manual_seed(config['seed'])
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=False)
    run_record = {'status': 'running', 'model': identity, 'data': data, 'config': config,
                  'command': args.command, 'python': sys.version, 'platform': platform.platform(),
                  'modelDirectory': str(args.model_dir.resolve()),
                  'dependencies': {k: importlib.metadata.version(k) for k in ('torch', 'transformers', 'numpy', 'tokenizers', 'safetensors')},
                  'sourceSha256': {p.name: sha256_file(p) for p in [Path(__file__), BASE/'short_training.py', BASE/'short_qwen_training.py', BASE/'short_qwen_codec.py']},
                  'historicalCheckpointReplay': False, 'productionIntegration': False, 'webgpuValidated': False}
    write_json(output / 'run.json', run_record)
    started = time.perf_counter()
    try:
        with (output / 'events.jsonl').open('x', encoding='utf-8') as log:
            def event(name, payload):
                # Retain operational evidence without dumping full tensors/inputs.
                compact = {k: v for k, v in payload.items() if k not in ('input', 'inputIds', 'tokenTypeIds', 'rawLogits')}
                log.write(json.dumps({'name': name, 'data': compact}, ensure_ascii=False) + '\n'); log.flush()
                return {'event': name}
            if args.model == 'qwen':
                from transformers import AutoModelForCausalLM, AutoTokenizer
                model = AutoModelForCausalLM.from_pretrained(args.model_dir, local_files_only=True, trust_remote_code=False,
                    torch_dtype=getattr(torch, config['basePrecision']), attn_implementation='sdpa', weights_only=True).to(config['device']).eval()
                tokenizer = AutoTokenizer.from_pretrained(args.model_dir, local_files_only=True, trust_remote_code=False)
                text_rows = [r for r in rows if r['kind'] == 'text']
                if previous:
                    checkpoint = args.checkpoint_dir / previous['result']['checkpoint']
                    if sha256_file(checkpoint) != previous['result']['checkpointSha256']: raise ValueError('Checkpoint bytes changed')
                    qwen.install_lora(torch, model, config)
                    qwen.restore_adapter(torch, model, torch.load(checkpoint, map_location='cpu', weights_only=True)['adapter'])
                    encoded = {r['exampleId']: qwen.tokenize_row(tokenizer, r, config) for r in text_rows}
                    result = metrics(qwen_predictions(torch, model, tokenizer, text_rows, encoded, config, output/'evaluation.jsonl'))
                else:
                    result = fit_qwen(torch, model, tokenizer, text_rows, config, output, event)
            else:
                model, tokenizer = heads.load_neural(torch, 'encoder', args.model_dir, config)
                selected = [r for r in rows if r['kind'] in ('label', 'reference', 'number')]
                if previous:
                    checkpoint = args.checkpoint_dir / previous['result']['checkpoint']
                    if sha256_file(checkpoint) != previous['result']['checkpointSha256']: raise ValueError('Checkpoint bytes changed')
                    specs = previous['result']['specs']; modules = heads.build_heads(torch, model.config.hidden_size, specs)
                    saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
                    for key, module in modules.items(): module.load_state_dict(saved[key], strict=True)
                    values = heads.evaluate_heads(torch, model, tokenizer, modules, [r for r in selected if r['split'] != 'train'], specs, config, event)
                    write_json(output/'evaluation.json', values); result = metrics(values)
                else:
                    trained = heads.train_heads(torch, model, tokenizer, selected, config, output/'model', event)
                    write_json(output/'training-summary.json', trained)
                    result = {'checkpoint': 'model/heads.pt', 'checkpointSha256': trained['checkpoint']['sha256'],
                              'specs': trained['specs'], 'after': metrics(trained['predictions']),
                              'untrainedComponents': sorted(set(trained['specs']) - set(trained['trainedHeadComponents']))}
            run_record.update(status='complete', result=result)
    except Exception as error:
        run_record.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        run_record['wallSeconds'] = time.perf_counter() - started
        write_json(output/'run.json', run_record)
    print(json.dumps(run_record['result'], ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['audit', 'download', 'train', 'evaluate'])
    parser.add_argument('--model', choices=['qwen', 'encoder'], default='qwen')
    parser.add_argument('--dataset', type=Path, default=DATASET)
    parser.add_argument('--splits', type=Path, default=HERE/'splits.json')
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--checkpoint-dir', type=Path)
    parser.add_argument('--device', choices=['cpu', 'mps', 'cuda'], default='cpu')
    parser.add_argument('--dtype', choices=['float32', 'bfloat16'], default='float32')
    parser.add_argument('--steps', type=int)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    if args.command == 'audit':
        print(json.dumps(audit(args.dataset, args.splits)[1], ensure_ascii=False, indent=2)); return
    if args.model_dir is None: parser.error('--model-dir is required')
    if args.command == 'download': download(args.model, args.model_dir); return
    if args.output_dir is None: parser.error('--output-dir must name a new directory')
    if args.command == 'evaluate' and args.checkpoint_dir is None: parser.error('--checkpoint-dir is required')
    run(args)


if __name__ == '__main__': main()
