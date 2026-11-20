"""Quality baseline over the frozen cf24 contract set (85 fact units / 24 sources).

No training and no parameter search: load one checkpoint, greedy-decode every
unit under the recorded budget, and archive the raw input, output, call count
and elapsed time so the same run can be re-judged or compared later.

The unit file comes from the pinned input root and is byte-checked before use;
outputs go to a run directory that cannot overlap the pinned inputs.
"""
import argparse
import hashlib
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from component_paths import ComponentPaths  # noqa: E402

UNIT_FILE = 'world-components/n4-cf24-contract.jsonl'
MODEL_FILES = ('config.json', 'spiece.model', 'model.safetensors')

# Variant rule for the first improvement round. Only moved units get one extra
# instruction line; every other input stays byte-identical to the pinned file.
MOVED_RULE = '移动句只写到抵达；不写抵达后做了什么、看到了什么。'
VARIANTS = {'none': None, 'moved-arrival-only': MOVED_RULE}


def variant_input(unit, rule):
    if not rule or unit['kind'] != 'moved':
        return unit['input']
    head, separator, tail = unit['input'].rpartition('短句：')
    if not separator:
        raise ValueError(f'Unexpected input shape for {unit["unitId"]}')
    return head + rule + '\n' + separator + tail


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, help='Read-only model directory')
    parser.add_argument('--units', default=UNIT_FILE, help='Pinned unit file to generate from')
    parser.add_argument('--out-name', default='cf24-baseline.json')
    parser.add_argument('--run-dir', required=True, help='New directory under artifacts/next-runs')
    parser.add_argument('--budget', type=float, default=20.0, help='Wall-clock seconds per unit')
    parser.add_argument('--limit', type=int, default=0, help='Debug only: stop after N units')
    parser.add_argument('--device', choices=('auto', 'cpu', 'cuda'), default='auto')
    parser.add_argument('--variant', choices=sorted(VARIANTS), default='none',
                        help='Input variant; the pinned file stays authoritative')
    args = parser.parse_args()

    paths = ComponentPaths()
    run_dir = paths.output(args.run_dir)
    if run_dir.exists() and any(run_dir.iterdir()):
        raise SystemExit(f'Run directory already holds evidence: {run_dir}')
    unit_path = paths.input(args.units)
    model_dir = paths.model(args.model)

    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    sys.path.insert(0, str(HERE / 'n4_narrative_dev'))
    import fact_contract as FC
    from sequence_policy import generate_greedy

    units = [json.loads(line) for line in unit_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    FC.check_units(units)
    if args.limit:
        units = units[:args.limit]

    if args.device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    else:
        if args.device == 'cuda' and not torch.cuda.is_available():
            raise SystemExit('CUDA was requested but is not available')
        device = args.device
    torch.set_num_threads(4)
    started = time.perf_counter()
    tokenizer = T5Tokenizer.from_pretrained(str(model_dir), legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(str(model_dir), torch_dtype=torch.float32)
    model.to(device).eval()
    load_seconds = time.perf_counter() - started

    rows = []
    rule = VARIANTS[args.variant]
    for index, unit in enumerate(units, 1):
        text_input = variant_input(unit, rule)
        encoded = tokenizer(text_input, return_tensors='pt', truncation=False).to(device)
        unit_started = time.perf_counter()
        ids, meta = generate_greedy(model, encoded, args.budget)
        elapsed = time.perf_counter() - unit_started
        text = tokenizer.decode(ids[0], skip_special_tokens=True)
        rows.append({'unitId': unit['unitId'], 'sourceId': unit.get('sourceId'),
                     'kind': unit['kind'], 'fact': unit['fact'],
                     'input': unit['input'], 'inputUsed': text_input,
                     'text': text,
                     'complete': meta['complete'], 'stopReason': meta.get('stopReason'),
                     'newTokens': meta.get('newTokens'), 'seconds': round(elapsed, 3)})
        print('%3d/%d %-8s %s' % (index, len(units), unit['unitId'], text), flush=True)

    run_dir.mkdir(parents=True, exist_ok=True)
    report = {
        'purpose': 'cf24 quality baseline; single-fact units, greedy, no training',
        'device': device,
        'estimateOnly': 'judging is separate; this file holds raw generation output',
        'model': {'dir': str(model_dir), 'files': {n: sha256(model_dir / n) for n in MODEL_FILES}},
        'environment': {'python': sys.version.split()[0], 'torch': torch.__version__,
                        'transformers': __import__('transformers').__version__,
                        'threads': torch.get_num_threads()},
        'decode': {'policy': 'greedy, EOS or wall-clock budget, no length cap',
                   'budgetSeconds': args.budget},
        'variant': {'name': args.variant, 'rule': rule,
                    'unitsChanged': sum(1 for unit in units if variant_input(unit, rule) != unit['input'])},
        'units': {'file': args.units, 'sha256': sha256(unit_path), 'count': len(units)},
        'loadSeconds': round(load_seconds, 3),
        'totalSeconds': round(time.perf_counter() - started, 3),
        'rows': rows,
    }
    out = run_dir / args.out_name
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('->', out)


if __name__ == '__main__':
    main()
