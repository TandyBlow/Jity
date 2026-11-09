"""D01, D07, D08 experiment orchestration, with no world writes."""
from __future__ import annotations

import copy
from short_contracts import (ContractError, FrozenValue, digest, empty, exact_coverage,
                             incomplete, integer_0_100, require_fields, result)


def _value(session, component, payload):
    answer = session.call(component, payload)
    if answer.status != 'result':
        raise ContractError(f'{component}:{answer.reason or "missing_required_result"}')
    return answer.value


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ContractError('missing_semantic_text')
    return value


class InitialDraft:
    """Revision-scoped draft identities; sealing needs A's validator callback."""
    def __init__(self, draft_id, brief, initial_time):
        self.draft_id = _text(draft_id)
        self.brief, self.initial_time = _text(brief), copy.deepcopy(initial_time)
        self.revision, self.candidate, self.sealed = 0, None, None

    def revise(self, brief):
        if self.sealed is not None:
            raise ContractError('sealed_initial_immutable')
        self.brief, self.revision, self.candidate = _text(brief), self.revision + 1, None

    def generate(self, session, *, max_tasks_per_character=32):
        if self.sealed is not None:
            return result(self.sealed.read())
        self.candidate = None
        try:
            if type(max_tasks_per_character) is not int or max_tasks_per_character < 0:
                raise ContractError('invalid_initial_task_budget')
            payload = {'brief': self.brief, 'draftId': self.draft_id, 'revision': self.revision}
            roster = _value(session, 'D01.1', payload)
            require_fields(roster, ('entities', 'protagonistIndex'))
            entities = roster['entities']
            if not isinstance(entities, list) or not entities:
                raise ContractError('empty_inventory')
            world = {'engineVersion': 'world-engine-v1', 'schemaVersion': 1,
                     'initialTime': self.initial_time, 'locations': {}, 'items': {}, 'characters': {}}
            ids = []
            for i, entity in enumerate(entities):
                if (not {'kind', 'name'} <= set(entity) or set(entity) - {'kind', 'name', 'slots'}
                        or entity['kind'] not in ('locations', 'items', 'characters')):
                    raise ContractError('invalid_inventory_entry')
                eid = f'{self.draft_id}_r{self.revision}_e{i}'
                ids.append(eid)
                world[entity['kind']][eid] = {'id': eid, 'name': _text(entity['name'])}
                if 'slots' in entity:
                    if not isinstance(entity['slots'], list):
                        raise ContractError('invalid_initial_slots')
                    world[entity['kind']][eid]['slots'] = [
                        {'id': f'{eid}_s{j}', 'label': _text(label)} for j, label in enumerate(entity['slots'])]
            index = roster['protagonistIndex']
            if type(index) is not int or not 0 <= index < len(ids) or ids[index] not in world['characters'] or not world['locations']:
                raise ContractError('invalid_initial_protagonist_or_places')
            world['protagonistId'] = ids[index]
            topology = _value(session, 'D01.2', dict(payload, draft=world))
            exact_coverage(topology, ids, 'initial_topology')
            parents = {}
            for eid in ids:
                if eid in world['locations']:
                    parent = topology[eid]
                    if parent is not None and parent not in world['locations']:
                        raise ContractError('unknown_location_parent')
                    world['locations'][eid]['parentLocationId'] = parent
                else:
                    pos = topology[eid]
                    require_fields(pos, ('containerId',))
                    parent = pos['containerId']
                    if parent not in ids:
                        raise ContractError('unknown_position_parent')
                    container = next(world[k][parent] for k in ('locations', 'items', 'characters') if parent in world[k])
                    if pos.get('slotId') is not None and pos['slotId'] not in {s['id'] for s in container.get('slots', [])}:
                        raise ContractError('unknown_initial_slot')
                    kind = 'items' if eid in world['items'] else 'characters'
                    world[kind][eid]['initialPosition'] = copy.deepcopy(pos)
                parents[eid] = parent
            for eid in ids:
                seen, node = set(), eid
                while node is not None:
                    if node in seen:
                        raise ContractError('initial_topology_cycle')
                    seen.add(node)
                    node = parents[node]
            for kind in ('locations', 'items', 'characters'):
                for eid, entity in world[kind].items():
                    entity['initialAppearance'] = _text(_value(session, 'D01.3', dict(payload, draft=world, entityId=eid)))
            for eid, person in world['characters'].items():
                person['tasks'] = {}
                for n in range(max_tasks_per_character + 1):
                    proposal = _value(session, 'D01.4', dict(payload, draft=world, characterId=eid))
                    if proposal == {'kind': 'end'}:
                        break
                    if n == max_tasks_per_character:
                        raise ContractError('initial_task_budget_without_end')
                    if set(proposal) != {'kind', 'goal', 'parentTaskId'} or proposal['kind'] != 'task':
                        raise ContractError('invalid_task_proposal')
                    parent = proposal['parentTaskId']
                    if parent is not None and parent not in person['tasks']:
                        raise ContractError('unknown_task_parent')
                    tid = f'{self.draft_id}_r{self.revision}_{eid}_t{n}'
                    person['tasks'][tid] = {'id': tid, 'ownerId': eid, 'parentTaskId': parent,
                                           'goal': _text(proposal['goal']), 'status': 'pending'}
            for eid, person in world['characters'].items():
                person['initialPersonality'] = _text(_value(session, 'D01.5', dict(payload, draft=world, characterId=eid)))
            for eid, person in world['characters'].items():
                person['initialSanity'] = integer_0_100(_value(session, 'D01.6', dict(payload, draft=world, characterId=eid)))
            self.candidate = FrozenValue(world)
            return result(world)
        except Exception as exc:
            return incomplete(str(exc))

    def seal(self, validator):
        if self.candidate is None:
            return incomplete('initial_draft_unfinished')
        try:
            candidate = self.candidate.read()
            if validator(copy.deepcopy(candidate)) is not True:
                return incomplete('authority_initial_validation_failed')
            self.sealed = FrozenValue(candidate)
            return result(self.sealed.read())
        except Exception as exc:
            return incomplete(f'initial_validation:{exc}')


