# -*- coding: utf-8 -*-
"""Build candidate-scoring pairs with leave-name-out splits."""
import json
import random
from pathlib import Path

ROOT = Path('D:/others/Jity')
LABELS = ROOT / 'artifacts/goal/micro-redesign'
OUT = ROOT / '.local/micro-generalize'
NAMES = {'lu': '路明非', 'nono': '诺诺', 'fingel': '芬格尔', 'lin': '林亦舟', 'qin': '秦越'}
HELD_PLACES = {'医护附楼', '跨溪小桥'}
HELD_CHARS = {'qin', 'lin'}
PLACES = ['西侧服务巷', '器材棚', '西回廊', '钟楼', '钟楼门厅', '二层平台', '顶层旗台',
          '庭院', '地下通道', '医护附楼', '跨溪小桥']
SEEN_START = 240


def load_rows():
    rows = []
    for n in range(1, 6):
        rows += [json.loads(line) for line in open(LABELS / f'labels-v{n}.jsonl', encoding='utf8')]
    return rows


def parse_position(text):
    fact = text.split('事实：', 1)[1].split('\n当前：', 1)[0]
    current = text.split('\n当前：', 1)[1].split('\n候选：', 1)[0]
    cands = text.split('\n候选：', 1)[1].split('、')
    return fact, current, cands


def parse_targets(text):
    action = text.split('行动：', 1)[1].split('\n在场：', 1)[0]
    present = text.split('\n在场：', 1)[1].split('、')
    return action, present


def main():
    random.seed(20261124)
    OUT.mkdir(parents=True, exist_ok=True)
    pairs = []
    for idx, row in enumerate(load_rows()):
        if row['task'] == 'position':
            fact, current, cands = parse_position(row['input'])
            if row['label'] in HELD_PLACES:
                split = 'held'
            elif any(name in row['input'] for name in HELD_PLACES):
                split = 'drop'
            else:
                split = 'seen' if idx >= SEEN_START else 'train'
            text = f'事实：{fact}\n当前：{current}'
            for cand in cands:
                pairs.append({'task': 'position', 'row': idx, 'text': text, 'candidate': cand,
                              'label': 1 if cand == row['label'] else 0, 'split': split,
                              'row_label': row['label'], 'candidates': cands})
            if split == 'train':
                extra = [p for p in PLACES if p not in cands and p not in HELD_PLACES]
                for cand in random.sample(extra, min(2, len(extra))):
                    pairs.append({'task': 'position', 'row': idx, 'text': text, 'candidate': cand,
                                  'label': 0, 'split': 'train', 'row_label': row['label'],
                                  'candidates': cands})
        elif row['task'] == 'targets':
            action, present = parse_targets(row['input'])
            labels = set(row['label'])
            if labels & HELD_CHARS:
                split = 'held'
            elif any(NAMES[c] in row['input'] for c in HELD_CHARS):
                split = 'drop'
            else:
                split = 'seen' if idx >= SEEN_START else 'train'
            for name in present:
                cid = next((k for k, v in NAMES.items() if v == name), None)
                if cid is None:
                    continue
                pairs.append({'task': 'targets', 'row': idx, 'text': row['input'],
                              'candidate': name, 'label': 1 if cid in labels else 0,
                              'split': split, 'row_label': sorted(labels),
                              'candidates': present})
            if split == 'train':
                extra = [NAMES[c] for c in NAMES if NAMES[c] not in present and c not in HELD_CHARS]
                for name in random.sample(extra, min(2, len(extra))):
                    pairs.append({'task': 'targets', 'row': idx, 'text': row['input'],
                                  'candidate': name, 'label': 0, 'split': 'train',
                                  'row_label': sorted(labels), 'candidates': present})
    (OUT / 'pairs.json').write_text(json.dumps(pairs, ensure_ascii=False), encoding='utf8')
    counts = {}
    for p in pairs:
        key = f"{p['task']}/{p['split']}"
        counts[key] = counts.get(key, 0) + 1
    print('pairs', counts)


if __name__ == '__main__':
    main()
