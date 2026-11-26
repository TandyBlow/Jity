# -*- coding: utf-8 -*-
"""Train the v3 candidate-pointer arm and export browser ONNX graphs.

Encoder (fixed 96), decoder-step (fixed 64), a past-KV decoder-step, and the
candidate encoder. All four are int8-quantized and copied to frontend/public/micro.
The parity check runs the same greedy loops on torch and onnxruntime CPU.
"""
import argparse
import importlib.util
import json
import math
import random
import statistics
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import onnxruntime.quantization as quant
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import BertTokenizer

HERE = Path(__file__).resolve().parent
ROOT = Path('D:/others/Jity')
OUT = HERE / 'micro-generative'
PUB = ROOT / 'frontend/public/micro'
SEED = 20261126
MAX_SOURCE, MAX_TARGET, MAX_TOKENS = 96, 64, 32
MAX_CANDIDATES, CAND_CHARS = 10, 11
HEADS, HEAD_DIM = 8, 32

spec = importlib.util.spec_from_file_location('v3', HERE / 'micro_generative_v3.py')
v3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v3)
v2 = v3.v2
from hand_train import ROWS as HAND_TRAIN  # noqa: E402
from hand_test import ROWS as HAND_ROWS  # noqa: E402


def build_rows():
    train_rows = v2.training_rows() + [v2.row_from_hand(row) for row in HAND_TRAIN]
    test_rows = [v2.row_from_hand(row) for row in HAND_ROWS]
    for row in train_rows + test_rows:
        continuation, gold, fields = v3.candidate_continuation(row)
        row['candidate_cont'] = continuation
        row['continuation'] = continuation
        row['sel_gold'] = gold
        row['sel_fields'] = fields
    return train_rows, test_rows


def build_vocabs(train_rows, test_rows):
    cand_vocab = v3.CandVocab(v3.candidate_texts(train_rows + test_rows))
    texts = [row['prefix'] + row['candidate_cont'] for row in train_rows]
    texts += [row['text'] for row in test_rows] + [row['prefix'] for row in test_rows]
    return cand_vocab, v2.OutVocab(texts, pointer=False)


def candidate_tensors(row, cand_vocab):
    ids = np.zeros((MAX_CANDIDATES, CAND_CHARS), dtype=np.int64)
    mask = np.zeros((MAX_CANDIDATES, CAND_CHARS), dtype=np.int64)
    types = np.zeros(MAX_CANDIDATES, dtype=np.int64)
    uni = v2.universe(v2.WORLDS[row['world']])
    for index, ident in enumerate(row['candidates']):
        tokens = v3.CAND_TOKEN.findall(uni[ident]['name'] + '=' + ident)[:CAND_CHARS]
        ids[index, :len(tokens)] = [cand_vocab.stoi.get(token, cand_vocab.unk) for token in tokens]
        mask[index, :len(tokens)] = 1
        types[index] = v3.TYPE_ID[uni[ident]['type']]
    return ids, mask, types


