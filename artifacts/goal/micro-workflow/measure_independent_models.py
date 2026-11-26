# -*- coding: utf-8 -*-
"""Separate ONNX export and CPU latency for the pilot's independent task models."""
import importlib.util
import json
import random
import time
from pathlib import Path

import torch

ROOT = Path('D:/others/Jity')
OUT = ROOT / 'artifacts/goal/micro-workflow/micro-generative'
PILOT_PATH = Path(__file__).with_name('micro_generative_pilot.py')

spec = importlib.util.spec_from_file_location('micro_generative_pilot', PILOT_PATH)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def train_with_fallback(rows, size, name, device, vocab):
    try:
        return pilot.train_arm(rows, size, name, device, vocab, epochs=40), device
    except RuntimeError as error:
        if 'out of memory' not in str(error).lower():
            raise
        torch.cuda.empty_cache()
        cpu = torch.device('cpu')
        return pilot.train_arm(rows, size, name, cpu, vocab, epochs=40), cpu


def export_int8(model, vocab, row, tag):
    import onnxruntime.quantization as quant
    src = torch.tensor([vocab.encode(row['input'], 96)])
    tgt = torch.tensor([vocab.encode(row['prefix'] + row['continuation'], 96)[:-1]])
    fp32_path = OUT / f'{tag}.onnx'
    int8_path = OUT / f'{tag}-int8.onnx'
    result = {}
    try:
        torch.onnx.export(model, (src, tgt), fp32_path, opset_version=17,
                          input_names=['src', 'tgt'], output_names=['logits'],
                          dynamic_axes={'src': {0: 'batch', 1: 'src_len'},
                                        'tgt': {0: 'batch', 1: 'tgt_len'}})
        result['fp32MB'] = round(fp32_path.stat().st_size / 1e6, 2)
        quant.quantize_dynamic(fp32_path.as_posix(), int8_path.as_posix(),
                               weight_type=quant.QuantType.QInt8)
        result['int8MB'] = round(int8_path.stat().st_size / 1e6, 2)
    except Exception as error:
        result['onnxError'] = f'{type(error).__name__}: {error}'
    finally:
        fp32_path.unlink(missing_ok=True)
    return result


def main():
    random.seed(20261126)
    torch.manual_seed(20261126)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    OUT.mkdir(parents=True, exist_ok=True)
    rows = pilot.condition_rows() + pilot.event_rows()
    task_keys = sorted({row['key'] for row in rows if row['task'] == 'conditions'})
    held_tasks = set(task_keys[::5])
    actor_keys = sorted({row['key'] for row in rows if row['task'] == 'events'})
    held_actors = set(actor_keys[::5])

    def is_test(row):
        return ((row['task'] == 'conditions' and row['key'] in held_tasks)
                or (row['task'] == 'events' and row['key'] in held_actors))

    train = [row for row in rows if not is_test(row)]
    test = [row for row in rows if is_test(row)]
    vocab = pilot.Vocab([row['input'] + row['output'] for row in rows])
    report = {'rows': len(rows), 'train': len(train), 'test': len(test), 'vocab': len(vocab.itos),
              'seed': 20261126, 'epochs': 40, 'device': str(device),
              'heldTasks': sorted(held_tasks), 'heldActors': sorted(held_actors), 'arms': {}}
    for size in ('5M', '15M', '30M'):
        for task in ('conditions', 'events'):
            subset = [row for row in train if row['task'] == task]
            test_subset = [row for row in test if row['task'] == task]
            name = f'indep_{size}_{task}'
            began = time.perf_counter()
            (model, _, params), arm_device = train_with_fallback(subset, size, name, device, vocab)
            metrics = pilot.evaluate(model, vocab, test_subset, arm_device)
            metrics['trainFieldRecall'] = pilot.evaluate(model, vocab, subset[:80], arm_device)['fieldRecall']
            metrics.update({'params': params, 'sizeMB': round(params * 4 / 1e6, 1),
                            'trainMs': round((time.perf_counter() - began) * 1000),
                            'device': str(arm_device)})
            cpu_model = model.to('cpu')
            cpu_metrics = pilot.evaluate(cpu_model, vocab, test_subset[:12], torch.device('cpu'))
            metrics['cpuP50Ms'] = cpu_metrics['p50Ms']
            metrics['cpuP95Ms'] = cpu_metrics['p95Ms']
            metrics.update(export_int8(cpu_model, vocab, test_subset[0], name))
            report['arms'][f'indep{size}_{task}'] = metrics
            print(name, json.dumps(metrics, ensure_ascii=False), flush=True)
            del model, cpu_model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
    required = {'params', 'fp32MB', 'int8MB', 'fieldRecall', 'exact', 'perField',
                'cpuP50Ms', 'cpuP95Ms', 'trainFieldRecall'}
    for key, arm in report['arms'].items():
        if 'onnxError' not in arm:
            assert required <= set(arm), (key, sorted(required - set(arm)))
    (OUT / 'independent-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                                 encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
