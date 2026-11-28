# -*- coding: utf-8 -*-
"""N17: what edits does a hand-written natural clause apply to its source
fragment? Aligns single-source clauses and classifies insertions."""
import difflib
import json
import re
from collections import Counter
from pathlib import Path

import renderer_dataset as rd

HERE = Path(__file__).resolve().parent
ASPECT = re.compile(r'^(了|着|过|已经|正|在)$')
CONNECTIVE = re.compile(r'^(则|也|并|而|又|却|但|随后|同时|因此|所以|因为|先|再|就|便)$')
PRONOUN = re.compile(r'^(他|她|它|他们|她们)$')
PUNCT = re.compile(r'^[，。；：、！？—…（）()]+$')


def classify(text):
    if ASPECT.match(text):
        return 'aspect'
    if CONNECTIVE.match(text):
        return 'connective'
    if PRONOUN.match(text):
        return 'pronoun'
    if PUNCT.match(text):
        return 'punct'
    return 'other'


def main():
    rows = {r['id']: r for r in (json.loads(l) for l in open(HERE / 'pairs.jsonl', encoding='utf8'))}
    refs = json.load(open(HERE / 'natural-reference.json', encoding='utf8'))
    counts = Counter()
    examples = []
    single = 0
    total_clauses = 0
    for ref in refs:
        point = rows[ref['id']]
        frags = rd.fragments(point)
        for clause in ref['clauses']:
            total_clauses += 1
            if len(clause['sources']) != 1:
                continue
            single += 1
            source = frags[clause['sources'][0]][1]
            matcher = difflib.SequenceMatcher(None, source, clause['text'])
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == 'equal':
                    continue
                if tag in ('insert', 'replace'):
                    text = clause['text'][j1:j2]
                    kind = classify(text)
                    counts[kind] += len(text)
                    if kind in ('aspect', 'connective', 'pronoun') and len(examples) < 12:
                        examples.append({'kind': kind, 'insert': text, 'around': clause['text'][max(0, j1 - 6):j2 + 6]})
                if tag in ('delete', 'replace'):
                    counts['deleted_chars'] += i2 - i1
            counts['clauses'] += 1
    out = {
        'clauses': total_clauses,
        'singleSourceClauses': single,
        'insertedChars': {k: v for k, v in counts.items() if k not in ('clauses', 'deleted_chars')},
        'deletedChars': counts['deleted_chars'],
        'examples': examples,
    }
    (HERE / 'edit-taxonomy.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in out.items() if k != 'examples'}, ensure_ascii=False))
    for e in examples[:8]:
        print(e['kind'], '|', e['insert'], '|', e['around'])


if __name__ == '__main__':
    main()