class EncoderExport(nn.Module):
    def __init__(self, bert):
        super().__init__()
        self.bert = bert

    def forward(self, input_ids, attention_mask):
        return self.bert(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state


class DecoderExport(nn.Module):
    def __init__(self, model):
        super().__init__()
        self.emb = model.tgt_emb
        self.pos = model.pos
        self.decoder = model.decoder
        self.out = model.out

    def forward(self, memory, tgt, src_mask):
        pos = self.pos(torch.arange(tgt.shape[1], device=tgt.device))[None]
        causal = nn.Transformer.generate_square_subsequent_mask(tgt.shape[1], device=tgt.device)
        hidden = self.decoder(self.emb(tgt) + pos, memory, tgt_mask=causal,
                              tgt_key_padding_mask=tgt.eq(0),
                              memory_key_padding_mask=src_mask.eq(0))
        return self.out(hidden), hidden


class KVDecoderExport(nn.Module):
    """One token step with explicit self-attention KV caches (fixed 64 slots)."""

    def __init__(self, model):
        super().__init__()
        self.emb = model.tgt_emb
        self.pos = model.pos
        self.layers = model.decoder.layers
        self.out = model.out

    def _heads(self, x):
        return x.view(1, x.shape[1], HEADS, HEAD_DIM).transpose(1, 2)

    def _attend(self, q, k, v, mask):
        scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(HEAD_DIM)
        weights = torch.softmax(scores + mask, dim=-1)
        return torch.matmul(weights, v).transpose(1, 2).reshape(1, 1, HEADS * HEAD_DIM)

    def _self_attention(self, layer, x, step, valid, k_cache, v_cache):
        proj = F.linear(layer.norm1(x), layer.self_attn.in_proj_weight,
                        layer.self_attn.in_proj_bias)
        q, k, v = proj.chunk(3, dim=-1)
        index = step.view(1, 1, 1, 1).expand(-1, HEADS, -1, HEAD_DIM)
        k = k_cache.scatter(2, index, self._heads(k))
        v = v_cache.scatter(2, index, self._heads(v))
        mask = (1.0 - valid.float()) * -1e9
        attended = self._attend(self._heads(q), k, v, mask[:, None, None, :])
        return x + layer.self_attn.out_proj(attended), k, v

    def _cross_attention(self, layer, x, memory, src_mask):
        size = layer.multihead_attn.embed_dim
        q = F.linear(layer.norm2(x), layer.multihead_attn.in_proj_weight[:size],
                     layer.multihead_attn.in_proj_bias[:size])
        kv = F.linear(memory, layer.multihead_attn.in_proj_weight[size:],
                      layer.multihead_attn.in_proj_bias[size:])
        k, v = kv.chunk(2, dim=-1)
        mask = (1.0 - src_mask.float()) * -1e9
        attended = self._attend(self._heads(q), self._heads(k), self._heads(v),
                                mask[:, None, None, :])
        return x + layer.multihead_attn.out_proj(attended)

    def forward(self, token, step, valid, memory, src_mask, k0, v0, k1, v1, k2, v2, k3, v3):
        x = self.emb(token) + self.pos(step)
        new = []
        for layer, k, v in zip(self.layers, (k0, k1, k2, k3), (v0, v1, v2, v3)):
            x, k, v = self._self_attention(layer, x, step, valid, k, v)
            new.extend([k, v])
            x = self._cross_attention(layer, x, memory, src_mask)
            x = x + layer.linear2(layer.activation(layer.linear1(layer.norm3(x))))
        return (self.out(x), x, *new)


class CandidateExport(nn.Module):
    def __init__(self, model):
        super().__init__()
        self.cand = model.cand

    def forward(self, cand_ids, cand_mask, cand_types):
        return self.cand(cand_ids, cand_mask, cand_types)


def np_scores(hidden, cand_vecs, cand_types, present, field):
    scores = cand_vecs @ hidden / math.sqrt(hidden.shape[-1])
    allowed = present.copy()
    if field == 'item':
        allowed &= cand_types == 1
    elif field == 'loc':
        allowed &= cand_types == 2
    elif field == 'target':
        allowed &= cand_types == 0
    if not allowed.any():
        allowed = present
    return int(np.argmax(np.where(allowed, scores, -1e9)))


def np_candidates(row, cand_vocab, session):
    ids, mask, types = candidate_tensors(row, cand_vocab)
    vecs = session.run(None, {'cand_ids': ids[None], 'cand_mask': mask[None],
                              'cand_types': types[None]})[0][0]
    return vecs, types, mask.any(-1)


def encode_np(tokenizer, text, session):
    encoded = tokenizer(text, padding='max_length', truncation=True, max_length=MAX_SOURCE)
    ids = np.array([encoded['input_ids']], dtype=np.int64)
    mask = np.array([encoded['attention_mask']], dtype=np.int64)
    return ids, mask, session.run(None, {'input_ids': ids, 'attention_mask': mask})[0]


def decode_fixed_np(tokenizer, row, seed, vocab, cand_vocab, sessions, max_tokens=MAX_TOKENS):
    src_ids, src_mask, memory = encode_np(tokenizer, row['input'], sessions['encoder'])
    cand_vecs, cand_types, present = np_candidates(row, cand_vocab, sessions['candidate'])
    out = [vocab.bos] + seed
    text, steps, pointer = [], [], 0
    for _ in range(max_tokens):
        tgt = np.full((1, MAX_TARGET), vocab.pad, dtype=np.int64)
        tgt[0, :len(out)] = out
        began = time.perf_counter()
        logits, hidden = sessions['decoder'].run(
            None, {'memory': memory, 'tgt': tgt, 'src_mask': src_mask})
        steps.append((time.perf_counter() - began) * 1000)
        best = int(np.argmax(logits[0, len(out) - 1]))
        if best == vocab.stoi['<e>']:
            field = v3.last_field(''.join(text))
            index = np_scores(hidden[0, len(out) - 1], cand_vecs, cand_types, present, field)
            text.append(row['candidates'][index] if index < len(row['candidates']) else '<bad>')
            out.append(best)
            pointer += 1
        else:
            out.append(best)
            if best == vocab.eos:
                break
            text.append(vocab.itos[best])
    return ''.join(text), out, pointer, steps


def decode_kv_np(tokenizer, row, seed, vocab, cand_vocab, sessions, max_tokens=MAX_TOKENS):
    src_ids, src_mask, memory = encode_np(tokenizer, row['input'], sessions['encoder'])
    cand_vecs, cand_types, present = np_candidates(row, cand_vocab, sessions['candidate'])
    caches = [np.zeros((1, HEADS, MAX_TARGET, HEAD_DIM), dtype=np.float32) for _ in range(8)]
    valid = np.zeros((1, MAX_TARGET), dtype=np.int64)
    names = [f'past_{kind}{index}' for index in range(4) for kind in ('k', 'v')]
    out = [vocab.bos] + seed
    text, pointer, calls, generated = [], 0, 0, 0

    def step(token, position):
        valid[0, position] = 1 if token != vocab.pad else 0
        feeds = {'token': np.array([[token]], dtype=np.int64),
                 'step': np.array([position], dtype=np.int64),
                 'valid': valid, 'memory': memory, 'src_mask': src_mask}
        feeds.update(dict(zip(names, caches)))
        values = sessions['decoder_kv'].run(None, feeds)
        return values[0], values[1], values[2:]

    logits, hidden = None, None
    for position, token in enumerate(out):
        logits, hidden, caches = step(token, position)
        calls += 1
    steps = []
    while generated < max_tokens and len(out) < MAX_TARGET:
        generated += 1
        best = int(np.argmax(logits[0, 0]))
        if best == vocab.stoi['<e>']:
            field = v3.last_field(''.join(text))
            index = np_scores(hidden[0, 0], cand_vecs, cand_types, present, field)
            text.append(row['candidates'][index] if index < len(row['candidates']) else '<bad>')
            out.append(best)
            pointer += 1
        else:
            out.append(best)
            if best == vocab.eos:
                break
            text.append(vocab.itos[best])
        began = time.perf_counter()
        logits, hidden, caches = step(best, len(out) - 1)
        steps.append((time.perf_counter() - began) * 1000)
        calls += 1
    return ''.join(text), out, pointer, steps, calls


def torch_decode(model, row, vocab, cand_vocab, device, max_len=MAX_TOKENS):
    model.eval()
    with torch.no_grad():
        src_ids, src_mask = model.encode_source([row['input']])
        src_ids, src_mask = src_ids.to(device), src_mask.to(device)
        memory = model.encode_memory(src_ids, src_mask)
        c_ids, c_mask, c_types = v3.candidate_tensors([row], cand_vocab, row['world'])
        c_ids, c_mask, c_types = c_ids.to(device), c_mask.to(device), c_types.to(device)
        cand_vecs = model.cand(c_ids, c_mask, c_types)[0]
        present = c_mask[0].any(-1)
        cand_types = c_types[0]
        seed = vocab.encode(row['prefix'], MAX_TARGET)[1:-1]
        out = [vocab.bos] + seed
        text = []
        for _ in range(max_len):
            tgt = torch.tensor([out], device=device)
            hidden = model.decode_hidden(memory, src_mask, tgt)
            logits = model.out(hidden)
            best = int(logits[0, -1].argmax())
            if best == vocab.stoi['<e>']:
                field = v3.last_field(''.join(text))
                scores = v3.score_candidates(hidden[0, -1], cand_vecs, cand_types, present, field)
                index = int(scores.argmax())
                text.append(row['candidates'][index] if 0 <= index < len(row['candidates']) else '<bad>')
                out.append(best)
            else:
                out.append(best)
                if best == vocab.eos:
                    break
                text.append(vocab.itos[best])
    return ''.join(text), out


def torch_kv_decode(model, row, vocab, cand_vocab, device, max_len=MAX_TOKENS):
    """fp32 KV check: same greedy loop with the exported cache layout."""
    kv = KVDecoderExport(model).eval()
    with torch.no_grad():
        src_ids, src_mask = model.encode_source([row['input']])
        src_ids, src_mask = src_ids.to(device), src_mask.to(device)
        memory = model.encode_memory(src_ids, src_mask)
        c_ids, c_mask, c_types = v3.candidate_tensors([row], cand_vocab, row['world'])
        c_ids, c_mask, c_types = c_ids.to(device), c_mask.to(device), c_types.to(device)
        cand_vecs = model.cand(c_ids, c_mask, c_types)[0]
        present = c_mask[0].any(-1)
        cand_types = c_types[0]
        seed = vocab.encode(row['prefix'], MAX_TARGET)[1:-1]
        out = [vocab.bos] + seed
        text = []
        caches = [torch.zeros(1, HEADS, MAX_TARGET, HEAD_DIM, device=device) for _ in range(8)]
        valid = torch.zeros(1, MAX_TARGET, dtype=torch.long, device=device)

        def step(token, position):
            valid[0, position] = 0 if token == vocab.pad else 1
            values = kv(torch.tensor([[token]], device=device),
                        torch.tensor([position], device=device), valid, memory, src_mask, *caches)
            return values[0], values[1], values[2:]

        logits = hidden = None
        for position, token in enumerate(out):
            logits, hidden, caches = step(token, position)
        for _ in range(max_len):
            best = int(logits[0, 0].argmax())
            if best == vocab.stoi['<e>']:
                field = v3.last_field(''.join(text))
                scores = v3.score_candidates(hidden[0, 0], cand_vecs, cand_types, present, field)
                index = int(scores.argmax())
                text.append(row['candidates'][index] if 0 <= index < len(row['candidates']) else '<bad>')
                out.append(best)
            else:
                out.append(best)
                if best == vocab.eos:
                    break
                text.append(vocab.itos[best])
            logits, hidden, caches = step(best, len(out) - 1)
    return ''.join(text), out


def export_graphs(model, tokenizer, sample, cand_vocab, vocab):
    encoder = EncoderExport(model.bert).eval()
    decoder = DecoderExport(model).eval()
    kv = KVDecoderExport(model).eval()
    candidate = CandidateExport(model).eval()
    encoded = tokenizer(sample['input'], padding='max_length', truncation=True,
                        max_length=MAX_SOURCE)
    ids = torch.tensor([encoded['input_ids']], dtype=torch.long)
    mask = torch.tensor([encoded['attention_mask']], dtype=torch.long)
    with torch.no_grad():
        memory = encoder(ids, mask)
        c_ids, c_mask, c_types = candidate_tensors(sample, cand_vocab)
        c_ids = torch.from_numpy(c_ids)[None]
        c_mask = torch.from_numpy(c_mask)[None]
        c_types = torch.from_numpy(c_types)[None]
    tgt = torch.zeros(1, MAX_TARGET, dtype=torch.long)
    src_mask = mask
    paths = {name: OUT / f'v3-{name}.onnx' for name in ('encoder', 'decoder', 'decoder-kv', 'candidate')}
    torch.onnx.export(encoder, (ids, mask), paths['encoder'], opset_version=17, dynamo=False,
                      input_names=['input_ids', 'attention_mask'], output_names=['memory'])
    torch.onnx.export(decoder, (memory, tgt, src_mask), paths['decoder'], opset_version=17,
                      dynamo=False, input_names=['memory', 'tgt', 'src_mask'],
                      output_names=['logits', 'hidden'])
    caches = tuple(torch.zeros(1, HEADS, MAX_TARGET, HEAD_DIM) for _ in range(8))
    torch.onnx.export(kv, (torch.zeros(1, 1, dtype=torch.long), torch.zeros(1, dtype=torch.long),
                           torch.ones(1, MAX_TARGET, dtype=torch.long), memory, src_mask, *caches),
                      paths['decoder-kv'], opset_version=17, dynamo=False,
                      input_names=['token', 'step', 'valid', 'memory', 'src_mask'] +
                                  [f'past_{kind}{index}' for index in range(4) for kind in ('k', 'v')],
                      output_names=['logits', 'hidden'] +
                                   [f'new_{kind}{index}' for index in range(4) for kind in ('k', 'v')])
    torch.onnx.export(candidate, (c_ids, c_mask, c_types), paths['candidate'], opset_version=17,
                      dynamo=False, input_names=['cand_ids', 'cand_mask', 'cand_types'],
                      output_names=['cand_vecs'])
    int8 = {}
    for name, path in paths.items():
        target = OUT / f'v3-{name}-int8.onnx'
        quant.quantize_dynamic(path.as_posix(), target.as_posix(), weight_type=quant.QuantType.QInt8)
        int8[name.replace('-', '_')] = target
        path.unlink()
    return int8


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reuse', action='store_true')
    parser.add_argument('--epochs', type=int, default=60)
    args = parser.parse_args()
    random.seed(SEED)
    torch.manual_seed(SEED)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    train_rows, test_rows = build_rows()
    assert len(train_rows) == 123, len(train_rows)
    cand_vocab, vocab = build_vocabs(train_rows, test_rows)
    sample = next(row for row in train_rows if row['id'] == 'lu' and row['kind'] == 'events'
                  and row['gold'].get('item') == 'foyer_table'
                  and row['gold'].get('env') == 'stairs_clear')
    assert max(len(row['candidates']) for row in train_rows + test_rows) <= MAX_CANDIDATES
    checkpoint = OUT / 'v3-candidate.pt'
    began = time.perf_counter()
    tokenizer = BertTokenizer.from_pretrained(v2.SNAP.as_posix())
    model = v3.CandidateSeq2Seq(tokenizer, len(vocab.itos), cand_vocab).to(device)
    v3.CAND_VOCAB = cand_vocab
    report = {'trainRows': len(train_rows), 'handTrainRows': len(HAND_TRAIN),
              'seed': SEED, 'epochs': args.epochs}
    if args.reuse:
        state = torch.load(checkpoint, map_location='cpu')
        model.load_state_dict(state['state_dict'])
        report['trainSeconds'] = state.get('trainSeconds')
        report['reusedCheckpoint'] = True
    else:
        model = v3.train(model, train_rows, vocab, device, epochs=args.epochs)
        report['trainSeconds'] = round(time.perf_counter() - began, 1)
        torch.save({'state_dict': model.state_dict(), 'itos': vocab.itos,
                    'candItos': cand_vocab.itos, 'seed': SEED, 'epochs': args.epochs,
                    'trainSeconds': report['trainSeconds']}, checkpoint)
        report['reusedCheckpoint'] = False
    model.to('cpu').eval()
    report['params'] = sum(parameter.numel() for parameter in model.parameters())
    report['checkpointMB'] = round(checkpoint.stat().st_size / 1e6, 1)

    metrics = v3.evaluate(model, vocab, test_rows, torch.device('cpu'))
    metrics.update(v3.summarize(metrics['predictions']))
    metrics.pop('predictions')
    report['testMetrics'] = metrics

    int8 = export_graphs(model, tokenizer, sample, cand_vocab, vocab)
    sizes = {name: round(path.stat().st_size / 1e6, 2) for name, path in int8.items()}
    report['int8MB'] = sizes
    report['kvExport'] = {
        'feasible': True,
        'cached': 'self-attention past K/V per layer, 8 tensors of [1,8,64,32]',
        'crossAttention': 'encoder memory tensor is computed once and reused; its K/V '
                          'projections are recomputed inside each step',
    }
    PUB.mkdir(parents=True, exist_ok=True)
    for name, path in int8.items():
        (PUB / path.name).write_bytes(path.read_bytes())

    session_options = ort.SessionOptions()
    session_options.intra_op_num_threads = 1
    session_options.inter_op_num_threads = 1
    sessions = {name: ort.InferenceSession(path.as_posix(), sess_options=session_options,
                                           providers=['CPUExecutionProvider'])
                for name, path in int8.items()}
    seed = vocab.encode(sample['prefix'], MAX_TARGET)[1:-1]
    torch_text, torch_ids = torch_decode(model, sample, vocab, cand_vocab, torch.device('cpu'))
    fixed_text, fixed_ids, fixed_pointer, fixed_steps = decode_fixed_np(
        tokenizer, sample, seed, vocab, cand_vocab, sessions)
    kv_text, kv_ids, kv_pointer, kv_steps, kv_calls = decode_kv_np(
        tokenizer, sample, seed, vocab, cand_vocab, sessions)

    torch_outputs, fixed_outputs, kv_outputs = [], [], []
    truncated = 0
    fp32_kv = 0
    for row in test_rows:
        encoded = tokenizer(row['input'])
        truncated += len(encoded['input_ids']) > MAX_SOURCE
        row_seed = vocab.encode(row['prefix'], MAX_TARGET)[1:-1]
        row_torch_ids = torch_decode(model, row, vocab, cand_vocab, torch.device('cpu'))[1]
        torch_outputs.append(row_torch_ids)
        fixed_outputs.append(decode_fixed_np(tokenizer, row, row_seed, vocab, cand_vocab, sessions)[1])
        kv_outputs.append(decode_kv_np(tokenizer, row, row_seed, vocab, cand_vocab, sessions)[1])
        fp32_kv += torch_kv_decode(model, row, vocab, cand_vocab, torch.device('cpu'))[1] == row_torch_ids
    report['testParity'] = {
        'rows': len(test_rows), 'truncatedSourceRows': truncated, 'fp32KvMatchesFixed': fp32_kv,
        'fixedMatchesTorch': sum(a == b for a, b in zip(fixed_outputs, torch_outputs)),
        'kvMatchesTorch': sum(a == b for a, b in zip(kv_outputs, torch_outputs)),
        'fixedKvEqual': sum(a == b for a, b in zip(fixed_outputs, kv_outputs)),
    }

    sample_json = {
        'maxSource': MAX_SOURCE, 'maxTarget': MAX_TARGET, 'maxTokens': MAX_TOKENS,
        'vocab': {'itos': vocab.itos, 'pad': vocab.pad, 'bos': vocab.bos, 'eos': vocab.eos,
                  'unk': vocab.unk, 'eId': vocab.stoi['<e>']},
        'sample': {
            'id': sample['id'], 'input': sample['input'], 'prefix': sample['prefix'],
            'gold': sample['gold'],
            'srcIds': encoded_sample_ids(tokenizer, sample),
            'srcMask': encoded_sample_mask(tokenizer, sample),
            'seedIds': seed,
            'candidates': [{'id': ident, 'name': v2.universe(v2.WORLDS[sample['world']])[ident]['name'],
                            'type': v3.TYPE_ID[v2.universe(v2.WORLDS[sample['world']])[ident]['type']],
                            'ids': candidate_ids(ident, sample, cand_vocab),
                            'mask': candidate_mask(ident, sample, cand_vocab)}
                           for ident in sample['candidates']],
            'torchOutput': torch_text,
            'onnxFixedOutput': fixed_text,
            'onnxKvOutput': kv_text,
        },
    }
    (OUT / 'v3-probe.json').write_text(json.dumps(sample_json, ensure_ascii=False, indent=1),
                                       encoding='utf8')
    (PUB / 'v3-probe.json').write_text(json.dumps(sample_json, ensure_ascii=False, indent=1),
                                       encoding='utf8')
    report['sample'] = {
        'id': sample['id'], 'input': sample['input'], 'gold': sample['gold'],
        'seedTokens': len(seed),
        'sourceTokens': sum(encoded_sample_mask(tokenizer, sample)),
        'candidates': len(sample['candidates']),
        'torchOutput': torch_text, 'onnxFixedOutput': fixed_text, 'onnxKvOutput': kv_text,
        'fixedTokens': len(fixed_ids), 'kvTokens': len(kv_ids),
        'fixedPointerSelections': fixed_pointer, 'kvPointerSelections': kv_pointer,
        'textsEqual': torch_text == fixed_text == kv_text,
        'fixedIdsMatchTorch': fixed_ids == torch_ids, 'kvIdsMatchTorch': kv_ids == torch_ids,
        'fixedKvEqual': fixed_ids == kv_ids,
        'onnxCpuFixedP50Ms': round(statistics.median(fixed_steps), 2),
        'onnxCpuKvP50Ms': round(statistics.median(kv_steps), 2) if kv_steps else None,
        'kvCalls': kv_calls,
        'note': 'onnxruntime CPU, int8; the browser probe measures ORT-WASM',
    }
    (OUT / 'v3-onnx-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                             encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


def encoded_sample_ids(tokenizer, sample):
    encoded = tokenizer(sample['input'], padding='max_length', truncation=True,
                        max_length=MAX_SOURCE)
    return encoded['input_ids']


def encoded_sample_mask(tokenizer, sample):
    encoded = tokenizer(sample['input'], padding='max_length', truncation=True,
                        max_length=MAX_SOURCE)
    return encoded['attention_mask']


def candidate_ids(ident, row, cand_vocab):
    uni = v2.universe(v2.WORLDS[row['world']])
    tokens = v3.CAND_TOKEN.findall(uni[ident]['name'] + '=' + ident)[:CAND_CHARS]
    return [cand_vocab.stoi.get(token, cand_vocab.unk) for token in tokens]


def candidate_mask(ident, row, cand_vocab):
    return [1] * len(candidate_ids(ident, row, cand_vocab))


if __name__ == '__main__':
    main()
