# -*- coding: utf-8 -*-
"""V3: candidate-scoring pointer head over a frozen BERT encoder.

Instead of emitting an entity ID or a <pN> index token, the decoder emits <e>
at an entity field and a dot-product head selects among the row's candidate
entities from the decoder state. The test set is the hand-authored v2 set.
"""
import importlib.util
import json
import math
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
spec = importlib.util.spec_from_file_location('v2', HERE / 'micro_generative_v2.py')
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)

ENTITY = {'loc', 'item', 'target', 'dest'}
CAND_TOKEN = re.compile(r'[A-Za-z_][A-Za-z0-9_]*|[一-鿿]')
TYPE_ID = {'char': 0, 'item': 1, 'loc': 2}


class CandVocab:
    def __init__(self, texts):
        counts = Counter(token for text in texts for token in CAND_TOKEN.findall(text))
        self.itos = ['<pad>', '<unk>'] + [token for token, _ in counts.most_common()]
        self.stoi = {token: index for index, token in enumerate(self.itos)}
        self.pad, self.unk = 0, 1


def candidate_texts(rows):
    texts = []
    for row in rows:
        uni = v2.universe(v2.WORLDS[row['world']])
        for ident in row['candidates']:
            texts.append(uni[ident]['name'] + '=' + ident)
    return texts


def candidate_tensors(rows, vocab, world):
    max_candidates = max([len(row['candidates']) for row in rows] + [1])
    char_texts = [v2.universe(v2.WORLDS[world])[ident]['name'] + '=' + ident
                  for row in rows for ident in row['candidates']]
    max_chars = max([len(CAND_TOKEN.findall(text)) for text in char_texts] + [1])
    ids = torch.zeros(len(rows), max_candidates, max_chars, dtype=torch.long)
    mask = torch.zeros(len(rows), max_candidates, max_chars, dtype=torch.long)
    types = torch.zeros(len(rows), max_candidates, dtype=torch.long)
    uni = v2.universe(v2.WORLDS[world])
    for row_index, row in enumerate(rows):
        for cand_index, ident in enumerate(row['candidates']):
            tokens = CAND_TOKEN.findall(uni[ident]['name'] + '=' + ident)[:max_chars]
            ids[row_index, cand_index, :len(tokens)] = torch.tensor(
                [vocab.stoi.get(token, vocab.unk) for token in tokens])
            mask[row_index, cand_index, :len(tokens)] = 1
            types[row_index, cand_index] = TYPE_ID[uni[ident]['type']]
    return ids, mask, types


def per_world_candidates(rows_by_world, vocab):
    result = {}
    for world, rows in rows_by_world.items():
        if rows:
            result[world] = candidate_tensors(rows, vocab, world)
    return result


def candidate_continuation(row):
    uni = v2.universe(v2.WORLDS[row['world']])
    index = {ident: i for i, ident in enumerate(row['candidates'])}
    parts, gold, fields = [], [], []
    for field in v2.FIELD_ORDER[row['kind']]:
        value = row['gold'].get(field)
        if not value:
            continue
        if field in ENTITY:
            base, sep, rest = value.partition('/')
            if base in index:
                parts.append(f'{field}=<e>{sep}{rest}')
                gold.append(index[base])
                fields.append(field)
                continue
        parts.append(f'{field}={value}')
    return '|'.join(parts) if parts else 'none', gold, fields


class CandidateEncoder(nn.Module):
    def __init__(self, vocab_size, d_model=256):
        super().__init__()
        self.emb = nn.Embedding(vocab_size, 64, padding_idx=0)
        self.type_emb = nn.Embedding(3, 32)
        self.proj = nn.Linear(96, d_model)

    def forward(self, ids, mask, types):
        embedded = self.emb(ids)
        pooled = (embedded * mask[..., None]).sum(2) / mask.sum(2, keepdim=True).clamp(min=1)
        return self.proj(torch.cat([pooled, self.type_emb(types)], -1))


