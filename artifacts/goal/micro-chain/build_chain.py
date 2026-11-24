# -*- coding: utf-8 -*-
"""Tokenize the 12 chain turns for the in-browser pipeline."""
import json
import sys
from pathlib import Path

from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
PROBE = ROOT / '.local/probe-transformers/models'
MAXLEN = 128
NAMES = {'lu': '路明非', 'nono': '诺诺', 'fingel': '芬格尔', 'lin': '林亦舟', 'qin': '秦越'}
sys.path.insert(0, str(ROOT / 'artifacts/goal/micro-facts'))
from rules import settle  # noqa: E402


def main():
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))

    def enc(text, pair=None):
        out = tok(text, pair, truncation=True, max_length=MAXLEN) if pair else tok(text, truncation=True, max_length=MAXLEN)
        return out['input_ids']

    turns = json.loads((Path('D:/others/Jity/artifacts/goal/micro-chain/turns.json')).read_text(encoding='utf8'))
    out = []
    for t in turns:
        npc = t['npc']
        intent_ids = enc(f"角色：{npc['role']}\n任务：{npc['task']}\n现场：{npc['scene']}")
        action_text = f"行动：{t['action']}\n在场：{'、'.join(t['present'])}"
        target_pairs = [{'candidate': n, 'ids': enc(action_text, n)} for n in t['present']]
        pos_text = f"事实：{t['position_fact']}\n当前：{t['current']}"
        pos_pairs = [{'candidate': c, 'ids': enc(pos_text, c)} for c in t['candidates']]
        variants = {}
        subsets = [[]] + [[n] for n in t['present']]
        if len(t['present']) > 1:
            subsets.append(list(t['present']))
        for sub in subsets:
            key = '、'.join(sub) if sub else '无'
            variants[key] = enc(f"行动：{t['action']}\n目标：{key}\n骰点：{t['dice']}")
        facts = settle(t['action'], t['dice'], t['present'], t['current'], t['candidates'])
        out.append({'id': t['id'], 'intent_ids': intent_ids, 'target_pairs': target_pairs,
                    'pos_pairs': pos_pairs, 'rules_position': facts['destination'],
                    'judgment_variants': variants,
                    'expect': {'intent': npc['intent'],
                               'targets': [NAMES[c] for c in t['expect']['targets']],
                               'position': t['expect']['position'],
                               'judgment': t['expect']['judgment']}})
    (PROBE / 'chain-data.json').write_text(json.dumps(out, ensure_ascii=False), encoding='utf8')
    print('turns', len(out))


if __name__ == '__main__':
    main()
