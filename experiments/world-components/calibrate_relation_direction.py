"""Relation-direction calibration: margin only, no span term, no optimiser.

For each of the eight direction pairs it records
  * what the model freely generates, and whether the direction comes out right
  * s(correct) and s(swapped), and their gap
  * the gap of the generated text against both, so a generating error can be compared
    with what the model already prefers
and then, over the whole set, the activation rate, the gradient norms over **all**
parameters, the angle against CE, the joint gradient for a few betas, and whether an
extra forward shifts the dropout stream.

Nothing calls step(); the optimiser is never constructed.
"""
import argparse
import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'n4_narrative_dev'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--set', default='artifacts/relation-direction-r1/set.jsonl')
    parser.add_argument('--out', default='artifacts/next-runs/relcal-r1/calibration-report.json')
    parser.add_argument('--margin', type=float, default=1.0)
    parser.add_argument('--budget', type=float, default=20.0)
    parser.add_argument('--betas', default='0.1,0.3,1.0')
    args = parser.parse_args()

    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    from sequence_policy import generate_greedy

    torch.manual_seed(0)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = T5ForConditionalGeneration.from_pretrained(args.model, torch_dtype=torch.float32).to(device)
    tokenizer = T5Tokenizer.from_pretrained(args.model, legacy=False, local_files_only=True)
    eos = tokenizer.eos_token_id
    rows = [json.loads(line) for line in
            pathlib.Path(args.set).read_text(encoding='utf-8').splitlines() if line.strip()]

    def ids_of(text):
        return tokenizer(text, add_special_tokens=False).input_ids

    def encode_inputs(texts):
        enc = tokenizer(texts, padding=True, return_tensors='pt')
        return {k: v.to(device) for k, v in enc.items()}

    def mean_logprob(texts, targets):
        enc = encode_inputs(texts)
        labels = tokenizer(text_target=targets, padding=True, return_tensors='pt')
        labels.input_ids.masked_fill_(labels.attention_mask == 0, -100)
        out = model(**enc, labels=labels.input_ids.to(device))
        logp = torch.log_softmax(out.logits.float(), dim=-1)
        picked = logp.gather(2, labels.input_ids.to(device).clamp(min=0).unsqueeze(2)).squeeze(2)
        valid = labels.input_ids.to(device).ne(-100).float()
        return (picked * valid).sum(1) / valid.sum(1), out.loss

    def direction(text, row):
        """Judge the relation order, not the word order.

        A row can carry an extra possessor prefix (门框上的铜铃挂在门框上) and still
        place the relation correctly, so the check looks for the attachment pattern
        铜铃挂在门框 rather than comparing first positions.
        """
        attached, anchor, relation = row['attached'], row['anchor'], row['relation']
        ok = '%s%s在%s' % (attached, relation, anchor) in text
        rev = '%s%s在%s' % (anchor, relation, attached) in text
        if ok and not rev:
            verdict = 'correct'
        elif rev and not ok:
            verdict = 'reversed'
        elif ok and rev:
            verdict = 'both'
        elif attached not in text or anchor not in text:
            verdict = 'entity-missing'
        else:
            verdict = 'no-relation-clause'
        if text.count(anchor) > 1 or text.count(attached) > 1:
            verdict += '+repeat'
        return verdict

    # 1. free generation
    model.eval()
    per_row = []
    with torch.inference_mode():
        for row in rows:
            enc = encode_inputs([row['input']])
            tokens, meta = generate_greedy(model, enc, timeout_seconds=args.budget)
            text = tokenizer.decode(tokens[0][1:], skip_special_tokens=True)
            s_ok, _ = mean_logprob([row['input']], [row['target']])
            s_neg, _ = mean_logprob([row['input']], [row['negative']])
            s_gen, _ = mean_logprob([row['input']], [text])
            per_row.append({'unitId': row['unitId'], 'relation': row['relation'],
                            'target': row['target'], 'negative': row['negative'],
                            'generated': text, 'direction': direction(text, row),
                            'stop': meta.get('reason'),
                            'sCorrect': round(float(s_ok), 4), 'sSwapped': round(float(s_neg), 4),
                            'margin': round(float(s_ok - s_neg), 4),
                            'sGenerated': round(float(s_gen), 4)})

    margins = [r['margin'] for r in per_row]
    activation = {'threshold': args.margin,
                  'active': sum(1 for m in margins if m < args.margin),
                  'n': len(margins),
                  'min': min(margins), 'median': sorted(margins)[len(margins) // 2], 'max': max(margins)}

    # 2. gradients over every parameter
    params = [(name, p) for name, p in model.named_parameters()]
    enc = encode_inputs([r['input'] for r in rows])
    labels = tokenizer(text_target=[r['target'] for r in rows], padding=True, return_tensors='pt')
    labels.input_ids.masked_fill_(labels.attention_mask == 0, -100)
    labels = labels.input_ids.to(device)
    out = model(**enc, labels=labels)
    ce = out.loss
    g_ce = torch.autograd.grad(ce, [p for _, p in params], retain_graph=True, allow_unused=True)

    s_ok, _ = mean_logprob([r['input'] for r in rows], [r['target'] for r in rows])
    s_neg, _ = mean_logprob([r['input'] for r in rows], [r['negative'] for r in rows])
    terms = torch.clamp(args.margin - s_ok + s_neg, min=0.0)
    dir_loss = terms.mean()
    g_dir = torch.autograd.grad(dir_loss, [p for _, p in params], allow_unused=True)

    def norm(vecs):
        return math.sqrt(sum(float(v.pow(2).sum()) for v in vecs if v is not None))

    def dot(a, b):
        return sum(float((x * y).sum()) for x, y in zip(a, b) if x is not None and y is not None)

    def joint(alpha_dir):
        combined = [(g if g is not None else None) for g in g_ce]
        merged = [None if g is None else g + alpha_dir * d for g, d in zip(combined, g_dir)]
        return norm(merged)

    n_ce, n_dir = norm(g_ce), norm(g_dir)
    gradients = {'scope': 'all %d parameter tensors, %d rows, single batch' % (len(params), len(rows)),
                 'lossValues': {'ce': round(float(ce), 4), 'direction': round(float(dir_loss), 4)},
                 'norms': {'ce': round(n_ce, 5), 'direction': round(n_dir, 5)},
                 'cosine': round(dot(g_ce, g_dir) / (n_ce * n_dir), 4) if n_ce and n_dir else None,
                 'joint': {}, 'upperBoundNote': 'the weighted sum of norms is an upper bound, not the joint gradient'}
    for beta in [float(x) for x in args.betas.split(',')]:
        gradients['joint']['beta=%.1f' % beta] = {
            'jointNorm': round(joint(beta), 5),
            'sumOfNorms': round(n_ce + beta * n_dir, 5),
            'ratioToCe': round(joint(beta) / n_ce, 4)}
    gradients['activeShare'] = round(float((terms > 0).float().mean()), 4)

    # 3. dropout stream, with the direction negative as the extra forward
    devices = [torch.cuda.current_device()] if device == 'cuda' else []
    model.train()

    def fwd():
        return model(**enc, labels=labels).logits.detach().clone()

    torch.manual_seed(11)
    base_first = fwd()
    base_second = fwd()
    torch.manual_seed(11)
    first = fwd()
    fwd()
    after_no_fork = fwd()
    torch.manual_seed(11)
    first_forked = fwd()
    with torch.random.fork_rng(devices=devices):
        fwd()
    after_fork = fwd()
    rng = {'step1Reproduces': round(float((first - base_first).abs().max()), 6),
           'step1Forked': round(float((first_forked - base_first).abs().max()), 6),
           'step2NoFork': round(float((after_no_fork - base_second).abs().max()), 6),
           'step2Forked': round(float((after_fork - base_second).abs().max()), 6)}

    report = {'purpose': 'relation-direction margin calibration; margin only, k=1, no optimiser',
              'device': device, 'model': str(pathlib.Path(args.model).name),
              'rows': len(rows), 'activation': activation, 'gradients': gradients,
              'dropoutRng': rng, 'perRow': per_row,
              'optimizer': 'never constructed'}
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'activation': activation, 'gradients': gradients, 'dropoutRng': rng},
                     ensure_ascii=False, indent=1))
    for r in per_row:
        print('%-5s %s | gen=%s %s | margin %.3f' % (r['unitId'], r['relation'], r['direction'],
                                                    r['generated'], r['margin']))


if __name__ == '__main__':
    main()
