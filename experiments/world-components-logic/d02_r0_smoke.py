"""R0 engineering smoke test: frozen two-layer MiniRBT + new M1/M2 heads.

This is not a quality experiment.  It verifies that the scale-v2 annotations can
be tokenized, that token/role/entity and expression heads can be optimized for a
few steps on CPU, that the frozen encoder is unchanged, and that the heads can be
saved and reloaded.  No development or sealed sample is evaluated.
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

PROCESS_START = time.time()

import torch
import torch.nn.functional as F

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data' / 'd02-checkers' / 'scale-v2'
BASE = Path('/Users/davidz/.cache/jity-d-short-semantics-20261109/encoder/M01/446e1b4012b10946f479563005700c54c9db3f7c')
TOKENIZERS = Path('/Users/davidz/Documents/GitHub/Jity-D-short-semantics/.local/world-components-logic/venv/lib/python3.12/site-packages')
OUT = HERE.parents[1] / 'artifacts' / 'world-components-logic' / 'd02-checkers' / 'r0-smoke'
EXPR = ('attempt', 'result_assertion', 'non_action', 'mixed', 'uncertain')
ROLES = ('subject', 'object', 'tool', 'recipient', 'destination')


def load_tokenizer():
    if TOKENIZERS.exists():
        sys.path.insert(0, str(TOKENIZERS))
    from tokenizers import Tokenizer
    from tokenizers.models import WordPiece
    from tokenizers.normalizers import BertNormalizer
    from tokenizers.pre_tokenizers import BertPreTokenizer
    from tokenizers.processors import BertProcessing
    vocab = {}
    for index, line in enumerate((BASE / 'vocab.txt').read_text().splitlines()):
        vocab[line] = index
    tokenizer = Tokenizer(WordPiece(vocab, unk_token='[UNK]'))
    tokenizer.normalizer = BertNormalizer(clean_text=True, handle_chinese_chars=True,
                                          strip_accents=False, lowercase=False)
    tokenizer.pre_tokenizer = BertPreTokenizer()
    tokenizer.post_processor = BertProcessing(('[SEP]', vocab['[SEP]']),
                                              ('[CLS]', vocab['[CLS]']))
    return tokenizer, vocab


class FrozenMiniRBT:
    def __init__(self, state, config):
        self.s = state
        self.hidden = config['hidden_size']
        self.heads = config['num_attention_heads']
        self.eps = config['layer_norm_eps']
        self.layers = 2
        self.position = state['bert.embeddings.position_embeddings.weight']
        self.token_type = state['bert.embeddings.token_type_embeddings.weight']
        self.word = state['bert.embeddings.word_embeddings.weight']
        self.emb_norm_w = state['bert.embeddings.LayerNorm.weight']
        self.emb_norm_b = state['bert.embeddings.LayerNorm.bias']

    def _linear(self, x, prefix):
        return F.linear(x, self.s[prefix + '.weight'], self.s[prefix + '.bias'])

    def _layer(self, x, index, mask):
        p = 'bert.encoder.layer.' + str(index) + '.'
        b, length, width = x.shape
        q = self._linear(x, p + 'attention.self.query').view(b, length, self.heads, width // self.heads).transpose(1, 2)
        k = self._linear(x, p + 'attention.self.key').view(b, length, self.heads, width // self.heads).transpose(1, 2)
        v = self._linear(x, p + 'attention.self.value').view(b, length, self.heads, width // self.heads).transpose(1, 2)
        scores = torch.matmul(q, k.transpose(-1, -2)) / math.sqrt(width // self.heads)
        scores = scores + (1.0 - mask[:, None, None, :]) * -1e9
        attn = torch.softmax(scores, dim=-1)
        ctx = torch.matmul(attn, v).transpose(1, 2).contiguous().view(b, length, width)
        ctx = self._linear(ctx, p + 'attention.output.dense')
        x = F.layer_norm(x + ctx, (width,), self.s[p + 'attention.output.LayerNorm.weight'],
                         self.s[p + 'attention.output.LayerNorm.bias'], self.eps)
        inter = F.gelu(self._linear(x, p + 'intermediate.dense'))
        out = self._linear(inter, p + 'output.dense')
        return F.layer_norm(x + out, (width,), self.s[p + 'output.LayerNorm.weight'],
                            self.s[p + 'output.LayerNorm.bias'], self.eps)

    def __call__(self, ids, types, mask):
        length = ids.shape[1]
        positions = torch.arange(length, dtype=torch.long).unsqueeze(0)
        x = self.word[ids] + self.position[positions] + self.token_type[types]
        x = F.layer_norm(x, (self.hidden,), self.emb_norm_w, self.emb_norm_b, self.eps)
        for index in range(self.layers):
            x = self._layer(x, index, mask)
        return x


class Heads(torch.nn.Module):
    def __init__(self, width, entities):
        super().__init__()
        self.mention = torch.nn.Linear(width, 3)
        self.role = torch.nn.Linear(width, len(ROLES))
        self.entity = torch.nn.Linear(width, entities)
        self.expression = torch.nn.Linear(width, len(EXPR))

    def forward(self, hidden):
        return {'mention': self.mention(hidden), 'role': self.role(hidden),
                'entity': self.entity(hidden), 'expression': self.expression(hidden[:, 0])}


def encoder_hash(encoder):
    h = hashlib.sha256()
    for key in sorted(encoder.s):
        tensor = encoder.s[key].detach().cpu().contiguous()
        h.update(key.encode())
        h.update(tensor.numpy().tobytes())
    return h.hexdigest()


def load_data():
    rows = [json.loads(line) for line in (DATA / 'samples.jsonl').read_text().splitlines()]
    rows = [row for row in rows if row['split'] == 'train']
    worlds = json.loads((DATA / 'worlds.json').read_text())
    entity_ids = sorted({f"{world_id}:{entity_id}" for world_id, world in worlds.items()
                         for entity_id in world['entities']})
    entity_index = {key: index for index, key in enumerate(entity_ids)}
    tokenizer, vocab = load_tokenizer()
    examples = []
    for row in rows:
        encoding = tokenizer.encode(row['text'], add_special_tokens=True)
        ids, offsets = encoding.ids, encoding.offsets
        mention = [0] * len(ids)
        roles = [[0] * len(ROLES) for _ in ids]
        entity = [-100] * len(ids)
        for step in row['roleAudit']['steps']:
            for item in step['mentions']:
                indices = [i for i, (start, end) in enumerate(offsets)
                           if start < item['end'] and item['start'] < end and end > start]
                if not indices:
                    continue
                first = indices[0]
                if mention[first] != 1:
                    mention[first] = 1
                for index in indices[1:]:
                    if mention[index] == 0:
                        mention[index] = 2
                for role in item['roles']:
                    roles[first][ROLES.index(role)] = 1
                if item.get('entityId'):
                    key = row['worldId'] + ':' + item['entityId']
                    if key in entity_index:
                        entity[first] = entity_index[key]
        examples.append({'ids': ids, 'mention': mention, 'roles': roles,
                         'entity': entity, 'expression': EXPR.index(row['expressionAudit']['label']),
                         'sampleId': row['sampleId']})
    return examples, entity_ids


def batch(examples, indices):
    selected = [examples[i] for i in indices]
    length = max(len(row['ids']) for row in selected)
    ids = torch.zeros((len(selected), length), dtype=torch.long)
    types = torch.zeros_like(ids)
    mention = torch.full_like(ids, -100)
    roles = torch.zeros((len(selected), length, len(ROLES)))
    entity = torch.full_like(ids, -100)
    expression = torch.tensor([row['expression'] for row in selected], dtype=torch.long)
    role_mask = torch.zeros((len(selected), length), dtype=torch.bool)
    entity_mask = torch.zeros((len(selected), length), dtype=torch.bool)
    for row_index, row in enumerate(selected):
        n = len(row['ids'])
        ids[row_index, :n] = torch.tensor(row['ids'])
        mention[row_index, :n] = torch.tensor(row['mention'])
        roles[row_index, :n] = torch.tensor(row['roles'], dtype=torch.float32)
        entity[row_index, :n] = torch.tensor(row['entity'])
        role_mask[row_index, :n] = torch.tensor(row['mention']) == 1
        entity_mask[row_index, :n] = torch.tensor(row['entity']) >= 0
    mask = (ids != 0).float()
    return {'ids': ids, 'types': types, 'mask': mask, 'mention': mention, 'roles': roles,
            'entity': entity, 'expression': expression, 'roleMask': role_mask,
            'entityMask': entity_mask, 'lengths': [len(row['ids']) for row in selected]}


def loss_and_stats(outputs, data):
    mention_loss = F.cross_entropy(outputs['mention'].view(-1, 3), data['mention'].view(-1),
                                   ignore_index=-100)
    role_logits = outputs['role'][data['roleMask']]
    role_targets = data['roles'][data['roleMask']]
    role_loss = F.binary_cross_entropy_with_logits(role_logits, role_targets) if role_logits.numel() else torch.tensor(0.0)
    entity_logits = outputs['entity'][data['entityMask']]
    entity_targets = data['entity'][data['entityMask']]
    entity_loss = F.cross_entropy(entity_logits, entity_targets) if entity_logits.numel() else torch.tensor(0.0)
    expression_loss = F.cross_entropy(outputs['expression'], data['expression'])
    total = mention_loss + role_loss + entity_loss + expression_loss
    stats = {
        'mentionAcc': (outputs['mention'].argmax(-1)[data['mention'] >= 0] ==
                       data['mention'][data['mention'] >= 0]).float().mean().item(),
        'roleAcc': ((role_logits > 0).float() == role_targets).float().mean().item() if role_logits.numel() else 0.0,
        'entityAcc': (entity_logits.argmax(-1) == entity_targets).float().mean().item() if entity_logits.numel() else 0.0,
        'expressionAcc': (outputs['expression'].argmax(-1) == data['expression']).float().mean().item(),
        'mentionLoss': mention_loss.item(), 'roleLoss': role_loss.item(),
        'entityLoss': entity_loss.item(), 'expressionLoss': expression_loss.item(),
        'totalLoss': total.item(),
    }
    return total, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples', type=int, default=96)
    parser.add_argument('--steps', type=int, default=8)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--seed', type=int, default=20261110)
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(2)
    started = time.time()
    config = json.loads((BASE / 'config.json').read_text())
    state = torch.load(BASE / 'pytorch_model.bin', map_location='cpu', weights_only=True)
    encoder = FrozenMiniRBT(state, config)
    before = encoder_hash(encoder)
    examples, entity_ids = load_data()
    random.shuffle(examples)
    examples = examples[:args.samples]
    heads = Heads(config['hidden_size'], len(entity_ids))
    before_heads = {k: v.detach().clone() for k, v in heads.state_dict().items()}
    optimizer = torch.optim.AdamW(heads.parameters(), lr=2e-3, weight_decay=0.0)
    history, stats_last = [], None
    for step in range(args.steps):
        indices = list(range(step * args.batch_size, min((step + 1) * args.batch_size, len(examples))))
        if len(indices) < 2:
            indices = list(range(min(args.batch_size, len(examples))))
        data = batch(examples, indices)
        with torch.no_grad():
            hidden = encoder(data['ids'], data['types'], data['mask'])
        outputs = heads(hidden)
        loss, stats = loss_and_stats(outputs, data)
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(heads.parameters(), 1.0)
        optimizer.step()
        stats_last = stats
        history.append({'step': step + 1, **stats})
    after = encoder_hash(encoder)
    changed = {key: float((heads.state_dict()[key] - before_heads[key]).abs().sum())
               for key in before_heads}
    reloaded = Heads(config['hidden_size'], len(entity_ids))
    reloaded.load_state_dict(heads.state_dict())
    data = batch(examples, list(range(min(args.batch_size, len(examples)))))
    with torch.no_grad():
        hidden = encoder(data['ids'], data['types'], data['mask'])
        reload_loss, reload_stats = loss_and_stats(reloaded(hidden), data)
    args.out.mkdir(parents=True, exist_ok=True)
    torch.save({'heads': heads.state_dict(), 'entityIds': entity_ids,
                'roles': ROLES, 'expressions': EXPR, 'base': str(BASE),
                'encoderLayers': [0, 1], 'tokenizer': 'WordPiece+char offsets'},
               args.out / 'heads.pt')
    record = {
        'schema': 'jity-d02-r0-engineering-smoke-v1',
        'status': 'engineering_smoke_only',
        'qualityClaim': False,
        'humanReviewUsed': False,
        'sealedUsed': False,
        'baseModel': str(BASE),
        'encoderLayers': [0, 1],
        'encoderHashBefore': before,
        'encoderHashAfter': after,
        'encoderUnchanged': before == after,
        'trainSamples': len(examples),
        'trainSplitOnly': True,
        'entityClasses': len(entity_ids),
        'steps': args.steps,
        'batchSize': args.batch_size,
        'headsChanged': all(value > 0 for value in changed.values()),
        'headDelta': changed,
        'history': history,
        'lastStats': stats_last,
        'reloadLoss': float(reload_loss),
        'reloadStats': reload_stats,
        'elapsedSeconds': round(time.time() - started, 3),
        'processWallSeconds': round(time.time() - PROCESS_START, 3),
        'artifactSha256': hashlib.sha256((args.out / 'heads.pt').read_bytes()).hexdigest(),
        'notes': [
            'M1 uses token mention BIO, 5-role BCE and entity classification over worldId:entityId; span offsets and expression issue spans are not evaluated.',
            'M2 uses only the 5-way expression label; issue span/scope heads are not implemented in this smoke.',
            'No development or sealed sample was read; no quality or A/B/C claim is possible.',
        ],
    }
    (args.out / 'record.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
