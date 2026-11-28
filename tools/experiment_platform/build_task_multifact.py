#!/usr/bin/env python3
"""Build multi-fact, cross-turn task cases from raw rule-arm evidence.

Each case is one task at one turn: the accumulated settlement events up to that
turn, the task's ledger conditions/evidence, the state diff for that turn, and
the task status history. Events come from `taskLedger.seenFacts` (the raw
settlement records), not from prompt text, so event count, actor, time,
outcome, state tags and source survive. The old task status is recorded as a
baseline, not as a gold label; `completion`/`support` labels stay empty.

Axis: completion. The ledger's condition evidence is kept as the support
relation, not voted into a completion verdict.

  python -m tools.experiment_platform.build_task_multifact
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.experiment_platform.narration_metrics import OUTCOMES  # noqa: E402

EVIDENCE = ROOT / 'artifacts/goal/narration-rules/scenarios8-rules.json'
SPECS = ROOT / 'artifacts/goal/platform/task-gold/task-gold-v1.tasks.json'
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'
OUT = ROOT / 'artifacts/goal/platform/task-gold/task-multifact-v1.jsonl'


def parse_seen(line: str) -> dict | None:
    match = re.match(r'^([^:：]{1,12})[:：](.+)$', (line or '').strip())
    if not match:
        return None
    key, body = match.group(1).strip(), match.group(2).strip()
    head, *rest = body.split('；')
    tags = {}
    for part in rest:
        if '=' in part:
            tag, value = part.split('=', 1)
            tags[tag.strip()] = value.strip()
    outcome = next((o for o in OUTCOMES if o in head), None)
    return {'actorKey': key, 'text': body, 'body': head, 'outcome': outcome, 'tags': tags}


def index_ledger(ledger: dict) -> dict:
    return {(e.get('ownerId'), e.get('taskId')): e for e in ledger.get('entries') or []}


def state_diff(prev: dict | None, cur: dict) -> dict:
    if not prev:
        return {'baseline': True}
    out = {'time': {'from': prev.get('time'), 'to': cur.get('time')},
           'tasks': [], 'positions': [], 'sanity': [], 'items': [], 'locations': []}
    for cid, char in (cur.get('characters') or {}).items():
        old = (prev.get('characters') or {}).get(cid) or {}
        if old.get('position') != char.get('position'):
            out['positions'].append({'id': cid, 'from': old.get('position'), 'to': char.get('position')})
        if old.get('sanity') != char.get('sanity'):
            out['sanity'].append({'id': cid, 'from': old.get('sanity'), 'to': char.get('sanity')})
        old_tasks = old.get('tasks') or {}
        for tid, task in (char.get('tasks') or {}).items():
            before = (old_tasks.get(tid) or {}).get('status')
            if before != task.get('status'):
                out['tasks'].append({'ownerId': cid, 'taskId': tid, 'from': before, 'to': task.get('status')})
    for iid, item in (cur.get('items') or {}).items():
        old = (prev.get('items') or {}).get(iid) or {}
        if old.get('position') != item.get('position'):
            out['items'].append({'id': iid, 'from': old.get('position'), 'to': item.get('position')})
    for lid, loc in (cur.get('locations') or {}).items():
        old = (prev.get('locations') or {}).get(lid) or {}
        before, after = len(old.get('appearanceChanges') or []), len(loc.get('appearanceChanges') or [])
        if before != after:
            out['locations'].append({'id': lid, 'changesAdded': after - before})
    return out


def ledger_delta(prev: dict, cur: dict) -> list[dict]:
    out = []
    for key, entry in cur.items():
        old = prev.get(key) or {}
        if (old.get('status') != entry.get('status') or old.get('active') != entry.get('active')
                or old.get('evidence') != entry.get('evidence')):
            out.append({'ownerId': key[0], 'taskId': key[1], 'status': entry.get('status'),
                        'active': entry.get('active'), 'evidence': entry.get('evidence'),
                        'prevStatus': old.get('status'), 'prevActive': old.get('active')})
    return out


def support_links(entry: dict, events: list[dict], with_text: bool = True) -> list[dict]:
    links = []
    for condition_id, evidence in (entry.get('evidence') or {}).items():
        text = (evidence or {}).get('text') or ''
        event_id = next((e['id'] for e in events if text and (e['text'] == text or e['text'].endswith(text))), None)
        link = {'conditionId': condition_id, 'eventId': event_id}
        if with_text:
            link['text'] = text
        links.append(link)
    return links


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--evidence', default=str(EVIDENCE))
    parser.add_argument('--specs', default=str(SPECS))
    parser.add_argument('--out', default=str(OUT))
    args = parser.parse_args(argv)
    doc = json.loads(Path(args.evidence).read_text(encoding='utf-8-sig'))
    evidence_path = Path(args.evidence).resolve()
    try:
        rel = evidence_path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = str(evidence_path)
    specs = json.loads(Path(args.specs).read_text(encoding='utf-8-sig')).get('tasks') or []
    spec_by_id = {t['taskId']: t for t in specs}
    world = json.loads(WORLD.read_text(encoding='utf-8-sig'))
    names = {cid: c.get('name') or cid for cid, c in (world['initial']['characters'] or {}).items()}
    turn_table = []
    turn_diffs = []
    prev_seen: set[str] = set()
    prev_state = prev_ledger = None
    accumulated: list[dict] = []
    history: dict[tuple, list] = {}
    cases: list[dict] = []
    seen: dict[tuple, dict] = {}
    repeats = 0
    for turn_index, turn in enumerate(doc.get('turns') or [], 1):
        snap = turn.get('snapshotAfterTurn') or {}
        state = (snap.get('transport') or {}).get('state') or {}
        turn_table.append({'turnIndex': turn_index, 'turnId': turn.get('id'),
                           'time': (state.get('time') or {}).get('dateTime')})
        ledger = snap.get('taskLedger') or {}
        seen_facts = ledger.get('seenFacts') or []
        current_index = index_ledger(ledger)
        for position, line in enumerate(seen_facts):
            if line in prev_seen:
                continue
            parsed = parse_seen(line)
            if not parsed:
                continue
            accumulated.append({
                'id': f"ev:{turn_index}:{position}", 'actorKey': parsed['actorKey'],
                'actorName': names.get(parsed['actorKey'], parsed['actorKey']),
                'text': parsed['text'], 'outcome': parsed['outcome'],
                'tags': parsed['tags'], 'time': (state.get('time') or {}).get('dateTime'),
                'turnIndex': turn_index,
            })
        diff = state_diff(prev_state, state)
        turn_diffs.append({'turnIndex': turn_index, 'diff': diff})
        delta = ledger_delta(prev_ledger or {}, current_index)
        signature = tuple(e['id'] for e in accumulated)
        tasks = [(cid, char, tid, task) for cid, char in (state.get('characters') or {}).items()
                 for tid, task in (char.get('tasks') or {}).items() if task.get('goal')]
        for cid, _char, tid, task in tasks:
            entry = current_index.get((cid, tid)) or {}
            history.setdefault((cid, tid), []).append({
                'turnIndex': turn_index, 'turnId': turn.get('id'), 'status': task.get('status'),
                'ledgerStatus': entry.get('status'), 'ledgerActive': entry.get('active'),
                'evidenceEventIds': support_links(entry, accumulated, with_text=False),
            })
        for cid, _char, tid, task in tasks:
            key = (cid, tid, signature)
            if key in seen:
                repeats += 1
                seen[key]['repeatTurns'].append(turn.get('id'))
                continue
            entry = current_index.get((cid, tid)) or {}
            events = [dict(e) for e in accumulated]
            spec = spec_by_id.get(tid)
            before = ((prev_state or {}).get('characters', {}).get(cid, {}) or {}).get('tasks', {}).get(tid, {})
            case = {
                'id': 'tmf-v1:' + hashlib.sha1(
                    (f'{cid}|{tid}|{turn_index}|{signature[-1] if signature else ""}').encode('utf-8')).hexdigest()[:12],
                'modality': 'semantic', 'world': 'dragon-raja-free-day', 'split': 'dev',
                'axis': 'completion',
                'taskId': tid, 'goal': task.get('goal'), 'ownerId': cid,
                'ownerName': names.get(cid, cid),
                'turnId': turn.get('id'), 'turnIndex': turn_index,
                'time': (state.get('time') or {}).get('dateTime'),
                'eventCount': len(events), 'events': events,
                'taskLedger': entry,
                'supportLinks': support_links(entry, events),
                'ledgerDelta': [d for d in delta if d['ownerId'] == cid and d['taskId'] == tid],
                'stateChanges': diff,
                'taskStatusHistory': [dict(h) for h in history[(cid, tid)]],
                'oldStatus': task.get('status'), 'oldStatusBefore': before.get('status'),
                'completion': None, 'support': None, 'needsReview': True,
                'spec': ({k: spec.get(k) for k in
                          ('kind', 'required', 'preconditions', 'negations', 'partialRule', 'forbiddenShortcuts')}
                         if spec else None),
                'repeatTurns': [],
                'provenance': {'evidence': rel},
            }
            seen[key] = case
            cases.append(case)
        prev_seen.update(seen_facts)
        prev_state, prev_ledger = state, current_index
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(json.dumps(c, ensure_ascii=False) for c in cases) + '\n', encoding='utf-8')
    canon = hashlib.sha256(json.dumps(cases, ensure_ascii=False).encode('utf-8')).hexdigest()
    try:
        out_rel = out.relative_to(ROOT).as_posix()
    except ValueError:
        out_rel = str(out)
    out.with_suffix('.jsonl.manifest.json').write_text(json.dumps(
        {'schema': 'jity-eval-set/1', 'path': out_rel, 'rows': len(cases),
         'sha256': canon, 'hashMode': 'canonical-json'}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    summary = {
        'schema': 'jity-task-multifact/2', 'turns': len(doc.get('turns') or []),
        'cases': len(cases), 'tasks': len({c['taskId'] for c in cases}),
        'owners': len({c['ownerId'] for c in cases}),
        'avgEvents': round(sum(c['eventCount'] for c in cases) / max(1, len(cases)), 1),
        'maxEvents': max((c['eventCount'] for c in cases), default=0),
        'turnsSpannedMean': round(sum(len({e['turnIndex'] for e in c['events']}) for c in cases)
                                  / max(1, len(cases)), 1),
        'casesWithSupportLinks': sum(bool(c['supportLinks']) for c in cases),
        'specCovered': sum(bool(c['spec']) for c in cases),
        'oldAchieved': sum(1 for c in cases if c['oldStatus'] == 'achieved'),
        'repeatDeduped': repeats,
        'usage': 'dev/regression; scenario evidence drove fixes, not independent',
        'runId': doc.get('runId'), 'arm': doc.get('arm'),
        'labelSource': 'raw taskLedger.seenFacts + state snapshot diff',
        'turnTable': turn_table, 'turnStateDiffs': turn_diffs,
    }
    out.with_suffix('.summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
