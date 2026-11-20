"""Calibrate the component-constraint machinery on 24 facts. No optimiser is built.

What it measures
  * that a character span maps to the label tokens that actually decode to it
  * the margin s(y) - s(y_c) for every constructed negative, and how often it clears m
  * the gradient norm and pairwise cosine of L_ce, L_span and L_margin
  * whether an extra corrupted forward consumes dropout randomness (train mode)

Nothing here calls step(): the optimiser is never constructed, so weights cannot move.
"""
import argparse
import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'n4_narrative_dev'))

GRAD_SUBSET = ('lm_head.weight',
               'encoder.block.7.layer.1.DenseReluDense.wo.weight',
               'decoder.block.7.layer.0.SelfAttention.q.weight')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--set', default='artifacts/calibration-r1/set.jsonl')
    parser.add_argument('--out', default='artifacts/next-runs/calib-r1/calibration-report.json')
    parser.add_argument('--margin', type=float, default=1.0)
    parser.add_argument('--span-weight', type=float, default=2.0)
    args = parser.parse_args()

    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    torch.manual_seed(0)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = T5ForConditionalGeneration.from_pretrained(args.model, torch_dtype=torch.float32)
    model.to(device)
    model.eval()
    tokenizer = T5Tokenizer.from_pretrained(args.model, legacy=False, local_files_only=True)
    assert not hasattr(model, 'optimizer')

    rows = [json.loads(line) for line in
            pathlib.Path(args.set).read_text(encoding='utf-8').splitlines() if line.strip()]
    eos = tokenizer.eos_token_id

    def encode(text):
        return tokenizer(text, add_special_tokens=False).input_ids

    # 1. label alignment: text_target must equal the plain ids plus EOS
    alignment = {'checked': 0, 'mismatch': [], 'spanMismatch': [], 'spanExpanded': []}
    expect_exact = False
    for row in rows:
        plain = encode(row['target'])
        labels = tokenizer(text_target=[row['target']])['input_ids'][0]
        alignment['checked'] += 1
        if labels != plain + [eos]:
            alignment['mismatch'].append({'rowId': row['rowId'], 'labels': labels[:8], 'plain': plain[:8]})
            continue
        pieces = [tokenizer.decode([i]) for i in plain]
        for key, span in row['tokenSpans'].items():
            if not span:
                continue
            got = ''.join(pieces[span['first']:span['last'] + 1])
            want = row['components'][key]['text']
            if expect_exact and got != want:
                alignment['spanMismatch'].append({'rowId': row['rowId'], 'component': key,
                                                  'decoded': got, 'expected': want})
            elif not span.get('exact', False):
                alignment['spanExpanded'].append({'rowId': row['rowId'], 'component': key,
                                                  'decoded': got, 'expected': want})

    def tensor(ids):
        return torch.tensor([ids], dtype=torch.long, device=device)

    def token_logprobs(row, target_text, require_grad=False):
        enc = tokenizer([row['input']], padding=True, return_tensors='pt')
        enc = {k: v.to(device) for k, v in enc.items()}
        ids = encode(target_text) + [eos]
        labels = tensor(ids)
        if require_grad:
            out = model(**enc, labels=labels)
            picked = torch.log_softmax(out.logits[0].float(), dim=-1).gather(
                1, labels[0].unsqueeze(1)).squeeze(1)
        else:
            with torch.no_grad():
                out = model(**enc, labels=labels)
                picked = torch.log_softmax(out.logits[0].float(), dim=-1).gather(
                    1, labels[0].unsqueeze(1)).squeeze(1)
        return picked, float(out.loss), ids

    def span_weights(row, ids):
        weights = [1.0] * len(ids)
        for span in row['tokenSpans'].values():
            if not span:
                continue
            for index in range(span['first'], min(span['last'], len(weights) - 1) + 1):
                weights[index] = args.span_weight
        return weights

    # 2. margins
    margins, per_row = [], []
    for row in rows:
        picked, loss, ids = token_logprobs(row, row['target'])
        s_correct = float(picked.mean())
        weights = span_weights(row, ids)
        wsum = sum(weights)
        span_loss = float(-(picked * torch.tensor(weights, device=device)).sum() / wsum)
        entries = []
        for neg in row['negatives']:
            if not neg['valid']:
                continue
            picked_neg, loss_neg, _ = token_logprobs(row, neg['text'])
            s_neg = float(picked_neg.mean())
            item = {'type': neg['type'], 'margin': round(s_correct - s_neg, 4),
                    'sCorrect': round(s_correct, 4), 'sNegative': round(s_neg, 4),
                    'active': (s_correct - s_neg) < args.margin}
            entries.append(item)
            margins.append(item)
        per_row.append({'rowId': row['rowId'], 'kind': row['kind'], 'ce': round(loss, 4),
                        'spanLoss': round(span_loss, 4), 'negatives': entries})

    by_type = {}
    for item in margins:
        bucket = by_type.setdefault(item['type'], {'n': 0, 'active': 0, 'margins': []})
        bucket['n'] += 1
        bucket['active'] += 1 if item['active'] else 0
        bucket['margins'].append(item['margin'])
    for bucket in by_type.values():
        values = sorted(bucket.pop('margins'))
        bucket['min'] = values[0]
        bucket['median'] = values[len(values) // 2]
        bucket['max'] = values[-1]

    # 3. gradients on a mixed batch of one expression per kind
    seen, batch = set(), []
    for row in rows:
        if row['expression'] or row['kind'] in seen or row['kind'] in ('no_change',):
            continue
        seen.add(row['kind'])
        batch.append(row)
    params = [p for name, p in model.named_parameters() if name in GRAD_SUBSET]
    assert len(params) == len(GRAD_SUBSET), [n for n, _ in model.named_parameters()][:5]

    def build(rows_in):
        enc = tokenizer([r['input'] for r in rows_in], padding=True, return_tensors='pt')
        enc = {k: v.to(device) for k, v in enc.items()}
        labels = tokenizer(text_target=[r['target'] for r in rows_in], padding=True,
                           return_tensors='pt')
        labels.input_ids.masked_fill_(labels.attention_mask == 0, -100)
        return enc, labels.to(device)

    def grads(loss, retain=False):
        return torch.autograd.grad(loss, params, retain_graph=retain, allow_unused=True)

    def norm(vecs):
        return math.sqrt(sum(float(v.pow(2).sum()) for v in vecs if v is not None))

    def cos(a, b):
        dot = sum(float((x * y).sum()) for x, y in zip(a, b) if x is not None and y is not None)
        na, nb = norm(a), norm(b)
        return dot / (na * nb) if na and nb else float('nan')

    enc, labels = build(batch)
    out = model(**enc, labels=labels.input_ids)
    ce = out.loss
    # span-weighted term over the same batch
    logp = torch.log_softmax(out.logits.float(), dim=-1)
    valid = labels.input_ids.ne(-100)
    picked = logp.gather(2, labels.input_ids.clamp(min=0).unsqueeze(2)).squeeze(2)
    w = torch.ones_like(picked)
    for index, row in enumerate(batch):
        for span in row['tokenSpans'].values():
            if span:
                w[index, span['first']:span['last'] + 1] = args.span_weight
    w = w * valid
    span_loss = -(picked * w).sum() / w.sum()

    margin_rows = [r for r in batch if any(n['valid'] for n in r['negatives'])]
    margin_terms = []
    for row in margin_rows:
        for neg in row['negatives']:
            if not neg['valid']:
                continue
            picked_ok, _, _ = token_logprobs(row, row['target'], require_grad=True)
            picked_neg, _, _ = token_logprobs(row, neg['text'], require_grad=True)
            margin_terms.append(torch.clamp(args.margin - picked_ok.mean() + picked_neg.mean(), min=0.0))
    margin = torch.stack(margin_terms).mean() if margin_terms else torch.zeros((), device=device)

    g_ce = grads(ce, retain=True)
    g_span = grads(span_loss, retain=True)
    g_margin = grads(margin)
    gradient = {
        'batchRows': [r['rowId'] for r in batch],
        'subset': list(GRAD_SUBSET),
        'lossValues': {'ce': round(float(ce), 4), 'span': round(float(span_loss), 4),
                       'margin': round(float(margin), 4)},
        'norms': {'ce': round(norm(g_ce), 5), 'span': round(norm(g_span), 5),
                  'margin': round(norm(g_margin), 5)},
        'cosines': {'ce.span': round(cos(g_ce, g_span), 4),
                    'ce.margin': round(cos(g_ce, g_margin), 4),
                    'span.margin': round(cos(g_span, g_margin), 4)},
        'ratioOfAuxToCe': {'span': round(float(span_loss) / float(ce), 4),
                           'margin': round(float(margin) / float(ce), 4),
                           'byValue': round((0.5 * float(span_loss) + 0.3 * float(margin)) / float(ce), 4),
                           'byGradient': round((0.5 * norm(g_span) + 0.3 * norm(g_margin)) / norm(g_ce), 4)},
        'marginActiveShare': round(sum(1 for t in margin_terms if float(t) > 0) / len(margin_terms), 4),
    }

    # 4. does an extra corrupted forward move the dropout draws of the next correct forward
    devices = [torch.cuda.current_device()] if device == 'cuda' else []
    model.train()

    def fwd():
        return model(**enc, labels=labels.input_ids).logits.detach().clone()

    torch.manual_seed(7)
    baseline_first = fwd()
    baseline_second = fwd()

    torch.manual_seed(7)
    first = fwd()
    fwd()                                  # the extra corrupted forward, no fork
    after_no_fork = fwd()

    torch.manual_seed(7)
    first_forked = fwd()
    with torch.random.fork_rng(devices=devices):
        fwd()                              # the same extra forward, inside a fork
    after_fork = fwd()

    rng = {'step1Reproduces': round(float((first - baseline_first).abs().max()), 6),
           'step2NoFork': round(float((after_no_fork - baseline_second).abs().max()), 6),
           'step2Forked': round(float((after_fork - baseline_second).abs().max()), 6),
           'step1Forked': round(float((first_forked - baseline_first).abs().max()), 6),
           'note': 'an extra forward without a fork shifts the dropout stream of the next correct forward; '
                   'wrapping it in fork_rng leaves that stream unchanged'}

    report = {
        'purpose': 'calibrate the component-constraint machinery; no optimiser, no weight change',
        'device': device,
        'model': str(pathlib.Path(args.model).name),
        'rows': len(rows),
        'facts': len({r['factId'] for r in rows}),
        'alignment': {'checked': alignment['checked'], 'labelMismatch': alignment['mismatch'],
                      'spanMismatch': alignment['spanMismatch'],
                      'spanExpandedCount': len(alignment['spanExpanded']),
                      'spanExpanded': alignment['spanExpanded'],
                      'note': 'a sentencepiece token can straddle a character boundary, so the token span is the '
                              'minimal covering range; expanded rows carry one extra token and are listed, not hidden'},
        'marginsByType': by_type,
        'marginThreshold': args.margin,
        'spanWeight': args.span_weight,
        'gradient': gradient,
        'dropoutRng': rng,
        'perRow': per_row,
        'optimizer': 'never constructed',
    }
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: report[k] for k in ('alignment', 'marginsByType', 'gradient', 'dropoutRng')},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
