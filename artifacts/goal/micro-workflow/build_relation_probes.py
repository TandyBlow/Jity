# -*- coding: utf-8 -*-
"""Freeze relation probes from existing verified facts (no authored rows here).

Families built now:
  outcome  one row per unique results fact; gold = the kernel outcome marker
           (achieved/partial/not_achieved/blocked/no_change); input text strips
           the marker and structured tags.
  target   one row per unique fact carrying 涉及=; gold = the involved entity.
A manifest records source and output sha256, counts, and the route-family
holdout. Model arms must read only the frozen files."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'real-semantic.jsonl'
OUT = HERE / 'relation-probes'
HOLDOUT_ROUTES = {'sm6-', 'sm10-', 'sm14-', 'sm18-', 'sm22-'}
MARKERS = {'（达到目的）': 'achieved', '（只完成一部分）': 'partial', '（没有成功）': 'not_achieved',
           '（被阻止）': 'blocked', '（没有变化）': 'no_change'}
STRIP = re.compile('；?(?:去向|环境|信息|涉及)=[^；。]*')


def sha256_text(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()


def main():
    rows = [json.loads(line) for line in SOURCE.read_text(encoding='utf8').splitlines() if line.strip()]
    rows = [row for row in rows if row.get('source') == 'semantic']
    outcome = {}
    target = {}
    for row in rows:
        route = row['id'].split('-')[0] + '-'
        split = 'test' if str(row['id']).startswith('sc') or route in HOLDOUT_ROUTES else 'train'
        for index, fact in enumerate(row.get('settled') or []):
            if fact.get('task') != 'results' or not fact.get('text'):
                continue
            text = str(fact['text'])
            key = (fact.get('key'), text)
            if key in outcome:
                continue
            raw = text
            for marker, label in MARKERS.items():
                raw = raw.replace(marker, '')
            clean = STRIP.sub('', raw).strip()
            involved = re.search('涉及=([^；。]*)', text)
            record = {'id': f"{row['id']}#{index}", 'rowId': row['id'], 'family': 'outcome',
                      'input': clean, 'raw': text, 'gold': None, 'split': split,
                      'provenance': 'program_record', 'class': row.get('class')}
            for marker, label in MARKERS.items():
                if marker in text:
                    record['gold'] = label
                    break
            if record['gold']:
                outcome[key] = record
            if involved:
                target.setdefault((fact.get('key'), clean), {
                    'id': f"{row['id']}#t{index}", 'rowId': row['id'], 'family': 'target',
                    'input': clean, 'raw': text, 'gold': [part.strip() for part in involved.group(1).split(',') if part.strip()],
                    'split': split, 'provenance': 'program_span', 'class': row.get('class')})
    OUT.mkdir(exist_ok=True)
    files = {}
    for name, records in (('outcome', list(outcome.values())), ('target', list(target.values()))):
        payload = ''.join(json.dumps(record, ensure_ascii=False) + '\n' for record in records)
        path = OUT / f'{name}.jsonl'
        path.write_text(payload, encoding='utf8')
        files[name] = {'rows': len(records), 'sha256': sha256_text(payload),
                       'split': dict(Counter(record['split'] for record in records)),
                       'gold': dict(Counter(str(record['gold']) for record in records))}
    manifest = {'source': {'file': SOURCE.name, 'sha256': sha256_text(SOURCE.read_text(encoding='utf8'))},
                'holdoutRoutes': sorted(HOLDOUT_ROUTES), 'files': files,
                'note': 'Outcome gold is the kernel marker (not independent semantics); target gold is the program 涉及 span.'}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(manifest, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
