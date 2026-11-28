# -*- coding: utf-8 -*-
"""Reverse decomposition v2: word-level alignment with jieba.

Copy      = target word identical to a fact word
Reorder   = copy words whose sequence differs from the facts order
Function  = particles/pronouns/connectives/punctuation
Paraphrase= unmatched content words that share a character with a fact word
Open      = unmatched content words with no character overlap with facts
Also records facts-side words never used (omissions) per passage."""
import json
import re
from collections import Counter
from pathlib import Path

import jieba

ROOT = Path('D:/others/Jity')
SRC = ROOT / '.local/narr-train/sft-v13.jsonl'
OUT = Path(__file__).resolve().parent

FUNCTION_WORDS = set('的 了 着 过 地 得 是 在 把 被 将 让 给 向 从 对 与 和 及 而 却 便 就 都 也 还 很 更 最 又 再 才 只 分 他 她 它 他们 她们 它们 自己 对方 这 那 其 我 你 我们 你们 一个 一 二 三 两 之 于 为 以 所 但 然 后 里 上 下 中 前 后 边 面 头')
CONNECTIVES = set('但是 可是 然而 不过 然后 随后 接着 于是 因此 因为 所以 虽然 尽管 并且 而且 同时 最后 此时 这时 已经 却 又 也 便')
PUNCT = re.compile(r'^[，。！？；：、"' + "'" + r'（）\n…—\s]+$')


def facts_of(prompt: str) -> str:
    marker = prompt.find('事实：')
    return prompt[marker + 3:] if marker >= 0 else prompt


def words(text: str):
    return [w for w in jieba.lcut(text) if w.strip()]


def decompose(target: str, facts: str):
    fact_words = words(facts)
    fact_set = set(fact_words)
    fact_chars = set(ch for w in fact_words for ch in w)
    target_words = words(target)
    used = Counter()
    stats = Counter()
    open_words = []
    para_words = []
    order_hits = []
    last_index = -1
    for word in target_words:
        if PUNCT.match(word) or word in FUNCTION_WORDS or word in CONNECTIVES:
            stats['function'] += len(word)
            continue
        index = None
        if used[word] < fact_words.count(word):
            index = next(i for i, w in enumerate(fact_words) if w == word and i not in [h for h, _ in order_hits] and not False) if False else None
        if word in fact_set:
            stats['copy'] += len(word)
            indices = [i for i, w in enumerate(fact_words) if w == word]
            if indices and indices[0] < last_index:
                stats['reorder'] += len(word)
            else:
                last_index = indices[0] if indices else last_index
            continue
        if any(ch in fact_chars for ch in word):
            stats['paraphrase'] += len(word)
            para_words.append(word)
            continue
        stats['open'] += len(word)
        open_words.append(word)
    total = sum(stats.values()) + stats['function'] * 0
    total = len(target)
    fact_used = Counter()
    for word in target_words:
        if word in fact_set:
            fact_used[word] += 1
    omitted = sum(1 for word in fact_words if word not in FUNCTION_WORDS and not PUNCT.match(word) and fact_used[word] < fact_words.count(word))
    return {
        'targetChars': len(target),
        'copy': stats['copy'], 'reorder': stats['reorder'], 'paraphrase': stats['paraphrase'],
        'open': stats['open'], 'function': stats['function'],
        'copyRatio': round(stats['copy'] / max(1, total), 3),
        'reorderRatio': round(stats['reorder'] / max(1, total), 3),
        'paraphraseRatio': round(stats['paraphrase'] / max(1, total), 3),
        'openRatio': round(stats['open'] / max(1, total), 3),
        'functionRatio': round(stats['function'] / max(1, total), 3),
        'factWords': len(fact_words),
        'omittedFactWords': omitted,
        'openWords': open_words,
        'paraWords': para_words,
    }


def main():
    rows = [json.loads(line) for line in SRC.read_text(encoding='utf8').splitlines() if line.strip()]
    rows.sort(key=lambda row: str(row['id']))
    sample = rows[:240]
    results = []
    totals = Counter()
    open_counter = Counter()
    para_counter = Counter()
    for row in sample:
        result = decompose(row['target'], facts_of(row['prompt']))
        result['id'] = row['id']
        results.append(result)
        for key in ('targetChars', 'copy', 'reorder', 'paraphrase', 'open', 'function', 'factWords', 'omittedFactWords'):
            totals[key] += result[key]
        for word in result['openWords']:
            open_counter[word] += 1
        for word in result['paraWords']:
            para_counter[word] += 1
    chars = totals['targetChars']
    summary = {
        'passages': len(sample),
        'targetChars': chars,
        'copyShare': round(totals['copy'] / chars, 3),
        'reorderShare': round(totals['reorder'] / chars, 3),
        'paraphraseShare': round(totals['paraphrase'] / chars, 3),
        'openShare': round(totals['open'] / chars, 3),
        'functionShare': round(totals['function'] / chars, 3),
        'omissionRate': round(totals['omittedFactWords'] / max(1, totals['factWords']), 3),
    }
    (OUT / 'decomp-v2.json').write_text(json.dumps({'summary': summary, 'rows': results}, ensure_ascii=False, indent=1), encoding='utf8')
    lines = ['# Reverse decomposition v2 (word-level)', '', json.dumps(summary, ensure_ascii=False), '',
             '## Top open words', '']
    for word, count in open_counter.most_common(60):
        lines.append(f'- {count}x {word}')
    lines += ['', '## Top paraphrase words', '']
    for word, count in para_counter.most_common(40):
        lines.append(f'- {count}x {word}')
    (OUT / 'decomp-v2.md').write_text('\n'.join(lines), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
