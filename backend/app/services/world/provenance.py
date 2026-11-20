"""Fact provenance and evidence-typed ordering relations.

Two different things are kept apart on purpose:

  * a ``point`` is when the authority committed something. Point order plus a
    positive time advance proves that *time passed*; it does not prove that
    the two facts' events happened in that order.
  * an ``event`` (one recorded change item inside a point) is what actually
    happened. Only events can be ordered, and only when each fact is bound to
    the event that produced it.

A fact bound to more than one point is a sustained state seen at several
commits. It has no single occurrence time, so it can never be ordered.
"""

POINT, EVENT = 'point', 'event'
UNIT_SECONDS = {'second': 1, 'minute': 60, 'hour': 3600}


class ProvenanceError(ValueError):
    pass


def _seconds(time_json):
    if not time_json or time_json.get('boundary') != 'elapsed':
        return 0
    duration = time_json.get('duration') or {}
    return int(duration.get('amount') or 0) * UNIT_SECONDS.get(duration.get('unit'), 0)


def bind_fact(fact_id, world_id, point_ids, evidence_ids):
    """The stable source record an extracted fact inherits.

    Deliberately a separate structure: it is never mixed into the N4 text
    serialization (``fact_contract``), which stays exactly as frozen.
    """
    if not world_id:
        raise ProvenanceError('缺少 worldId')
    points = tuple(dict.fromkeys(point_ids))
    events = tuple(dict.fromkeys(evidence_ids))
    if not points:
        raise ProvenanceError(f'{fact_id}: 没有来源点')
    if not events:
        raise ProvenanceError(f'{fact_id}: 没有来源事件，只有点是追溯不到事件的')
    if len(points) > 1:
        return {'factId': fact_id, 'worldId': world_id, 'pointIds': points,
                'evidenceIds': events, 'sustained': True}
    return {'factId': fact_id, 'worldId': world_id, 'pointIds': points,
            'evidenceIds': events, 'sustained': False}


def _elapsed_between(a, b, points):
    """Seconds between two points on one chain, or None when not comparable."""
    by_id = {p['id']: p for p in points}
    if a not in by_id or b not in by_id:
        return None
    if by_id[a].get('worldId') != by_id[b].get('worldId'):
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
    return sum(_seconds(by_id[p].get('time')) for p in chain[1:])


def validate_relations(relations, facts, points, evidence_index):
    """Validate ``before`` relations against real evidence.

    facts:          {factId: provenance}   (from bind_fact)
    points:         [{'id','worldId','previousPointId','time'}]
    evidence_index: {evidenceId: pointId}  (from the evidence ledger)
    """
    problems = []
    claimed = []
    for i, relation in enumerate(relations):
        tag = f'relations[{i}]'
        if relation.get('type') != 'before':
            problems.append(f'{tag}: 第一版只允许 before，得到 {relation.get("type")!r}')
            continue
        source, target = relation.get('fromFactId'), relation.get('toFactId')
        if source not in facts or target not in facts:
            problems.append(f'{tag}: factId 不在计划内（{source!r}→{target!r}）')
            continue
        if source == target:
            problems.append(f'{tag}: 自指（{source}→{target}）')
            continue
        claimed.append((source, target))
        evidence = relation.get('evidence') or []
        if not evidence:
            problems.append(f'{tag}: 缺少 evidence')
            continue
        bad_type = [e for e in evidence if e.get('type') not in (POINT, EVENT)]
        if bad_type:
            problems.append(f'{tag}: 证据必须带 type=point|event，得到 {bad_type[:2]}')
            continue
        resolved = {}
        for side in (source, target):
            bound = facts[side]
            if bound.get('sustained'):
                problems.append(f'{tag}: {side} 绑定多个点（持续状态），无法排序')
                resolved[side] = None
                continue
            event_refs = [e['evidenceId'] for e in evidence
                          if e.get('type') == EVENT and 'evidenceId' in e]
            if not event_refs:
                problems.append(
                    f'{tag}: {side} 只有点证据，点顺序不构成事件先后')
                resolved[side] = None
                continue
            own = [e for e in event_refs if e in bound['evidenceIds']]
            if not own:
                problems.append(
                    f'{tag}: {side} 的证据事件不属于该事实 {event_refs[:2]}')
                resolved[side] = None
                continue
            unknown = [e for e in own if e not in evidence_index]
            if unknown:
                problems.append(f'{tag}: 证据事件无法追溯 {unknown[:2]}')
                resolved[side] = None
                continue
            resolved[side] = evidence_index[own[0]]
        if resolved.get(source) is None or resolved.get(target) is None:
            continue
        if resolved[source] == resolved[target]:
            problems.append(f'{tag}: 两端证据在同一时间点，没有先后')
            continue
        elapsed = _elapsed_between(resolved[source], resolved[target], points)
        if elapsed is None:
            problems.append(f'{tag}: 两端证据点不在同一 chain，无法比较')
            continue
        if elapsed <= 0:
            problems.append(f'{tag}: 两端之间时间推进为 0，不构成先后证据')
            continue
    if _has_cycle(claimed):
        problems.append('关系成环')
    return problems


def _has_cycle(edges):
    adjacency = {}
    for source, target in edges:
        adjacency.setdefault(source, []).append(target)
    state = {}

    def visit(node):
        state[node] = 1
        for nxt in adjacency.get(node, []):
            if state.get(nxt) == 1:
                return True
            if state.get(nxt) is None and visit(nxt):
                return True
        state[node] = 2
        return False

    return any(state.get(node) is None and visit(node) for node in list(adjacency))


VALIDATOR_VERSION = 'world-relation-validator/1'


def authorize(facts, relations, points, evidence_index):
    """The only thing N3 may use: a verdict, not the client's own guesses.

    Validated per relation, so one bad request cannot void the others. The
    aggregate verdict is ``pass`` (all accepted), ``partial`` (some accepted)
    or ``reject`` (none).
    """
    accepted, rejected = [], []
    for index, relation in enumerate(relations):
        problems = validate_relations([relation], facts, points, evidence_index)
        if problems:
            rejected.append({'relation': {'type': relation.get('type'),
                                          'fromFactId': relation.get('fromFactId'),
                                          'toFactId': relation.get('toFactId')},
                             'problems': problems})
            continue
        accepted.append({
            'type': 'before',
            'fromFactId': relation['fromFactId'],
            'toFactId': relation['toFactId'],
            'evidence': relation['evidence'],
            'authorization': {'verdict': 'pass', 'validatorVersion': VALIDATOR_VERSION},
        })
    if accepted and not rejected:
        verdict = 'pass'
    elif accepted:
        verdict = 'partial'
    else:
        verdict = 'reject'
    return {'verdict': verdict, 'validatorVersion': VALIDATOR_VERSION,
            'relations': accepted, 'rejected': rejected, 'problems': []}
