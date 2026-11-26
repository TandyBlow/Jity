# -*- coding: utf-8 -*-
"""V2 pilot: pointer output, pretrained encoder, from-scratch control.

Training rows are the deduplicated rule/action-structure rows from the first
pilot (one surface form per task/event, not four prefix variants). The test set
is hand-authored (`hand_test.py`), never used for training. Pointer models emit
<pN> for entity fields and resolve them from the row candidate list; free-ID
models emit entity IDs directly. BERT MiniRBT encoders are frozen; the decoder
is trained from scratch.
"""
import importlib.util
import json
import random
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import BertModel, BertTokenizer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from hand_test import MISTPORT, ROWS as HAND_ROWS  # noqa: E402

spec = importlib.util.spec_from_file_location('pilot', HERE / 'micro_generative_pilot.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)

SNAP = Path('D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot')
OUT = HERE / 'micro-generative'
OUT.mkdir(parents=True, exist_ok=True)

DRAGON = {
    'chars': {cid: name for cid, name in pilot.CHARS.items()},
    'items': {iid: name for iid, name in pilot.ITEMS.items()},
    'locs': {lid: name for lid, name in pilot.LOCS.items()},
}
WORLDS = {'dragon': DRAGON, 'mistport': MISTPORT}
FIELD_ORDER = {
    'conditions': ['time', 'loc', 'item', 'target', 'conf', 'act', 'decision', 'promise', 'info', 'env', 'neg'],
    'events': ['result', 'target', 'item', 'dest', 'info', 'env', 'promise', 'decision', 'cause'],
}
ENTITY_FIELDS = {'conditions': {'loc', 'item', 'target'}, 'events': {'target', 'item', 'dest'}}

OUT_TOKEN = re.compile(r'<e>|<p\d+>|[A-Za-z_][A-Za-z0-9_]*|\d{1,2}:\d{2}|[\u4e00-\u9fff]|[=|/；;，。:：]')
SRC_TOKEN = re.compile(r'[A-Za-z_][A-Za-z0-9_]*|\d{1,2}:\d{2}|[\u4e00-\u9fff]|[=|/；;，。:：]')


def universe(world):
    result = {}
    for typ in ('chars', 'items', 'locs'):
        kind = {'chars': 'char', 'items': 'item', 'locs': 'loc'}[typ]
        for ident, name in world[typ].items():
            result[ident] = {'type': kind, 'name': name}
    return result


def parse_fields(text):
    return {part.split('=', 1)[0]: part.split('=', 1)[1] for part in text.split('|') if '=' in part}


def serialize(fields, order, candidates, variant):
    index = {ident: i + 1 for i, ident in enumerate(candidates)}
    parts = []
    for key in order:
        value = fields.get(key)
        if not value:
            continue
        if variant == 'pointer' and key in ENTITY_FIELDS_FOR(key):
            if key == 'dest':
                base, sep, rest = value.partition('/')
                if base in index:
                    value = f'<p{index[base]}>' + (sep + rest if sep else '')
            elif value in index:
                value = f'<p{index[value]}>'
        parts.append(f'{key}={value}')
    return '|'.join(parts) if parts else 'none'


def ENTITY_FIELDS_FOR(key):
    return {'loc', 'item', 'target', 'dest'}


def build_candidates(world, fields, text, row_id):
    uni = universe(world)
    seed = []
    for key in ('loc', 'item', 'target'):
        value = fields.get(key)
        if value in uni and value not in seed:
            seed.append(value)
    dest = fields.get('dest')
    if dest:
        base = dest.split('/', 1)[0]
        if base in uni and base not in seed:
            seed.append(base)
    mentioned = [ident for ident, row in uni.items() if len(row['name']) >= 2 and row['name'] in text]
    for ident in mentioned:
        if ident not in seed:
            seed.append(ident)
    chosen = list(seed)
    rng = random.Random(row_id)
    for kind in ('char', 'item', 'loc'):
        pool = [ident for ident, row in uni.items() if row['type'] == kind and ident not in chosen]
        rng.shuffle(pool)
        if any(uni[ident]['type'] == kind for ident in chosen):
            chosen.extend(pool[:2])
    chosen = chosen[:10]
    rng.shuffle(chosen)
    return chosen


def row_from_pilot(row):
    task = row['task']
    if task == 'conditions':
        fields = parse_fields(row['output'][len('COND|'):]) if row['output'] != 'COND|none' else {}
        actor = re.search(r'角色=([a-z_][a-z0-9_]*)', row['input'])
        actor = actor.group(1) if actor else ''
        text = re.sub(r'；实体=[^；]*', '', row['input'])
        kind = 'conditions'
    else:
        fields = parse_fields(row['output'])
        actor = fields.pop('actor', row['key'])
        text = re.sub(r'；实体=[^；]*', '', row['input'])
        kind = 'events'
    candidates = build_candidates(DRAGON, fields, text, row.get('key', '') + kind)
    base = {'id': row.get('key', ''), 'kind': kind, 'world': 'dragon', 'type': 'rule',
            'actor': actor, 'text': text, 'gold': fields, 'candidates': candidates}
    base['prefix'] = 'COND|' if kind == 'conditions' else f'EV|actor={actor}|'
    base['input'] = text + '；候选=' + '；'.join(f'{i + 1}:{universe(DRAGON)[ident]["name"]}={ident}'
                                                for i, ident in enumerate(candidates))
    return base


def row_from_hand(row):
    world = WORLDS[row['world']]
    candidates = build_candidates(world, row['gold'], row['text'], row['id'])
    text = row['text'] + f'；角色={row["actor"]}'
    base = {'id': row['id'], 'kind': row['kind'], 'world': row['world'], 'type': row['type'],
            'actor': row['actor'], 'text': text, 'gold': dict(row['gold']), 'candidates': candidates}
    base['prefix'] = 'COND|' if row['kind'] == 'conditions' else f'EV|actor={row["actor"]}|'
    base['input'] = text + '；候选=' + '；'.join(f'{i + 1}:{universe(world)[ident]["name"]}={ident}'
                                                for i, ident in enumerate(candidates))
    return base


def training_rows():
    rows = pilot.condition_rows() + pilot.event_rows()
    conditions, events = {}, {}
    for row in rows:
        if row['task'] == 'conditions':
            conditions.setdefault(row['key'], row)
        else:
            events.setdefault((row['key'], row['output']), row)
    return [row_from_pilot(row) for row in list(conditions.values()) + list(events.values())]


def gold_text(row, variant):
    return serialize(row['gold'], FIELD_ORDER[row['kind']], row['candidates'], variant)


def prepare(row, variant):
    item = dict(row)
    item['continuation'] = gold_text(row, variant)
    item['output'] = row['prefix'] + item['continuation']
    return item


class OutVocab:
    def __init__(self, texts, pointer=False):
        counts = Counter(token for text in texts for token in OUT_TOKEN.findall(text))
        special = ['<pad>', '<bos>', '<eos>', '<unk>']
        if pointer:
            special += [f'<p{i}>' for i in range(1, 17)]
        self.itos = special + [token for token, _ in counts.most_common() if token not in special]
        self.stoi = {token: index for index, token in enumerate(self.itos)}
        self.pad, self.bos, self.eos, self.unk = 0, 1, 2, 3

    def encode(self, text, max_len):
        ids = [self.stoi.get(token, self.unk) for token in OUT_TOKEN.findall(text)][:max_len - 2]
        return [self.bos] + ids + [self.eos]


class SrcVocab:
    def __init__(self, texts):
        counts = Counter(token for text in texts for token in SRC_TOKEN.findall(text))
        self.itos = ['<pad>', '<unk>'] + [token for token, _ in counts.most_common()]
        self.stoi = {token: index for index, token in enumerate(self.itos)}
        self.pad, self.unk = 0, 1

    def encode(self, text, max_len=128):
        return [self.stoi.get(token, self.unk) for token in SRC_TOKEN.findall(text)][:max_len]


class BaseSeq2Seq(nn.Module):
    def __init__(self, tgt_vocab, d_model=256, layers=4, heads=8, max_len=64):
        super().__init__()
        self.tgt_emb = nn.Embedding(tgt_vocab, d_model, padding_idx=0)
        self.pos = nn.Embedding(max_len, d_model)
        self.decoder = nn.TransformerDecoder(
            nn.TransformerDecoderLayer(d_model, heads, 4 * d_model, batch_first=True, norm_first=True), layers)
        self.out = nn.Linear(d_model, tgt_vocab)

    def decode_memory(self, memory, memory_mask, tgt):
        t = tgt.shape[1]
        tgt_pos = self.pos(torch.arange(t, device=tgt.device))[None]
        mask = nn.Transformer.generate_square_subsequent_mask(t, device=tgt.device)
        return self.out(self.decoder(self.tgt_emb(tgt) + tgt_pos, memory, tgt_mask=mask,
                                     tgt_key_padding_mask=tgt.eq(0),
                                     memory_key_padding_mask=memory_mask.eq(0)))


class ScratchSeq2Seq(BaseSeq2Seq):
    def __init__(self, src_vocab, tgt_vocab, d_model=256, layers=4, heads=8):
        super().__init__(tgt_vocab, d_model, layers, heads)
        self.src_vocab = src_vocab
        self.src_emb = nn.Embedding(len(src_vocab.itos), d_model, padding_idx=0)
        self.src_pos = nn.Embedding(128, d_model)
        self.encoder = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d_model, heads, 4 * d_model, batch_first=True, norm_first=True), layers)

    def encode_source(self, texts):
        tokens_list = [SRC_TOKEN.findall(text)[:128] for text in texts]
        width = max(1, max(len(tokens) for tokens in tokens_list))
        ids = torch.zeros(len(texts), width, dtype=torch.long)
        for index, tokens in enumerate(tokens_list):
            ids[index, :len(tokens)] = torch.tensor(
                [self.src_vocab.stoi.get(token, self.src_vocab.unk) for token in tokens])
        return ids, ids.ne(0)

    def encode_memory(self, ids, mask):
        pos = self.src_pos(torch.arange(ids.shape[1], device=ids.device))[None]
        return self.encoder(self.src_emb(ids) + pos, src_key_padding_mask=mask.eq(0))