class CandidateSeq2Seq(nn.Module):
    def __init__(self, tokenizer, tgt_vocab, cand_vocab, d_model=256, layers=4, heads=8):
        super().__init__()
        self.d_model = d_model
        self.tokenizer = tokenizer
        self.bert = BertModel.from_pretrained(v2.SNAP.as_posix())
        for parameter in self.bert.parameters():
            parameter.requires_grad = False
        self.tgt_emb = nn.Embedding(tgt_vocab, d_model, padding_idx=0)
        self.pos = nn.Embedding(64, d_model)
        self.decoder = nn.TransformerDecoder(
            nn.TransformerDecoderLayer(d_model, heads, 4 * d_model, batch_first=True, norm_first=True), layers)
        self.out = nn.Linear(d_model, tgt_vocab)
        self.cand = CandidateEncoder(len(cand_vocab.itos), d_model)

    def encode_source(self, texts):
        encoded = self.tokenizer(texts, padding=True, truncation=True, max_length=256, return_tensors='pt')
        return encoded['input_ids'], encoded['attention_mask']

    def encode_memory(self, ids, mask):
        with torch.no_grad():
            return self.bert(input_ids=ids, attention_mask=mask).last_hidden_state

    def decode_hidden(self, memory, mask, tgt):
        t = tgt.shape[1]
        pos = self.pos(torch.arange(t, device=tgt.device))[None]
        causal = nn.Transformer.generate_square_subsequent_mask(t, device=tgt.device)
        return self.decoder(self.tgt_emb(tgt) + pos, memory, tgt_mask=causal,
                            tgt_key_padding_mask=tgt.eq(0), memory_key_padding_mask=mask.eq(0))

    def forward(self, src_ids, src_mask, tgt, cand_ids, cand_mask, cand_types):
        memory = self.encode_memory(src_ids, src_mask)
        hidden = self.decode_hidden(memory, src_mask, tgt)
        return self.out(hidden), hidden, self.cand(cand_ids, cand_mask, cand_types)


class ScratchCandidateSeq2Seq(nn.Module):
    def __init__(self, src_vocab, tgt_vocab, cand_vocab, d_model=256, layers=4, heads=8):
        super().__init__()
        self.src_vocab = src_vocab
        self.src_emb = nn.Embedding(len(src_vocab.itos), d_model, padding_idx=0)
        self.src_pos = nn.Embedding(128, d_model)
        self.encoder = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d_model, heads, 4 * d_model, batch_first=True, norm_first=True), layers)
        self.tgt_emb = nn.Embedding(tgt_vocab, d_model, padding_idx=0)
        self.pos = nn.Embedding(64, d_model)
        self.decoder = nn.TransformerDecoder(
            nn.TransformerDecoderLayer(d_model, heads, 4 * d_model, batch_first=True, norm_first=True), layers)
        self.out = nn.Linear(d_model, tgt_vocab)
        self.cand = CandidateEncoder(len(cand_vocab.itos), d_model)

    def encode_source(self, texts):
        tokens_list = [v2.SRC_TOKEN.findall(text)[:128] for text in texts]
        width = max(1, max(len(tokens) for tokens in tokens_list))
        ids = torch.zeros(len(texts), width, dtype=torch.long)
        for index, tokens in enumerate(tokens_list):
            ids[index, :len(tokens)] = torch.tensor(
                [self.src_vocab.stoi.get(token, self.src_vocab.unk) for token in tokens])
        return ids, ids.ne(0)

    def encode_memory(self, ids, mask):
        pos = self.src_pos(torch.arange(ids.shape[1], device=ids.device))[None]
        return self.encoder(self.src_emb(ids) + pos, src_key_padding_mask=mask.eq(0))

    def decode_hidden(self, memory, mask, tgt):
        t = tgt.shape[1]
        pos = self.pos(torch.arange(t, device=tgt.device))[None]
        causal = nn.Transformer.generate_square_subsequent_mask(t, device=tgt.device)
        return self.decoder(self.tgt_emb(tgt) + pos, memory, tgt_mask=causal,
                            tgt_key_padding_mask=tgt.eq(0), memory_key_padding_mask=mask.eq(0))

    def forward(self, src_ids, src_mask, tgt, cand_ids, cand_mask, cand_types):
        memory = self.encode_memory(src_ids, src_mask)
        hidden = self.decode_hidden(memory, src_mask, tgt)
        return self.out(hidden), hidden, self.cand(cand_ids, cand_mask, cand_types)


def score_candidates(hidden, cand_vecs, cand_types, cand_present, field):
    scores = (cand_vecs * hidden[None, :]).sum(-1) / math.sqrt(hidden.shape[-1])
    allowed = cand_present.clone()
    if field == 'item':
        allowed &= cand_types.eq(1)
    elif field == 'loc':
        allowed &= cand_types.eq(2)
    elif field == 'target':
        allowed &= cand_types.eq(0)
    if not bool(allowed.any()):
        allowed = cand_present
    return scores.masked_fill(~allowed, -1e9)


def last_field(text):
    match = re.search(r'([a-z]+)=$', text)
    return match.group(1) if match else ''


