"""Statement-verification serializer / contract (no training).

The model sees the full unit text, one numbered candidate, and the authorized
facts/scene/visible items with stable source IDs. It returns a label and source
IDs; it never returns a deletion, a position, or rewritten text.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path('D:/others/Jity')
PAIRS = ROOT / 'artifacts' / 'statement-verification' / 'pairs-v1.jsonl'
REGRESSION = ROOT / 'artifacts' / 'statement-verification' / 'regression-v1.jsonl'
LABELS = ('supported', 'unsupported', 'uncertain')


def source_maps(record):
    facts = {f['sourceId']: f['factText'] for f in record.get('facts', [])}
    scene = {s['sourceId']: s['text'] for s in record.get('scene', [])}
    visible = {v['sourceId']: v['text'] for v in record.get('visible', [])}
    return facts, scene, visible


def serialize(record, with_answer=False):
    facts, scene, visible = source_maps(record)
    lines = [f"正文：{record['fullText']}",
             f"片段 {record['candidateId']}：{record['candidateText']}",
             "事实："]
    spans = []
    pos = sum(len(x) + 1 for x in lines)
    for sid, text in facts.items():
        line = f"{sid}｜{text}"
        spans.append({'sourceId': sid, 'kind': 'fact', 'start': pos, 'end': pos + len(line)})
        lines.append(line)
        pos += len(line) + 1
    if not facts:
        lines.append('无')
        pos += 2
    lines.append('场景：')
    pos += len('场景：') + 1
    for sid, text in scene.items():
        line = f"{sid}｜{text}"
        spans.append({'sourceId': sid, 'kind': 'scene', 'start': pos, 'end': pos + len(line)})
        lines.append(line)
        pos += len(line) + 1
    if not scene:
        lines.append('无')
        pos += 2
    lines.append('可见：')
    pos += len('可见：') + 1
    for sid, text in visible.items():
        line = f"{sid}｜{text}"
        spans.append({'sourceId': sid, 'kind': 'visible', 'start': pos, 'end': pos + len(line)})
        lines.append(line)
        pos += len(line) + 1
    if not visible:
        lines.append('无')
        pos += 2
    lines.append('判定：')
    text = '\n'.join(lines)
    if with_answer:
        text += record['label']
    return {'text': text, 'sourceSpans': spans, 'sourceIds': [s['sourceId'] for s in spans]}


def validate(record):
    errors = []
    if record.get('label') not in LABELS:
        errors.append('bad-label')
    if record.get('candidateText') not in (record.get('fullText') or ''):
        errors.append('candidate-not-in-fulltext')
    ids = set()
    for key in ('facts', 'scene', 'visible'):
        for item in record.get(key, []):
            sid = item.get('sourceId')
            if not sid or sid in ids:
                errors.append(f'bad-or-duplicate-source:{sid}')
            ids.add(sid)
    for sid in record.get('goldSourceIds', []):
        if sid not in ids:
            errors.append(f'gold-source-missing:{sid}')
    return errors


def main():
    rows = []
    for path in (PAIRS, REGRESSION):
        rows += [json.loads(l) for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]
    errors = []
    max_chars = 0
    for r in rows:
        errors += [f"{r.get('exampleId')}:{e}" for e in validate(r)]
        max_chars = max(max_chars, len(serialize(r)['text']))
    print(json.dumps({'records': len(rows), 'errors': errors[:20],
                      'errorCount': len(errors), 'maxSerializedChars': max_chars},
                     ensure_ascii=False, indent=1))
    try:
        from transformers.models.bert.tokenization_bert import BertTokenizer
        tok = BertTokenizer.from_pretrained('ckpt-n5')
        lens = [len(tok.encode(serialize(r)['text'], add_special_tokens=True)) for r in rows]
        lens.sort()
        print(json.dumps({'tokenizer': 'ckpt-n5', 'min': lens[0], 'p50': lens[len(lens)//2],
                          'p90': lens[int(len(lens)*.9)], 'max': lens[-1],
                          'over256': sum(1 for x in lens if x > 256)}, ensure_ascii=False))
    except Exception as exc:
        print('tokenizer unavailable:', type(exc).__name__, exc)


if __name__ == '__main__':
    main()
