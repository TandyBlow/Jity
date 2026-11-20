"""Selection and exposure account for the routed-split run.

The frozen rule chooses ONE shared observation point for the whole arm-B pair.
It is not a per-model selection: the control checkpoint at that point is a
by-product of the shared point, not a separately selected control optimum.

Three things are recorded here, separately:
  1. the frozen rule and the dev table at every observation point;
  2. per-unit draw exposure at the selected point and over the full run,
     compared unit-by-unit against control (the totals are not comparable);
  3. training cost at the selected point and over the full run: draws,
     optimizer updates, tokens, parameters and an approximate FLOPs figure.
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ART = ROOT / 'artifacts' / 'world-components'
DRAWS = ART / 'n4-mix431-draws.jsonl'
FREEZE = ART / 'route-split-freeze-v1.json'
RUN = ART / 'n4-route-split-run-v1.json'
OUT = ART / 'route-split-selection-basis-v1.json'
UNITS = HERE / 'verbalizer_pairs.jsonl'
EXPAND = ART / 'n4-expand78-unified.jsonl'
OBJECTS = ART / 'n4-object-train40-clean.jsonl'
MANIFEST = ART / 'n4-two-arm-manifest-r1.json'
ACT_KINDS = {'moved', 'outcome'}
STATE_KINDS = {'appearance_changed', 'sanity_changed', 'personality_changed'}
PARAMS = 77440384


def rows(p):
    return [json.loads(line) for line in pathlib.Path(p).read_text(encoding='utf-8').splitlines()
            if line.strip()]


def key_of(unit):
    return unit.get('unitId') or unit.get('pairId') or f"{unit.get('sourceId')}:{unit.get('factId')}"


def load_pool():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    split = {source['sourceId']: source['split'] for source in manifest['sources']}
    base = rows(UNITS)
    original = [unit for unit in base if split.get(unit['sourceId']) == 'formal-train']
    expanded = rows(EXPAND)
    objects = rows(OBJECTS)
    pool = {}
    for name, units in (('orig', original), ('expand', expanded), ('object', objects)):
        for unit in units:
            pool[(name, key_of(unit))] = unit
    return pool


def draw_counts(draws, upto):
    control = collections.Counter()
    act = collections.Counter()
    state = collections.Counter()
    for draw in draws[:upto * 8]:
        key = (draw['pool'], draw['unitId'])
        control[key] += 1
        if draw['kind'] in ACT_KINDS:
            act[key] += 1
        elif draw['kind'] in STATE_KINDS:
            state[key] += 1
    return control, act, state


def arm_updates(draws, upto):
    return {
        'control': upto,
        'act': sum(1 for step in range(upto)
                   if any(draw['kind'] in ACT_KINDS
                          for draw in draws[step * 8:(step + 1) * 8])),
        'state': sum(1 for step in range(upto)
                     if any(draw['kind'] in STATE_KINDS
                            for draw in draws[step * 8:(step + 1) * 8])),
    }


def schedule_units(draws, pool, upto):
    schedule = {'control': [], 'act': [], 'state': []}
    for step in range(upto):
        for draw in draws[step * 8:(step + 1) * 8]:
            unit = pool[(draw['pool'], draw['unitId'])]
            schedule['control'].append(unit)
            if draw['kind'] in ACT_KINDS:
                schedule['act'].append(unit)
            elif draw['kind'] in STATE_KINDS:
                schedule['state'].append(unit)
    return schedule


def token_count(units, tokenizer, encode_training_batch):
    input_tokens = target_tokens = 0
    for index in range(0, len(units), 16):
        encoded, labels = encode_training_batch(tokenizer, units[index:index + 16])
        input_tokens += int(encoded['attention_mask'].sum())
        target_tokens += int((labels.input_ids != -100).sum())
    return {'inputTokens': input_tokens, 'targetTokens': target_tokens,
            'totalTokens': input_tokens + target_tokens}


def exposure_block(control, act, state):
    output = {}
    for name, counter in (('control', control), ('act', act), ('state', state)):
        values = list(counter.values())
        output[name] = {
            'units': len(values),
            'draws': sum(values),
            'min': min(values) if values else None,
            'max': max(values) if values else None,
            'mean': round(sum(values) / len(values), 2) if values else None,
        }
    for name, routed in (('act', act), ('state', state)):
        pairs = [(routed[key], control[key]) for key in routed]
        output[name]['perUnitMatchesControl'] = sum(1 for a, c in pairs if a == c)
        output[name]['perUnitCompared'] = len(pairs)
        output[name]['maxAbsoluteDifference'] = max((abs(a - c) for a, c in pairs),
                                                     default=0)
        output[name]['routedUnitsMissingFromControl'] = [
            key for key in routed if key not in control]
    return output


def compute_block(draws, pool, upto, tokenizer, encode_training_batch):
    control, act, state = draw_counts(draws, upto)
    updates = arm_updates(draws, upto)
    schedule = schedule_units(draws, pool, upto)
    tokens = {name: token_count(units, tokenizer, encode_training_batch)
              for name, units in schedule.items()}
    routed_tokens = {key: tokens['act'][key] + tokens['state'][key]
                     for key in ('inputTokens', 'targetTokens', 'totalTokens')}
    routed_updates = updates['act'] + updates['state']
    routed_draws = sum(act.values()) + sum(state.values())

    def flops(token_count_value):
        return 6 * PARAMS * token_count_value

    return {
        'globalSteps': upto,
        'examples': {'control': sum(control.values()),
                     'act': sum(act.values()),
                     'state': sum(state.values()),
                     'routed': routed_draws,
                     'threeModels': sum(control.values()) + routed_draws},
        'optimizerUpdates': {**updates, 'routed': routed_updates,
                             'threeModels': updates['control'] + routed_updates},
        'tokens': {**tokens, 'routed': routed_tokens,
                   'threeModels': {key: tokens['control'][key] + routed_tokens[key]
                                   for key in ('inputTokens', 'targetTokens',
                                               'totalTokens')}},
        'parameters': {'perModel': PARAMS,
                       'controlArm': PARAMS,
                       'routedDeployment': 3 * PARAMS,
                       'trainingRun': 3 * PARAMS},
        'approximateTrainingFlops': {
            'formula': '6 * parameters * tokens (order-of-magnitude only)',
            'control': flops(tokens['control']['totalTokens']),
            'act': flops(tokens['act']['totalTokens']),
            'state': flops(tokens['state']['totalTokens']),
            'routed': flops(routed_tokens['totalTokens']),
            'threeModels': flops(tokens['control']['totalTokens']
                                 + routed_tokens['totalTokens']),
        },
        'exposure': exposure_block(control, act, state),
    }


def main():
    freeze = json.loads(FREEZE.read_text(encoding='utf-8'))
    run = json.loads(RUN.read_text(encoding='utf-8'))
    point = run['selectedPoint']
    draws = rows(DRAWS)
    pool = load_pool()

    # Tokenisation is only needed for cost; it does not touch the models.
    sys.path.insert(0, str(HERE))
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    from sequence_policy import encode_training_batch
    tokenizer = T5Tokenizer.from_pretrained(
        str(ROOT / 'experiments' / 'world-components' / 'assets' / 'randeng-t5-77m'),
        legacy=False)

    selected = compute_block(draws, pool, point, tokenizer, encode_training_batch)
    full = compute_block(draws, pool, len(draws) // 8, tokenizer, encode_training_batch)
    doc = {
        'version': 'route-split-selection-basis-v1',
        'created': '2026-11-05',
        'ruleFrozenBeforeTraining': True,
        'ruleSource': str(FREEZE.relative_to(ROOT)),
        'ruleSha256': hashlib.sha256(FREEZE.read_bytes()).hexdigest(),
        'rule': freeze['selectionRule'],
        'ruleReading': (
            'The freeze has ONE shared-point rule for the arm-B pair. The control '
            'checkpoint is taken at that same global point; it is not independently '
            'selected. If the same lexicographic rule were applied to control alone, '
            '240 also has its highest mustExpress (12), but that is a descriptive '
            'check, not the selection basis.'),
        'observationPoints': freeze['observationPoints'],
        'devSet': {'path': 'experiments/world-components/n4_narrative_dev/dev-units-v1.jsonl',
                   'units': 14, 'routedToAct': 9, 'routedToState': 4,
                   'noChange': 1},
        'devTable': [{key: history[key] for key in ('point', 'control', 'routed')}
                     for history in run['history']],
        'selectedPoint': point,
        'selectedScore': run['selectionScore'],
        'selectionArithmetic': {
            'primary': 'routed mustExpress (higher)',
            'secondary': 'routed addition (lower)',
            'tertiary': 'routed repetition (lower)',
            'tie': 'earliest point',
            'note': ('both specialist checkpoints are taken from the SAME global '
                     'point; the control checkpoint at that point is the arm-B '
                     'no-change path and the control arm of the comparison'),
        },
        'exposureAtSelectedPoint': selected['exposure'],
        'exposureFullRun': full['exposure'],
        'computeAtSelectedPoint': selected,
        'computeFullRun': full,
        'exposureNote': (
            'Per-unit exposure is compared against control at the same global '
            'point. Totals are not the comparison: act and state are smaller pools '
            'by design, so their total draws are lower even when every routed unit '
            'has exactly the same draw count as in control.'),
        'trainingCostNote': (
            'The training loop ran all 2880 global steps and saved the 240 '
            'checkpoint at the end; the selected-point cost is the exposure the '
            'saved checkpoints actually consumed, while the full-run cost is what '
            'the search spent.'),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'selectedPoint': point,
        'exposureAtSelectedPoint': doc['exposureAtSelectedPoint'],
        'computeAtSelectedPoint': {
            key: doc['computeAtSelectedPoint'][key]
            for key in ('examples', 'optimizerUpdates', 'tokens',
                        'parameters', 'approximateTrainingFlops')},
        'computeFullRun': {
            key: doc['computeFullRun'][key]
            for key in ('examples', 'optimizerUpdates', 'tokens')}},
        ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
