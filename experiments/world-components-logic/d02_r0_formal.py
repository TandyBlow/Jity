"""Formal R0 heads on frozen MiniRBT layers 0/1 + development evaluation.

Engineering/experimental only: train split for fitting, development for the
first evaluation, sealed untouched.  No provider, production integration, or
quality approval is produced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

import torch
import torch.nn.functional as F

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from d02_r0_smoke import BASE, DATA, EXPR, ROLES, FrozenMiniRBT, load_tokenizer

OUT = HERE.parents[1] / 'artifacts' / 'world-components-logic' / 'd02-checkers' / 'r0-formal'
SCOPES = ('main', 'condition', 'negation', 'quote', 'hypothesis', 'background')


def encoder_hash(encoder):
    h = hashlib.sha256()
    for key in sorted(encoder.s):
        h.update(key.encode())
        h.update(encoder.s[key].detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def token_span(offsets, start, end):
    return [i for i, (a, b) in enumerate(offsets) if b > a and a < end and start < b]


def build_examples(rows, worlds, tokenizer, entity_index, entity_embeddings):
    examples = []
    for row in rows:
        encoding = tokenizer.encode(row['text'], add_special_tokens=True)
        ids, offsets = encoding.ids, encoding.offsets
        n = len(ids)
        mention = [0] * n
        role = [[0.0] * len(ROLES) for _ in range(n)]
        issue = [0] * n
        scope = [-100] * n
        gold_mentions = []
        for step in row['roleAudit']['steps']:
            for item in step['mentions']:
                indices = token_span(offsets, item['start'], item['end'])
                if not indices:
                    continue
                first, last = indices[0], indices[-1]
                if mention[first] == 0:
                    mention[first] = 1
                for index in indices[1:]:
                    if mention[index] == 0:
                        mention[index] = 2
                vector = [1.0 if role_name in item['roles'] else 0.0 for role_name in ROLES]
                role[first] = vector
                entity_index_in_candidates = -1
                if item.get('entityId'):
                    key = row['worldId'] + ':' + item['entityId']
                    entity_index_in_candidates = entity_index[row['worldId']].get(key, -1)
                gold_mentions.append({'start': item['start'], 'end': item['end'],
                                      'roles': list(item['roles']),
                                      'entity': item.get('entityId'),
                                      'candidate': entity_index_in_candidates,
                                      'token': first})
        gold_issues = []
        for item in row['expressionAudit']['issues']:
            if 'start' not in item or 'end' not in item:
                continue
            indices = token_span(offsets, item['start'], item['end'])
            if not indices:
                continue
            first, last = indices[0], indices[-1]
            if issue[first] == 0:
                issue[first] = 1
            for index in indices[1:]:
                if issue[index] == 0:
                    issue[index] = 2
            scope[first] = SCOPES.index(item['scope']) if item['scope'] in SCOPES else -100
            gold_issues.append({'start': item['start'], 'end': item['end'],
                                'scope': item['scope'], 'token': first})
        examples.append({
            'sampleId': row['sampleId'], 'worldId': row['worldId'],
            'actorId': row['actorId'], 'ids': ids, 'offsets': offsets,
            'mention': mention, 'role': role, 'issue': issue, 'scope': scope,
            'expression': EXPR.index(row['expressionAudit']['label']),
            'goldMentions': gold_mentions, 'goldIssues': gold_issues,
            'text': row['text'],
        })
    return examples


def load_entity_embeddings(encoder, tokenizer, worlds):
    entity_embeddings, entity_index, entity_names = {}, {}, {}
    for world_id, world in worlds.items():
        names = sorted(world['entities'])
        entity_index[world_id] = {world_id + ':' + name: index for index, name in enumerate(names)}
        entity_names[world_id] = names
        sequences = []
        for name in names:
            entity = world['entities'][name]
            surface = entity['name'] + ('/' + '/'.join(entity.get('aliases', [])) if entity.get('aliases') else '')
            sequences.append(tokenizer.encode(surface, add_special_tokens=True).ids)
        length = max(len(seq) for seq in sequences)
        ids = torch.zeros((len(sequences), length), dtype=torch.long)
        mask = torch.zeros((len(sequences), length), dtype=torch.float32)
        for row, seq in enumerate(sequences):
            ids[row, :len(seq)] = torch.tensor(seq)
            mask[row, :len(seq)] = 1
        with torch.no_grad():
            hidden = encoder(ids, torch.zeros_like(ids), mask)
        entity_embeddings[world_id] = hidden[:, 0]
    return entity_embeddings, entity_index, entity_names


class Heads(torch.nn.Module):
    def __init__(self, width, entities=1):
        super().__init__()
        self.mention = torch.nn.Linear(width, 3)
        self.role = torch.nn.Linear(width, len(ROLES))
        self.entity = torch.nn.Bilinear(width, width, 1)
        self.expression = torch.nn.Linear(width, len(EXPR))
        self.issue = torch.nn.Linear(width, 3)
        self.scope = torch.nn.Linear(width, len(SCOPES))

    def forward(self, hidden):
        return {'mention': self.mention(hidden), 'role': self.role(hidden),
                'expression': self.expression(hidden[:, 0]),
                'issue': self.issue(hidden), 'scope': self.scope(hidden)}


def collate(examples, indices):
    selected = [examples[i] for i in indices]
    length = max(len(row['ids']) for row in selected)
    b = len(selected)
    ids = torch.zeros((b, length), dtype=torch.long)
    types = torch.zeros_like(ids)
    mention = torch.full_like(ids, -100)
    issue = torch.full_like(ids, -100)
    role = torch.zeros((b, length, len(ROLES)))
    scope = torch.full_like(ids, -100)
    expression = torch.tensor([row['expression'] for row in selected], dtype=torch.long)
    mask = torch.zeros((b, length), dtype=torch.float32)
    for row_index, row in enumerate(selected):
        n = len(row['ids'])
        ids[row_index, :n] = torch.tensor(row['ids'])
        mask[row_index, :n] = 1
        mention[row_index, :n] = torch.tensor(row['mention'])
        issue[row_index, :n] = torch.tensor(row['issue'])
        role[row_index, :n] = torch.tensor(row['role'], dtype=torch.float32)
        scope[row_index, :n] = torch.tensor(row['scope'])
    return {'ids': ids, 'types': types, 'mask': mask, 'mention': mention,
            'issue': issue, 'role': role, 'scope': scope,
            'expression': expression, 'selected': selected}


def head_loss(heads, hidden, data, entity_embeddings, entity_index):
    out = heads(hidden)
    mention_loss = F.cross_entropy(out['mention'].view(-1, 3), data['mention'].view(-1),
                                   ignore_index=-100)
    issue_loss = F.cross_entropy(out['issue'].view(-1, 3), data['issue'].view(-1),
                                 ignore_index=-100)
    expression_loss = F.cross_entropy(out['expression'], data['expression'])
    role_rows, role_targets = [], []
    scope_rows, scope_targets = [], []
    entity_losses = []
    for row_index, row in enumerate(data['selected']):
        for item in row['goldMentions']:
            role_rows.append(out['role'][row_index, item['token']])
            role_targets.append(torch.tensor(item['roles'] and
                [1.0 if role in item['roles'] else 0.0 for role in ROLES] or [0.0] * len(ROLES)))
            if item['candidate'] >= 0:
                candidates = entity_embeddings[row['worldId']]
                mention = hidden[row_index, item['token']].unsqueeze(0).expand(candidates.shape[0], -1)
                score = heads.entity(mention, candidates).squeeze(-1)
                entity_losses.append(F.cross_entropy(score.unsqueeze(0), torch.tensor([item['candidate']])))
        for item in row['goldIssues']:
            if item['scope'] in SCOPES:
                scope_rows.append(out['scope'][row_index, item['token']])
                scope_targets.append(torch.tensor(SCOPES.index(item['scope'])))
    role_loss = F.binary_cross_entropy_with_logits(torch.stack(role_rows), torch.stack(role_targets)) if role_rows else torch.tensor(0.0)
    scope_loss = F.cross_entropy(torch.stack(scope_rows), torch.stack(scope_targets)) if scope_rows else torch.tensor(0.0)
    entity_loss = torch.stack(entity_losses).mean() if entity_losses else torch.tensor(0.0)
    total = mention_loss + issue_loss + expression_loss + role_loss + scope_loss + entity_loss
    return total, {'mention': float(mention_loss.detach()), 'issue': float(issue_loss.detach()),
                   'expression': float(expression_loss.detach()), 'role': float(role_loss.detach()),
                   'scope': float(scope_loss.detach()), 'entity': float(entity_loss.detach()),
                   'total': float(total.detach())}


def decode_spans(labels, offsets):
    spans, index = [], 1
    while index < len(labels) - 1:
        if labels[index] == 1:
            end = index
            while end + 1 < len(labels) - 1 and labels[end + 1] == 2:
                end += 1
            start_char, end_char = offsets[index][0], offsets[end][1]
            if end_char > start_char:
                spans.append((start_char, end_char, index, end))
            index = end + 1
        else:
            index += 1
    return spans


def predict(heads, encoder, examples, entity_embeddings, entity_names):
    predictions = []
    for row in examples:
        data = collate([row], [0])
        with torch.no_grad():
            hidden = encoder(data['ids'], data['types'], data['mask'])
            out = heads(hidden)
        labels = out['mention'][0].argmax(-1).tolist()
        issue_labels = out['issue'][0].argmax(-1).tolist()
        mentions = []
        for start, end, token, last in decode_spans(labels, row['offsets']):
            roles = [role for role, value in zip(ROLES, torch.sigmoid(out['role'][0, token]).tolist()) if value >= 0.5]
            candidates = entity_embeddings[row['worldId']]
            mention = hidden[0, token].unsqueeze(0).expand(candidates.shape[0], -1)
            score = heads.entity(mention, candidates).squeeze(-1)
            entity = entity_names[row['worldId']][int(score.argmax())]
            mentions.append({'start': start, 'end': end, 'roles': roles, 'entity': entity})
        issues = []
        for start, end, token, last in decode_spans(issue_labels, row['offsets']):
            issues.append({'start': start, 'end': end,
                           'scope': SCOPES[int(out['scope'][0, token].argmax())]})
        predictions.append({'sampleId': row['sampleId'], 'label': EXPR[int(out['expression'][0].argmax())],
                            'mentions': mentions, 'issues': issues})
    return predictions


def metrics(examples, predictions):
    span_tp = span_fp = span_fn = role_exact = entity_exact = full_exact = 0
    gold_span_total = pred_span_total = matched_span_total = 0
    role_hits = {role: 0 for role in ROLES}
    role_gold = {role: 0 for role in ROLES}
    entity_gold_total = 0
    actor_gold = actor_pred = 0
    label_gold = label_pred = label_correct = safe_false = 0
    non_attempt_gold = 0
    actor_false_subject = 0
    confusion = {}
    issue_tp = issue_fp = issue_fn = scope_correct = 0
    for row, pred in zip(examples, predictions):
        gold_spans = {(item['start'], item['end']): item for item in row['goldMentions']}
        pred_spans = {(item['start'], item['end']): item for item in pred['mentions']}
        matched = set(gold_spans) & set(pred_spans)
        gold_span_total += len(gold_spans); pred_span_total += len(pred_spans); matched_span_total += len(matched)
        span_tp += len(matched); span_fp += len(set(pred_spans) - set(gold_spans)); span_fn += len(set(gold_spans) - set(pred_spans))
        for span in matched:
            gold, guess = gold_spans[span], pred_spans[span]
            roles_ok = set(gold['roles']) == set(guess['roles'])
            role_exact += roles_ok
            full = roles_ok
            if gold['entity'] is not None:
                entity_gold_total += 1
                entity_ok = gold['entity'] == guess['entity']
                entity_exact += entity_ok
                full = full and entity_ok
            full_exact += full
        for role in ROLES:
            for span, item in gold_spans.items():
                if role in item['roles']:
                    role_gold[role] += 1
                    if span in pred_spans and role in pred_spans[span]['roles']:
                        role_hits[role] += 1
        gold_subject = {item['entity'] for item in row['goldMentions'] if 'subject' in item['roles'] and item['entity']}
        pred_subject = {item['entity'] for item in pred['mentions'] if 'subject' in item['roles'] and item['entity']}
        actor_gold += row['actorId'] in gold_subject
        actor_pred += row['actorId'] in pred_subject
        actor_false_subject += (row['actorId'] in pred_subject and row['actorId'] not in gold_subject)
        label_gold += 1
        label_correct += EXPR[row['expression']] == pred['label']
        confusion[(EXPR[row['expression']], pred['label'])] = confusion.get((EXPR[row['expression']], pred['label']), 0) + 1
        if EXPR[row['expression']] != 'attempt':
            non_attempt_gold += 1
        if pred['label'] == 'attempt' and EXPR[row['expression']] != 'attempt':
            safe_false += 1
        gold_issues = {(item['start'], item['end']): item for item in row['goldIssues']}
        pred_issues = {(item['start'], item['end']): item for item in pred['issues']}
        matched_issues = set(gold_issues) & set(pred_issues)
        issue_tp += len(matched_issues); issue_fp += len(set(pred_issues) - set(gold_issues)); issue_fn += len(set(gold_issues) - set(pred_issues))
        for span in matched_issues:
            scope_correct += gold_issues[span]['scope'] == pred_issues[span]['scope']
    precision = span_tp / (span_tp + span_fp) if span_tp + span_fp else 0
    recall = span_tp / (span_tp + span_fn) if span_tp + span_fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    issue_precision = issue_tp / (issue_tp + issue_fp) if issue_tp + issue_fp else 0
    issue_recall = issue_tp / (issue_tp + issue_fn) if issue_tp + issue_fn else 0
    issue_f1 = 2 * issue_precision * issue_recall / (issue_precision + issue_recall) if issue_precision + issue_recall else 0
    labels = sorted({EXPR[row['expression']] for row in examples})
    f1s = []
    for label in labels:
        tp = sum(1 for row, pred in zip(examples, predictions) if EXPR[row['expression']] == label and pred['label'] == label)
        fp = sum(1 for row, pred in zip(examples, predictions) if EXPR[row['expression']] != label and pred['label'] == label)
        fn = sum(1 for row, pred in zip(examples, predictions) if EXPR[row['expression']] == label and pred['label'] != label)
        f1s.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0)
    return {
        'samples': len(examples),
        'm1': {'spanPrecision': precision, 'spanRecall': recall, 'spanF1': f1,
               'matchedSpans': span_tp, 'goldSpans': gold_span_total,
               'predictedSpans': pred_span_total, 'roleExact': role_exact,
               'roleDenominator': matched_span_total,
               'entityExact': entity_exact, 'entityGoldTotal': entity_gold_total,
               'fullBindingExact': full_exact,
               'fullBindingDenominator': matched_span_total,
               'roleRecall': {role: role_hits[role] / role_gold[role] if role_gold[role] else None for role in ROLES},
               'actorGoldSubject': actor_gold, 'actorPredSubject': actor_pred,
               'actorFalseSubject': actor_false_subject},
        'm2': {'labelAccuracy': label_correct / label_gold if label_gold else 0,
               'macroF1': sum(f1s) / len(f1s) if f1s else 0,
               'labels': labels,
               'labelSupport': {label: sum(1 for row in examples if EXPR[row['expression']] == label) for label in labels},
               'safeAttemptFalse': safe_false, 'nonAttemptGold': non_attempt_gold,
               'issuePrecision': issue_precision, 'issueRecall': issue_recall,
               'issueF1': issue_f1, 'issueTp': issue_tp,
               'issueFp': issue_fp, 'issueFn': issue_fn,
               'scopeAccuracy': scope_correct / issue_tp if issue_tp else None,
               'confusion': [{'gold': gold, 'predicted': predicted, 'count': count}
                             for (gold, predicted), count in sorted(confusion.items())]},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--seed', type=int, default=20261110)
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    random.seed(args.seed); torch.manual_seed(args.seed); torch.set_num_threads(2)
    start = time.time()
    config = json.loads((BASE / 'config.json').read_text())
    state = torch.load(BASE / 'pytorch_model.bin', map_location='cpu', weights_only=True)
    encoder = FrozenMiniRBT(state, config)
    tokenizer, _ = load_tokenizer()
    worlds = json.loads((DATA / 'worlds.json').read_text())
    entity_embeddings, entity_index, entity_names = load_entity_embeddings(encoder, tokenizer, worlds)
    all_rows = [json.loads(line) for line in (DATA / 'samples.jsonl').read_text().splitlines()]
    train_rows = [row for row in all_rows if row['split'] == 'train']
    dev_rows = [row for row in all_rows if row['split'] == 'development']
    train_groups = {row['scenarioGroup'] for row in train_rows}
    dev_groups = {row['scenarioGroup'] for row in dev_rows}
    if train_groups & dev_groups:
        raise SystemExit('train/dev scenario groups overlap')
    train = build_examples(train_rows, worlds, tokenizer, entity_index, entity_embeddings)
    dev = build_examples(dev_rows, worlds, tokenizer, entity_index, entity_embeddings)
    heads = Heads(config['hidden_size'])
    before_encoder = encoder_hash(encoder)
    before_heads = {key: value.detach().clone() for key, value in heads.state_dict().items()}
    optimizer = torch.optim.AdamW(heads.parameters(), lr=2e-3)
    history = []
    for epoch in range(args.epochs):
        order = list(range(len(train))); random.shuffle(order)
        total = 0.0; count = 0
        for begin in range(0, len(order), args.batch_size):
            indices = order[begin:begin + args.batch_size]
            data = collate(train, indices)
            with torch.no_grad():
                hidden = encoder(data['ids'], data['types'], data['mask'])
            loss, parts = head_loss(heads, hidden, data, entity_embeddings, entity_index)
            optimizer.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(heads.parameters(), 1.0); optimizer.step()
            total += float(loss); count += 1
        history.append({'epoch': epoch + 1, 'trainLoss': total / count})
        if (epoch + 1) % 5 == 0 or epoch == args.epochs - 1:
            predictions = predict(heads, encoder, dev, entity_embeddings, entity_names)
            metrics_result = metrics(dev, predictions)
            history[-1]['dev'] = metrics_result
            print('epoch', epoch + 1, json.dumps(metrics_result['m2'], ensure_ascii=False), flush=True)
    after_encoder = encoder_hash(encoder)
    changed = {key: float((heads.state_dict()[key] - before_heads[key]).abs().sum()) for key in before_heads}
    predictions = predict(heads, encoder, dev, entity_embeddings, entity_names)
    result = metrics(dev, predictions)
    args.out.mkdir(parents=True, exist_ok=True)
    torch.save({'heads': heads.state_dict(), 'roles': ROLES, 'expressions': EXPR,
                'scopes': SCOPES, 'base': str(BASE)}, args.out / 'heads.pt')
    record = {
        'schema': 'jity-d02-r0-formal-dev-v1',
        'status': 'engineering_experimental',
        'qualityClaim': False,
        'humanReviewUsed': False,
        'sealedUsed': False,
        'baseModel': str(BASE), 'encoderLayers': [0, 1],
        'encoderHashBefore': before_encoder, 'encoderHashAfter': after_encoder,
        'encoderUnchanged': before_encoder == after_encoder,
        'headsChanged': all(value > 0 for value in changed.values()),
        'headDelta': changed,
        'trainSamples': len(train), 'devSamples': len(dev),
        'trainGroups': sorted(train_groups), 'devGroups': sorted(dev_groups),
        'epochs': args.epochs, 'batchSize': args.batch_size,
        'history': history, 'devMetrics': result,
        'elapsedSeconds': round(time.time() - start, 3),
        'headsSha256': hashlib.sha256((args.out / 'heads.pt').read_bytes()).hexdigest(),
        'entityNames': {world: names for world, names in entity_names.items()},
        'predictions': predictions,
        'notes': ['Only train/development scale-v2 samples; sealed untouched.',
                  'M2 issue span/scope is token BIO + scope at start; labels and scopes are evaluated on development.',
                  'No provider, production integration, or quality approval.'],
    }
    (args.out / 'record.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': record['status'], 'encoderUnchanged': record['encoderUnchanged'],
                      'dev': result['m2']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
