# -*- coding: utf-8 -*-
"""Pilot: tiny encoder-decoder models for structured task conditions and events.

Teacher labels come from the current rule decomposition/action structure; this
is a scale/latency pilot, not a semantic-generalization result. Entity IDs are
copied from the world; outputs are short key=value sequences.
"""
import json
import random
import re
import statistics
import time
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
WORLD = json.loads((ROOT / 'data/worlds/dragon-raja-free-day.world.json').read_text(encoding='utf8'))
OUT = PUB / 'micro-generative'

CONFIRM = ['确认', '报告', '说明', '告知', '问清', '核实', '看见', '检查', '证明', '登记', '回答', '听清', '核对']
ACTION = ['前往', '走向', '走进', '进入', '赶到', '回到', '退到', '离开', '登上', '走到',
          '守住', '护住', '挡住', '拦住', '守', '递给', '交给', '戴上', '戴好', '拿起', '开笼', '放出',
          '发布', '扣好', '恢复', '更换', '换上', '打开', '使用', '到达']
TIME = re.compile(r'\d{1,2}:\d{2}|停赛前|结束前|午夜|天亮|天黑|明天|次日|黄昏|清晨|小时后|分钟后|入夜')

TASKS = []
for owner, character in WORLD['characters'].items():
    for task in (character.get('tasks') or {}).values():
        TASKS.append((task['id'], owner, task['goal']))
ITEMS = {iid: item.get('name', iid) for iid, item in WORLD['initial']['items'].items()}
LOCS = {lid: loc.get('name', lid) for lid, loc in WORLD['initial']['locations'].items()}
CHARS = {cid: c.get('name', cid) for cid, c in WORLD['initial']['characters'].items()}


def core(name):
    return re.sub(r'^.+?的', '', name)


def item_id(goal):
    for iid, name in sorted(ITEMS.items(), key=lambda row: -len(row[1])):
        if name in goal or (core(name) in goal and len(core(name)) >= 3):
            return iid
    return None


def loc_id(goal):
    for lid, name in sorted(LOCS.items(), key=lambda row: -len(row[1])):
        if name in goal:
            return lid
    return None


def char_id(goal):
    for cid, name in CHARS.items():
        if name in goal:
            return cid
    return None


def conditions_for(goal):
    decision = re.search(r'选择[^，。；]*|决定[^，。；]*|选定[^，。；]*|选一条[^，。；]*', goal)
    fields = []
    time = TIME.search(goal)
    if time:
        fields.append(('time', time.group(0)))
    if not decision:
        loc = loc_id(goal)
        if loc:
            fields.append(('loc', loc))
    item = item_id(goal)
    if item:
        fields.append(('item', item))
    target = char_id(goal)
    if target:
        fields.append(('target', target))
    if decision:
        fields.append(('decision', decision.group(0)))
    conf = next((word for word in CONFIRM if word in goal), None)
    if conf:
        fields.append(('conf', conf))
    act = next((word for word in ACTION if word in goal), None)
    if act:
        fields.append(('act', act))
    return 'COND|' + '|'.join(f'{key}={value}' for key, value in fields) if fields else 'COND|none'


def glossary(text):
    found = []
    for cid, character in CHARS.items():
        name = character if isinstance(character, str) else character.get('name', cid)
        if name and name in text:
            found.append((name, cid))
    for iid, name in ITEMS.items():
        if name in text or (core(name) in text and len(core(name)) >= 3):
            found.append((name, iid))
    for lid, name in LOCS.items():
        if name in text:
            found.append((name, lid))
    seen = set()
    pairs = []
    for name, ident in found:
        if ident in seen:
            continue
        seen.add(ident)
        pairs.append(f'{name}={ident}')
    return '，'.join(pairs[:10])


def variants(text, count=5):
    base = ['目标：' + text, '请完成：' + text, text + '（这是本回合要做的事）', '需要做到：' + text]
    base = base[:count]
    return base


def condition_rows():
    rows = []
    for task_id, owner, goal in TASKS:
        target = conditions_for(goal)
        entity = glossary(goal)
        suffix = f'；实体={entity}' if entity else ''
        prefix = 'COND|'
        for variant in variants(goal, 5):
            rows.append({'task': 'conditions', 'key': task_id, 'input': f'任务|角色={owner}；目标={variant}{suffix}',
                         'output': target, 'prefix': prefix, 'continuation': target[len('COND|'):]})
    return rows