def train(model, rows, vocab, device, epochs=60):
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=3e-4)
    e_id = vocab.stoi['<e>']
    random.shuffle(rows)
    for _ in range(epochs):
        for start in range(0, len(rows), 12):
            batch = rows[start:start + 12]
            by_world = {}
            for row in batch:
                by_world.setdefault(row['world'], []).append(row)
            cand_cache = per_world_candidates(by_world, CAND_VOCAB)
            # Candidate tensors are per world; split the batch by world.
            total_loss = torch.tensor(0.0, device=device)
            opt.zero_grad()
            for world, world_rows in by_world.items():
                texts = [row['input'] for row in world_rows]
                src_ids, src_mask = model.encode_source(texts)
                src_ids, src_mask = src_ids.to(device), src_mask.to(device)
                tgt = v2.pad_target(vocab, world_rows).to(device)
                c_ids, c_mask, c_types = cand_cache[world]
                c_ids, c_mask, c_types = c_ids.to(device), c_mask.to(device), c_types.to(device)
                logits, hidden, cand_vecs = model(src_ids, src_mask, tgt[:, :-1], c_ids, c_mask, c_types)
                labels = tgt[:, 1:]
                token_loss = F.cross_entropy(logits.reshape(-1, len(vocab.itos)), labels.reshape(-1),
                                             ignore_index=vocab.pad, reduction='none').reshape(labels.shape)
                loss_mask = torch.ones_like(labels, dtype=torch.float)
                for index, row in enumerate(world_rows):
                    loss_mask[index, :max(0, len(vocab.encode(row['prefix'], 64)) - 2)] = 0
                loss = (token_loss * loss_mask).sum() / loss_mask.sum().clamp(min=1)
                sel_loss = 0.0
                sel_count = 0
                cand_present = c_mask.any(-1)
                for index, row in enumerate(world_rows):
                    positions_in_labels = [j for j in range(labels.shape[1]) if int(labels[index, j]) == e_id]
                    for j, gold_index, field in zip(positions_in_labels, row['sel_gold'], row['sel_fields']):
                        scores = score_candidates(hidden[index, j], cand_vecs[index], c_types[index],
                                                  cand_present[index], field)
                        sel_loss = sel_loss + F.cross_entropy(scores[None], torch.tensor([gold_index], device=device))
                        sel_count += 1
                if sel_count:
                    loss = loss + sel_loss / sel_count
                total_loss = total_loss + loss
            total_loss.backward()
            opt.step()
    return model


def generate(model, vocab, row, device, max_len=32):
    model.eval()
    with torch.no_grad():
        src_ids, src_mask = model.encode_source([row['input']])
        src_ids, src_mask = src_ids.to(device), src_mask.to(device)
        memory = model.encode_memory(src_ids, src_mask)
        c_ids, c_mask, c_types = candidate_tensors([row], CAND_VOCAB, row['world'])
        c_ids, c_mask, c_types = c_ids.to(device), c_mask.to(device), c_types.to(device)
        cand_vecs = model.cand(c_ids, c_mask, c_types)[0]
        cand_present = c_mask[0].any(-1)
        cand_types = c_types[0]
        seed = vocab.encode(row['prefix'], 64)[1:-1]
        out = [vocab.bos] + seed
        start = 1 + len(seed)
        text = []
        e_id = vocab.stoi['<e>']
        for _ in range(max_len):
            tgt = torch.tensor([out], device=device)
            hidden = model.decode_hidden(memory, src_mask, tgt)
            logits = model.out(hidden)
            best = int(logits[0, -1].argmax())
            if best == e_id:
                field = last_field(''.join(text))
                scores = score_candidates(hidden[0, -1], cand_vecs, cand_types, cand_present, field)
                index = int(scores.argmax())
                resolved = row['candidates'][index] if 0 <= index < len(row['candidates']) else '<bad>'
                text.append(resolved)
                out.append(e_id)
            else:
                out.append(best)
                if best == vocab.eos:
                    break
                text.append(vocab.itos[best])
        return ''.join(text)


def evaluate(model, vocab, rows, device):
    predictions = []
    hits = total = exact = 0
    times = []
    per_field = Counter()
    per_field_total = Counter()
    result_hits = result_total = 0
    for row in rows:
        began = time.perf_counter()
        got = v2.parse_fields(generate(model, vocab, row, device))
        times.append((time.perf_counter() - began) * 1000)
        want = row['gold']
        exact += all(got.get(key) == value for key, value in want.items()) and set(got) <= set(want)
        hits += sum(1 for key, value in want.items() if got.get(key) == value)
        total += len(want)
        for key in set(got) | set(want):
            per_field_total[key] += 1
            if got.get(key) == want.get(key):
                per_field[key] += 1
        if 'result' in want:
            result_total += 1
            result_hits += got.get('result') == want['result']
        predictions.append({'id': row['id'], 'world': row['world'], 'type': row['type'], 'got': got, 'want': want})
    times.sort()
    return {'rows': len(rows), 'exact': round(exact / max(1, len(rows)), 3),
            'fieldRecall': round(hits / max(1, total), 3),
            'perField': {key: round(per_field[key] / per_field_total[key], 3) for key in sorted(per_field_total)},
            'resultAccuracy': round(result_hits / max(1, result_total), 3) if result_total else None,
            'p50Ms': round(statistics.median(times), 1) if times else None,
            'p95Ms': round(times[min(len(times) - 1, int(len(times) * 0.95))], 1) if times else None,
            'predictions': predictions}


