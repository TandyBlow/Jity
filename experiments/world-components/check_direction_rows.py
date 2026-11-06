"""Check whether the previously confirmed direction errors still exist at C, and whether a
direction margin would actually cover them.

Group: the six location-reference rolepair rows, taken whole. Those are the rows the blind review
judged as reversed (R02, R08, R09, R15, R17, R35, R36 all map into this half). No filtering by
whether the error reproduces.

For each row three texts are scored: the correct target, the legal reversal (the name used as the
agent of the relation, which is exactly the observed error shape), and what the model generates.
Both the summed log-probability including EOS and the per-token mean are reported, so a length
difference cannot be mistaken for a preference.

No optimiser is built and no weights change.
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'n4_narrative_dev'))

# unitId -> (correct, reversed) built from the frozen probe fields:
#   correct  = relation + 在 + name + locative + 的 + other + predicate
#   reversed = name + relation + 着 + 的 + other + predicate
PAIRS = {
    'p-rp1b': ('压在潮汐簿上的干纸滑开了。', '潮汐簿压着的干纸滑开了。'),
    'p-rp2b': ('靠在木桩上的渡船退了半尺。', '木桩靠着的渡船退了半尺。'),
    'p-rp3b': ('堆在鱼筐底的银鳞鱼露出来。', '鱼筐堆着的银鳞鱼露出来。'),
    'p-rp4b': ('插在铜灯罩里的灯芯歪了。', '铜灯罩插着的灯芯歪了。'),
    'p-rp5b': ('靠在石板上的油纸伞歪了。', '石板靠着的油纸伞歪了。'),
    'p-rp6b': ('搭在钟架上的钟绳垂到堤面。', '钟架搭着的钟绳垂到堤面。'),
}
CONFIRMED = {'R02': 'p-rp6b', 'R08': 'p-rp4b', 'R09': 'p-rp1b', 'R15': 'p-rp3b',
             'R17': 'p-rp5b', 'R35': 'p-rp3b', 'R36': 'p-rp2b'}


def classify(text, row, correct, reversed_):
    """What kind of error does the generated sentence carry?"""
    name, other, relation = row['name'], row['other'], row['relation']
    tags = []
    if text.count(name) > 1 or text.count(other) > 1:
        tags.append('repeat')
    if other not in text:
        tags.append('other-missing')
    if name not in text:
        tags.append('name-missing')
    if name in text and other in text and (name + '的') in text:
        tail = text.split(name + '的', 1)[1]
        if tail.startswith(other) or tail.startswith(relation):
            tags.append('possessive-swap')
    if name in text and relation in text:
        after = text.split(name, 1)[1]
        if after.startswith(relation) or after.startswith('的' + relation):
            tags.append('name-as-agent')
    if relation not in text:
        tags.append('relation-missing')
    return tags or ['no-tag']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--set', default='artifacts/next-inputs/world-components/n4-rolepair-r1.jsonl')
    parser.add_argument('--out', default='artifacts/next-runs/dircheck-r1/report.json')
    parser.add_argument('--margin', type=float, default=1.0)
    parser.add_argument('--budget', type=float, default=20.0)
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
    rows = [r for r in rows if r['unitId'] in PAIRS]
    assert len(rows) == len(PAIRS), len(rows)

    for row in rows:
        correct, reversed_ = PAIRS[row['unitId']]
        for text in (correct, reversed_):
            for required in (row['name'], row['other'], row['relation']):
                assert required in text, (row['unitId'], required, text)

    def score(texts):
        enc = tokenizer(texts, padding=True, return_tensors='pt')
        enc = {k: v.to(device) for k, v in enc.items()}
        labels = tokenizer(text_target=texts, padding=True, return_tensors='pt')
        mask = labels.attention_mask.to(device)
        ids = labels.input_ids.to(device)
        with torch.no_grad():
            out = model(**enc, labels=ids.clone().masked_fill(mask == 0, -100))
        logp = torch.log_softmax(out.logits.float(), dim=-1)
        picked = logp.gather(2, ids.clamp(min=0).unsqueeze(2)).squeeze(2)
        picked = picked * mask
        return picked.sum(1).tolist(), (picked.sum(1) / mask.sum(1)).tolist(), mask.sum(1).tolist()

    model.eval()
    per_row = []
    for row in rows:
        correct, reversed_ = PAIRS[row['unitId']]
        with torch.inference_mode():
            enc = tokenizer([row['input']], padding=True, return_tensors='pt')
            enc = {k: v.to(device) for k, v in enc.items()}
            tokens, meta = generate_greedy(model, enc, timeout_seconds=args.budget)
        generated = tokenizer.decode(tokens[0][1:], skip_special_tokens=True).strip()
        sums, means, lengths = score([correct, reversed_, generated])
        margin_sum = sums[0] - sums[1]
        margin_mean = means[0] - means[1]
        per_row.append({
            'unitId': row['unitId'], 'pair': row['pair'], 'name': row['name'],
            'other': row['other'], 'relation': row['relation'],
            'correct': correct, 'reversed': reversed_, 'generated': generated,
            'stop': meta.get('reason'),
            'sum': {'correct': round(sums[0], 3), 'reversed': round(sums[1], 3), 'generated': round(sums[2], 3)},
            'mean': {'correct': round(means[0], 3), 'reversed': round(means[1], 3), 'generated': round(means[2], 3)},
            'tokens': lengths,
            'marginSum': round(margin_sum, 3), 'marginMean': round(margin_mean, 3),
            'lossActive': bool(margin_mean < args.margin),
            'errorTags': classify(generated, row, correct, reversed_),
            'prefersGeneratedOverCorrect': bool(means[2] > means[0]),
        })

    report = {
        'purpose': 'does the direction margin cover the errors that actually occur at C',
        'device': device, 'model': str(pathlib.Path(args.model).name),
        'group': 'the six location-reference rolepair rows, whole',
        'confirmedPreviously': CONFIRMED,
        'marginThreshold': args.margin,
        'rows': per_row,
        'optimizer': 'never constructed',
    }
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    for r in per_row:
        print('%-8s %-4s | gen=%s | tags=%s | marginMean %.2f active=%s | gen>correct=%s'
              % (r['unitId'], r['relation'], r['generated'], ','.join(r['errorTags']),
                 r['marginMean'], r['lossActive'], r['prefersGeneratedOverCorrect']))


if __name__ == '__main__':
    main()