EVENTS = [
    ('lu', '我向诺诺问清当前红蓝局势。', 'partial', 'nono', '', '', 'red_position', '', '', '', ''),
    ('lu', '我把护目镜戴好，检查镜片。', 'completed', '', 'goggles_lu', 'lu', '', '', '', '', ''),
    ('lu', '我把弹匣乙从弹药箱塞进背心胸袋。', 'completed', '', 'spare_mag2', 'jacket_lu/slot_chest', '', '', '', '', ''),
    ('lu', '我走进庭院，躲到花槽后。', 'completed', '', '', 'yard', '', '', '', '', ''),
    ('lu', '我抓住检修盖拉环提开盖子。', 'completed', '', 'hatch_cover', '', '', 'hatch_open', '', '', ''),
    ('lu', '我把门厅长桌拖到侧墙让出楼梯口。', 'completed', '', 'foyer_table', '', '', 'stairs_clear', '', '', ''),
    ('lu', '我决定走地下检修通道。', 'completed', '', '', '', '', '', '', 'route_hatch', ''),
    ('nono', '诺诺没有回答路明非。', 'partial', 'lu', '', '', '', '', '', '', 'unanswered'),
    ('nono', '诺诺回答路明非，红方控制钟楼。', 'completed', 'lu', '', '', 'red_holds_bell', '', '', '', ''),
    ('tang', '唐骁拦住靠近的敌人。', 'completed', '', '', '', '', '', '', '', ''),
    ('chu', '楚子航守住顶层。', 'completed', '', '', 'top', '', '', '', '', ''),
    ('su', '苏茜报告三人蓝方和松动护栏。', 'completed', 'chu', '', '', 'three_blue_loose_rail', '', '', '', ''),
    ('zhou', '周映确认安全绳固定。', 'completed', '', 'safety_rope', '', '', '', '', '', ''),
    ('fingel', '芬格尔准备拍摄争旗场面。', 'partial', '', 'camera', '', '', '', '', '', ''),
    ('doctor', '顾岚检查手套是否需要更换。', 'partial', '', 'gloves', '', '', '', '', '', ''),
    ('lin', '林亦舟说明是实际扭伤。', 'partial', '', '', '', '', '', '', '', 'real_injury'),
    ('manstein', '曼施坦因核对旗台状态。', 'partial', '', '', '', '', '', '', '', ''),
    ('qin', '秦越向芬格尔求助。', 'completed', 'fingel', '', '', '', '', '', '', ''),
]


def event_output(actor, result, target, item, dest, info, env, promise, decision, cause):
    fields = [('actor', actor), ('result', result)]
    for key, value in (('target', target), ('item', item), ('dest', dest), ('info', info), ('env', env),
                       ('promise', promise), ('decision', decision), ('cause', cause)):
        if value:
            fields.append((key, value))
    return 'EV|' + '|'.join(f'{key}={value}' for key, value in fields)


def event_rows():
    rows = []
    for actor, text, result, target, item, dest, info, env, promise, decision, cause in EVENTS:
        output = event_output(actor, result, target, item, dest, info, env, promise, decision, cause)
        entity = glossary(text)
        suffix = f'；实体={entity}' if entity else ''
        prefix = f'EV|actor={actor}|'
        for variant in variants(text, 5):
            rows.append({'task': 'events', 'key': actor, 'input': f'事件|角色={actor}；行动={variant}{suffix}',
                         'output': output, 'prefix': prefix, 'continuation': output[len(prefix):]})
    # Hard negatives: same keyword, different result.
    for result, ending in (('blocked', '，但被拦住了。'), ('failed', '，但没有成功。')):
        for actor, text, *_ in EVENTS[:8]:
            entity = glossary(text)
            suffix = f'；实体={entity}' if entity else ''
            output = event_output(actor, result, '', '', '', '', '', '', '', '')
            prefix = f'EV|actor={actor}|'
            rows.append({'task': 'events', 'key': actor, 'input': f'事件|角色={actor}；行动={text}{ending}{suffix}',
                         'output': output, 'prefix': prefix, 'continuation': output[len(prefix):]})
    return rows