class BertSeq2Seq(BaseSeq2Seq):
    def __init__(self, tokenizer, tgt_vocab, d_model=256, layers=4, heads=8):
        super().__init__(tgt_vocab, d_model, layers, heads)
        self.tokenizer = tokenizer
        self.bert = BertModel.from_pretrained(SNAP.as_posix())
        for parameter in self.bert.parameters():
            parameter.requires_grad = False

    def encode_source(self, texts):
        encoded = self.tokenizer(texts, padding=True, truncation=True, max_length=256, return_tensors='pt')
        return encoded['input_ids'], encoded['attention_mask']

    def encode_memory(self, ids, mask):
        with torch.no_grad():
            return self.bert(input_ids=ids, attention_mask=mask).last_hidden_state


def pad_target(vocab, rows, max_len=64):
    encoded = [vocab.encode(row['prefix'] + row['continuation'], max_len) for row in rows]
    width = max(len(row) for row in encoded)
    ids = torch.full((len(rows), width), vocab.pad, dtype=torch.long)
    for index, row in enumerate(encoded):
        ids[index, :len(row)] = torch.tensor(row)
    return ids


def train_seq2seq(model, rows, vocab, device, epochs=60):
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=3e-4)
    random.shuffle(rows)
    model.train()
    for _ in range(epochs):
        for start in range(0, len(rows), 12):
            batch = rows[start:start + 12]
            src, mask = model.encode_source([row['input'] for row in batch])
            src, mask = src.to(device), mask.to(device)
            tgt = pad_target(vocab, batch).to(device)
            opt.zero_grad()
            logits = model.decode_memory(model.encode_memory(src, mask), mask, tgt[:, :-1])
            labels = tgt[:, 1:]
            token_loss = F.cross_entropy(logits.reshape(-1, len(vocab.itos)), labels.reshape(-1),
                                         ignore_index=vocab.pad, reduction='none').reshape(labels.shape)
            loss_mask = torch.ones_like(labels, dtype=torch.float)
            for index, row in enumerate(batch):
                loss_mask[index, :max(0, len(vocab.encode(row['prefix'], 64)) - 2)] = 0
            loss = (token_loss * loss_mask).sum() / loss_mask.sum().clamp(min=1)
            loss.backward()
            opt.step()
    return model


