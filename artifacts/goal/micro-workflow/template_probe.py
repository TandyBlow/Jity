# -*- coding: utf-8 -*-
"""How often can a structured template replace the generated text fields?

Checks results facts against the member action (first person -> actor name),
and action text against the actor's declared tasks (copying them is forbidden,
so a high overlap would mean a template is not a real substitute).
"""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
MEMBER = re.compile(r'- ([^（(]+)（id=([^）)]+)）行动：(.+)')


def main():
    rows = [json.loads(line) for line in open(PUB / 'records.jsonl', encoding='utf8')]
    fact_stats = {'facts': 0, 'ge_06': 0, 'ge_04': 0, 'ge_02': 0, 'lt_02': 0}
    samples = []
    task_stats = {'actions': 0, 'task_overlap_ge_04': 0}
    task_samples = []
    for row in rows:
        if row['task'] == 'results':
            try:
                raw = json.loads(row['raw'])
            except json.JSONDecodeError:
                continue
            members = {mid: (name, action) for name, mid, action in MEMBER.findall(row['prompt'])}
            for fact in raw.get('facts') or []:
                actor = fact.get('actorId')
                if actor not in members:
                    continue
                name, action = members[actor]
                normalized = action.replace('我', name)
                ratio = SequenceMatcher(None, normalized, fact.get('text', '')).ratio()
                fact_stats['facts'] += 1
                for key, limit in (('ge_06', 0.6), ('ge_04', 0.4), ('ge_02', 0.2)):
                    if ratio >= limit:
                        fact_stats[key] += 1
                if ratio < 0.2:
                    fact_stats['lt_02'] += 1
                if len(samples) < 5 or ratio < 0.2:
                    samples.append({'action': normalized, 'fact': fact.get('text'), 'ratio': round(ratio, 2)})
        if row['task'] == 'action':
            try:
                raw = json.loads(row['raw'])
            except json.JSONDecodeError:
                continue
            text = raw.get('text') or ''
            if raw.get('kind') != 'act' or not text:
                continue
            task_stats['actions'] += 1
            block = row['prompt'].split('待办=', 1)[-1][:400]
            ratio = SequenceMatcher(None, text, block).ratio()
            if ratio >= 0.4:
                task_stats['task_overlap_ge_04'] += 1
            if len(task_samples) < 5:
                task_samples.append({'text': text, 'task_block': block[:80], 'ratio': round(ratio, 2)})
    out = {'facts': fact_stats, 'actions': task_stats, 'fact_samples': samples[:10], 'action_samples': task_samples}
    (PUB / 'template-probe.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: out[k] for k in ('facts', 'actions')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
