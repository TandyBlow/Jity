# -*- coding: utf-8 -*-
"""Offline LLM arm for the same blind rows the heads see.

One Qwen3-0.6B call per candidate, same context format as the browser port.
The arm is a comparison, not a quality authority: the prompt is a compact
single-candidate judgement, not the product's full continuation prompt.
"""
import json
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODEL = ROOT / 'frontend/public/micro/continuation-heads-int8.onnx'
CLI = ROOT / '.local/llama-cpp/llama-cli.exe'
GGUF = ROOT / 'frontend/public/models/Qwen3-0.6B-Q4_K_M.gguf'
KEYS = ('novelty', 'unfinished', 'necessity', 'intervene')
THRESHOLDS = {'novelty': 0.5, 'unfinished': 0.4, 'necessity': 0.5, 'intervene': 0.5}
ANSI = re.compile(r'\x1b\[[0-9;]*m')


def prompt(row):
    return '\n'.join([
        '你是中文跑团游戏的自动推进判断器。只输出 JSON，不要解释。',
        '给定一条候选行动，判断 likely（在这条世界线中是否大概率真的发生）和 related（是否与主角当前处境或目标直接相关）。只有两者都为 true 才允许自动推进。',
        f"情境：{row['context']}",
        f"候选：{row['candidate']}",
        '输出 {"likely":true或false,"related":true或false,"reason":"一句话"}。/no_think',
    ])


def run_llm(row):
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf8') as handle:
        handle.write(prompt(row))
        path = handle.name
    try:
        result = subprocess.run([
            str(CLI), '-m', str(GGUF), '-f', path, '-st', '-n', '100',
            '--temp', '0', '--seed', '11', '--no-display-prompt',
        ], cwd=str(ROOT), capture_output=True, text=True, encoding='utf8', errors='replace', timeout=90)
        text = ANSI.sub('', result.stdout)
        for match in re.finditer(r'\{"likely".*?\}', text, re.S):
            try:
                value = json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
            if isinstance(value.get('likely'), bool) and isinstance(value.get('related'), bool):
                return value
    finally:
        Path(path).unlink(missing_ok=True)
    return None


def model_decision(row, tok, session):
    enc = tok(row['context'], row['candidate'], truncation=True, max_length=160)
    logits = session.run(None, {
        'input_ids': np.array([enc['input_ids']], dtype=np.int64),
        'attention_mask': np.array([enc['attention_mask']], dtype=np.int64),
    })
    scores = {key: 1 / (1 + np.exp(-float(value[0]))) for key, value in zip(KEYS, logits)}
    if row['repeat'] == 'same_world' or row['category'] == 'wait':
        return False
    scores['intervene'] = max(scores['intervene'], 0.75 if row['involves_protagonist'] else 0)
    return (scores['novelty'] >= THRESHOLDS['novelty']
            and scores['unfinished'] >= THRESHOLDS['unfinished']
            and scores['necessity'] >= THRESHOLDS['necessity']
            and scores['intervene'] < THRESHOLDS['intervene'])


def main():
    template = json.loads((PUB / 'continuation-human-eval-template.json').read_text(encoding='utf8'))
    rules = [json.loads(line) for line in open(PUB / 'continuation-data.jsonl', encoding='utf8')]
    by_key = {(row['scenario'], row['candidate']): row for row in rules}
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    session = ort.InferenceSession(str(MODEL), providers=['CPUExecutionProvider'])
    rows, counts = [], Counter()
    for blind in template['rows']:
        rule = by_key[(blind['scenario'], blind['candidate'])]
        llm = run_llm(rule)
        llm_ok = bool(llm and llm['likely'] and llm['related']) if llm else False
        rule_ok = (rule['novelty'] == 1 and rule['unfinished'] == 1 and rule['necessity'] == 1
                   and rule['intervene'] == 0 and rule['repeat'] != 'same_world'
                   and rule['category'] != 'wait')
        micro_ok = model_decision(rule, tok, session)
        counts['rows'] += 1
        counts['llm_parse'] += int(llm is not None)
        counts['llm_continue'] += int(llm_ok)
        counts['rule_continue'] += int(rule_ok)
        counts['micro_continue'] += int(micro_ok)
        counts['llm_rule_same'] += int(llm_ok == rule_ok)
        counts['micro_rule_same'] += int(micro_ok == rule_ok)
        counts['llm_micro_same'] += int(llm_ok == micro_ok)
        rows.append({
            'id': blind['id'], 'scenario': blind['scenario'], 'candidate': blind['candidate'],
            'llm': llm, 'llm_continue': int(llm_ok), 'rule_continue': int(rule_ok),
            'micro_continue': int(micro_ok),
        })
    report = {'summary': dict(counts), 'rows': rows}
    (PUB / 'continuation-llm-arm.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(dict(counts), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