@torch.no_grad()
def generate(model, vocab, text, prefix, device, max_len=32):
    model.eval()
    src, mask = model.encode_source([text])
    src, mask = src.to(device), mask.to(device)
    memory = model.encode_memory(src, mask)
    seed = vocab.encode(prefix, 64)[1:-1]
    out = [vocab.bos] + seed
    start = 1 + len(seed)
    for _ in range(max_len):
        tgt = torch.tensor([out], device=device)
        logits = model.decode_memory(memory, mask, tgt)
        best = int(logits[0, -1].argmax())
        out.append(best)
        if best == vocab.eos:
            break
    return ''.join(vocab.itos[index] for index in out[start:]
                   if index not in (vocab.pad, vocab.bos, vocab.eos))


def resolve(value, candidates):
    match = re.fullmatch(r'<p(\d+)>(.*)', value)
    if not match:
        return value
    index = int(match.group(1)) - 1
    base = candidates[index] if 0 <= index < len(candidates) else '<bad>'
    return base + match.group(2)


def evaluate(model, vocab, rows, device, world=None):
    rows = [row for row in rows if world is None or row['world'] == world]
    exact = 0
    hits = total = 0
    per_field = Counter()
    per_field_total = Counter()
    times = []
    predictions = []
    for row in rows:
        began = time.perf_counter()
        got = generate(model, vocab, row['input'], row['prefix'], device)
        times.append((time.perf_counter() - began) * 1000)
        got_fields = parse_fields(got)
        got_fields = {key: resolve(value, row['candidates']) for key, value in got_fields.items()}
        want = row['gold']
        exact += all(got_fields.get(key) == value for key, value in want.items()) and set(got_fields) <= set(want)
        hits += sum(1 for key, value in want.items() if got_fields.get(key) == value)
        total += len(want)
        for key in set(got_fields) | set(want):
            per_field_total[key] += 1
            if got_fields.get(key) == want.get(key):
                per_field[key] += 1
        predictions.append({'id': row['id'], 'world': row['world'], 'type': row['type'],
                            'got': got_fields, 'want': want})
    times.sort()
    return {
        'rows': len(rows), 'exact': round(exact / max(1, len(rows)), 3),
        'fieldRecall': round(hits / max(1, total), 3),
        'perField': {key: round(per_field[key] / per_field_total[key], 3) for key in sorted(per_field_total)},
        'p50Ms': round(statistics.median(times), 1) if times else None,
        'p95Ms': round(times[min(len(times) - 1, int(len(times) * 0.95))], 1) if times else None,
        'predictions': predictions,
    }


class BertResultClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP.as_posix())
        for parameter in self.bert.parameters():
            parameter.requires_grad = False
        self.linear = nn.Linear(256, 4)

    def forward(self, ids, mask):
        with torch.no_grad():
            hidden = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state
        pooled = (hidden * mask[..., None]).sum(1) / mask.sum(1, keepdim=True).clamp(min=1)
        return self.linear(pooled)


def train_result(rows, tokenizer, device, epochs=20):
    labels = {'partial': 0, 'completed': 1, 'blocked': 2, 'failed': 3}
    model = BertResultClassifier().to(device)
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
            loss = F.cross_entropy(model(ids, mask), target)
            loss.backward()
            opt.step()
    return model, labels


@torch.no_grad()
def eval_result(model, labels, tokenizer, rows, device):
    model.eval()
    correct = 0
    confusion = Counter()
    for row in rows:
        encoded = tokenizer([row['input']], padding=True, truncation=True, max_length=256, return_tensors='pt')
        ids, mask = encoded['input_ids'].to(device), encoded['attention_mask'].to(device)
        pred = int(model(ids, mask).argmax(1))
        want = labels[row['gold']['result']]
        correct += pred == want
        confusion[f'{row["gold"]["result"]}->{list(labels)[pred]}'] += 1
    return {'accuracy': round(correct / max(1, len(rows)), 3), 'rows': len(rows),
            'confusion': dict(confusion)}