def continuation(session, context, allocate_round, *, max_candidates=64, verify_round=None):
    """D07 after committed segment coverage and matching C ready gates only."""
    try:
        if type(max_candidates) is not int or max_candidates < 1:
            raise ContractError('invalid_continuation_budget')
        require_fields(context, ('world', 'roundChanges', 'roundId', 'requiredPointIds',
                                 'completedPointIds', 'readyPointIds', 'roundComplete', 'budgetPaused'))
        if context['budgetPaused']:
            return incomplete('budget_paused')
        if context['roundComplete'] is not True:
            return incomplete('round_or_linked_segments_unfinished')
        exact_coverage(context['completedPointIds'], context['requiredPointIds'], 'completed_segments')
        exact_coverage(context['readyPointIds'], context['requiredPointIds'], 'ready_segments')
        changes = context['roundChanges']
        if changes['roundId'] != context['roundId']:
            raise ContractError('round_changes_identity_mismatch')
        exact_coverage([p['pointId'] for p in changes['points']], context['requiredPointIds'], 'round_changes')
        if [p['pointId'] for p in changes['points']] != context['requiredPointIds'] or not changes['points']:
            raise ContractError('round_changes_order_or_empty')
        require_fields(context, ('committedHead', 'currentWorldHash', 'requiredGates', 'readyReceipts'))
        if context['currentWorldHash'] != digest(context['world']):
            raise ContractError('stale_continuation_world')
        head = context['committedHead']
        require_fields(head, ('worldId', 'pointId', 'version', 'stateDigest'))
        if head['worldId'] != context['world'].get('worldId') or head['pointId'] != changes['points'][-1]['pointId']:
            raise ContractError('continuation_head_mismatch')
        for index, point in enumerate(changes['points']):
            require_fields(point, ('pointId', 'previousPointId', 'version', 'stateDigest', 'timeAdvance', 'entityDeltas'))
            if index and (point['previousPointId'] != changes['points'][index-1]['pointId']
                          or point['version'] != changes['points'][index-1]['version'] + 1):
                raise ContractError('round_committed_lineage_mismatch')
        if any(head[k] != changes['points'][-1][k] for k in ('pointId', 'version', 'stateDigest')):
            raise ContractError('continuation_head_version_mismatch')
        exact_coverage(context['requiredGates'], context['requiredPointIds'], 'required_gates')
        exact_coverage([r['pointId'] for r in context['readyReceipts']], context['requiredPointIds'], 'ready_receipts')
        for receipt in context['readyReceipts']:
            expected = context['requiredGates'][receipt['pointId']]
            if receipt != dict(expected, status='ready'):
                raise ContractError('stale_ready_receipt')
        if verify_round is None or verify_round(copy.deepcopy(context)) is not True:
            raise ContractError('round_commit_and_ready_provenance_unverified')
        proposed = []
        for n in range(max_candidates + 1):
            candidate = _value(session, 'D07.1', dict(context, proposed=proposed))
            if candidate == {'kind': 'end'}:
                break
            if n == max_candidates:
                raise ContractError('continuation_budget_without_end')
            if set(candidate) != {'kind', 'characterId', 'text'} or candidate['kind'] != 'candidate':
                raise ContractError('invalid_continuation_candidate')
            if candidate['characterId'] not in context['world']['characters']:
                raise ContractError('unknown_continuation_character')
            _text(candidate['text'])
            if candidate in proposed:
                raise ContractError('duplicate_continuation_candidate')
            proposed.append(copy.deepcopy(candidate))
        accepted = []
        for index, candidate in enumerate(proposed):
            payload = dict(context, proposed=proposed, candidateIndex=index)
            likely = _value(session, 'D07.2', payload)
            related = _value(session, 'D07.3', payload)
            if likely not in ('likely', 'unlikely') or related not in ('related', 'unrelated'):
                raise ContractError('invalid_continuation_judgment')
            if likely == 'likely' and related == 'related' and candidate['characterId'] not in accepted:
                accepted.append(candidate['characterId'])
        if not accepted:
            return empty()  # Adapter may now emit the existing model handback.
        new_id = _text(allocate_round())
        if new_id == context['roundId']:
            raise ContractError('round_identity_reused')
        return result({'kind': 'continue', 'closedBy': 'model', 'cancelReason': None,
                       'candidateCharacterIds': accepted, 'nextRoundId': new_id})
    except Exception as exc:
        return incomplete(str(exc))