TOKEN = re.compile(r'\d{1,2}:\d{2}|[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]|[=|/；;，。]')


class Vocab:
    def __init__(self, texts):
        counts = Counter(token for text in texts for token in TOKEN.findall(text))
        self.itos = ['<pad>', '<bos>', '<eos>', '<unk>'] + [token for token, _ in counts.most_common()]
        self.stoi = {token: index for index, token in enumerate(self.itos)}
        self.pad, self.bos, self.eos, self.unk = 0, 1, 2, 3

    def encode(self, text, max_len):
        ids = [self.stoi.get(token, self.unk) for token in TOKEN.findall(text)][:max_len - 2]
        return [self.bos] + ids + [self.eos]


class Seq2Seq(nn.Module):
    def __init__(self, vocab, d_model, layers, heads, max_len=160):
        super().__init__()
        self.d_model = d_model
        self.src_emb = nn.Embedding(vocab, d_model, padding_idx=0)
        self.tgt_emb = nn.Embedding(vocab, d_model, padding_idx=0)
        self.pos = nn.Embedding(max_len, d_model)
        self.encoder = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d_model, heads, 4 * d_model, batch_first=True, norm_first=True), layers)
        self.decoder = nn.TransformerDecoder(
            nn.TransformerDecoderLayer(d_model, heads, 4 * d_model, batch_first=True, norm_first=True), layers)
        self.out = nn.Linear(d_model, vocab)

    def forward(self, src, tgt):
        b, s = src.shape
        t = tgt.shape[1]
        src_pos = self.pos(torch.arange(s, device=src.device))[None]
        tgt_pos = self.pos(torch.arange(t, device=tgt.device))[None]
        memory = self.encoder(self.src_emb(src) + src_pos, src_key_padding_mask=src.eq(0))
        mask = nn.Transformer.generate_square_subsequent_mask(t, device=src.device)
        out = self.decoder(self.tgt_emb(tgt) + tgt_pos, memory, tgt_mask=mask,
                           tgt_key_padding_mask=tgt.eq(0), memory_key_padding_mask=src.eq(0))
        return self.out(out)


class SharedTwoDecoder(nn.Module):
    def __init__(self, vocab, d_model, layers, heads, max_len=160):
        super().__init__()
        self.src_emb = nn.Embedding(vocab, d_model, padding_idx=0)
        self.tgt_emb = nn.Embedding(vocab, d_model, padding_idx=0)
        self.pos = nn.Embedding(max_len, d_model)
        self.encoder = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d_model, heads, 4 * d_model, batch_first=True, norm_first=True), layers)
        self.decoders = nn.ModuleDict({
            task: nn.TransformerDecoder(
                nn.TransformerDecoderLayer(d_model, heads, 4 * d_model, batch_first=True, norm_first=True), layers)
            for task in ('conditions', 'events')})
        self.out = nn.Linear(d_model, vocab)

    def forward(self, src, tgt, task):
        s = src.shape[1]
        t = tgt.shape[1]
        src_pos = self.pos(torch.arange(s, device=src.device))[None]
        tgt_pos = self.pos(torch.arange(t, device=tgt.device))[None]
        memory = self.encoder(self.src_emb(src) + src_pos, src_key_padding_mask=src.eq(0))
        mask = nn.Transformer.generate_square_subsequent_mask(t, device=src.device)
        out = self.decoders[task](self.tgt_emb(tgt) + tgt_pos, memory, tgt_mask=mask,
                                  tgt_key_padding_mask=tgt.eq(0), memory_key_padding_mask=src.eq(0))
        return self.out(out)


def pad_batch(rows, vocab, max_len):
    width = max(len(row) for row in rows)
    ids = torch.full((len(rows), width), vocab.pad, dtype=torch.long)
    for index, row in enumerate(rows):
        ids[index, :len(row)] = torch.tensor(row)
    return ids