def summarize(predictions):
    result = {'byWorld': {}}
    ent_hits = ent_total = open_hits = open_total = all_hits = all_total = 0
    for row in predictions:
        for key, value in row['want'].items():
            all_total += 1
            all_hits += row['got'].get(key) == value
            if key in ENTITY:
                ent_total += 1
                ent_hits += row['got'].get(key) == value
            else:
                open_total += 1
                open_hits += row['got'].get(key) == value
    result['fieldRecall'] = round(all_hits / max(1, all_total), 3)
    result['entityFieldRecall'] = round(ent_hits / max(1, ent_total), 3)
    result['openFieldRecall'] = round(open_hits / max(1, open_total), 3)
    for world in ('dragon', 'mistport'):
        subset = [row for row in predictions if row['world'] == world]
        ent_hits = ent_total = all_hits = all_total = 0
        for row in subset:
            for key, value in row['want'].items():
                all_total += 1
                all_hits += row['got'].get(key) == value
                if key in ENTITY:
                    ent_total += 1
                    ent_hits += row['got'].get(key) == value
        result['byWorld'][world] = {'rows': len(subset),
                                    'fieldRecall': round(all_hits / max(1, all_total), 3),
                                    'entityFieldRecall': round(ent_hits / max(1, ent_total), 3)}
    return result


CAND_VOCAB = None


def main():
    random.seed(20261126)
    torch.manual_seed(20261126)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    train_rows = v2.training_rows()
    test_rows = [v2.row_from_hand(row) for row in v2.HAND_ROWS]
    for row in train_rows + test_rows:
        continuation, gold, fields = candidate_continuation(row)
        row['candidate_cont'] = continuation
        row['continuation'] = continuation
        row['sel_gold'] = gold
        row['sel_fields'] = fields
    global CAND_VOCAB
    CAND_VOCAB = CandVocab(candidate_texts(train_rows + test_rows))
    texts = [row['prefix'] + row['candidate_cont'] for row in train_rows]
    texts += [row['text'] for row in test_rows] + [row['prefix'] for row in test_rows]
    vocab = v2.OutVocab(texts, pointer=False)
    tokenizer = BertTokenizer.from_pretrained(v2.SNAP.as_posix())
    bert = CandidateSeq2Seq(tokenizer, len(vocab.itos), CAND_VOCAB).to(device)
    bert = train(bert, train_rows, vocab, device)
    bert_metrics = evaluate(bert, vocab, test_rows, device)
    bert_metrics.update(summarize(bert_metrics['predictions']))
    bert_metrics['params'] = sum(p.numel() for p in bert.parameters())
    bert_metrics['eTokenInVocab'] = '<e>' in vocab.stoi
    bert_metrics['candVocab'] = len(CAND_VOCAB.itos)
    src_vocab = v2.SrcVocab([row['input'] for row in train_rows + test_rows])
    scratch = ScratchCandidateSeq2Seq(src_vocab, len(vocab.itos), CAND_VOCAB).to(device)
    scratch = train(scratch, train_rows, vocab, device)
    scratch_metrics = evaluate(scratch, vocab, test_rows, device)
    scratch_metrics.update(summarize(scratch_metrics['predictions']))
    scratch_metrics['params'] = sum(p.numel() for p in scratch.parameters())
    scratch_metrics['eTokenInVocab'] = '<e>' in vocab.stoi
    scratch_metrics['candVocab'] = len(CAND_VOCAB.itos)
    report = {'trainRows': len(train_rows), 'testRows': len(test_rows),
              'arms': {'bert_candidate_pointer': bert_metrics, 'scratch_candidate_pointer': scratch_metrics}}
    v2_path = v2.OUT / 'v2-report.json'
    if v2_path.exists():
        v2_report = json.loads(v2_path.read_text(encoding='utf8'))
        report['resultClassifier'] = v2_report.get('resultClassifier')
        report['v2Comparison'] = {arm: {key: v2_report['arms'][arm].get(key)
                                        for key in ('fieldRecall', 'entityFieldRecall', 'byWorld')}
                                  for arm in v2_report.get('arms', {})}
    (v2.OUT / 'v3-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    for name, metrics in report['arms'].items():
        print(name, json.dumps({key: metrics[key] for key in ('rows', 'exact', 'fieldRecall', 'entityFieldRecall',
                                                              'openFieldRecall', 'byWorld', 'resultAccuracy', 'params',
                                                              'p50Ms', 'p95Ms')}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
