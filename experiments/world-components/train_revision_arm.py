"""Equal-budget continuation from one checkpoint, for the target-revision round.

Both arms run this script with the same base, steps, seed, batch and pool mix;
they differ only in which pool files they read. The sampling order is recorded
so the two arms can be compared device-independently: identical id sequences and
a differing target sequence is the evidence that only the labels changed.

Writes the checkpoint, the tokenizer and a run report with every hash needed to
reproduce the run. The base checkpoint is only read.
"""
import argparse
import hashlib
import json
import pathlib
import random
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from component_paths import ComponentPaths  # noqa: E402

TASKS = ('cf24-revision',)


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def load(path):
    return [json.loads(line) for line in pathlib.Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='Checkpoint to continue from (read-only)')
    parser.add_argument('--pool', action='append', required=True,
                        help='Pool file; repeat in mix order')
    parser.add_argument('--mix', default='4,3,1', help='Units per step from each pool')
    parser.add_argument('--steps', type=int, default=240)
    parser.add_argument('--batch', type=int, default=8)
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--seed', type=int, default=20261102)
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--out-name', default='ckpt')
    parser.add_argument('--arm', required=True, help='Arm label recorded in the report')
    parser.add_argument('--save-at', default='',
                        help='Comma-separated steps to snapshot in addition to the last one; the '
                             'shorter run is then a prefix of the longer one by construction')
    args = parser.parse_args()

    systems = ComponentPaths()
    run_dir = systems.output(args.run_dir)
    if run_dir.exists() and any(run_dir.iterdir()):
        raise SystemExit(f'Run directory already holds evidence: {run_dir}')
    base = systems.model(args.base) if not pathlib.Path(args.base).is_absolute() else pathlib.Path(args.base).expanduser().resolve()
    for name in ('config.json', 'spiece.model', 'model.safetensors'):
        if not (base / name).is_file():
            raise SystemExit(f'Missing base checkpoint file: {base / name}')
    mix = [int(part) for part in args.mix.split(',')]
    if len(mix) != len(args.pool):
        raise SystemExit('--mix must name one count per --pool')
    if sum(mix) != args.batch:
        raise SystemExit('--mix must add up to --batch')

    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    sys.path.insert(0, str(HERE / 'n4_narrative_dev'))
    from sequence_policy import encode_training_batch

    pools = []
    for path in args.pool:
        rows = load(path)
        for row in rows:
            if not row.get('input') or not row.get('target'):
                raise SystemExit(f'Pool row without input/target: {path}')
        pools.append(rows)

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    tokenizer = T5Tokenizer.from_pretrained(str(base), legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(str(base), torch_dtype=torch.float32)
    model.to(device)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    rngs = [random.Random(args.seed + index) for index in range(len(pools))]
    orders = [list(range(len(pool))) for pool in pools]
    cursor = [0] * len(pools)

    save_at = sorted({int(part) for part in args.save_at.split(',') if part.strip()})
    if any(step < 1 or step > args.steps for step in save_at):
        raise SystemExit('--save-at steps must fall inside 1..steps')
    id_sequence, target_sequence, losses = [], [], []
    snapshots = {}
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    for step in range(1, args.steps + 1):
        batch = []
        for index, take in enumerate(mix):
            if take == 0:
                continue
            if cursor[index] + take > len(orders[index]):
                rngs[index].shuffle(orders[index])
                cursor[index] = 0
            for position in orders[index][cursor[index]:cursor[index] + take]:
                batch.append(pools[index][position])
            cursor[index] += take
        for row in batch:
            id_sequence.append(row.get('unitId') or row.get('pairId'))
            target_sequence.append(sha256_text(row['target']))
        encoded, labels = encode_training_batch(tokenizer, batch)
        encoded = {key: value.to(device) for key, value in encoded.items()}
        out = model(**encoded, labels=labels.input_ids.to(device))
        optimizer.zero_grad()
        out.loss.backward()
        optimizer.step()
        if step in save_at:
            snap = run_dir / ('%s-%d' % (args.out_name, step))
            model.save_pretrained(snap)
            tokenizer.save_pretrained(snap)
            snapshots[step] = {'dir': str(snap.relative_to(ComponentPaths().worktree)),
                               'modelSha256': sha256(snap / 'model.safetensors'),
                               'ids': len(id_sequence),
                               'idSha256': sha256_text(chr(10).join(id_sequence))}
        if step % 40 == 0 or step == 1 or step == args.steps:
            losses.append({'step': step, 'loss': round(float(out.loss), 4)})
            print('step %d loss %.4f' % (step, float(out.loss)), flush=True)

    ckpt = run_dir / args.out_name
    ckpt.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(ckpt)
    tokenizer.save_pretrained(ckpt)
    report = {
        'purpose': 'equal-budget continuation for the target-revision round',
        'arm': args.arm,
        'device': device,
        'base': {'dir': str(base), 'files': {name: sha256(base / name)
                                             for name in ('config.json', 'spiece.model', 'model.safetensors')}},
        'pools': [{'path': pathlib.Path(p).resolve().relative_to(ComponentPaths().worktree).as_posix(),
                   'rows': len(rows), 'sha256': sha256(p)} for p, rows in zip(args.pool, pools)],
        'hyper': {'steps': args.steps, 'batch': args.batch, 'mix': mix, 'lr': args.lr,
                  'seed': args.seed, 'precision': 'fp32', 'optimizer': 'AdamW'},
        'sampling': {'ids': len(id_sequence), 'idSha256': sha256_text('\n'.join(id_sequence)),
                     'targetSha256': sha256_text('\n'.join(target_sequence))},
        'losses': losses,
        'seconds': round(time.perf_counter() - started, 1),
        'checkpoint': {'dir': str(ckpt.relative_to(ComponentPaths().worktree)),
                       'modelSha256': sha256(ckpt / 'model.safetensors')},
        'snapshots': snapshots,
    }
    (run_dir / 'train-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n',
                                               encoding='utf-8', newline='\n')
    print('->', run_dir / 'train-report.json')


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


if __name__ == '__main__':
    main()