def constraints_for(row):
    text = row['input']
    role = re.search(r'角色=([a-z_][a-z0-9_]*)', text)
    actor = re.search(r'actor=([a-z_][a-z0-9_]*)', row.get('prefix', ''))
    speaker = actor.group(1) if actor else (role.group(1) if role else '')
    entity = text.split('实体=', 1)[1] if '实体=' in text else ''
    ids = re.findall(r'=([a-z_][a-z0-9_]*)', entity)
    chars = {ident for ident in ids if ident in CHARS}
    items = {ident for ident in ids if ident in ITEMS}
    locs = {ident for ident in ids if ident in LOCS}
    return {'target': chars - {speaker}, 'item': items, 'loc': locs, 'dest': set(ids)}


def decode(model, vocab, text, device, max_len=32, prefix='', constraints=None, task='conditions'):
    model.eval()
    decoder = model.decoders[task] if hasattr(model, 'decoders') else model.decoder
    seed = vocab.encode(prefix, 96)[1:-1] if prefix else []
    with torch.no_grad():
        src = torch.tensor([vocab.encode(text, 96)], device=device)
        s = src.shape[1]
        src_pos = model.pos(torch.arange(s, device=device))[None]
        memory = model.encoder(model.src_emb(src) + src_pos)
        out = [vocab.bos] + seed
        start = 1 + len(seed)
        for _ in range(max_len):
            tgt = torch.tensor([out], device=device)
            tgt_pos = model.pos(torch.arange(tgt.shape[1], device=device))[None]
            mask = nn.Transformer.generate_square_subsequent_mask(tgt.shape[1], device=device)
            logits = model.out(decoder(model.tgt_emb(tgt) + tgt_pos, memory, tgt_mask=mask))
            generated = ''.join(vocab.itos[index] for index in out[start:])
            for field, allowed in (constraints or {}).items():
                if not generated.endswith(field + '='):
                    continue
                candidates = [vocab.stoi[ident] for ident in allowed if ident in vocab.stoi]
                if candidates:
                    masked = torch.full_like(logits[0, -1], -1e9)
                    masked[candidates] = logits[0, -1, candidates]
                    logits[0, -1] = masked
                break
            best = int(logits[0, -1].argmax())
            out.append(best)
            if best == vocab.eos:
                break
    return ' '.join(vocab.itos[index] for index in out[start:] if index not in (vocab.pad, vocab.bos, vocab.eos))


def normalize(text):
    return re.sub(r'\s+', '', text)


def fields(text):
    return set(part for part in normalize(text).split('|') if part)


def train_arm(rows, size, name, device, vocab, epochs=40):
    config = {'5M': (224, 3, 7), '15M': (352, 4, 8), '30M': (480, 5, 8)}[size]
    model = Seq2Seq(len(vocab.itos), *config).to(device)
    params = sum(p.numel() for p in model.parameters())
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
    random.shuffle(rows)
    for epoch in range(epochs):
        model.train()
        for start in range(0, len(rows), 24):
            batch = rows[start:start + 24]
            src = pad_batch([vocab.encode(row['input'], 96) for row in batch], vocab, 96).to(device)
            tgt = pad_batch([vocab.encode(row['prefix'] + row['continuation'], 96) for row in batch], vocab, 96).to(device)
            opt.zero_grad()
            logits = model(src, tgt[:, :-1])
            labels = tgt[:, 1:]
            token_loss = F.cross_entropy(logits.reshape(-1, len(vocab.itos)), labels.reshape(-1),
                                         ignore_index=vocab.pad, reduction='none').reshape(labels.shape)
            mask = torch.ones_like(labels, dtype=torch.float)
            for index, row in enumerate(batch):
                mask[index, :max(0, len(vocab.encode(row['prefix'], 96)) - 2)] = 0
            loss = (token_loss * mask).sum() / mask.sum().clamp(min=1)
            loss.backward()
            opt.step()
    return model, vocab, params


