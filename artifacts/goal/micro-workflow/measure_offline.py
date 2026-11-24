# -*- coding: utf-8 -*-
"""Offline run of the movement-head position port over every recorded merged
scene answer. The input strings and decision rules mirror
`frontend/src/lib/world-engine/local/micro/updates.ts` and the runner's
missing-move guard; the model is the same int8 ONNX the browser loads.

Outputs: per-call accept/abstain, move/stay agreement with the recorded LLM
answer, and the LLM calls the new workflow would have avoided.
"""
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODEL = ROOT / '.local/micro-heads/movement-head-int8.onnx'
ENTITY = re.compile(r'^- ([^=\n]+)=([^@\n]+)@([^/\n]+)(?:/([^\n]+))?', re.M)
FACT = re.compile(r'^f\d+ \[([^\]]+)\] (.+)$', re.M)
MOVE_WORDS = ['走进', '走入', '走到', '走向', '进入', '来到', '回到', '退回', '退到', '跑到', '冲向', '赶到', '爬上', '走下', '钻出', '穿过']


def slots_of(container):
    return {slot.get('id') for slot in (container or {}).get('slots') or [] if slot.get('id')}


def destination_of_fact(locations, text):
    if not any(word in text for word in MOVE_WORDS):
        return None
    best = None
    for location_id, location in locations.items():
        name = location.get('name') or ''
        if len(name) < 2:
            continue
        at = text.rfind(name)
        if at < 0:
            continue
        if best is None or at > best[2]:
            best = (location_id, name, at)
    return best


def missing_moves(prompt, names, entities, micro_pos):
    current = {entity_id: cid for _name, entity_id, cid, _sid in entities}
    missing = []
    for key, text in FACT.findall(prompt):
        member = key.split(' ')[0]
        dest = destination_of_fact(locations, text)
        if not dest:
            continue
        name = names.get(member, '')
        at = text.find(name) if name else -1
        if at < 0 or at > dest[2]:
            continue
        if current.get(member) == dest[0]:
            continue
        if micro_pos.get(member) == dest[0]:
            continue
        missing.append(member)
    return missing


def main():
    global locations
    world = json.loads(WORLD.read_text(encoding='utf8'))['initial']
    locations = world.get('locations', {})
    containers = {loc['id']: slots_of(loc) for loc in locations.values()}
    for item in world.get('items', {}).values():
        if item.get('slots'):
            containers[item['id']] = slots_of(item)
    names = {key: entity.get('name', key) for group in ('characters', 'items') for key, entity in world.get(group, {}).items()}
    rows = [json.loads(line) for line in open(PUB / 'records.jsonl', encoding='utf8')]
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    session = ort.InferenceSession(str(MODEL), providers=['CPUExecutionProvider'])

    def score(text):
        enc = tok(text, truncation=True, max_length=64)
        ids = np.array([enc['input_ids']], dtype=np.int64)
        mask = np.array([enc['attention_mask']], dtype=np.int64)
        logits = session.run(None, {'input_ids': ids, 'attention_mask': mask})[0][0]
        exps = np.exp(logits - logits.max())
        return float(exps[1] / exps.sum())

    points = dropped = accepted = 0
    abstain_reason = Counter()
    agree = Counter()
    for row in rows:
        if row['task'] != 'updates':
            continue
        prompt = row['prompt']
        if '顺带结算外貌' not in prompt:
            continue
        try:
            raw = json.loads(row['raw'])
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict) or 'positions' not in raw:
            continue
        points += 1
        invalid_rows = 0
        llm_pos = {}
        for pos in raw.get('positions') or []:
            cid, sid = pos.get('containerId'), pos.get('slotId')
            if cid not in containers or (sid is not None and sid not in containers[cid]):
                invalid_rows += 1
                continue
            llm_pos[pos.get('entityId')] = cid
        dropped += invalid_rows
        entities = ENTITY.findall(prompt)
        facts = FACT.findall(prompt)[:3]
        fact_text = ' | '.join(f'{key}: {text[:50]}' for key, text in facts)[:160]
        moved = []
        for name, entity_id, cid, sid in entities:
            if score(f'实体：{name}；当前：{cid}/{sid or "-"}；本组结果：{fact_text}') >= 0.5:
                moved.append((entity_id, name))
        micro_pos = {}
        reason = None
        for entity_id, name in moved:
            own = next((text for key, text in FACT.findall(prompt) if key.split(' ')[0] == entity_id), None)
            dest = destination_of_fact(locations, own) if own else None
            named = dest is not None and name and own.find(name) >= 0 and own.find(name) <= dest[2]
            if not dest or not named:
                reason = f'no_destination:{entity_id}'
                break
            micro_pos[entity_id] = dest[0]
        if reason:
            abstain_reason[reason.split(':')[0]] += 1
            continue
        missing = missing_moves(prompt, names, entities, micro_pos)
        if missing:
            abstain_reason['missing_move'] += 1
            continue
        accepted += 1
        for _name, entity_id, _cid, _sid in entities:
            pred = 'move' if entity_id in micro_pos else 'stay'
            truth = 'move' if entity_id in llm_pos else 'stay'
            agree[f'pred_{pred}_llm_{truth}'] += 1
            if pred == 'move' and truth == 'move' and micro_pos[entity_id] != llm_pos[entity_id]:
                agree['container_mismatch'] += 1

    result = {
        'merged_scene_calls': points,
        'invalid_llm_rows': dropped,
        'micro_accepted': accepted,
        'micro_abstained': dict(abstain_reason),
        'llm_scene_calls_saved': accepted,
        'appearance_calls_saved_by_reuse': points,
        'agreement': dict(agree),
        'model': 'movement-head-int8.onnx',
    }
    (PUB / 'offline-port-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
