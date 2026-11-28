# -*- coding: utf-8 -*-
"""Planning examples v2: deduplicated clauses, type labels, paraphrase-aware
expression. v1 double-counted the player action (request line + settlement
echo) and missed paraphrased clauses."""
import json
import re
from collections import Counter
from pathlib import Path

import jieba

ROOT = Path('D:/others/Jity')
SRC = ROOT / '.local/narr-train/sft-v13.jsonl'
OUT = Path(__file__).resolve().parent / 'planning-examples-v2.jsonl'
STOP = set('的 了 着 过 地 得 是 在 把 被 将 让 给 向 从 对 与 和 及 而 却 便 就 都 也 还 很 更 最 又 再 才 只 分 他 她 它 他们 她们 它们 自己 对方 这 那 其 我 你 我们 你们 一个 一 二 三 两 之 于 为 以 所 但 然 后 里 上 下 中 前 后 边 面 头'.split())
PUNCT = re.compile(r'^[，。！？；：、"' + "'" + r'（）\n…—\s]+$')
TIME = re.compile(r'时间到了|过去\d|过去[一二三四五六七八九十]')


def facts_of(prompt: str) -> str:
    marker = prompt.find('事实：')
    return prompt[marker + 3:] if marker >= 0 else prompt


def content_words(text: str):
    return [w for w in jieba.lcut(text) if not PUNCT.match(w) and w not in STOP]


def clause_type(clause: str) -> str:
    if TIME.search(clause):
        return 'time'
    if clause.startswith('玩家这回合'):
        return 'player_action'
    if re.match(r'^[\u4e00-\u9fa5]{1,4}：', clause):
        return 'actor_result'
    if clause.startswith('路明非现在') or '现在在' in clause:
        return 'location_state'
    if clause.startswith('屋里有') or '挂着' in clause or '贴着' in clause or '敞着' in clause:
        return 'appearance'
    return 'scene'


def main():
    rows = [json.loads(line) for line in SRC.read_text(encoding='utf8').splitlines() if line.strip()]
    rows.sort(key=lambda row: str(row['id']))
    examples = []
    stats = Counter()
    type_stats = Counter()
    for row in rows:
        target = row['target']
        raw = re.split(r'[。；]', facts_of(row['prompt']))
        clauses = []
        seen = []
        for part in raw:
            clause = part.strip()
            if len(clause) < 4:
                continue
            body = re.sub(r'^玩家这回合.*?做的事：', '', clause)
            body = re.sub(r'^这一回合的结算结果：', '', body)
            body = re.sub(r'^[一-龥]{1,4}[：:]', '', body)
            key = re.sub(r'[^一-龥A-Za-z0-9]', '', body)[:16]
            if any(key and key in prior for prior in seen):
                continue
            seen.append(key)
            clauses.append(clause)
        expressed = []
        for index, clause in enumerate(clauses):
            stats['clauses'] += 1
            kind = clause_type(clause)
            type_stats[kind] += 1
            words = [w for w in content_words(clause) if len(w) >= 2]
            hit = any(target.find(word) >= 0 for word in words)
            if not hit:
                chars = [c for c in clause if '\u4e00' <= c <= '\u9fff']
                hit = bool(chars) and sum(1 for c in chars if c in target) / len(chars) >= 0.5
            if hit:
                expressed.append(index)
                stats['expressed'] += 1
                type_stats[kind + ':used'] += 1
        examples.append({
            'id': str(row['id']),
            'types': [clause_type(c) for c in clauses],
            'clauses': clauses,
            'selected': expressed,
            'selectionRate': round(len(expressed) / max(1, len(clauses)), 3),
            'targetChars': len(target),
        })
    OUT.write_text(''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in examples), encoding='utf8')
    summary = {
        'passages': len(examples),
        'clauseCount': stats['clauses'],
        'expressed': stats['expressed'],
        'selectionRate': round(stats['expressed'] / max(1, stats['clauses']), 3),
        'typeSelection': {kind: round(type_stats[kind + ':used'] / max(1, type_stats[kind]), 3)
                          for kind in ('player_action', 'actor_result', 'location_state', 'appearance', 'scene', 'time')},
        'typeCounts': {kind: type_stats[kind] for kind in ('player_action', 'actor_result', 'location_state', 'appearance', 'scene', 'time')},
    }
    (Path(__file__).resolve().parent / 'planning-summary-v2.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