def train_shared_two(rows, device, vocab, epochs=40):
    model = SharedTwoDecoder(len(vocab.itos), 352, 4, 8).to(device)
    params = sum(p.numel() for p in model.parameters())
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
    random.shuffle(rows)
    for _ in range(epochs):
        model.train()
        for start in range(0, len(rows), 24):
            batch = rows[start:start + 24]
            opt.zero_grad()
            for task in ('conditions', 'events'):
                subset = [row for row in batch if row['task'] == task]
                if not subset:
                    continue
                src = pad_batch([vocab.encode(row['input'], 96) for row in subset], vocab, 96).to(device)
                tgt = pad_batch([vocab.encode(row['prefix'] + row['continuation'], 96) for row in subset],
                                vocab, 96).to(device)
                logits = model(src, tgt[:, :-1], task)
                labels = tgt[:, 1:]
                token_loss = F.cross_entropy(logits.reshape(-1, len(vocab.itos)), labels.reshape(-1),
                                             ignore_index=vocab.pad, reduction='none').reshape(labels.shape)
                mask = torch.ones_like(labels, dtype=torch.float)
                for index, row in enumerate(subset):
                    mask[index, :max(0, len(vocab.encode(row['prefix'], 96)) - 2)] = 0
                loss = (token_loss * mask).sum() / mask.sum().clamp(min=1)
                loss.backward()
            opt.step()
    return model, params


def evaluate(model, vocab, rows, device):
    exact = 0
    field_hits = field_total = 0
    field_counts = Counter()
    field_correct = Counter()
    times = []
    encode_times = []
    token_counts = []
    if not rows:
        return {'exact': None, 'fieldRecall': None, 'p50Ms': None, 'p95Ms': None,
                'encodeMs': None, 'perTokenMs': None, 'tokens': None, 'perField': {}}
    for row in rows:
        model.eval()
        with torch.no_grad():
            src = torch.tensor([vocab.encode(row['input'], 96)], device=device)
            src_pos = model.pos(torch.arange(src.shape[1], device=device))[None]
            began_encode = time.perf_counter()
            model.encoder(model.src_emb(src) + src_pos)
            encode_times.append((time.perf_counter() - began_encode) * 1000)
        began = time.perf_counter()
        got = normalize(decode(model, vocab, row['input'], device, prefix=row.get('prefix', ''),
                                 constraints=constraints_for(row), task=row['task']))
        times.append((time.perf_counter() - began) * 1000)
        token_counts.append(len(TOKEN.findall(got)))
        want = normalize(row.get('continuation', row['output']))
        exact += got == want
        got_fields, want_fields = fields(got), fields(want)
        field_hits += len(got_fields & want_fields)
        field_total += len(want_fields)
        got_map = dict(part.split('=', 1) for part in got_fields if '=' in part)
        want_map = dict(part.split('=', 1) for part in want_fields if '=' in part)
        for key in set(got_map) | set(want_map):
            field_counts[key] += 1
            if got_map.get(key) == want_map.get(key):
                field_correct[key] += 1
    times.sort()
    encode_mean = statistics.mean(encode_times)
    full_mean = statistics.mean(times)
    token_mean = statistics.mean(token_counts)
    return {
        'exact': round(exact / len(rows), 3),
        'fieldRecall': round(field_hits / max(1, field_total), 3),
        'p50Ms': round(statistics.median(times), 1),
        'p95Ms': round(times[min(len(times) - 1, int(len(times) * 0.95))], 1),
        'encodeMs': round(encode_mean, 1),
        'perTokenMs': round(max(0.0, full_mean - encode_mean) / max(1, token_mean), 2),
        'tokens': round(token_mean, 1),
        'perField': {key: round(field_correct[key] / field_counts[key], 3) for key in sorted(field_counts)},
    }


