"""Program assembly for narrow D06 heads: labels/references, never JSON generation.

The provider must perform real trained primitive inference or return incomplete.
All calls preserve the exact full original payload as well as the query and
current candidates. Candidate enumeration contains existing identities only.
"""
from __future__ import annotations

from copy import deepcopy
from short_contracts import Completion, ContractError, digest, result, incomplete

COMPONENTS = frozenset({'U1.2', 'U2.1', 'U5.1', 'D06.P.mapping'})
RELATIONS = ('under', 'above', 'beside', 'in_front_of', 'behind')


def _require(ok, reason):
    if not ok:
        raise ContractError(reason)


def _input(payload, query, candidates=None):
    # The aggregate input often already uses `candidates` for prior stages.
    # Preserve it unmodified inside originalPayload before placing the complete
    # legal reference candidate list where the pointer head expects it.
    out = deepcopy(payload)
    out['originalPayload'] = deepcopy(payload)
    out['semanticQuery'] = deepcopy(query)
    if candidates is not None:
        out['candidates'] = deepcopy(candidates)
    return out


def _primitive(provider, component, payload, query, *, labels=None, candidates=None):
    answer = provider(component, _input(payload, query, candidates))
    _require(isinstance(answer, Completion), component + ': Completion required')
    _require(answer.status == 'result', component + ': ' + str(answer.reason or answer.status))
    value = answer.value
    if labels is not None:
        _require(isinstance(value, str) and value in labels, component + ': invalid judgment label')
    if candidates is not None:
        ids = [x['id'] for x in candidates]
        _require(len(ids) == len(set(ids)), 'duplicate legal reference candidate')
        _require(isinstance(value, str) and value in ids, component + ': unregistered reference')
    return value


def _world(payload):
    world = payload.get('world') or payload.get('context', {}).get('world')
    from short_settlement import _world as validate_world
    entities, people, _ = validate_world(world)
    candidates = []
    for kind in ('locations', 'items', 'characters'):
        for key, entity in world[kind].items():
            candidates.append({'id': key, 'kind': kind, 'initial': deepcopy(world['initial'][kind][key]),
                               'state': deepcopy(entity)})
    return world, entities, people, candidates


def _positions(provider, payload):
    from short_settlement import validate_positions
    world, entities, people, references = _world(payload)
    ids = payload['entityIds']
    _require(isinstance(ids, list) and len(ids) == len(set(ids)) and set(ids) <= (set(world['items']) | set(people)),
             'position target coverage invalid')
    rows = []
    for entity in ids:
        query = {'entityId': entity, 'currentPositions': deepcopy(rows)}
        candidates = [c for c in references if c['id'] != entity]
        container = _primitive(provider, 'U1.2.container', payload, query, candidates=candidates)
        query['selectedContainerId'] = container
        slot_mode = _primitive(provider, 'U1.2.slot_mode', payload, query, labels=('none', 'select'))
        slot = None
        if slot_mode == 'select':
            initial = next(c['initial'] for c in references if c['id'] == container)
            slots = [{'id': x['id'], 'containerId': container, 'label': x['label']} for x in initial.get('slots', [])]
            _require(slots, 'slot selected but chosen container has no slots')
            slot = _primitive(provider, 'U1.2.slot', payload, query, candidates=slots)
        query['selectedSlotId'] = slot
        relative_mode = _primitive(provider, 'U1.2.relative_mode', payload, query, labels=('none', 'select'))
        relative = None
        if relative_mode == 'select':
            target = _primitive(provider, 'U1.2.relative_entity', payload, query, candidates=candidates)
            query['relativeEntityId'] = target
            relation = _primitive(provider, 'U1.2.relation', payload, query, labels=RELATIONS)
            relative = {'entityId': target, 'relation': relation}
        rows.append({'entityId': entity, 'position': {'containerId': container, 'slotId': slot, 'relativeTo': relative}})
    # Full simultaneous graph only; earlier proposals do not constrain later
    # semantic choices by their transient sequential application.
    validate_positions(world, {r['entityId']: r['position'] for r in rows})
    verdict = _primitive(provider, 'U1.2.audit', payload, {'positions': rows}, labels=('pass', 'reject'))
    _require(verdict == 'pass', 'joint position semantic audit rejected')
    return {'positions': rows}


