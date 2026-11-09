"""D02–D04 candidate-only short-intent orchestration.

No action catalogue, semantic rule engine, legacy realizer fallback, service
writes or dice sampling lives here. A/B owns accepted identities and dice.
A model-reported audit pass is evidence to retain, not a quality certificate.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from short_contracts import Completion, ContractError, digest, result, empty, incomplete

ROLES = frozenset({'subject', 'object', 'tool', 'recipient', 'destination'})
CHECKS = {
    'D02.4': ('dependencies', 'conditions', 'requirements'),
    'D02.5': ('actor', 'tools', 'objects', 'qualifiers', 'attempt'),
}


def _require(ok, message):
    if not ok:
        raise ContractError(message)


def _text(value, label):
    _require(isinstance(value, str) and bool(value.strip()), label + ': nonempty text required')
    return value


def _keys(value, keys):
    _require(isinstance(value, dict) and set(value) == set(keys), 'unexpected or missing output fields')
    return value


def _ids(value, expected=None):
    _require(isinstance(value, list) and all(isinstance(x, str) and x for x in value), 'ID list required')
    _require(len(set(value)) == len(value), 'duplicate IDs')
    if expected is not None:
        _require(set(value) == set(expected), 'incomplete or unknown coverage IDs')
    return value


def _entities(world):
    """Accept existing WorldState without lossy flattening into old lab format.

    Returned rows are an identity/name index only. Model payload retains the
    exact world including initial records, inactive changes and all tasks.
    """
    if isinstance(world, dict) and 'initial' in world:
        from short_settlement import _world as validate_world
        entities, people, _ = validate_world(world)
        registered = {}
        for kind in ('locations', 'items', 'characters'):
            for key, state in world[kind].items():
                initial = world['initial'][kind][key]
                _require(initial.get('id') == key, 'initial entity identity mismatch')
                _text(initial.get('name'), 'initial entity name')
                _text(initial.get('initialAppearance'), 'initial appearance')
                if kind == 'characters':
                    _text(initial.get('initialPersonality'), 'initial personality')
                registered[key] = {**copy.deepcopy(state), 'name': initial['name']}
        _require(world.get('protagonistId') in people, 'unknown world protagonist')
        return registered, set(people)
    from lab import _world
    people = _world(world)
    return {e['id']: e for kind in ('places', 'items', 'characters') for e in world[kind]}, people


def _context(context):
    """Validate complete fields; keep original bytes/extra context in every call."""
    _require(isinstance(context, dict), 'context required')
    _require({'world', 'actorId', 'protagonistId', 'advance', 'confirmedPrefix'} <= set(context),
             'missing current action context')
    def reject_review_material(value):
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = key.replace('_', '').replace('-', '').lower()
                if normalized.startswith(('gold', 'expected', 'future')) or normalized in {
                        'answer', 'answers', 'drafttarget', 'draftexpected', 'rubric', 'review', 'humanreview', 'sourcegroup'}:
                    raise ContractError('answer/review leakage into action input')
                reject_review_material(child)
        elif isinstance(value, list):
            for child in value:
                reject_review_material(child)
    try:
        entities, people = _entities(context['world'])
        reject_review_material(context)
    except ValueError as exc:
        raise ContractError(str(exc)) from exc
    _require(context['actorId'] in people and context['protagonistId'] in people, 'unknown actor')
    if 'initial' in context['world']:
        _require(context['world']['protagonistId'] == context['protagonistId'], 'protagonist binding mismatch')
    advance = context['advance']
    _require(isinstance(advance, dict) and {'inputText', 'intentStatus'} <= set(advance), 'missing input consumption state')
    _require(advance['intentStatus'] in ('pending', 'consumed', 'expired'), 'invalid input consumption state')
    _require(advance['inputText'] is None or isinstance(advance['inputText'], str), 'invalid player text')
    if advance['intentStatus'] == 'pending':
        _text(advance['inputText'], 'pending player input')
    _require(isinstance(context['confirmedPrefix'], list), 'confirmed prefix required')
    ids = []
    for row in context['confirmedPrefix']:
        _require(isinstance(row, dict) and row.get('memberId') in people, 'unknown confirmed actor')
        _text(row.get('actionText'), 'confirmed action')
        ids.append(row['memberId'])
    _ids(ids)
    return entities


def _call(session, component, payload):
    value = session.call(component, copy.deepcopy(payload))
    _require(isinstance(value, Completion), 'model adapter must return Completion')
    if value.status == 'incomplete':
        raise ContractError(component + ': ' + str(value.reason))
    _require(value.status == 'result', component + ': explicit result required; empty is not an answer')
    return copy.deepcopy(value.value)


def _audit(session, component, payload, fragment_ids):
    audit = _call(session, component, payload)
    _keys(audit, ('verdict', 'fragmentIds', 'checks', 'issues'))
    _ids(audit['fragmentIds'], fragment_ids)
    _keys(audit['checks'], CHECKS[component])
    _require(isinstance(audit['issues'], list), 'audit issues must be a list')
    for issue in audit['issues']:
        _keys(issue, ('fragmentId', 'code'))
        _require(issue['fragmentId'] in fragment_ids, 'issue points outside fragments')
        _text(issue['code'], 'issue code')
    _require(audit['verdict'] == 'pass' and not audit['issues']
             and all(x == 'pass' for x in audit['checks'].values()), component + ': semantic audit rejected')
    return audit


def _references(value, text, entities, actor, representation):
    _keys(value, ('verdict', 'references'))
    _require(value['verdict'] == 'pass', 'D02.3: binding audit rejected')
    refs = value['references']
    _require(isinstance(refs, list) and refs, 'fragment needs explicit subject binding')
    spans = []
    subjects = []
    for ref in refs:
        _keys(ref, ('role', 'entityId', 'start', 'end'))
        _require(ref['role'] in ROLES and ref['entityId'] in entities, 'invalid role/entity reference')
        start, end = ref['start'], ref['end']
        _require(type(start) is int and type(end) is int and 0 <= start < end <= len(text), 'invalid reference span')
        expected = entities[ref['entityId']]['name'] if representation == 'natural' else '[[' + ref['entityId'] + ']]'
        _require(text[start:end] == expected, 'reference does not match source name/marker')
        if ref['role'] == 'subject':
            subjects.append(ref['entityId'])
        if ref['role'] == 'recipient':
            _require(any(e['id'] == ref['entityId'] for e in entities.values() if 'sanity' in e), 'recipient must be a character')
        spans.append((start, end))
    # One span can have two semantic roles, but nonidentical overlaps reject.
    unique = sorted(set(spans))
    _require(all(a[1] <= b[0] for a, b in zip(unique, unique[1:])), 'overlapping reference spans')
    _require(actor in subjects, 'action actor missing from subject references')
    if representation == 'references':
        markers = {(m.start(), m.end()) for m in re.finditer(r'\[\[[^\[\]]+\]\]', text)}
        _require(markers == set(spans), 'unbound or malformed reference markers')
        stripped = re.sub(r'\[\[[^\[\]]+\]\]', '', text)
        _require('[[' not in stripped and ']]' not in stripped, 'malformed reference marker')
    return refs


@dataclass(frozen=True)
class FrozenAction:
    """Immutable local candidate; acceptance still belongs to A/B."""
    actor_id: str
    opportunity_id: str
    context_digest: str
    text: str
    material_json: str
    content_digest: str

    def wire(self):
        return {'kind': 'act', 'text': self.text}

    def material(self):
        return json.loads(self.material_json)

    def verify(self):
        _text(self.actor_id, 'frozen actor')
        _text(self.opportunity_id, 'frozen opportunity')
        _text(self.text, 'frozen text')
        body = {'actorId': self.actor_id, 'opportunityId': self.opportunity_id,
                'contextDigest': self.context_digest, 'text': self.text, 'material': self.material()}
        _require(digest(body) == self.content_digest, 'frozen action tampered')
        return self



def restore_action(record, context, opportunity_id):
    """Restore the exact candidate; never regenerate fragments or change identity."""
    _keys(record, ('actor_id', 'opportunity_id', 'context_digest', 'text', 'material_json', 'content_digest'))
    restored = FrozenAction(**record).verify()
    _require(restored.actor_id == context['actorId'] and restored.opportunity_id == opportunity_id
             and restored.context_digest == digest(context), 'restored action belongs to another input/opportunity')
    return restored


def _freeze(context, opportunity_id, fragments, representation, audits):
    entities = _context(context)
    lines = []
    for fragment in fragments:
        text = fragment['text']
        if representation == 'references':
            # Replace verified spans once, right to left. Names may themselves
            # contain marker-looking strings; never recursively interpret them.
            replacements = {(r['start'], r['end']): entities[r['entityId']]['name'] for r in fragment['references']}
            for (start, end), name in sorted(replacements.items(), reverse=True):
                text = text[:start] + name + text[end:]
        lines.append(text)
    # Newlines are separators only: no inferred connective, verb or success.
    text = '\n'.join(lines)
    material = {'representation': representation, 'fragments': fragments, 'audits': audits,
                'renderedFragments': [{'id': context['actorId'] + ':' + f['fragmentId'], 'text': line}
                                      for f, line in zip(fragments, lines)]}
    body = {'actorId': context['actorId'], 'opportunityId': opportunity_id,
            'contextDigest': digest(context), 'text': text, 'material': material}
    return FrozenAction(context['actorId'], opportunity_id, digest(context), text,
                        json.dumps(material, ensure_ascii=False, sort_keys=True), digest(body))


def produce_intent(session, context, opportunity_id, *, max_fragments=8,
                   representation='natural', reaction_constraints=None):
    """D02.1–.6. No retries/candidate fallback; budget exhaustion is incomplete.

    D04 supplies reaction_constraints and bypasses ordinary act/skip judgment.
    A single unsplittable intention is accepted as one semantic fragment.
    """
    try:
        context = copy.deepcopy(context)
        entities = _context(context)
        _text(opportunity_id, 'opportunity ID')
        _require(type(max_fragments) is int and max_fragments > 0, 'positive fragment budget required')
        _require(representation in ('natural', 'references'), 'unknown representation')
        if context['actorId'] in [x['memberId'] for x in context['confirmedPrefix']]:
            raise ContractError('already frozen actor: reuse confirmed action, do not regenerate')
        payload = {'context': copy.deepcopy(context), 'opportunityId': opportunity_id,
                   'representation': representation, 'reactionConstraints': reaction_constraints}
        if reaction_constraints is None:
            decision = _call(session, 'D02.1', payload)
            _require(decision in ('act', 'skip'), 'D02.1: unknown decision')
            if decision == 'skip':
                return empty()
        fragments = []
        while True:
            current = {**payload, 'fragments': copy.deepcopy(fragments)}
            nxt = _call(session, 'D02.2', current)
            _require(isinstance(nxt, dict), 'D02.2: fragment or end required')
            if nxt.get('kind') == 'end':
                _keys(nxt, ('kind',))
                _require(bool(fragments), 'act/reaction ended without an action')
                break
            _keys(nxt, ('kind', 'text'))
            _require(nxt['kind'] == 'fragment', 'unknown next-fragment label')
            _text(nxt['text'], 'fragment')
            _require(len(fragments) < max_fragments, 'fragment_budget_pause: no explicit end within limit')
            fragment_id = 'fragment-' + str(len(fragments) + 1)
            binding = _call(session, 'D02.3', {**current, 'fragmentId': fragment_id, 'text': nxt['text']})
            refs = _references(binding, nxt['text'], entities, context['actorId'], representation)
            fragments.append({'fragmentId': fragment_id, 'text': nxt['text'], 'references': refs})
        current = {**payload, 'fragments': copy.deepcopy(fragments)}
        ids = [f['fragmentId'] for f in fragments]
        audits = {key: _audit(session, key, current, ids) for key in CHECKS}
        return result(_freeze(context, opportunity_id, fragments, representation, audits))
    except Exception as exc:
        return incomplete(str(exc))


def action_wire(completion):
    if completion.status == 'empty':
        return {'kind': 'skip'}
    _require(completion.status == 'result' and isinstance(completion.value, FrozenAction), 'unfinished action cannot adapt to wire')
    return completion.value.verify().wire()


def analyze_targets(session, context, source, *, confirmed_group, already_acted_ids, judgments):
    """D03 sees the full roster, frozen raw text and all prior actual judgments."""
    try:
        _context(context)
        source.verify()
        _require(source.context_digest == digest(context), 'stale action context')
        people = list(context['world']['characters']) if isinstance(context['world']['characters'], dict) else [p['id'] for p in context['world']['characters']]
        _ids(already_acted_ids)
        _require(set(already_acted_ids) <= set(people), 'unknown already-acted actor')
        _require(isinstance(confirmed_group, list), 'complete confirmed group required')
        group_ids = []
        for member in confirmed_group:
            _require(isinstance(member, dict) and member.get('memberId') in people, 'unknown confirmed member')
            _text(member.get('actionText'), 'confirmed group action')
            group_ids.append(member['memberId'])
        _ids(group_ids)
        _require(source.actor_id in group_ids, 'target source missing from frozen group')
        _require(next(x['actionText'] for x in confirmed_group if x['memberId'] == source.actor_id) == source.text,
                 'target source text differs from frozen action')
        _judgments(judgments, set(people), group_ids)
        _require(not any(j['sourceId'] == source.actor_id for j in judgments), 'current-source future judgment leakage')
        payload = {'context': context, 'source': {'memberId': source.actor_id, 'actionText': source.text,
                   'contentDigest': source.content_digest}, 'candidateIds': people,
                   'alreadyActedIds': already_acted_ids, 'confirmedGroup': confirmed_group,
                   'knownPriorJudgments': judgments}
        relations = _call(session, 'D03.1', payload)
        _require(isinstance(relations, list), 'target relation list required')
        ids = []
        targets = []
        for row in relations:
            _keys(row, ('candidateId', 'relation'))
            ids.append(row['candidateId'])
            _require(row['relation'] in ('target', 'none'), 'unfinished/invalid target relation')
            if row['relation'] == 'target':
                targets.append(row['candidateId'])
        _ids(ids, people)
        _require(source.actor_id not in targets, 'source cannot force itself to react')
        audit = _call(session, 'D03.2', {**payload, 'relations': relations, 'targetIds': targets})
        _keys(audit, ('verdict', 'candidateIds', 'targetIds'))
        _ids(audit['candidateIds'], people)
        _ids(audit['targetIds'], targets)
        _require(audit['verdict'] == 'pass', 'target set audit rejected')
        return result(targets) if targets else empty()
    except Exception as exc:
        return incomplete(str(exc))


def targets_wire(completion):
    _require(completion.status in ('empty', 'result'), 'unfinished targets cannot adapt to wire')
    targets = [] if completion.status == 'empty' else _ids(completion.value)
    return {'targets': [{'targetId': t} for t in targets]}


def _judgments(rows, people, members):
    """Actual program/service receipts, not semantic success determinations."""
    _require(isinstance(rows, list), 'actual judgments required')
    rolls, relations, groups, triggers = [], [], set(), []
    for row in rows:
        _require(isinstance(row, dict) and {'rollId', 'sourceId', 'targetId', 'result', 'target', 'eligible', 'admitted', 'ruleVersion', 'groupId', 'triggerKey', 'eligibilityBaselineDigest'} <= set(row),
                 'incomplete actual judgment')
        _require(row['ruleVersion'] == 'reaction-d20-v1', 'unregistered dice rule')
        _text(row['groupId'], 'roll group identity')
        _text(row['triggerKey'], 'roll trigger identity')
        _require(isinstance(row['eligibilityBaselineDigest'], str) and re.fullmatch(r'[0-9a-f]{64}', row['eligibilityBaselineDigest']) is not None, 'invalid eligibility baseline identity')
        _require(row['sourceId'] in members and row['targetId'] in people, 'judgment source/target not registered')
        _require(type(row['result']) is int and 1 <= row['result'] <= 20 and row['target'] == 11,
                 'invalid actual d20 rule/result')
        _require(type(row['eligible']) is bool and type(row['admitted']) is bool, 'invalid admission flags')
        _require(row['admitted'] == (row['eligible'] and row['result'] >= row['target']), 'inconsistent actual admission')
        groups.add(row['groupId'])
        triggers.append(row['triggerKey'])
        rolls.append(row['rollId'])
        relations.append(row['sourceId'] + '\0' + row['targetId'])
    _require(len(groups) <= 1, 'mixed group dice receipts')
    _ids(triggers)
    _ids(rolls)
    _ids(relations)
    return rows


def produce_reaction(session, context, opportunity_id, *, member_id, confirmed_actions,
                     threats, judgments, max_fragments=8, representation='natural'):
    """D04: reuse an existing frozen action, otherwise obtain constraints then D02."""
    try:
        _context(context)
        people = _entities(context['world'])[1]
        _require(member_id in people, 'unknown reaction member')
        _require(all(isinstance(x, FrozenAction) for x in confirmed_actions), 'frozen actions required')
        members = [x.verify().actor_id for x in confirmed_actions]
        _ids(members)
        _judgments(judgments, people, members)
        relevant = [j for j in judgments if j['targetId'] == member_id]
        _require(relevant, 'reaction without actual relevant judgment')
        expected_threats = {j['sourceId'] for j in relevant}
        _require(isinstance(threats, list), 'complete relevant threats required')
        _ids([t['memberId'] for t in threats], expected_threats)
        actions = {x.actor_id: x for x in confirmed_actions}
        for threat in threats:
            _require(threat['actionText'] == actions[threat['memberId']].text, 'threat differs from frozen action')
        if member_id in actions:
            return result(actions[member_id])
        _require(any(j['admitted'] for j in relevant), 'reaction requires actual admission')
        constraints = _call(session, 'D04.1', {'context': context, 'memberId': member_id,
                            'threats': threats, 'judgments': judgments,
                            'frozenActions': [{'memberId': x.actor_id, 'actionText': x.text} for x in confirmed_actions]})
        _keys(constraints, ('threatSourceIds', 'constraint'))
        _ids(constraints['threatSourceIds'], expected_threats)
        _text(constraints['constraint'], 'reaction constraint')
        reaction_context = copy.deepcopy(context)
        reaction_context['actorId'] = member_id
        # Existing group actions remain complete context; a new member must not
        # already have a confirmed opportunity in the prefix.
        reaction_context['reactionGroup'] = [{'memberId': x.actor_id, 'actionText': x.text} for x in confirmed_actions]
        reaction_context['actualJudgments'] = copy.deepcopy(judgments)
        return produce_intent(session, reaction_context, opportunity_id, max_fragments=max_fragments,
                              representation=representation, reaction_constraints=constraints)
    except Exception as exc:
        return incomplete(str(exc))


def run_action_chain(session, context, opportunity_id, *, roll_targets: Callable,
                     max_sources=16, max_fragments=8, representation='natural'):
    """Actual-upstream D02→D03→D04 loop; complete closed-group candidate only.

    roll_targets receives exact source + confirmed target set. It must return
    immutable actual A/B judgments for every target, including ineligible and
    refused targets. This module never samples, edits or rerolls judgments.
    """
    first = produce_intent(session, context, opportunity_id, max_fragments=max_fragments, representation=representation)
    if first.status != 'result':
        return first
    try:
        _require(type(max_sources) is int and max_sources > 0, 'positive source budget required')
        actions = [first.value]
        contexts = {first.value.actor_id: copy.deepcopy(context)}
        judgments, target_sets = [], []
        processed = 0
        people = _entities(context['world'])[1]
        acted = [x['memberId'] for x in context['confirmedPrefix']]
        while processed < len(actions):
            _require(processed < max_sources, 'source_budget_pause: group not closed')
            source = actions[processed]
            group = [{'memberId': a.actor_id, 'actionText': a.text} for a in actions]
            target_result = analyze_targets(session, contexts[source.actor_id], source,
                                            confirmed_group=group, already_acted_ids=acted, judgments=judgments)
            _require(target_result.status != 'incomplete', 'targets unfinished: ' + str(target_result.reason))
            targets = [] if target_result.status == 'empty' else target_result.value
            # No roll is called before complete candidate/set confirmation.
            new_rows = copy.deepcopy(roll_targets(source, tuple(targets))) if targets else []
            _require(isinstance(new_rows, list), 'roll callback must return all actual receipts')
            _ids([r['targetId'] for r in new_rows], targets)
            _require(all(r['sourceId'] == source.actor_id for r in new_rows), 'roll receipt names another source')
            _judgments(judgments + new_rows, people, [a.actor_id for a in actions])
            for row in new_rows:
                if row['targetId'] in acted:
                    _require(not row['eligible'] and not row['admitted'], 'already-acted target cannot act again')
            judgments.extend(new_rows)
            target_sets.append({'sourceId': source.actor_id, 'targetIds': targets})
            for row in new_rows:
                target = row['targetId']
                if not row['admitted'] or target in {a.actor_id for a in actions}:
                    continue
                relevant = [j for j in judgments if j['targetId'] == target]
                threat_ids = {j['sourceId'] for j in relevant}
                threats = [{'memberId': a.actor_id, 'actionText': a.text} for a in actions if a.actor_id in threat_ids]
                reaction = produce_reaction(session, context, opportunity_id + '/reaction/' + target,
                                             member_id=target, confirmed_actions=actions, threats=threats,
                                             judgments=judgments, max_fragments=max_fragments, representation=representation)
                _require(reaction.status == 'result', 'admitted reaction unfinished: ' + str(reaction.reason))
                actions.append(reaction.value)
                rcontext = copy.deepcopy(context)
                rcontext['actorId'] = target
                rcontext['reactionGroup'] = [{'memberId': a.actor_id, 'actionText': a.text} for a in actions[:-1]]
                rcontext['actualJudgments'] = copy.deepcopy(judgments)
                contexts[target] = rcontext
            processed += 1
        return result({'memberIds': [a.actor_id for a in actions], 'alreadyActedIds': acted,
                       'members': [{'memberId': a.actor_id, 'actionText': a.text,
                                    'actionDigest': a.content_digest, 'fragments': a.material()['renderedFragments']} for a in actions],
                       'judgments': judgments, 'confirmedTargets': target_sets, 'closed': True,
                       'frozenActions': actions})
    except Exception as exc:
        return incomplete(str(exc))