def main():
    random.seed(20261126)
    torch.manual_seed(20261126)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    OUT.mkdir(parents=True, exist_ok=True)
    rows = condition_rows() + event_rows()
    task_keys = sorted({row['key'] for row in rows if row['task'] == 'conditions'})
    held_tasks = set(task_keys[::5])
    actor_keys = sorted({row['key'] for row in rows if row['task'] == 'events'})
    held_actors = set(actor_keys[::5])

    def is_test(row):
        return ((row['task'] == 'conditions' and row['key'] in held_tasks)
                or (row['task'] == 'events' and row['key'] in held_actors))

    train = [row for row in rows if not is_test(row)]
    test = [row for row in rows if is_test(row)]
    vocab = Vocab([row['input'] + row['output'] for row in rows])
    (OUT / 'rows.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf8')
    report = {'rows': len(rows), 'train': len(train), 'test': len(test), 'vocab': len(vocab.itos),
              'heldTasks': sorted(held_tasks), 'heldActors': sorted(held_actors), 'arms': {}}
    models = {}
    for size in ('5M', '15M', '30M'):
        began = time.perf_counter()
        model, vocab, params = train_arm(train, size, f'multi_{size}', device, vocab)
        metrics = evaluate(model, vocab, test, device)
        metrics['condFieldRecall'] = evaluate(model, vocab, [row for row in test if row['task'] == 'conditions'], device)['fieldRecall']
        metrics['eventFieldRecall'] = evaluate(model, vocab, [row for row in test if row['task'] == 'events'], device)['fieldRecall']
        metrics['trainFieldRecall'] = evaluate(model, vocab, train[:80], device)['fieldRecall']
        metrics.update({'params': params, 'sizeMB': round(sum(p.numel() * 4 for p in model.parameters()) / 1e6, 1),
                        'trainMs': round((time.perf_counter() - began) * 1000)})
        report['arms'][f'multi_{size}'] = metrics
        models[size] = model
        print(size, json.dumps(metrics, ensure_ascii=False))
    # Independent dedicated pair at each scale: one model per task.
    for size in ('5M', '15M', '30M'):
        for task in ('conditions', 'events'):
            subset = [row for row in train if row['task'] == task]
            test_subset = [row for row in test if row['task'] == task]
            model, vocab, params = train_arm(subset, size, f'indep_{size}_{task}', device, vocab)
            metrics = evaluate(model, vocab, test_subset, device)
            metrics['trainFieldRecall'] = evaluate(model, vocab, subset[:80], device)['fieldRecall']
            metrics.update({'params': params, 'sizeMB': round(sum(p.numel() * 4 for p in model.parameters()) / 1e6, 1)})
            report['arms'][f'indep{size}_{task}'] = metrics
            print('indep', size, task, json.dumps(metrics, ensure_ascii=False))
    # Shared encoder + two task decoders at the 15M width.
    test_conditions = [row for row in test if row['task'] == 'conditions']
    test_events = [row for row in test if row['task'] == 'events']
    shared_model, shared_params = train_shared_two(train, device, vocab)
    shared_metrics = evaluate(shared_model, vocab, test, device)
    shared_metrics.update({
        'params': shared_params,
        'sizeMB': round(sum(p.numel() * 4 for p in shared_model.parameters()) / 1e6, 1),
        'condFieldRecall': evaluate(shared_model, vocab, test_conditions, device)['fieldRecall'],
        'eventFieldRecall': evaluate(shared_model, vocab, test_events, device)['fieldRecall'],
    })
    report['arms']['shared2_15M'] = shared_metrics
    print('shared2', json.dumps(shared_metrics, ensure_ascii=False))
    # ONNX export, dynamic int8 size, and CPU latency per scale.
    report['onnx'] = {}
    for size, model in models.items():
        cpu_metrics = evaluate(model.to('cpu'), vocab, test[:12], torch.device('cpu'))
        report['arms'][f'multi_{size}']['cpuP50Ms'] = cpu_metrics['p50Ms']
        report['arms'][f'multi_{size}']['cpuP95Ms'] = cpu_metrics['p95Ms']
        try:
            import onnxruntime.quantization as quant
            src = torch.tensor([vocab.encode(test[0]['input'], 96)])
            tgt = torch.tensor([vocab.encode(test[0]['prefix'] + test[0]['continuation'], 96)[:-1]])
            path = OUT / f'multi_{size}.onnx'
            torch.onnx.export(model, (src, tgt), path, opset_version=17, input_names=['src', 'tgt'],
                              output_names=['logits'], dynamic_axes={'src': {0: 'batch', 1: 'src_len'},
                                                                    'tgt': {0: 'batch', 1: 'tgt_len'}})
            qpath = OUT / f'multi_{size}-int8.onnx'
            quant.quantize_dynamic(path.as_posix(), qpath.as_posix(), weight_type=quant.QuantType.QInt8)
            report['onnx'][size] = {'fp32MB': round(path.stat().st_size / 1e6, 2),
                                    'int8MB': round(qpath.stat().st_size / 1e6, 2)}
        except Exception as error:
            report['onnx'][size] = {'error': f'{type(error).__name__}: {error}'}
    (OUT / 'pilot-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
