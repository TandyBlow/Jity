"""Evaluate the routed-split arms on the fixed 215-unit diagnostic sets and the
10 real rounds.

Arms
  control : the new single model (u240 recipe replay) -- NOT the frozen u240
  routed  : act model for moved/outcome, state model for
            appearance_changed/sanity_changed/personality_changed,
            control for no_change (unchanged path)
Both arms use the SAME checkpoint point inside their own arm. Product decode
budget (20 s) is used here; dev selection used 3 s. Completion is recorded
per unit and reported separately from the four quality metrics.
"""
from __future__ import annotations

import argparse
import importlib.machinery
import json
import pathlib
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
from sequence_policy import generate_greedy  # noqa: E402
from conservative_edit import strip_subject  # noqa: E402

ART = ROOT / 'artifacts' / 'world-components'
OUT = ART / 'route-split-eval-v1.json'
ROUNDS = ROOT / 'artifacts' / 'world-provenance' / 'pairs' / 'rounds.jsonl'
CKPT = WC / 'assets' / 'n4-finetune'
SETS = [('final24', 'n4-final24-contract.jsonl'),
        ('cf24', 'n4-cf24-contract.jsonl'),
        ('object18', 'n4-object18-contract.jsonl'),
        ('expand36', 'n4-expand36-contract.jsonl')]
ACT_KINDS = {'moved', 'outcome'}
STATE_KINDS = {'appearance_changed', 'sanity_changed', 'personality_changed'}
BUDGET = 20.0


def rows(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding='utf-8').splitlines()
            if l.strip()]


