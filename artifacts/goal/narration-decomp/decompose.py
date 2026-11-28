# -*- coding: utf-8 -*-
"""Reverse decomposition v1: how much of the v13 narration targets is
reconstructible from the settled facts (copy/reorder/glue), and how much needs
open generation. Char-level matching with difflib; six-operation taxonomy."""
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path('D:/others/Jity')
SRC = ROOT / '.local/narr-train/sft-v13.jsonl'
OUT = Path(__file__).resolve().parent

GLUE = set('的了着过地得是在把被将让给向从对与和及而却便就都也还很更最又再才只分才')
PRONOUNS = ['他们', '她们', '它们', '自己', '对方', '他', '她', '它', '这', '那', '其']
CONNECTIVES = ['但是', '可是', '然而', '不过', '然后', '随后', '接着', '于是', '因此', '因为', '所以',
               '虽然', '尽管', '并且', '而且', '同时', '最后', '此时', '这时', '已经', '还', '便', '就']
PUNCT = set('，。！？；：、“”‘’（）\n…— ')


def facts_of(prompt: str) -> str:
    marker = prompt.find('事实：')
    return prompt[marker + 3:] if marker >= 0 else prompt


def classify(span: str) -> str:
    clean = span.strip()
    if not clean or all(ch in PUNCT for ch in clean):
        return 'punctuation'
    if any(word in clean for word in PRONOUNS):
        return 'pronoun'
    if any(word in clean for word in CONNECTIVES):
        return 'connective'
    if all(ch in GLUE or ch in PUNCT for ch in clean):
        return 'glue'
    if len(clean) <= 2:
        return 'short_edit'
    return 'open'


def decompose(target: str, facts: str):
    matcher = SequenceMatcher(None, facts, target, autojunk=False)
    covered = [False] * len(target)
    for block in matcher.get_matching_blocks():
        for index in range(block.a, block.a + block.size):
            pass
        if block.size >= 2:
            for offset in range(block.size):
                covered[block.b + offset] = True
    spans = []
    index = 0
    while index < len(target):
        if covered[index]:
            index += 1
            continue
        start = index
        while index < len(target) and not covered[index]:
            index += 1
        spans.append(target[start:index])
    kinds = Counter(classify(span) for span in spans)
    matched = sum(covered)
    open_chars = sum(len(span.strip()) for span in spans if classify(span) == 'open')
    return {
        'targetChars': len(target),
        'matchedChars': matched,
        'coverage': round(matched / max(1, len(target)), 3),
        'openChars': open_chars,
        'openRatio': round(open_chars / max(1, len(target)), 3),
        'kinds': dict(kinds),
        'spans': [{'text': span, 'kind': classify(span)} for span in spans],
    }


def main():
    rows = [json.loads(line) for line in SRC.read_text(encoding='utf8').splitlines() if line.strip()]
    rows.sort(key=lambda row: str(row['id']))
    sample = rows[:240]
    results = []
    totals = Counter()
    for row in sample:
        result = decompose(row['target'], facts_of(row['prompt']))
        result['id'] = row['id']
        results.append(result)
        totals['targetChars'] += result['targetChars']
        totals['matchedChars'] += result['matchedChars']
        totals['openChars'] += result['openChars']
        for kind, count in result['kinds'].items():
            totals[kind] += count
    summary = {
        'passages': len(sample),
        'targetChars': totals['targetChars'],
        'coverage': round(totals['matchedChars'] / totals['targetChars'], 3),
        'openRatio': round(totals['openChars'] / totals['targetChars'], 3),
        'operationCounts': {k: totals[k] for k in ('punctuation', 'pronoun', 'connective', 'glue', 'short_edit', 'open')},
        'coverageMean': round(sum(r['coverage'] for r in results) / len(results), 3),
        'openRatioMean': round(sum(r['openRatio'] for r in results) / len(results), 3),
    }
    (OUT / 'decomp-v1.json').write_text(json.dumps({'summary': summary, 'rows': results}, ensure_ascii=False, indent=1), encoding='utf8')
    open_texts = Counter()
    for result in results:
        for span in result['spans']:
            if span['kind'] == 'open':
                open_texts[span['text'].strip()] += 1
    lines = ['# Reverse decomposition v1', '', json.dumps(summary, ensure_ascii=False), '', '## Top open spans', '']
    for text, count in open_texts.most_common(40):
        lines.append(f'- {count}x {text[:60]}')
    (OUT / 'decomp-v1.md').write_text('\n'.join(lines), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
