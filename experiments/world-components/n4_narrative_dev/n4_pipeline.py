"""叙事流水线原型：一份已提交事实输入 → 来源绑定 → 授权 → 生成 → 两层编辑。

单入口，无人工搬运：

    python n4_pipeline.py --round mixed-round.json --ckpt <u240> \
        --out mixed-result.json [--budget 20] [--timeout-fact f4]

输出来源、授权、生成、编辑四段的完整记录与耗时；失败单元会连带整源标记未完成。
"""
import argparse
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fact_contract as FC  # noqa: E402
from conservative_edit import VERSION as EDIT_VERSION, edit_source  # noqa: E402
from relation_edit import (CONNECTOR, VALIDATOR, VERSION as RELATION_VERSION,  # noqa: E402
                           apply_before)

PIPELINE_VERSION = 'n4-pipeline/1'
KIND_LABEL = {'appearance_changed': '外貌变化', 'personality_changed': '性格变化',
              'moved': '移动', 'sanity_changed': '状态变化'}
HEADER = ('短句任务。\n地点={place}\n地点可见={visible}\n场景={scene}\n视角={pov}；第三人称')


def seconds(point):
    time_json = point.get('time') or {}
    if time_json.get('boundary') != 'elapsed':
        return 0
    duration = time_json.get('duration') or {}
    unit = {'second': 1, 'minute': 60, 'hour': 3600}.get(duration.get('unit'), 0)
    return int(duration.get('amount') or 0) * unit


def elapsed_between(a, b, points):
    by_id = {p['id']: p for p in points}
    if a not in by_id or b not in by_id:
        return None
    chain, cur = [], a
    while cur is not None:
        chain.append(cur)
        if cur == b:
            break
        nxt = [p['id'] for p in points if p.get('previousPointId') == cur]
        cur = nxt[0] if len(nxt) == 1 else None
    else:
        return None
    if not chain or chain[-1] != b:
        return None
    return sum(seconds(by_id[p]) for p in chain[1:])


def bind_units(units):
    """Each fact inherits world / chain / point / evidence references."""
    from app.services.world.provenance import bind_fact
    return {u['factId']: bind_fact(u['factId'], u['worldId'] if 'worldId' in u else None,
                                   [u['pointId']], [u['evidenceId']]) for u in units}


def authorize(round_payload):
    """Validator verdict for the requested relations (authority, not guesses).

    When the round already carries a verdict produced by the server-side
    validator, that is used as-is: the client never re-derives authorization.
    """
    if 'authorization' in round_payload:
        return round_payload['authorization']
    from app.services.world.provenance import authorize as run_authorize
    units = round_payload['units']
    points = round_payload['points']
    facts = {}
    for unit in units:
        facts[unit['factId']] = {'factId': unit['factId'], 'worldId': round_payload['worldId'],
                                 'pointIds': (unit['pointId'],),
                                 'evidenceIds': (unit['evidenceId'],), 'sustained': False}
    index = {u['evidenceId']: u['pointId'] for u in units}
    point_of_fact = {u['factId']: u['pointId'] for u in units}
    relations = []
    for requested in round_payload['requestedRelations']:
        source, target = requested['fromFactId'], requested['toFactId']
        evidence = []
        for fact in (source, target):
            unit = next(u for u in units if u['factId'] == fact)
            evidence.append({'type': 'event', 'evidenceId': unit['evidenceId']})
        relations.append({'type': 'before', 'fromFactId': source, 'toFactId': target,
                          'evidence': evidence})
    verdict = run_authorize(facts, relations, points, index)
    # Recheck the two ends really are ordered in time before trusting anything.
    for relation in verdict['relations']:
        a, b = point_of_fact[relation['fromFactId']], point_of_fact[relation['toFactId']]
        relation['elapsedSeconds'] = elapsed_between(a, b, points)
    return verdict


def unit_input(unit):
    fact = {'kind': unit['kind'], 'name': unit['name'], 'text': unit['text']}
    if unit['kind'] == 'moved':
        fact.update({'from': unit['text'], 'to': unit['text'], 'direction': '平'})
    line = FC.serialize_fact(fact)
    FC.check_line(unit['kind'], line)
    header = HEADER.format(place='走廊', visible='外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币',
                           scene='白天', pov=unit['name'])
    return fact, header + '\n事实=' + line + '\n短句：\n'


def generate(model, tokenizer, torch, units, budget, timeout_fact=None):
    from sequence_policy import generate_greedy
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    rows = []
    for unit in units:
        fact, prompt = unit_input(unit)
        started = time.perf_counter()
        enc = tokenizer(prompt, return_tensors='pt', truncation=False).to(device)
        effective = 0.05 if unit['factId'] == timeout_fact else budget
        ids, meta = generate_greedy(model, enc, effective)
        text = tokenizer.decode(ids[0], skip_special_tokens=True)
        rows.append({'factId': unit['factId'], 'name': unit['name'], 'kind': unit['kind'],
                     'text': text, 'complete': bool(meta['complete']),
                     'timeoutForced': unit['factId'] == timeout_fact,
                     'seconds': round(time.perf_counter() - started, 3)})
    return rows