def route_arm(kind):
    if kind in ACT_KINDS:
        return 'act'
    if kind in STATE_KINDS:
        return 'state'
    return 'control'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', default=str(ART / 'route-split-run-v1.json'))
    ap.add_argument('--out', default=str(OUT))
    ap.add_argument('--budget', type=float, default=BUDGET)
    args = ap.parse_args()

    rep = json.loads(pathlib.Path(args.report).read_text(encoding='utf-8'))
    point = rep['selectedPoint']
    print('selected point', point)

    tok = T5Tokenizer.from_pretrained(str(CKPT / f'route-control-s{point}'), legacy=False)
    models = {}
    for nm in ('control', 'act', 'state'):
        m = T5ForConditionalGeneration.from_pretrained(
            str(CKPT / f'route-{nm}-s{point}'), torch_dtype=torch.float32)
        m.to('cuda' if torch.cuda.is_available() else 'cpu').eval()
        models[nm] = m
    device = next(models['control'].parameters()).device

    def gen(nm, prompt):
        t0 = time.perf_counter()
        enc = tok(prompt, return_tensors='pt', truncation=False).to(device)
        ids, meta = generate_greedy(models[nm], enc, args.budget)
        text = tok.decode(ids[0], skip_special_tokens=True)
        return text, meta, round(time.perf_counter() - t0, 3)

    # ---------------- diagnostic sets
    diag = {}
    for setname, fn in SETS:
        units = rows(ART / fn)
        out = []
        for u in units:
            arm_c, arm_r = 'control', route_arm(u['kind'])
            tc, mc, sc = gen(arm_c, u['input'])
            tr, mr, sr = gen(arm_r, u['input'])
            jc = J.judge_unit_row(u, tc)
            jr = J.judge_unit_row(u, tr)
            out.append({'unitId': u['unitId'], 'kind': u['kind'], 'set': setname,
                        'input': u['input'], 'fact': u['fact'],
                        'control': {'text': tc, 'complete': mc['complete'],
                                    'stopReason': mc['stopReason'], 'seconds': sc, **jc},
                        'routed': {'text': tr, 'complete': mr['complete'],
                                   'stopReason': mr['stopReason'], 'seconds': sr,
                                   'arm': arm_r, **jr}})
        diag[setname] = out
        print(setname, 'control', J.summarize(
            [{k: r['control'][k] for k in ('mustExpress', 'binding', 'repetition',
                                           'addition', 'extraAction', 'extraObject',
                                           'extraState')} for r in out]),
            'routed', J.summarize(
            [{k: r['routed'][k] for k in ('mustExpress', 'binding', 'repetition',
                                          'addition', 'extraAction', 'extraObject',
                                          'extraState')} for r in out]), flush=True)

    # ---------------- real rounds
    sys.path.insert(0, str(HERE))
    from n4_pipeline import unit_input  # noqa: E402
    rounds = rows(ROUNDS)
    round_out = []
    for rd in rounds:
        units = rd['payload']['units']
        per = []
        for u in units:
            fact, prompt = unit_input(u)
            arm_c, arm_r = 'control', route_arm(u['kind'])
            tc, mc, sc = gen(arm_c, prompt)
            tr, mr, sr = gen(arm_r, prompt)
            jc = J.judge_unit(u['kind'], '', tc) if False else J.judge_unit_row(
                {'fact': fact, 'input': prompt}, tc)
            jr = J.judge_unit_row({'fact': fact, 'input': prompt}, tr)
            per.append({'factId': u['factId'], 'kind': u['kind'], 'name': u['name'],
                        'factText': u.get('text'), 'prompt': prompt,
                        'control': {'text': tc, 'complete': mc['complete'],
                                    'seconds': sc, **jc},
                        'routed': {'text': tr, 'complete': mr['complete'],
                                   'seconds': sr, 'arm': arm_r, **jr}})
        # assemble the paragraph with the same two-layer edit (no relations here)
        def assemble(key):
            units_in = [{'factId': p['factId'], 'name': p['name'],
                         'text': p[key]['text'].strip(),
                         'entityId': ''} for p in per]
            blocks, i = [], 0
            while i < len(units_in):
                head = units_in[i]
                run = [head]
                while i + len(run) < len(units_in) and \
                        units_in[i + len(run)]['name'] == head['name']:
                    body, _op = strip_subject(units_in[i + len(run)]['text'],
                                              units_in[i + len(run)]['name'])
                    if body is None:
                        break
                    run.append(units_in[i + len(run)])
                parts = [run[0]['text'].rstrip('。')]
                for extra in run[1:]:
                    body, _op = strip_subject(extra['text'], extra['name'])
                    parts.append(body)
                blocks.append('，'.join(parts) + '。')
                i += len(run)
            return ''.join(blocks)

        para_c, para_r = assemble('control'), assemble('routed')
        round_out.append({'roundId': rd['roundId'], 'units': per,
                          'paragraphControl': para_c, 'paragraphRouted': para_r})
        print('round', rd['roundId'], 'units', len(per), flush=True)

    def summ_diag(arm):
        allrows = []
        for setname, rs in diag.items():
            allrows += [r[arm] for r in rs]
        return {'all': J.summarize(allrows),
                'perSet': {s: J.summarize([r[arm] for r in rs])
                           for s, rs in diag.items()}}

    def summ_rounds(arm):
        allrows = [p[arm] for r in round_out for p in r['units']]
        return J.summarize(allrows)

    # differing cases, for manual reading
    diff = []
    for setname, rs in diag.items():
        for r in rs:
            c, t = r['control'], r['routed']
            keys = ('mustExpress', 'binding', 'repetition', 'addition')
            if any(c[k] != t[k] for k in keys):
                diff.append({'set': setname, 'unitId': r['unitId'], 'kind': r['kind'],
                             'control': {k: c[k] for k in keys} | {'text': c['text']},
                             'routed': {k: t[k] for k in keys} | {'text': t['text']}})

    completion = {}
    for setname, rs in diag.items():
        completion[setname] = {
            'controlIncomplete': sum(1 for r in rs if not r['control']['complete']),
            'routedIncomplete': sum(1 for r in rs if not r['routed']['complete']),
            'units': len(rs),
            'controlMeanSeconds': round(sum(r['control']['seconds'] for r in rs) / len(rs), 2),
            'routedMeanSeconds': round(sum(r['routed']['seconds'] for r in rs) / len(rs), 2)}
    completion['rounds'] = {
        'controlIncomplete': sum(1 for r in round_out for p in r['units']
                                 if not p['control']['complete']),
        'routedIncomplete': sum(1 for r in round_out for p in r['units']
                                if not p['routed']['complete']),
        'units': sum(len(r['units']) for r in round_out)}

    doc = {
        'version': 'route-split-eval-v1',
        'selectedPoint': point,
        'decodeBudgetSeconds': args.budget,
        'diagnostic': {'control': summ_diag('control'), 'routed': summ_diag('routed')},
        'rounds': {'control': summ_rounds('control'), 'routed': summ_rounds('routed')},
        'completion': completion,
        'differingCases': diff,
        'rows': diag,
        'roundRows': round_out,
    }
    pathlib.Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                                      encoding='utf-8')
    print(json.dumps({'diagAll': doc['diagnostic'], 'rounds': doc['rounds'],
                      'completion': completion,
                      'differing': len(diff)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
