"""D03 full-encoder fine-tuning. Offline inputs, no truncation, scene-level metrics."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import time
import statistics

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / 'docs/research/d03-gameplay-dataset-20261110-v1/scenes.jsonl'
BASE = ROOT / '.local/d03-macbert/base'
PARENT = ROOT / '.local/d03-macbert/runs/macbert-r3'
PARENT_SHA = '86ff927eae91c783c05e11dd471ec3ac361235633336907cbefeaedd9f3ff645'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_data(path=DATA):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines()]
    owners, ids = {}, set()
    for row in rows:
        group, split = row['sourceGroup'], row['split']
        if split not in {'train', 'development', 'test'}:
            raise ValueError('Unknown split')
        if group in owners and owners[group] != split:
            raise ValueError('Scene group crosses splits')
        owners[group] = split
        if row['sceneId'] in ids:
            raise ValueError('Duplicate scene ID')
        ids.add(row['sceneId'])
        roster = [c['id'] for c in row['input']['characters']]
        if len(roster) != len(set(roster)) or not set(row['targetIds']) <= set(roster):
            raise ValueError('Invalid candidate roster or target IDs')
    return rows

def pair_text(row, candidate):
    # Include every supplied world fact, candidate and already-acted flag.
    # Labels, split and sourceGroup never enter the model input.
    value = row['input']
    roster = '；'.join(c['id'] + '=' + c['name'] for c in value['characters'])
    premise = ('人物名册：' + roster + '。行动者编号：' + value['actorId'] +
               '。已行动编号：' + ('未知' if row.get('alreadyActedStatus') == 'unknown_in_legacy_capture_not_observed_empty' else '、'.join(value['alreadyActedIds'])) +
               '。世界事实：' + value['world'] + '当前已确认行动：' + value['action'])
    query = ('候选角色：' + candidate['id'] + '=' + candidate['name'] +
             '。判断此角色是否被当前行动牵连。已行动不排除受影响，行动者自身不算其他目标。')
    return premise, query

def metrics(records, threshold):
    tp = fp = fn = tn = exact = empty_correct = empty_count = 0
    groups = {}
    for row in records:
        gold = set(row['targetIds'])
        pred = {key for key, score in row['scores'].items() if score >= threshold}
        tp += len(gold & pred)
        fp += len(pred - gold)
        fn += len(gold - pred)
        tn += len(set(row['scores']) - (gold | pred))
        correct = pred == gold
        exact += int(correct)
        groups.setdefault(row['sourceGroup'], []).append(correct)
        if not gold:
            empty_count += 1
            empty_correct += int(not pred)
    return {'scenes': len(records), 'groups': len(groups), 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': tp / (tp + fp) if tp + fp else 0.,
            'recall': tp / (tp + fn) if tp + fn else 0.,
            'exactCount': exact, 'exactMatch': exact / len(records),
            'groupExactMatch': sum(all(v) for v in groups.values()) / len(groups),
            'emptyCount': empty_count, 'emptyCorrect': empty_correct,
            'emptyAccuracy': empty_correct / empty_count if empty_count else None}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='gameplay-v1')
    parser.add_argument('--device', choices=['cpu', 'mps', 'cuda'], default='mps')
    args = parser.parse_args()
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    import torch
    import transformers
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    torch.set_num_threads(2)
    random.seed(42)
    torch.manual_seed(42)
    if args.device == 'mps' and not torch.backends.mps.is_available():
        raise RuntimeError('MPS unavailable; refusing an implicit device change')
    run = ROOT / '.local/d03-gameplay/runs' / args.run
    run.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    config = {'seed': 42, 'epochs': 8, 'batchSize': 8, 'learningRate': 2e-5,
              'weightDecay': .01, 'gradientClip': 1., 'maxTokens': 512,
              'thresholdGrid': [i / 20 for i in range(1, 20)],
              'device': args.device, 'dtype': 'float32', 'encoderFrozen': False,
              'datasetSha256': sha(DATA), 'codeSha256': sha(__file__),
              'protocolSha256': sha(ROOT / 'docs/research/d03-gameplay-dataset-20261110-v1/training-protocol.md'),
              'torch': torch.__version__, 'transformers': transformers.__version__,
              'scope': 'user-accepted captured-gameplay subset, game-separated',
              'parentCheckpointSha256': PARENT_SHA,
              'initialization': 'R3 selected epoch 4; classifier and encoder continued',
              'testUsedForSelection': False}
    (run / 'run.json').write_text(json.dumps(config, indent=2))
    events = (run / 'events.jsonl').open('a', buffering=1)
    def event(kind, **fields):
        record = {'kind': kind, 'seconds': time.perf_counter() - start, **fields}
        events.write(json.dumps(record) + '\n')
        print(json.dumps(record), flush=True)
    try:
        manifest = json.loads((BASE / 'manifest.json').read_text())
        for name, identity in manifest['files'].items():
            if sha(BASE / name) != identity['sha256']:
                raise ValueError('Base file identity mismatch: ' + name)
        (run / 'base-manifest.json').write_text(json.dumps(manifest, indent=2))
        rows = load_data()
        if any(len(r['input']['characters']) not in (2,3) for r in rows):
            raise ValueError('Gameplay subset requires 2-3 total characters')
        data_manifest = json.loads((DATA.parent / 'data-manifest.json').read_text())
        if sha(DATA) != data_manifest['datasetSha256']:
            raise ValueError('Frozen dataset hash mismatch')
        tokenizer = AutoTokenizer.from_pretrained(BASE, local_files_only=True, trust_remote_code=False)
        pairs = []
        for row in rows:
            for candidate in row['input']['characters']:
                encoding = tokenizer(*pair_text(row, candidate), truncation=False)
                if len(encoding['input_ids']) > 512:
                    raise ValueError('Input exceeds 512; no truncation: ' + row['sceneId'])
                pairs.append({'scene': row, 'candidateId': candidate['id'], 'encoding': encoding,
                              'label': int(candidate['id'] in row['targetIds'])})
        event('audit', scenes=len(rows), pairs=len(pairs),
              maxTokens=max(len(p['encoding']['input_ids']) for p in pairs),
              splitScenes={s: sum(r['split'] == s for r in rows) for s in ['train','development','test']})
        parent_summary = json.loads((PARENT / 'summary.json').read_text())
        if sha(PARENT / 'model/model.safetensors') != PARENT_SHA or parent_summary['checkpointSha256'] != PARENT_SHA:
            raise ValueError('Parent model identity mismatch')
        model = AutoModelForSequenceClassification.from_pretrained(
            PARENT / 'model', local_files_only=True, trust_remote_code=False).to(args.device)
        model.config.id2label = {0: 'not_affected', 1: 'affected'}
        model.config.label2id = {'not_affected': 0, 'affected': 1}
        event('model', parameters=sum(p.numel() for p in model.parameters()),
              trainable=sum(p.numel() for p in model.parameters() if p.requires_grad))
        def synchronize():
            if args.device == 'mps': torch.mps.synchronize()
            elif args.device == 'cuda': torch.cuda.synchronize()
        def batch(batch_pairs):
            return tokenizer.pad([p['encoding'] for p in batch_pairs], return_tensors='pt').to(args.device)
        def evaluate(split, evaluation_rows=None):
            model.eval()
            output = []
            with torch.inference_mode():
                for row in (rows if evaluation_rows is None else evaluation_rows):
                    if row['split'] != split: continue
                    synchronize()
                    before = time.perf_counter()
                    # Re-tokenize to include input preparation in whole-roster latency.
                    current = []
                    for candidate in row['input']['characters']:
                        current.append({'encoding': tokenizer(*pair_text(row, candidate), truncation=False)})
                    logits = model(**batch(current)).logits
                    scores = logits.softmax(-1)[:, 1].cpu().tolist()
                    synchronize()
                    output.append({'sceneId': row['sceneId'], 'sourceGroup': row['sourceGroup'],
                                   'targetIds': row['targetIds'], 'characterCount': len(row['input']['characters']),
                                   'category': row.get('category', 'captured_gameplay'),
                                   'scores': dict(zip([c['id'] for c in row['input']['characters']], scores)),
                                   'rosterMs': (time.perf_counter() - before) * 1000})
            return output
        train = [p for p in pairs if p['scene']['split'] == 'train']
        positives = sum(p['label'] for p in train)
        weight = torch.tensor([1., (len(train) - positives) / positives], device=args.device)
        loss_fn = torch.nn.CrossEntropyLoss(weight=weight)
        optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5, weight_decay=.01)
        steps = math.ceil(len(train) / 8) * 8
        scheduler = transformers.get_linear_schedule_with_warmup(optimizer, int(steps * .1), steps)
        best_key = None
        best_threshold = .5
        best_epoch = None
        best_dev = None
        event('training_start', steps=steps, positivePairs=positives, negativePairs=len(train)-positives)
        for epoch in range(1, 9):
            model.train()
            random.shuffle(train)
            loss_sum = 0.
            for offset in range(0, len(train), 8):
                current = train[offset:offset + 8]
                optimizer.zero_grad(set_to_none=True)
                logits = model(**batch(current)).logits
                labels = torch.tensor([p['label'] for p in current], device=args.device)
                loss = loss_fn(logits, labels)
                if not torch.isfinite(loss): raise RuntimeError('Non-finite loss')
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1., error_if_nonfinite=True)
                optimizer.step()
                scheduler.step()
                loss_sum += loss.item() * len(current)
            dev = evaluate('development')
            choices = []
            for threshold in config['thresholdGrid']:
                score = metrics(dev, threshold)
                key = (score['exactMatch'], -score['fn'], -score['fp'], -abs(threshold-.5))
                choices.append((key, threshold, score))
            key, threshold, score = max(choices, key=lambda item: item[0])
            (run / f'development-epoch-{epoch}.json').write_text(json.dumps(dev, ensure_ascii=False, indent=2))
            if best_key is None or key > best_key:
                best_key, best_threshold, best_epoch, best_dev = key, threshold, epoch, score
                torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()}, run / 'best.pt')
            event('epoch', epoch=epoch, meanLoss=loss_sum / len(train), threshold=threshold,
                  development=score, selectedEpoch=best_epoch)
        del optimizer, scheduler
        model.load_state_dict(torch.load(run / 'best.pt', map_location='cpu', weights_only=True))
        model.eval()
        # Save/reload the deployable classifier before the single final test pass.
        model.save_pretrained(run / 'model', safe_serialization=True)
        tokenizer.save_pretrained(run / 'model')
        del model
        if args.device == 'mps': torch.mps.empty_cache()
        model = AutoModelForSequenceClassification.from_pretrained(run / 'model', local_files_only=True).to(args.device)
        train_records = evaluate('train')
        test_records = evaluate('test')
        test_metrics = metrics(test_records, best_threshold)
        train_metrics = metrics(train_records, best_threshold)
        for name, records in [('train',train_records),('test',test_records)]:
            (run / f'{name}-predictions.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))
        old_data = ROOT / 'docs/research/d03-macbert/r2/scenes.jsonl'
        old_manifest = json.loads((old_data.parent/'data-manifest.json').read_text())
        if sha(old_data) != old_manifest['datasetSha256']:
            raise ValueError('R2 regression dataset changed')
        regression_records = evaluate('test', load_data(old_data))
        regression_metrics = metrics(regression_records, best_threshold)
        (run/'r2-regression-predictions.json').write_text(json.dumps(regression_records,ensure_ascii=False,indent=2))
        del model
        if args.device == 'mps': torch.mps.empty_cache()
        model = AutoModelForSequenceClassification.from_pretrained(PARENT/'model',local_files_only=True).to(args.device)
        parent_records = evaluate('test')
        parent_metrics = metrics(parent_records, parent_summary['threshold'])
        (run/'parent-on-new-test.json').write_text(json.dumps(parent_records,ensure_ascii=False,indent=2))
        all_none = [{**r, 'scores': {cid: 0. for cid in r['scores']}} for r in test_records]
        passed = test_metrics['exactMatch'] >= .9 and test_metrics['fn'] == 0 and test_metrics['emptyAccuracy'] == 1.
        latencies = sorted(r['rosterMs'] for r in test_records)
        summary = {'selectedEpoch': best_epoch, 'threshold': best_threshold,
                   'train': train_metrics, 'development': best_dev, 'test': test_metrics,
                   'parentOnNewTest': parent_metrics, 'r2Regression': regression_metrics,
                   'testByCategory': {c: metrics([r for r in test_records if r['category']==c], best_threshold) for c in sorted({r['category'] for r in test_records})},
                   'testByCharacterCount': {str(n): metrics([r for r in test_records if r['characterCount']==n], best_threshold) for n in [2,3]},
                   'testNonempty': metrics([r for r in test_records if r['targetIds']], best_threshold),
                   'allNoneBaseline': metrics(all_none, .5), 'exploratoryQualityGate': passed,
                   'productionApproved': False,
                   'curriculumGate': passed and regression_metrics['exactMatch'] == 1.,
                   'distillationDecision': 'requires_broader_reviewed_validation' if passed and regression_metrics['exactMatch'] == 1. else 'stop_quality_or_regression_gate_failed',
                   'testLatencyMs': {'median': statistics.median(latencies), 'max': max(latencies)},
                   'checkpointSha256': sha(run / 'model/model.safetensors'),
                   'seconds': time.perf_counter()-start}
        (run / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        event('complete', **summary)
    except BaseException as exc:
        event('failed', error=repr(exc))
        (run / 'failure.json').write_text(json.dumps({'error': repr(exc), 'seconds': time.perf_counter()-start}))
        raise
    finally:
        events.close()

if __name__ == '__main__':
    main()