def _descriptions(provider, component, payload, max_operations, max_references):
    _, entities, people, _ = _world(payload)
    targets = payload['entityIds']; active = payload['activeRecords']
    expected = people if component == 'U5.1' else entities
    _require(isinstance(targets, list) and len(targets) == len(set(targets)) and set(targets) <= set(expected), 'description entities invalid')
    _require(isinstance(active, dict) and set(targets) <= set(active), 'active description records missing')
    operations = []
    all_record_ids = []
    for entity in targets:
        records = active[entity]
        _require(isinstance(records, dict), 'active records must be keyed by record ID')
        for key, record in records.items():
            _require(record.get('id') == key and record.get('active') is True, 'inactive or wrong record identity')
        _require(not set(all_record_ids).intersection(records), 'description record identity repeated across entities')
        all_record_ids += list(records)
        touched, assigned = 0, set()
        while True:
            query = {'entityId': entity, 'operations': deepcopy(operations), 'unassignedRecordIds': [r for r in records if r not in assigned]}
            label = _primitive(provider, component + '.next_op', payload, query, labels=('keep', 'remove', 'add', 'replace', 'end'))
            if label == 'end':
                _require(touched > 0, 'entity ended without explicit keep/operation')
                _require(assigned == set(records), 'description ended before all old records were judged')
                break
            _require(touched < max_operations, 'description_operation_budget_pause')
            selected = []
            if label != 'add':
                while True:
                    query = {'entityId': entity, 'operation': label, 'operations': deepcopy(operations), 'selectedRecordIds': selected}
                    more = _primitive(provider, component + '.record_more', payload, query, labels=('more', 'end'))
                    if more == 'end':
                        break
                    _require(len(selected) < max_references, 'description_reference_budget_pause')
                    candidates = [{'id': key, 'entityId': entity, 'record': deepcopy(record)} for key, record in records.items()
                                  if key not in assigned and key not in selected]
                    _require(candidates, 'description requested a record after references were exhausted')
                    selected.append(_primitive(provider, component + '.record', payload, query, candidates=candidates))
                _require(label == 'keep' or selected, 'remove/replace requires an existing record')
            assigned.update(selected)
            operations.append({'entityId': entity, 'op': label, 'recordIds': selected})
            touched += 1
    verdict = _primitive(provider, component + '.audit', payload, {'operations': operations}, labels=('pass', 'reject'))
    _require(verdict == 'pass', 'description semantic audit rejected')
    return {'checkedEntityIds': deepcopy(targets), 'checkedRecordIds': all_record_ids, 'operations': operations}


def _mapping(provider, payload, max_references):
    facts = deepcopy(payload['facts'])
    if payload.get('timeFact') is not None:
        facts.append(deepcopy(payload['timeFact']))
    _require(isinstance(facts, list) and len({f['id'] for f in facts}) == len(facts), 'duplicate fact identity')
    refs = payload['candidateRefs']
    _require(isinstance(refs, list), 'candidate references required')
    available = {digest(r): r for r in refs}
    _require(len(available) == len(refs), 'duplicate state candidate reference')
    mappings, used = [], set()
    for fact in facts:
        query = {'factId': fact['id'], 'mappings': deepcopy(mappings)}
        kind = _primitive(provider, 'D06.P.mapping.kind', payload, query, labels=('state', 'unchanged', 'transient', 'gap'))
        _require(kind != 'gap', 'interface_gap: required fact has no existing protocol representation')
        selected = []
        if kind == 'state':
            while True:
                query = {'factId': fact['id'], 'kind': kind, 'mappings': deepcopy(mappings), 'selectedTargets': deepcopy(selected)}
                more = _primitive(provider, 'D06.P.mapping.more', payload, query, labels=('more', 'end'))
                if more == 'end':
                    break
                _require(len(selected) < max_references, 'mapping_reference_budget_pause')
                selected_ids = {digest(r) for r in selected}
                candidates = [{'id': 'candidate:' + key, 'reference': deepcopy(ref)} for key, ref in available.items() if key not in selected_ids]
                _require(candidates, 'mapping requested exhausted references')
                chosen = _primitive(provider, 'D06.P.mapping.target', payload, query, candidates=candidates)
                selected.append(deepcopy(available[chosen.removeprefix('candidate:')]))
            _require(selected, 'state fact requires at least one model-selected consequence')
        used.update(digest(r) for r in selected)
        mappings.append({'factId': fact['id'], 'kind': kind, 'targets': selected})
    _require(used == set(available), 'candidate consequence lacks semantic source selection')
    verdict = _primitive(provider, 'D06.P.mapping.audit', payload, {'mappings': mappings}, labels=('pass', 'reject'))
    _require(verdict == 'pass', 'fact/state semantic audit rejected')
    return {'verdict': verdict, 'mappings': mappings}


def assemble_update_head(provider, component, payload, *, max_operations=32, max_references=256):
    """Build one existing aggregate from trained primitive outputs only."""
    try:
        _require(component in COMPONENTS, 'unregistered_update_head')
        _require(type(max_operations) is int and max_operations > 0 and type(max_references) is int and max_references > 0,
                 'invalid primitive resource budget')
        _require(isinstance(payload, dict), 'complete payload required')
        if component == 'U1.2':
            value = _positions(provider, payload)
        elif component in ('U2.1', 'U5.1'):
            value = _descriptions(provider, component, payload, max_operations, max_references)
        else:
            value = _mapping(provider, payload, max_references)
        return result(value)
    except Exception as exc:
        return incomplete(component + ': ' + str(exc))
