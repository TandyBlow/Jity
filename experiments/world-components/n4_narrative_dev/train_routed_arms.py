"""One fixed comparison: one model (u240 recipe) vs two models routed by fact kind.

Shared global schedule: the archived u240 sampling log
(artifacts/world-components/n4-mix431-draws.jsonl, 2880 steps x 8 draws).
Every arm replays the SAME log, so at global step s each routed model has seen
exactly the draws of its own kind up to s -- each training unit keeps the
exposure count it had in u240.

Arms
  control : one model, all 8 draws per step        (the u240 recipe)
  act     : kind in {moved, outcome}                (action / movement)
  state   : kind in {appearance_changed, sanity_changed, personality_changed}
  no_change is outside the split: it keeps the control checkpoint at the same
  global observation point (the "existing path").

Observation points: every 240 global steps (12 points). At each point the
FULL dev workflow is generated and edited for arm B (act for action kinds,
state for state kinds, control for no-change) and for arm A. The pair for arm B
is chosen at ONE shared point, never per model.
"""
from __future__ import annotations

import argparse
import importlib.machinery
import json
import pathlib
import random
import re
import sys
import time
import types

try:
    import pyarrow  # noqa: F401
except Exception:
    _stub = types.ModuleType('pyarrow')
    _stub.__version__ = '16.1.0'
    _stub.__path__ = []
    sys.modules['pyarrow'] = _stub
_tf = types.ModuleType('tensorflow')
_tf.__spec__ = importlib.machinery.ModuleSpec('tensorflow', None)
_tf.__path__ = []
sys.modules.setdefault('tensorflow', _tf)

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import fact_contract as FC  # noqa: E402
import judge_expression as J  # noqa: E402
from sequence_policy import encode_training_batch, generate_greedy  # noqa: E402
from conservative_edit import strip_subject  # noqa: E402

BASE = WC / 'assets' / 'randeng-t5-77m'
DRAWS = ROOT / 'artifacts' / 'world-components' / 'n4-mix431-draws.jsonl'
UNITS = HERE / 'verbalizer_pairs.jsonl'
EXPAND = ROOT / 'artifacts' / 'world-components' / 'n4-expand78-unified.jsonl'
OBJECTS = ROOT / 'artifacts' / 'world-components' / 'n4-object-train40-clean.jsonl'
MANIFEST = ROOT / 'artifacts' / 'world-components' / 'n4-two-arm-manifest-r1.json'
OUT = ROOT / 'artifacts' / 'world-components' / 'n4-route-split-run-v1.json'
ART = ROOT / 'artifacts' / 'world-components'
CKPT = WC / 'assets' / 'n4-finetune'

SEED = 20261102
LR = 3e-4
STEPS = 2880
OBSERVE_EVERY = 240

ACT_KINDS = {'moved', 'outcome'}
STATE_KINDS = {'appearance_changed', 'sanity_changed', 'personality_changed'}
NOCHANGE = {'no_change'}


def rows(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding='utf-8').splitlines()
            if l.strip()]


def key_of(u):
    return u.get('unitId') or u.get('pairId') or f"{u.get('sourceId')}:{u.get('factId')}"


def posa_of(u):
    return u.get('pairId') or u.get('unitId')