def main():
    random.seed(20261126)
    torch.manual_seed(20261126)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    train = training_rows()
    test = [row_from_hand(row) for row in HAND_ROWS]
    train_events = [row for row in train if row['kind'] == 'events']
    test_events = [row for row in test if row['kind'] == 'events']
    tokenizer = BertTokenizer.from_pretrained(SNAP.as_posix())
    src_texts = [row['input'] for row in train + test]
    src_vocab = SrcVocab(src_texts)
    test_text = [row['text'] for row in test] + [row['prefix'] for row in test]
    pointer_texts = [row['prefix'] + gold_text(row, 'pointer') for row in train] + test_text
    pointer_texts += [f'<p{i}>' for i in range(1, 17)]
    dragon_ids = list(DRAGON['chars']) + list(DRAGON['items']) + list(DRAGON['locs'])
    free_texts = [row['prefix'] + gold_text(row, 'free') for row in train] + test_text + dragon_ids
    vocab_pointer = OutVocab(pointer_texts, pointer=True)
    vocab_free = OutVocab(free_texts, pointer=False)
    report = {'trainRows': len(train), 'testRows': len(test),
              'trainConditions': sum(1 for row in train if row['kind'] == 'conditions'),
              'trainEvents': len(train_events), 'testConditions': len(test) - len(test_events),
              'testEvents': len(test_events), 'worlds': sorted({row['world'] for row in test}),
              'srcVocab': len(src_vocab.itos), 'outPointerVocab': len(vocab_pointer.itos),
              'outFreeVocab': len(vocab_free.itos), 'arms': {}}
    for variant, vocab in (('pointer', vocab_pointer), ('free', vocab_free)):
        train_variant = [prepare(row, variant) for row in train]
        test_variant = [prepare(row, variant) for row in test]
        scratch = ScratchSeq2Seq(src_vocab, len(vocab.itos)).to(device)
        scratch = train_seq2seq(scratch, train_variant, vocab, device)
        scratch_metrics = evaluate(scratch, vocab, test_variant, device)
        scratch_metrics['params'] = sum(p.numel() for p in scratch.parameters())
        report['arms'][f'scratch_{variant}'] = scratch_metrics
        print('scratch', variant, {k: v for k, v in scratch_metrics.items() if k != 'predictions'})
        bert = BertSeq2Seq(tokenizer, len(vocab.itos)).to(device)
        bert = train_seq2seq(bert, train_variant, vocab, device)
        bert_metrics = evaluate(bert, vocab, test_variant, device)
        bert_metrics['params'] = sum(p.numel() for p in bert.parameters())
        report['arms'][f'bert_{variant}'] = bert_metrics
        print('bert', variant, {k: v for k, v in bert_metrics.items() if k != 'predictions'})
    # Result classifier and generative result comparison.
    rng = random.Random(20261126)
    rng.shuffle(train_events)
    classifier, labels = train_result(train_events, tokenizer, device)
    report['resultClassifier'] = eval_result(classifier, labels, tokenizer, test_events, device)
    for arm, metrics in report['arms'].items():
        rows = [row for row in test_events]
        correct = 0
        for row in rows:
            pred = next(item for item in metrics['predictions'] if item['id'] == row['id'])
            correct += pred['got'].get('result') == row['gold'].get('result')
        report['resultClassifier'][arm] = round(correct / max(1, len(rows)), 3)
    (OUT / 'v2-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'arms'}, ensure_ascii=False, indent=1))
    for arm, metrics in report['arms'].items():
        print(arm, json.dumps({k: v for k, v in metrics.items() if k != 'predictions'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