def continuation_wire(completion):
    if completion.status == 'incomplete':
        raise ContractError('unfinished_continuation_has_no_wire')
    return ({'kind': 'handback', 'closedBy': 'model', 'cancelReason': None}
            if completion.status == 'empty' else copy.deepcopy(completion.value))


def validate_time(value):
    if not isinstance(value, dict) or set(value) != {'boundary', 'duration'}:
        raise ContractError('invalid_time')
    d = value['duration']
    if (not isinstance(d, dict) or set(d) != {'amount', 'unit'}
            or type(d['amount']) is not int or not 0 <= d['amount'] <= 9007199254740991):
        raise ContractError('invalid_time_duration')
    if d['unit'] not in ('second', 'minute', 'hour', 'day', 'month', 'year'):
        raise ContractError('invalid_time_unit')
    if value['boundary'] not in ('elapsed', 'instant') or (value['boundary'] == 'instant' and d != {'amount': 0, 'unit': 'second'}):
        raise ContractError('invalid_time_boundary')
    return value


def propose_time(session, context):
    try:
        require_fields(context, ('world', 'pointId', 'timeLocked', 'timeAdvance'))
        if context['timeLocked']:
            return result(validate_time(copy.deepcopy(context['timeAdvance'])))
        return result(validate_time(_value(session, 'D08.1', context)))
    except Exception as exc:
        return incomplete(str(exc))


def propose_segments(session, context, allocate_point):
    """Proposal only: confirmed work and actual visitedIds never move."""
    try:
        require_fields(context, ('world', 'roundId', 'order', 'actedIds', 'visitedIds', 'frozenActions'))
        proposal = _value(session, 'D08.2', context)
        if not isinstance(proposal, list) or not proposal:
            raise ContractError('empty_segment_proposal')
        if context['frozenActions']:
            raise ContractError('cannot_resegment_confirmed_actions')
        point_ids, actors, output, ordinary_ranks = set(), [], [], []
        for index, segment in enumerate(proposal):
            if set(segment) != {'kind', 'timeAdvance', 'actorIds'}:
                raise ContractError('segment_model_cannot_assign_identity_or_visits')
            if segment['kind'] not in ('normal', 'instant', 'linked'):
                raise ContractError('invalid_segment_kind')
            if index == 0 and segment['kind'] == 'linked':
                raise ContractError('linked_without_predecessor')
            if segment['kind'] == 'instant' and segment['timeAdvance'] != {'boundary': 'instant', 'duration': {'amount': 0, 'unit': 'second'}}:
                raise ContractError('instant_point_requires_zero_duration')
            if segment['kind'] == 'linked' and (not index or proposal[index-1]['kind'] != 'instant'):
                raise ContractError('linked_must_follow_instant')
            if index and segment['kind'] == 'normal':
                raise ContractError('normal_inside_linked_round')
            if index and (segment['kind'] == 'instant' or proposal[index-1]['kind'] == 'instant'):
                if segment['timeAdvance']['boundary'] != 'instant':
                    raise ContractError('associated_boundary_must_be_instant')
            validate_time(segment['timeAdvance'])
            for actor in segment['actorIds']:
                if actor not in context['order'] or actor in actors or actor in context['actedIds']:
                    raise ContractError('segment_actor_invalid_or_repeated')
                actors.append(actor)
            if segment['kind'] != 'instant':
                ranks = [context['order'].index(actor) for actor in segment['actorIds']]
                ordinary_ranks.extend(ranks)
                if ordinary_ranks != sorted(ordinary_ranks):
                    raise ContractError('segment_reorders_frozen_slots')
            pid = _text(allocate_point(index))
            if pid in point_ids:
                raise ContractError('point_identity_reused')
            point_ids.add(pid)
            output.append(dict(copy.deepcopy(segment), pointId=pid))
        # The scheduler still visits omitted slots. Suggestions are never visits.
        return result({'pointPlan': output, 'unassignedActorIds': [a for a in context['order'] if a not in actors and a not in context['actedIds']],
                       'orderHash': digest(context['order']), 'visitedIds': copy.deepcopy(context['visitedIds'])})
    except Exception as exc:
        return incomplete(str(exc))
