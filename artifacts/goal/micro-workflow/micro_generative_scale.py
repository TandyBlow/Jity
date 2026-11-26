# -*- coding: utf-8 -*-
"""Fixed BERT candidate pointer: data-scale curve, open-field diagnostics,
and weighted vs unweighted result classifiers."""
import importlib.util
import json
import random
import statistics
import time
from collections import Counter
from pathlib import Path

import torch
import torch.nn.functional as F

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v3', HERE / 'micro_generative_v3.py')
v3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v3)
v2 = v3.v2
from scale_data import finalize, make_rows  # noqa: E402

OPEN = {'info', 'env', 'promise', 'decision', 'cause', 'neg'}
ENTITY = {'loc', 'item', 'target', 'dest'}


def prepare(rows, world=None):
    for row in rows:
        continuation, gold, fields = v3.candidate_continuation(row)
        row['continuation'] = continuation
        row['sel_gold'] = gold
        row['sel_fields'] = fields
    return rows


def field_metrics(predictions, fields):
    result = {}
    for field in sorted(fields):
        tp = fp = fn = gold_pos = 0
        for row in predictions:
            want = row['want']
            got = row['got']
            gold_has = field in want
            pred_has = field in got
            gold_pos += gold_has
            if gold_has and pred_has and got.get(field) == want.get(field):
                tp += 1
            elif pred_has and (not gold_has or got.get(field) != want.get(field)):
                fp += 1
            elif gold_has:
                fn += 1
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        result[field] = {'goldPositives': gold_pos, 'precision': round(precision, 3),
                         'recall': round(recall, 3),
                         'f1': round(2 * precision * recall / (precision + recall), 3)
                         if precision + recall else 0.0}
    return result


def span_coverage(rows, fields):
    result = {}
    for field in sorted(fields):
        values = [row['gold'][field] for row in rows if row['gold'].get(field)]
        hits = sum(1 for row in rows if row['gold'].get(field) and
                   str(row['gold'][field]) in row['input'])
        result[field] = {'rows': len(values), 'substringRate': round(hits / max(1, len(values)), 3)}
    return result


def train_weighted(rows, tokenizer, device, epochs=20):
    labels = {'partial': 0, 'completed': 1, 'blocked': 2, 'failed': 3}
    counts = Counter(labels[row['gold']['result']] for row in rows)
    total = len(rows)
    weights = torch.tensor([total / (4 * max(1, counts[index])) for index in range(4)], device=device)
    model = v2.BertResultClassifier().to(device)
    opt = torch.optim.AdamW(model.linear.parameters(), lr=1e-3)
    for _ in range(epochs):
        random.shuffle(rows)
        for start in range(0, len(rows), 16):
            batch = rows[start:start + 16]
            encoded = tokenizer([row['input'] for row in batch], padding=True, truncation=True,
                                max_length=256, return_tensors='pt')
            ids, mask = encoded['input_ids'].to(device), encoded['attention_mask'].to(device)
            target = torch.tensor([labels[row['gold']['result']] for row in batch], device=device)
            opt.zero_grad()
            loss = F.cross_entropy(model(ids, mask), target, weight=weights)
            loss.backward()
            opt.step()
    return model, labels, weights.tolist()


def main():
    random.seed(20261126)
    torch.manual_seed(20261126)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    base = prepare(v2.training_rows() + [v2.row_from_hand(row) for row in v3.HAND_TRAIN])
    generated = prepare(finalize(make_rows(877, seed=20261126)))
    train_all = base + generated
    test = prepare([v2.row_from_hand(row) for row in v2.HAND_ROWS])
    v3.CAND_VOCAB = v3.CandVocab(v3.candidate_texts(train_all + test))
    test_text = [row['text'] for row in test] + [row['prefix'] for row in test]
    pointer_texts = [row['prefix'] + row['continuation'] for row in train_all] + test_text
    pointer_texts += [f'<p{i}>' for i in range(1, 17)]
    vocab = v2.OutVocab(pointer_texts, pointer=False)
    tokenizer = v3.BertTokenizer.from_pretrained(v2.SNAP.as_posix())
    model = v3.CandidateSeq2Seq(tokenizer, len(vocab.itos), v3.CAND_VOCAB).to(device)
    stages = [(250, 60), (500, 30), (1000, 30)]
    report = {'baseRows': len(base), 'generatedRows': len(generated), 'testRows': len(test),
              'testWorlds': sorted({row['world'] for row in test}),
              'openCounts': {field: sum(1 for row in train_all if field in row['gold']) for field in sorted(OPEN)},
              'testOpenCounts': {field: sum(1 for row in test if field in row['gold']) for field in sorted(OPEN)},
              'spanCoverage': span_coverage(test, OPEN), 'stages': {}}
    for size, epochs in stages:
        began = time.perf_counter()
        v3.train(model, train_all[:size], vocab, device, epochs=epochs)
        metrics = v3.evaluate(model, vocab, test, device)
        metrics.update(v3.summarize(metrics['predictions']))
        metrics['trainMs'] = round((time.perf_counter() - began) * 1000)
        metrics['trainSize'] = size
        metrics['fieldMetrics'] = field_metrics(metrics['predictions'], OPEN | ENTITY)
        report['stages'][str(size)] = metrics
        print(size, json.dumps({key: metrics[key] for key in ('fieldRecall', 'entityFieldRecall',
                                                              'openFieldRecall', 'exact', 'byWorld',
                                                              'p50Ms', 'trainMs')}, ensure_ascii=False))
    train_events = [row for row in train_all if row['kind'] == 'events']
    test_events = [row for row in test if row['kind'] == 'events']
    random.Random(20261126).shuffle(train_events)
    unweighted, labels = v2.train_result(train_events, tokenizer, device)
    weighted, _, weights = train_weighted(train_events, tokenizer, device)
    report['result'] = {
        'classes': list(labels),
        'weights': weights,
        'unweighted': v2.eval_result(unweighted, labels, tokenizer, test_events, device),
        'weighted': v2.eval_result(weighted, labels, tokenizer, test_events, device),
    }
    for stage, metrics in report['stages'].items():
        metrics.pop('predictions', None)
    (v3.v2.OUT / 'scale-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                                 encoding='utf8')
    print(json.dumps({key: report[key] for key in ('baseRows', 'generatedRows', 'openCounts',
                                                   'testOpenCounts', 'spanCoverage', 'result')},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
