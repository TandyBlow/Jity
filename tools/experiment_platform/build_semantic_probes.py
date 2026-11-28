#!/usr/bin/env python3
"""Author an independent semantic probe set from the static world file.

Cases are new player lines, not present in the semantic training export. Ground
truth comes from `initialAppearance` in the world: inspecting an entity must
yield info from that entity's appearance; entering a location must yield its
environment appearance; inspecting an unregistered entity must not yield info.
No model is run here — the set is frozen so any workflow can be scored later.

Output: artifacts/goal/platform/eval/semantic-probes-v1.{dev,test}.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'
TRAIN = ROOT / 'artifacts/goal/micro-workflow/real-semantic-train.jsonl'
OUT_DIR = ROOT / 'artifacts/goal/platform/eval'


def clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r'[。；]', text or '') if len(c.strip()) > 3]


def pick(entities: dict, names_seen: set[str], limit: int) -> list[dict]:
    chosen = []
    for key in sorted(entities):
        entry = entities[key]
        appearance = entry.get('initialAppearance') or ''
        name = entry.get('name') or key
        if not appearance or name in names_seen:
            continue
        chosen.append({'id': key, 'name': name, 'appearance': appearance,
                       'container': (entry.get('initialPosition') or {}).get('containerId')})
        if len(chosen) >= limit:
            break
    return chosen


def make_case(identity: str, family: str, action: str, expected: list[str],
              any_of: list[str], forbidden: dict, extra: dict, split: str,
              status: dict | None = None) -> dict:
    return {
        'id': identity, 'family': family, 'modality': 'semantic', 'world': 'dragon-raja-free-day', 'split': split,
        'input': {'playerLine': action, **extra},
        'expected': {'facts': expected, 'anyOf': any_of, 'status': status or {}},
        'forbidden': forbidden,
        'provenance': {'labelSource': 'world-initial-appearance', 'humanVerified': False,
                       'notes': 'new action line; expected clause taken from the static world'},
    }


def build() -> tuple[dict, dict]:
    world = json.loads(WORLD.read_text(encoding='utf-8-sig'))
    initial = world['initial']
    train_text = ''.join(line for line in TRAIN.read_text(encoding='utf-8').splitlines()
                         if line.strip())
    seen = {entry.get('name') for entry in initial['items'].values() if entry.get('name') in train_text}

    items = pick(initial['items'], seen, 12)
    places = pick(initial['locations'], set(), 8)
    people = pick(initial['characters'], set(), 6)
    cases = []

    def split_of(identity: str) -> str:
        return 'dev' if int(hashlib.sha1(identity.encode()).hexdigest()[:2], 16) % 5 < 3 else 'test'

    for item in items:
        name = item['name']
        identity = f'sem-probe:item:{item["id"]}'
        action = f'我拿起{name}，仔细看它的说明和外观。'
        any_of = clauses(item['appearance'])
        cases.append(make_case(identity, 'item_inspect', action,
                               [f'信息={name}:{any_of[0]}'], any_of,
                               {'infoAboutOtherEntities': True},
                               {'entityId': item['id'], 'entityName': name}, split_of(identity),
                               {'info': 'present'}))
    for place in places:
        name = place['name']
        identity = f'sem-probe:place:{place["id"]}'
        action = f'我走进{name}，留意这里的环境。'
        any_of = clauses(place['appearance'])
        cases.append(make_case(identity, 'place_enter', action,
                               [f'环境={name}:{any_of[0]}'], any_of,
                               {'envAboutOtherPlaces': True},
                               {'entityId': place['id'], 'entityName': name}, split_of(identity),
                               {'env': 'present'}))
    for person in people:
        name = person['name']
        identity = f'sem-probe:person:{person["id"]}'
        action = f'我打量{name}的衣着和身上的状态。'
        any_of = clauses(person['appearance'])
        cases.append(make_case(identity, 'person_observe', action,
                               [f'信息={name}:{any_of[0]}'], any_of,
                               {'infoAboutOtherEntities': True},
                               {'entityId': person['id'], 'entityName': name}, split_of(identity),
                               {'info': 'present'}))
    if len(items) >= 2:
        a, b = items[0], items[1]
        cases.append(make_case(
            f'sem-probe:negation:{a["id"]}:{b["id"]}',
            'negation',
            f'我不碰{a["name"]}，只查看{b["name"]}的外观。',
            [f'信息={b["name"]}:{clauses(b["appearance"])[0]}'], clauses(b['appearance']),
            {'infoAbout': [a['name']]},
            {'entityId': b['id'], 'entityName': b['name'], 'negatedEntity': a['id']},
            split_of(f'sem-probe:negation:{a["id"]}:{b["id"]}'), {'info': 'present'}))
        cases.append(make_case(
            f'sem-probe:compound:{a["id"]}:{b["id"]}',
            'compound',
            f'我拿起{a["name"]}，同时看清{b["name"]}的说明。',
            [f'信息={b["name"]}:{clauses(b["appearance"])[0]}'], clauses(b['appearance']),
            {'infoAbout': [a['name']]},
            {'entityId': b['id'], 'entityName': b['name'], 'carriedEntity': a['id']},
            split_of(f'sem-probe:compound:{a["id"]}:{b["id"]}'), {'info': 'present'}))
    cases.append(make_case(
        'sem-probe:unknown:storage-locker', 'unknown_entity',
        '我查看墙边那只不存在的储物柜，想读上面的标签。',
        ['信息=储物柜:未登记'], [], {'anyInfoPresent': True},
        {'entityName': '储物柜'}, 'test', {'info': 'absent'}))
    dev = sorted((c for c in cases if c['split'] == 'dev'), key=lambda c: c['id'])
    test = sorted((c for c in cases if c['split'] == 'test'), key=lambda c: c['id'])
    summary = {
        'schema': 'jity-semantic-probes/1',
        'worldSha256': hashlib.sha256(WORLD.read_bytes()).hexdigest(),
        'devRows': len(dev), 'testRows': len(test),
        'families': dict(Counter(c['family'] for c in cases)),
        'excludedEntitiesInTrainText': sorted(seen),
        'gaps': ['task change', 'multi-person settlement', 'NPC autonomy', 'partial success'],
    }
    return {'dev': dev, 'test': test}, summary


def write_set(rows: list[dict], path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    canon = hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode('utf-8')).hexdigest()
    manifest = {'schema': 'jity-eval-set/1', 'path': path.relative_to(ROOT).as_posix(),
                'rows': len(rows), 'sha256': canon, 'hashMode': 'canonical-json'}
    (path.with_suffix('.jsonl.manifest.json')).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out-dir', default=str(OUT_DIR))
    args = parser.parse_args(argv)
    sets, summary = build()
    out = Path(args.out_dir)
    manifests = {name: write_set(rows, out / f'semantic-probes-v1.{name}.jsonl')
                 for name, rows in sets.items()}
    (out / 'semantic-probes-v1.summary.json').write_text(
        json.dumps({**summary, 'manifests': manifests}, ensure_ascii=False, indent=1) + '\n',
        encoding='utf-8')
    print(json.dumps({**summary, 'manifests': manifests}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
