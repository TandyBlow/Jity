"""Pick beta for the direction-margin arm without touching any weight.

One batch, twelve training rows, m = 1. It reports the CE gradient norm, the margin gradient
norm, their cosine, and the joint norm for a few betas, then proposes the beta that makes
beta * |g_margin| equal a stated share of |g_ce|. The proposal is recorded and frozen before
any training run starts.
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
    parser.add_argument('--rows', default='artifacts/margin-r1/train.jsonl')
    parser.add_argument('--out', default='artifacts/next-runs/marginbeta-r1/report.json')
    parser.add_argument('--margin', type=float, default=1.0)
    parser.add_argument('--share', type=float, default=0.3,
                        help='Target ratio of the margin gradient norm to the CE gradient norm')
    args = parser.parse_args()

    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    torch.manual_seed(0)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = T5ForConditionalGeneration.from_pretrained(args.model, torch_dtype=torch.float32).to(device)
    model.eval()
    tokenizer = T5Tokenizer.from_pretrained(args.model, legacy=False, local_files_only=True)
    rows = [json.loads(line) for line in
            pathlib.Path(args.rows).read_text(encoding='utf-8').splitlines() if line.strip()]

    def batch(texts, key):
        enc = tokenizer([r['input'] for r in rows], padding=True, return_tensors='pt')
        enc = {k: v.to(device) for k, v in enc.items()}
        labels = tokenizer(text_target=[r[key] for r in rows], padding=True, return_tensors='pt')
        labels.input_ids.masked_fill_(labels.attention_mask == 0, -100)
        return enc, labels.input_ids.to(device)

    enc, labels = batch(rows, 'target')
    out = model(**enc, labels=labels)
    ce = out.loss
    mask = labels.ne(-100)
    logp = torch.log_softmax(out.logits.float(), dim=-1)
    picked = logp.gather(2, labels.clamp(min=0).unsqueeze(2)).squeeze(2)
    s_correct = (picked * mask).sum(1) / mask.sum(1)

    enc_neg, neg_labels = batch(rows, 'negative')
    neg_out = model(**enc_neg, labels=neg_labels)
    neg_mask = neg_labels.ne(-100)
    neg_logp = torch.log_softmax(neg_out.logits.float(), dim=-1)
    neg_picked = neg_logp.gather(2, neg_labels.clamp(min=0).unsqueeze(2)).squeeze(2)
    s_negative = (neg_picked * neg_mask).sum(1) / neg_mask.sum(1)

    gaps = (s_correct - s_negative).tolist()
    terms = torch.clamp(args.margin - s_correct + s_negative, min=0.0)
    direction = terms.mean()

    params = [p for _, p in model.named_parameters()]
    g_ce = torch.autograd.grad(ce, params, retain_graph=True, allow_unused=True)
    g_dir = torch.autograd.grad(direction, params, allow_unused=True)

    def norm(v):
        return math.sqrt(sum(float(x.pow(2).sum()) for x in v if x is not None))

    def dot(a, b):
        return sum(float((x * y).sum()) for x, y in zip(a, b) if x is not None and y is not None)

    n_ce, n_dir = norm(g_ce), norm(g_dir)
    beta = args.share * n_ce / n_dir if n_dir else 0.0
    joint = [(None if g is None else g + beta * d) for g, d in zip(g_ce, g_dir)]

    report = {
        'purpose': 'choose beta for the direction margin before any training; no weight changes',
        'device': device, 'model': str(pathlib.Path(args.model).name), 'rows': len(rows),
        'margin': args.margin,
        'gapsPerRow': [round(g, 4) for g in gaps],
        'activeShare': round(float((terms > 0).float().mean()), 4),
        'lossValues': {'ce': round(float(ce), 4), 'direction': round(float(direction), 4)},
        'norms': {'ce': round(n_ce, 5), 'direction': round(n_dir, 5)},
        'cosine': round(dot(g_ce, g_dir) / (n_ce * n_dir), 4) if n_ce and n_dir else None,
        'proposal': {'share': args.share, 'beta': round(beta, 6),
                     'jointNorm': round(norm(joint), 5),
                     'jointRatioToCe': round(norm(joint) / n_ce, 4),
                     'upperBound': round(n_ce + beta * n_dir, 5)},
        'optimizer': 'never constructed',
    }
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
