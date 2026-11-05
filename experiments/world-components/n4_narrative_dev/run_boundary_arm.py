"""边界臂训练：4 原 + 2 扩容 + 1 物件 + 1 边界；复用 u240 的采样日志。

每批第 3 条扩容样本的位置（旧日志第 6 位）换成一条边界样本，其余 7 条与
u240 完全一致（旧的 4 原、2 扩容、物件），所以两臂只差这一个位置。
"""
import argparse
import json
import pathlib
import random
import sys
import time

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fact_contract as FC  # noqa: E402
from sequence_policy import encode_training_batch, rethrow_oom  # noqa: E402

SEED = 20261102
LR = 3e-4
BATCH = 8
MAX_UPDATES = 2880
EVAL_EVERY = 240


def rows(path):
    return [json.loads(line) for line in pathlib.Path(path).read_text(encoding='utf-8').splitlines()
            if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    for key in ('manifest', 'units', 'expand', 'objects', 'boundary', 'draws'):
        parser.add_argument('--' + key, required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--ckpt240', required=True)
    parser.add_argument('--ckptbest', required=True)
    args = parser.parse_args()

    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding='utf-8'))
    split = {s['sourceId']: s['split'] for s in manifest['sources']}
    base_units = rows(args.units)
    orig = [u for u in base_units if split.get(u['sourceId']) == 'formal-train']
    dev = [u for u in base_units if split.get(u['sourceId']) == 'formal-dev']
    expand = rows(args.expand)
    objects = rows(args.objects)
    boundary = rows(args.boundary)
    FC.check_units(orig + expand + objects + boundary)

    u240 = json.loads(pathlib.Path(args.draws).read_text(encoding='utf-8'))
    draws = u240['drawIds']
    index = {}
    def key_of(unit):
        return unit.get('unitId') or unit.get('pairId')             or f"{unit.get('sourceId')}:{unit.get('factId')}"

    for pool, name in ((orig, 'orig'), (expand, 'expand'), (objects, 'object')):
        for unit in pool:
            index[(name, key_of(unit))] = unit
    rng = random.Random(SEED)
    order = list(range(len(boundary)))
    rng.shuffle(order)
    cursor = [0]

    def next_boundary():
        if cursor[0] >= len(order):
            rng.shuffle(order)
            cursor[0] = 0
        unit = boundary[order[cursor[0]]]
        cursor[0] += 1
        return unit

    def replay():
        batches = []
        for step in range(MAX_UPDATES):
            chunk = draws[step * BATCH:(step + 1) * BATCH]
            assert len(chunk) == BATCH, '采样日志长度不足'
            picked = []
            for position, unit_id in enumerate(chunk):
                if position < 4:
                    picked.append(index[('orig', unit_id)])
                elif position < 6:
                    picked.append(index[('expand', unit_id)])
                elif position == 7:
                    picked.append(index[('object', unit_id)])
            picked.append(next_boundary())      # 替换旧日志第 6 位的第 3 条扩容
            batches.append(picked)
        return batches

    batches = replay()
    tokenizer = T5Tokenizer.from_pretrained(args.base, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(args.base, torch_dtype=torch.float32)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model.to(device)
    torch.manual_seed(SEED)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    report = {'arm': 'boundary-4o2e1obj1b', 'mix': [4, 2, 1, 1], 'seed': SEED,
              'counts': {'orig': len(orig), 'expand': len(expand), 'object': len(objects),
                         'boundary': len(boundary), 'dev': len(dev)},
              'history': []}

    def eval_dev():
        model.eval()
        total, count = 0.0, 0
        with torch.inference_mode():
            for start in range(0, len(dev), BATCH):
                chunk = dev[start:start + BATCH]
                enc, labels = encode_training_batch(tokenizer, chunk)
                enc = {k: v.to(device) for k, v in enc.items()}
                out = model(**enc, labels=labels.input_ids.to(device))
                total += float(out.loss) * len(chunk)
                count += len(chunk)
        model.train()
        return round(total / max(count, 1), 4)

    model.train()
    started = time.perf_counter()
    best = None
    for step, batch in enumerate(batches, start=1):
        enc, labels = encode_training_batch(tokenizer, batch)
        enc = {k: v.to(device) for k, v in enc.items()}
        try:
            out = model(**enc, labels=labels.input_ids.to(device))
        except torch.cuda.OutOfMemoryError as exc:
            rethrow_oom(exc, enc, labels)
        optimizer.zero_grad()
        out.loss.backward()
        optimizer.step()
        if step == 240:
            model.save_pretrained(args.ckpt240)
            tokenizer.save_pretrained(args.ckpt240)
            print('step 240 saved', flush=True)
        if step % EVAL_EVERY == 0 or step == MAX_UPDATES:
            loss = eval_dev()
            report['history'].append({'step': step, 'devLoss': loss})
            print(f'step {step} dev {loss}', flush=True)
            if best is None or loss < best['devLoss']:
                best = {'step': step, 'devLoss': loss,
                        'state': {k: v.detach().clone() for k, v in model.state_dict().items()}}
    report['train'] = {'updates': MAX_UPDATES,
                       'wallSeconds': round(time.perf_counter() - started, 1)}
    report['selectedCheckpoint'] = {'step': best['step'], 'devLoss': best['devLoss']}
    model.load_state_dict(best['state'])
    model.save_pretrained(args.ckptbest)
    tokenizer.save_pretrained(args.ckptbest)
    pathlib.Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                      encoding='utf-8')
    print(json.dumps({'train': report['train'], 'selected': report['selectedCheckpoint'],
                      'counts': report['counts']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
