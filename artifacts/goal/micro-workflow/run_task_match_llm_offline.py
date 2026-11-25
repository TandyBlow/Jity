# -*- coding: utf-8 -*-
"""Offline arms on the hand-authored task/fact pairs: int8 pair model vs Qwen3."""
import json, re, subprocess, tempfile
from collections import Counter
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODEL = ROOT / 'frontend/public/micro/task-match-int8.onnx'
CLI = ROOT / '.local/llama-cpp/llama-cli.exe'
GGUF = ROOT / 'frontend/public/models/Qwen3-0.6B-Q4_K_M.gguf'
SAT = ['yes', 'partial', 'no']
ANSI = re.compile(r'\x1b\[[0-9;]*m')


def llm(goal, fact):
    prompt = '\n'.join([
        '你是中文跑团游戏的任务条件核验器。只输出 JSON，不要解释。',
        '判断给出的已发生事实是否让任务目标条件成立。只有事实本身已经让条件成立才判 yes；部分完成、尝试、接近、只提到相关人物、只复述目标都判 partial 或 no。',
        f'任务：{goal}',
        f'事实：{fact}',
        '输出 {"satisfied":"yes|partial|no","reason":"一句话"}。/no_think',
    ])
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf8') as handle:
        handle.write(prompt); path = handle.name
    try:
        result = subprocess.run([str(CLI), '-m', str(GGUF), '-f', path, '-st', '-n', '80',
                                 '--temp', '0', '--seed', '11', '--no-display-prompt'],
                                cwd=str(ROOT), capture_output=True, text=True, encoding='utf8', errors='replace', timeout=90)
        text = ANSI.sub('', result.stdout)
        for match in re.finditer(r'\{"satisfied".*?\}', text, re.S):
            try:
                value = json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
            if value.get('satisfied') in SAT:
                return value['satisfied']
    finally:
        Path(path).unlink(missing_ok=True)
    return None


def model(goal, fact, tok, session):
    enc = tok(f'任务：{goal}', fact, truncation=True, max_length=160)
    out = session.run(None, {'input_ids': np.array([enc['input_ids']], dtype=np.int64),
                             'attention_mask': np.array([enc['attention_mask']], dtype=np.int64)})
    relevance = 1 / (1 + np.exp(-float(out[0][0])))
    logits = np.array(out[1][0], dtype=np.float64)
    probabilities = np.exp(logits - logits.max()); probabilities /= probabilities.sum()
    return SAT[int(probabilities.argmax())] if relevance >= 0.5 else 'no', float(probabilities.max())


def main():
    rows = [json.loads(line) for line in open(PUB / 'task-match-data.jsonl', encoding='utf8')]
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    session = ort.InferenceSession(str(MODEL), providers=['CPUExecutionProvider'])
    counts = Counter(); detail = []
    for row in rows:
        predicted_llm = llm(row['goal'], row['fact'])
        predicted_model, confidence = model(row['goal'], row['fact'], tok, session)
        label = row['satisfaction']
        counts['rows'] += 1
        counts['llm_parse'] += int(predicted_llm is not None)
        if predicted_llm is not None:
            counts['llm_correct'] += int(predicted_llm == label)
        counts['model_correct'] += int(predicted_model == label)
        detail.append({'task_id': row['task_id'], 'label': label, 'llm': predicted_llm,
                       'model': predicted_model, 'model_confidence': round(confidence, 3),
                       'relevance': row['relevance']})
    (PUB / 'task-match-llm-arm.json').write_text(json.dumps({'summary': dict(counts), 'rows': detail}, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(dict(counts), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
