"""Real model load + one fact + one full round, saved only in this worktree."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from component_paths import PATHS
from narration_service import Engine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default=None)
    parser.add_argument('--round', default='fixture-r1')
    parser.add_argument('--budget', type=float, default=60.0)
    parser.add_argument('--out', default='acceptance/runtime-smoke.json')
    args = parser.parse_args()
    target = PATHS.output(args.out)
    inputs = PATHS.verify_inputs()
    model = PATHS.model(args.model)
    before = {name: hashlib.sha256((model / name).read_bytes()).hexdigest()
              for name in ('config.json', 'model.safetensors', 'spiece.model')}
    started = time.perf_counter()
    engine = Engine(model, 'world-provenance/pairs')
    import numpy
    import transformers
    payload = engine.load_round(args.round)
    fact = engine.generate_fact(payload['units'][0], args.budget)
    result = engine.process_round(payload, args.budget)
    assert fact['complete'] and fact['text'].strip(), fact
    assert result['sourceComplete'] and result['edited'].strip(), result
    assert result['quality']['status'] == 'unverified'
    assert len(result['generation']) == len(payload['units'])
    assert result['modelCalls']['encoder'] == len(payload['units'])
    after = {name: hashlib.sha256((model / name).read_bytes()).hexdigest() for name in before}
    assert before == after, 'Shared model files changed'
    report = {'purpose': 'Runtime acceptance only; not a model quality evaluation',
              'inputs': inputs, 'modelDirectory': str(model), 'modelSha256': before,
              'modelUnchanged': True, 'device': engine.device,
              'environment': {'python': sys.version, 'torch': engine.torch.__version__,
                              'transformers': transformers.__version__, 'numpy': numpy.__version__,
                              'threads': engine.torch.get_num_threads()},
              'coldStartSeconds': engine.cold_start_seconds,
              'totalSeconds': round(time.perf_counter() - started, 3),
              'singleFact': fact, 'roundId': args.round, 'round': result}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'output': str(target), 'modelLoaded': True, 'singleFactComplete': fact['complete'],
                      'roundComplete': result['sourceComplete'], 'facts': len(result['generation']),
                      'coldStartSeconds': engine.cold_start_seconds, 'quality': 'unverified'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
