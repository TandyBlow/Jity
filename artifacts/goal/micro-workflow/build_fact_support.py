# -*- coding: utf-8 -*-
"""Fact-support verification pairs from verified labels + cached proposals.

Supported: final status present (the verifier accepted the claim).
Unsupported: final status absent while the proposal asserted present (the claim
was rejected). insufficient/conflict are skipped: they are not negatives.
Distractor: a supported claim paired with another row's fact set (same field)
whose text does not contain the claim, so every field reaches 50/50.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = HERE / 'real-semantic.jsonl'
CACHE = HERE / 'real-semantic-cache.jsonl'
OUT = HERE / 'semantic-support.jsonl'


def input_hash(row):
    payload = row.get('input', '') + '\n' + row.get('text', '') + '\n' + json.dumps(
        row.get('settled') or [], ensure_ascii=False) + '\n' + json.dumps(
        row.get('stateDiff') or {}, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf8')).hexdigest()


def fact_text(row):
    facts = [str(item.get('text') or '') for item in row.get('settled') or [] if item.get('task') == 'results']
    env_keys = (row.get('stateDiff') or {}).get('env') or []
    if env_keys:
        facts.append('状态变化：' + ', '.join(str(key) for key in env_keys))
    return '\n'.join(text for text in facts if text)[:1200]


def main():
    rows = [json.loads(line) for line in DATASET.read_text(encoding='utf8').splitlines() if line.strip()]
    cache = [json.loads(line) for line in CACHE.read_text(encoding='utf8').splitlines() if line.strip()]
    by_key = {(record.get('id'), record.get('promptVersion'), record.get('inputHash')): record for record in cache}
    pairs = []
    for row in rows:
        if row.get('source') != 'semantic':
            continue
        record = by_key.get((row['id'], 'v2', input_hash(row)))
        if not record:
            continue
        cache_label = record.get('label') or {}
        for field in ('info', 'env'):
            final = (row.get('label') or {}).get(field) or {}
            proposal = cache_label.get(field) or {}
            status = final.get('status')
            claim = str(final.get('content') or '').strip()
            if status == 'present' and claim:
                label, reason = True, 'verified_present'
            elif status == 'absent' and proposal.get('present') and str(proposal.get('content') or '').strip():
                label, reason = False, 'rejected_claim'
                claim = str(proposal.get('content') or '').strip()
            else:
                continue
            facts = fact_text(row)
            if not facts:
                continue
            pairs.append({'id': f"{row['id']}:{field}", 'rowId': row['id'], 'field': field,
                          'claim': claim, 'facts': facts, 'label': label, 'reason': reason,
                          'class': row.get('class'), 'split': 'test' if str(row['id']).startswith('sc') else 'train'})

    # 干扰负例：同一字段另一行的结算事实，事实里不含该主张
    by_field = {}
    for pair in pairs:
        if pair['label']:
            by_field.setdefault(pair['field'], []).append(pair)
    seen = {(pair['field'], pair['claim'], pair['facts'], pair['label']) for pair in pairs}
    for field, supported in by_field.items():
        ordered = sorted(supported, key=lambda pair: pair['id'])
        for index, pair in enumerate(ordered):
            for step in range(1, len(ordered)):
                other = ordered[(index + step) % len(ordered)]
                if other['facts'] == pair['facts'] or pair['claim'] in other['facts']:
                    continue
                key = (field, pair['claim'], other['facts'], False)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append({'id': f"{pair['rowId']}:{field}:distract", 'rowId': pair['rowId'], 'field': field,
                              'claim': pair['claim'], 'facts': other['facts'], 'label': False,
                              'reason': 'other_fact_set', 'class': pair.get('class'), 'split': pair['split']})
                break

    OUT.write_text(''.join(json.dumps(pair, ensure_ascii=False) + '\n' for pair in pairs), encoding='utf8')
    counts = {}
    for pair in pairs:
        key = f"{pair['field']}:{pair['split']}:{'pos' if pair['label'] else 'neg'}"
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({'pairs': len(pairs), 'counts': counts}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