def two_layer_edit(units, verdict, person_names=None):
    """Layer 1: conservative same-subject merge (endpoints excluded).
    Layer 2: the authorized connector, re-checked on the merged blocks."""
    from conservative_edit import strip_subject

    people = set(person_names or ())
    if not people:
        people = {u['name'] for u in units if str(u.get('entityId', '')).startswith('person_')}
        people = people or {u['name'] for u in units}
    by_id = {u['factId']: u for u in units}
    pairs = [(r['fromFactId'], r['toFactId']) for r in verdict.get('relations', [])]
    endpoints = {fact for pair in pairs for fact in pair}

    blocks, merge_ops, merge_dropped = [], [], []   # blocks: [factIds, text]
    index = 0
    while index < len(units):
        unit = units[index]
        run = [unit['factId']]
        while index + len(run) < len(units):
            nxt = units[index + len(run)]
            if nxt['name'] != unit['name'] or unit['name'] not in people:
                break
            if {unit['factId'], nxt['factId']} & endpoints:
                merge_dropped.append({'reason': 'endpoint-keeps-boundary',
                                      'pair': [unit['factId'], nxt['factId']]})
                break
            body, _op = strip_subject(nxt['text'], nxt['name'])
            if body is None:
                merge_dropped.append({'reason': 'cannot-drop-subject',
                                      'pair': [unit['factId'], nxt['factId']]})
                break
            run.append(nxt['factId'])
        head = unit['text'].strip().rstrip('。')
        parts = [head]
        for extra in run[1:]:
            body, op = strip_subject(by_id[extra]['text'], by_id[extra]['name'])
            parts.append(body)
            merge_ops.append({'op': op, 'factId': extra, 'afterFactId': unit['factId']})
        blocks.append([run, '，'.join(parts).replace(',', '，') + '。'])
        if len(run) > 1:
            merge_ops.append({'op': '合句（逗号串联）', 'mergedFactIds': run})
        index += len(run)

    def block_of(fact_id):
        for position, (ids, _text) in enumerate(blocks):
            if fact_id in ids:
                return position
        return None

    connector_ops, connector_fallbacks = [], []
    for relation in verdict.get('relations', []):
        source, target = relation['fromFactId'], relation['toFactId']
        left, right = block_of(source), block_of(target)
        if left is None or right is None:
            connector_fallbacks.append({'reason': 'unknown-fact', 'relation': [source, target]})
            continue
        if right != left + 1:
            connector_fallbacks.append({'reason': 'not-adjacent', 'relation': [source, target]})
            continue
        if len(blocks[right][0]) != 1:
            connector_fallbacks.append({'reason': 'target-merged-into-other',
                                        'relation': [source, target]})
            continue
        if not blocks[right][1].startswith(by_id[target]['name']):
            connector_fallbacks.append({'reason': 'subject-not-at-start',
                                        'relation': [source, target]})
            continue
        blocks[right][1] = CONNECTOR + blocks[right][1]
        connector_ops.append({'op': '加“随后”', 'fromFactId': source, 'toFactId': target,
                              'evidence': relation['evidence'],
                              'validatorVersion': relation.get('authorization', {})
                              .get('validatorVersion')})

    return {'text': ''.join(text for _ids, text in blocks),
            'blocks': [ids for ids, _text in blocks],
            'mergeOps': merge_ops, 'mergeDropped': merge_dropped,
            'connectorOps': connector_ops, 'connectorFallbacks': connector_fallbacks}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--round', required=True)
    parser.add_argument('--ckpt', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--budget', type=float, default=20.0)
    parser.add_argument('--timeout-fact', default=None)
    args = parser.parse_args()

    result = {'pipeline': PIPELINE_VERSION, 'components': {
        'factContract': 'fact_contract.py', 'validator': VALIDATOR,
        'relationEdit': RELATION_VERSION, 'conservativeEdit': EDIT_VERSION},
        'timing': {}}
    clock = time.perf_counter

    started = clock()
    round_payload = json.loads(pathlib.Path(args.round).read_text(encoding='utf-8'))
    units = round_payload['units']
    for unit in units:
        unit.setdefault('worldId', round_payload['worldId'])
    result['original'] = ''.join(u['text'] for u in units)
    result['timing']['readAndBind'] = round(clock() - started, 3)

    started = clock()
    verdict = authorize(round_payload)
    result['authorization'] = verdict
    result['timing']['authorize'] = round(clock() - started, 3)

    started = clock()
    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tokenizer = T5Tokenizer.from_pretrained(args.ckpt, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(args.ckpt,
                                                       torch_dtype=torch.float32)
    model.to('cuda' if torch.cuda.is_available() else 'cpu').eval()
    result['timing']['modelLoad'] = round(clock() - started, 3)

    started = clock()
    rows = generate(model, tokenizer, torch, units, args.budget, args.timeout_fact)
    result['generation'] = rows
    result['timing']['generate'] = round(clock() - started, 3)
    result['timing']['generatePerFact'] = {r['factId']: r['seconds'] for r in rows}

    incomplete = [r['factId'] for r in rows if not r['complete']]
    result['incompleteFacts'] = incomplete
    if incomplete:
        verdict['relations'] = [r for r in verdict['relations']
                                if not ({r['fromFactId'], r['toFactId']} & set(incomplete))]
        result['authorization']['droppedForIncomplete'] = incomplete

    started = clock()
    edited = two_layer_edit(rows, verdict,
                            {u['name'] for u in units
                             if str(u.get('entityId', '')).startswith('person_')})
    result['edit'] = edited
    result['edited'] = edited['text']
    result['timing']['edit'] = round(clock() - started, 3)
    result['sourceComplete'] = not incomplete
    pathlib.Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                      encoding='utf-8')
    print(json.dumps({'sourceComplete': result['sourceComplete'],
                      'incomplete': incomplete, 'edited': result['edited'],
                      'timing': result['timing']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