def name_of_input(inp):
    m = re.search(r'视角=([^；\n]+)', inp or '')
    return m.group(1).strip() if m else ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dev-units', default=str(HERE / 'dev-units-v1.jsonl'))
    ap.add_argument('--out', default=str(OUT))
    ap.add_argument('--dev-budget', type=float, default=3.0,
                    help='diagnostic decode budget for dev selection (product budget is 20 s)')
    ap.add_argument('--progress', default=str(ART / 'route-split-progress-v1.jsonl'))
    ap.add_argument('--max-steps', type=int, default=0, help='smoke only')
    ap.add_argument('--observe-every', type=int, default=0, help='smoke only')
    args = ap.parse_args()
    global STEPS, OBSERVE_EVERY
    smoke = bool(args.max_steps)
    if smoke:
        STEPS = args.max_steps
        OBSERVE_EVERY = args.observe_every or args.max_steps

    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    split = {s['sourceId']: s['split'] for s in manifest['sources']}
    base_units = rows(UNITS)
    orig = [u for u in base_units if split.get(u['sourceId']) == 'formal-train']
    dev = [u for u in base_units if split.get(u['sourceId']) == 'formal-dev']
    expand = rows(EXPAND)
    objects = rows(OBJECTS)
    # The contract check runs on the verbalizer + expansion pools. The object
    # pool predates the current `外貌变化` label and carries `外观` instead; it
    # was trained as-is by u240, so its bytes are NOT rewritten here. The
    # deviation is recorded rather than silently repaired.
    FC.check_units(orig + expand)
    for u in objects:
        assert u['kind'] in ('appearance_changed', 'outcome'), u['unitId']
        assert '事实=' in u['input'] and u['target'].strip(), u['unitId']
    objectLabelDeviation = sorted({m.group(1) for u in objects
                                   for m in [__import__('re').search(r'事实=([^｜]+)｜', u['input'])]
                                   if m})

    draws = rows(DRAWS)
    assert len(draws) >= STEPS * 8, len(draws)

    pool = {}
    for pool_name, units in (('orig', orig), ('expand', expand), ('object', objects)):
        for u in units:
            pool[(pool_name, key_of(u))] = u

    # schedule: per global step, the routed subsets
    sched_control, sched_act, sched_state, sched_other = [], [], [], []
    for step in range(STEPS):
        chunk = draws[step * 8:(step + 1) * 8]
        c, a, s, o = [], [], [], []
        for d in chunk:
            u = pool[(d['pool'], d['unitId'])]
            c.append(u)
            if d['kind'] in ACT_KINDS:
                a.append(u)
            elif d['kind'] in STATE_KINDS:
                s.append(u)
            else:
                o.append(u)
        sched_control.append(c)
        sched_act.append(a)
        sched_state.append(s)
        sched_other.append(o)

    def counts(sched):
        return {'stepsWithData': sum(1 for b in sched if b),
                'updatesPerUnit': dict(sorted(
                    {k: sum(1 for b in sched for u in b if key_of(u) == k)
                     for k in {key_of(u) for b in sched for u in b}}.items()))}

    exposure = {nm: counts(sc) for nm, sc in
                (('control', sched_control), ('act', sched_act), ('state', sched_state))}
    for nm in exposure:
        vals = list(exposure[nm]['updatesPerUnit'].values())
        exposure[nm]['unitCount'] = len(vals)
        exposure[nm]['totalUpdates'] = sum(vals)
        exposure[nm]['minExposure'] = min(vals) if vals else None
        exposure[nm]['maxExposure'] = max(vals) if vals else None

    freeze = {
        'version': 'route-split-freeze-v1', 'created': '2026-11-05',
        'samplingLog': str(DRAWS.relative_to(ROOT)),
        'samplingLogSha256': __import__('hashlib').sha256(DRAWS.read_bytes()).hexdigest(),
        'sharedGlobalSteps': STEPS, 'observeEvery': OBSERVE_EVERY,
        'observationPoints': list(range(OBSERVE_EVERY, STEPS + 1, OBSERVE_EVERY)),
        'routing': {'act': sorted(ACT_KINDS), 'state': sorted(STATE_KINDS),
                    'no_change': 'control checkpoint at the same global point'},
        'base': str(BASE.relative_to(WC)),
        'baseSha256': __import__('hashlib').sha256((BASE / 'model.safetensors').read_bytes()).hexdigest(),
        'devDecodeBudgetSeconds': args.dev_budget,
        'hyper': {'seed': SEED, 'lr': LR, 'optimizer': 'AdamW', 'precision': 'fp32',
                  'batch': 'routed subset of the 8 draws (no resampling)',
                  'truncation': False},
        'exposure': exposure,
        'objectPoolFactLabel': objectLabelDeviation,
        'objectPoolNote': 'the object pool writes 外观 where the current contract '
                          'writes 外貌变化; u240 trained these bytes unchanged, so they '
                          'are kept and recorded instead of rewritten',
        'selectionRule': [
            'one shared observation point for the whole arm-B pair (never per model)',
            'primary: dev must-express units / total routed dev units (higher)',
            'secondary: fewer dev unauthorized-addition units',
            'tertiary: fewer dev repetition units',
            'tie: earliest observation point',
        ],
        'devHint': 'formal-dev units of the same material; the fixed diagnostic sets and '
                   'the real rounds are reporting-only and never used for selection',
    }
    ART.mkdir(parents=True, exist_ok=True)
    (ART / 'route-split-freeze-v1.json').write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'exposure': {k: {kk: vv for kk, vv in v.items()
                                       if kk != 'updatesPerUnit'}
                                   for k, v in exposure.items()}},
                     ensure_ascii=False, indent=1))

    # ---- dev rows (routed), from the frozen dev file
    dev_rows = rows(HERE / 'dev-units-v1.jsonl')
    dev_freeze = json.loads((ART / 'route-split-dev-freeze-v1.json').read_text(encoding='utf-8'))
    got = __import__('hashlib').sha256((HERE / 'dev-units-v1.jsonl').read_bytes()).hexdigest()
    if got != dev_freeze['sha256']:
        raise SystemExit('REFUSED: dev units moved after the freeze')

    tok = T5Tokenizer.from_pretrained(str(BASE), legacy=False)
    models = {}
    opt = {}
    for nm in ('control', 'act', 'state'):
        m = T5ForConditionalGeneration.from_pretrained(str(BASE), torch_dtype=torch.float32)
        m.to('cuda' if torch.cuda.is_available() else 'cpu')
        models[nm] = m
        opt[nm] = torch.optim.AdamW(m.parameters(), lr=LR)
    device = next(models['control'].parameters()).device
    torch.manual_seed(SEED)
    random.seed(SEED)

    def generate(m, r):
        m.eval()
        enc = tok(r['input'], return_tensors='pt', truncation=False).to(device)
        ids, meta = generate_greedy(m, enc, args.dev_budget)
        txt = tok.decode(ids[0], skip_special_tokens=True)
        m.train()
        return txt, meta

    def routed_arm_b(r):
        if r['kind'] in ACT_KINDS:
            return 'act'
        if r['kind'] in STATE_KINDS:
            return 'state'
        return 'control'

    def dev_eval(point):
        out = {'control': [], 'routed': []}
        for r in dev_rows:
            t, meta = generate(models['control'], r)
            out['control'].append({**r, 'text': t, 'complete': meta['complete']})
            which = routed_arm_b(r)
            t2, meta2 = generate(models[which], r)
            out['routed'].append({**r, 'text': t2, 'complete': meta2['complete'],
                                  'routedTo': which})
        res = {}
        for arm in ('control', 'routed'):
            judged = [J.judge_unit(x['fact'], x['input'], x['text']) for x in out[arm]]
            res[arm] = J.summarize(judged)
            res[arm + 'Rows'] = [{k: x[k] for k in ('id', 'kind', 'text')} | judged[i]
                                 for i, x in enumerate(out[arm])]
        res['point'] = point
        return res

    history = []
    best = None
    t0 = time.perf_counter()
    for step in range(STEPS):
        for nm, sched in (('control', sched_control), ('act', sched_act),
                          ('state', sched_state)):
            batch = sched[step]
            if not batch:
                continue
            enc, labels = encode_training_batch(tok, batch)
            enc = {k: v.to(device) for k, v in enc.items()}
            m = models[nm]
            m.train()
            try:
                out = m(**enc, labels=labels.input_ids.to(device))
            except torch.cuda.OutOfMemoryError:
                raise SystemExit(f'OOM at step {step} arm {nm} batch {len(batch)}')
            opt[nm].zero_grad()
            out.loss.backward()
            opt[nm].step()
        gstep = step + 1
        if gstep % OBSERVE_EVERY == 0:
            d = dev_eval(gstep)
            d['lossesHandled'] = True
            history.append(d)
            rb = d['routed']
            score = (rb['mustExpress'], -rb['addition'], -rb['repetition'], -gstep)
            if best is None or score > best[0]:
                best = (score, gstep, {nm: {k: v.detach().cpu().clone()
                                            for k, v in models[nm].state_dict().items()}
                                       for nm in models})
            line = json.dumps({'point': gstep, 'control': d['control'],
                               'routed': rb}, ensure_ascii=False)
            print(line, flush=True)
            with open(args.progress, 'a', encoding='utf-8') as fh:
                fh.write(line + chr(10))
            if gstep == STEPS:
                break

    score, point, states = best
    for nm in models:
        models[nm].load_state_dict(states[nm])
    saved = {}
    if smoke:
        print(json.dumps({'smoke': 'ok', 'point': point,
                          'routed': [h for h in history if h['point'] == point][0]['routed']},
                         ensure_ascii=False))
        return 0
    for nm in models:
        p = CKPT / f'route-{nm}-s{point}'
        models[nm].save_pretrained(str(p))
        tok.save_pretrained(str(p))
        saved[nm] = str(p)
    ckpt_control = CKPT / 'route-control-u240recipe'
    models['control'].save_pretrained(str(ckpt_control))
    tok.save_pretrained(str(ckpt_control))
    saved['controlAnyPoint'] = str(ckpt_control)

    report = {
        'version': 'route-split-run-v1',
        'freeze': freeze,
        'selectedPoint': point,
        'selectionScore': list(score),
        'selectedAtPoint': [h for h in history if h['point'] == point][0],
        'history': [{k: v for k, v in h.items() if not k.endswith('Rows')}
                    for h in history],
        'devRowsAtSelectedPoint': [h for h in history if h['point'] == point][0],
        'devDecodeBudgetSeconds': args.dev_budget,
        'wallSeconds': round(time.perf_counter() - t0, 1),
        'saved': saved,
        'cost': {'models': 3, 'paramsPerModel': sum(p.numel() for p in models['control'].parameters()),
                 'note': 'arm B runs 2 models; the control model is also the no-change path '
                         'in arm B, so the 3rd copy exists only for this comparison'},
    }
    pathlib.Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                      encoding='utf-8')
    print(json.dumps({'selectedPoint': point, 'wallSeconds': report['wallSeconds'],
                      'saved': saved}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
