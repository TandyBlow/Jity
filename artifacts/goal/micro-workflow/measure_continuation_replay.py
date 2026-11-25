# -*- coding: utf-8 -*-
"""Fixed-input replay of recorded continuation calls.

For each real continuation call, rebuild the scene from the last point of that
round, generate the same candidates the browser port would, run the four heads,
and compare the accepted character set with the recorded LLM proposal+judgment.
This is a replay on the recorded end-of-round state, not a full-turn A/B.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODEL = ROOT / 'frontend/public/micro/continuation-heads-int8.onnx'
sys.path.insert(0, str(PUB))
from make_continuation_data import candidates_for, rank, repeat_label  # noqa: E402

KEYS = ('novelty', 'unfinished', 'necessity', 'intervene')
THRESHOLDS = {'novelty': 0.5, 'unfinished': 0.4, 'necessity': 0.5, 'intervene': 0.5}


def current_view(state):
    view = json.loads(json.dumps(state['initial']))
    for cid, cur in state['characters'].items():
        view['characters'][cid]['initialPosition'] = cur['position']
        view['characters'][cid]['tasks'] = cur['tasks']
    for iid, cur in state['items'].items():
        view['items'][iid]['initialPosition'] = cur['position']
    return view


def entity_name(state, eid):
    init = state['initial']
    return (init['characters'].get(eid) or {}).get('name') or (init['items'].get(eid) or {}).get('name') or eid


def recent_lines(state, points, round_id):
    lines = []
    for point in points.values():
        if point.get('roundId') != round_id:
            continue
        for eid, delta in (point.get('entityDeltas') or {}).items():
            name = entity_name(state, eid)
            if delta.get('positionSet'):
                container = delta['positionSet'].get('containerId')
                lines.append(f'{name}移动到{entity_name(state, container)}')
            for change in delta.get('appearanceChanges') or []:
                lines.append(f'{name}外貌变化：{change.get("text") or "更新"}')
            if delta.get('sanitySet') is not None:
                lines.append(f'{name}理智变为{delta["sanitySet"]}')
            if delta.get('tasksAchieved'):
                lines.append(f'{name}完成任务')
    return lines[-4:]


def main(paths):
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    session = ort.InferenceSession(str(MODEL), providers=['CPUExecutionProvider'])
    summary = Counter()
    detail = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding='utf8'))
        for turn in data.get('turns') or []:
            product = turn.get('product') or {}
            calls = [call for call in (product.get('semanticCalls') or []) if call.get('task') == 'continuation']
            if not calls:
                continue
            transport = (turn.get('snapshotAfterTurn') or {}).get('transport') or {}
            points = transport.get('points') or {}
            point_states = transport.get('pointStates') or {}
            state_final = transport.get('state')
            if not state_final:
                continue
            history = []
            for call in calls:
                summary['calls'] += 1
                round_id = call.get('key')
                round_points = [p for p in points.values() if p.get('roundId') == round_id]
                state = state_final
                digest = None
                if round_points:
                    last = round_points[-1]
                    ps = point_states.get(last.get('pointId')) or {}
                    state = ps.get('state') or state
                    digest = ps.get('stateDigest')
                view = current_view(state)
                recent = recent_lines(state, points, round_id)
                # LLM arm: accepted = likely && related, one per character.
                proposed, accepted = [], []
                raw_candidates, judgments = [], []
                try:
                    raw = json.loads(call.get('raw') or '')
                except Exception:
                    raw = {}
                # The recorded raw may contain proposal and judgment in one
                # concatenated string (older runs); parse both halves.
                if 'candidates' in raw:
                    raw_candidates = raw['candidates']
                if 'judgments' in raw:
                    judgments = raw['judgments']
                if not raw_candidates and isinstance(call.get('raw'), str):
                    for chunk in call['raw'].split('---'):
                        try:
                            value = json.loads(chunk)
                        except Exception:
                            continue
                        if isinstance(value, dict):
                            raw_candidates = value.get('candidates') or raw_candidates
                            judgments = value.get('judgments') or judgments
                proposed = [row.get('characterId') for row in raw_candidates if isinstance(row, dict)]
                by_id = {f'c{index + 1}': row.get('characterId') for index, row in enumerate(raw_candidates) if isinstance(row, dict)}
                for judgment in judgments:
                    if not isinstance(judgment, dict):
                        continue
                    cid = by_id.get(judgment.get('candidateId')) or judgment.get('characterId')
                    if judgment.get('likely') and judgment.get('related') and cid and cid not in accepted:
                        accepted.append(cid)
                protagonist = state['protagonistId']
                visible = sorted(cid for cid in state['characters']
                                 if cid != protagonist and _room(state, cid) == _room(state, protagonist))[:4]
                accepted = [cid for cid in accepted if cid in visible]
                rows = []
                for character_id in visible:
                    cands, _room_name, _visible = candidates_for(view, character_id, bool(recent))
                    cands = sorted(cands, key=rank)[:6]
                    for row in cands:
                        repeat = 'new'
                        for old in history:
                            if old['characterId'] == character_id and old['text'] == row['text']:
                                repeat = 'same_world' if digest and old.get('digest') == digest else 'new_world'
                        involves = protagonist in row['target_ids'] or view['characters'][protagonist]['name'] in row['text']
                        task_pending = bool(row['task_id'])
                        context = (
                            f"现场：本轮事件={'；'.join(recent) or '无'}；重复={repeat_label(repeat)}；"
                            f"任务状态={'未完成' if task_pending else '无待办'}；涉及主角={'是' if involves else '否'}；"
                            f"类别={row['category']}；角色={view['characters'][character_id]['name']}；位置={_room_name}；"
                            f"个性={view['characters'][character_id].get('initialPersonality', '')[:40]}"
                        )
                        enc = tok(context, row['text'], truncation=True, max_length=160)
                        logits = session.run(None, {
                            'input_ids': np.array([enc['input_ids']], dtype=np.int64),
                            'attention_mask': np.array([enc['attention_mask']], dtype=np.int64),
                        })
                        scores = {key: 1 / (1 + np.exp(-float(value[0]))) for key, value in zip(KEYS, logits)}
                        rows.append({'characterId': character_id, 'text': row['text'], 'category': row['category'],
                                     'repeat': repeat, 'involves': involves, 'scores': scores})
                best = {}
                for row in rows:
                    if row['repeat'] == 'same_world' or row['category'] == 'wait':
                        continue
                    adjusted = {**row['scores'], 'intervene': max(row['scores']['intervene'], 0.75 if row['involves'] else 0)}
                    passed = (adjusted['novelty'] >= THRESHOLDS['novelty']
                              and adjusted['unfinished'] >= THRESHOLDS['unfinished']
                              and adjusted['necessity'] >= THRESHOLDS['necessity']
                              and adjusted['intervene'] < THRESHOLDS['intervene'])
                    total = adjusted['novelty'] + adjusted['unfinished'] + adjusted['necessity'] - adjusted['intervene']
                    if passed and (row['characterId'] not in best or total > best[row['characterId']][0]):
                        best[row['characterId']] = (total, row['text'])
                micro = sorted(best)
                summary['llm_continue'] += int(bool(accepted))
                summary['micro_continue'] += int(bool(micro))
                summary['same_set'] += int(set(micro) == set(accepted))
                summary['micro_only'] += int(bool(set(micro) - set(accepted)))
                summary['llm_only'] += int(bool(set(accepted) - set(micro)))
                detail.append({
                    'file': Path(path).name, 'roundId': round_id,
                    'visible': visible, 'proposed': proposed, 'llm': accepted,
                    'micro': micro, 'microTexts': {cid: text for cid, (_total, text) in best.items()},
                })
                for cid in accepted:
                    text = next((row.get('text') for row in raw_candidates if row.get('characterId') == cid), '')
                    history.append({'characterId': cid, 'text': text or '', 'digest': digest})
    print(json.dumps({'summary': dict(summary), 'detail': detail}, ensure_ascii=False, indent=1))


def _room(state, entity_id):
    pos = state['characters'][entity_id]['position']
    container = pos['containerId']
    seen = set()
    while container in state['items'] and container not in seen:
        seen.add(container)
        container = state['items'][container]['position']['containerId']
    if container in state['characters']:
        return _room(state, container)
    return container


if __name__ == '__main__':
    main(sys.argv[1:] or sorted(PUB.glob('evidence-*.json')))
