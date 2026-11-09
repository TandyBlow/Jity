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


def _verified_segment_prefix(context, verify_prefix):
    """Read-only A/B recovery evidence for extending a committed round prefix.

    verify_prefix checks service provenance, state digest, complete frozen work,
    narration readiness and the actual round cursor. A matching local hash is
    only an integrity check, never authority evidence.
    """
    require_fields(context, ('lockedPrefix', 'head', 'cursor', 'currentWorldHash'))
    prefix = context['lockedPrefix']
    require_fields(prefix, ('roundId', 'orderHash', 'cursor', 'actedIds', 'visitedIds',
                            'frozenActions', 'head', 'points', 'currentWorldHash', 'allowedNextKinds'))
    if (prefix['roundId'] != context['roundId'] or prefix['orderHash'] != digest(context['order'])
            or prefix['currentWorldHash'] != digest(context['world'])
            or context['currentWorldHash'] != prefix['currentWorldHash']):
        raise ContractError('stale_segment_prefix_world_or_order')
    for key in ('head', 'cursor', 'actedIds', 'visitedIds', 'frozenActions'):
        if digest(prefix[key]) != digest(context[key]):
            raise ContractError('segment_prefix_binding_mismatch:' + key)
    head = prefix['head']
    require_fields(head, ('pointId', 'kind', 'version', 'stateDigest'))
    if (type(head['version']) is not int or not 0 <= head['version'] <= 9007199254740991
            or not isinstance(head['stateDigest'], str) or not head['stateDigest']):
        raise ContractError('invalid_segment_predecessor_version')
    cursor = 0
    while cursor < len(context['order']) and context['order'][cursor] in context['visitedIds']:
        cursor += 1
    if type(context['cursor']) is not int or context['cursor'] != cursor:
        raise ContractError('segment_cursor_not_first_unvisited')
    allowed = prefix['allowedNextKinds']
    if not isinstance(allowed, list) or not allowed or not set(allowed) <= {'normal', 'instant', 'linked'}:
        raise ContractError('missing_legal_suffix_boundaries')
    exact_coverage(allowed, allowed, 'allowed_suffix_kinds')
    points = prefix['points']
    if not isinstance(points, list) or not points:
        raise ContractError('empty_locked_segment_prefix')
    points_by_id, acted, visited = {}, [], []
    previous = None
    for point in points:
        require_fields(point, ('pointId', 'previousPointId', 'kind', 'version', 'stateDigest',
                               'timeAdvance', 'actorIds', 'visitedIds'))
        pid = _text(point['pointId'])
        if pid in points_by_id or point['kind'] not in ('normal', 'instant', 'linked'):
            raise ContractError('invalid_locked_point_identity_or_kind')
        if type(point['version']) is not int or not 0 <= point['version'] <= 9007199254740991:
            raise ContractError('invalid_locked_point_version')
        if previous and (point['previousPointId'] != previous['pointId'] or point['version'] != previous['version'] + 1):
            raise ContractError('locked_segment_lineage_mismatch')
        validate_time(point['timeAdvance'])
        if point['kind'] == 'normal' and point['timeAdvance']['boundary'] != 'elapsed':
            raise ContractError('locked_normal_boundary_mismatch')
        if point['kind'] != 'normal' and point['timeAdvance'] != {'boundary': 'instant', 'duration': {'amount': 0, 'unit': 'second'}}:
            raise ContractError('locked_associated_boundary_mismatch')
        for key in ('actorIds', 'visitedIds'):
            if not isinstance(point[key], list):
                raise ContractError('invalid_locked_point_slots')
            exact_coverage(point[key], point[key], 'locked_point_' + key)
            if not set(point[key]) <= set(context['order']):
                raise ContractError('locked_point_unknown_slot')
        if not set(point['actorIds']) <= set(point['visitedIds']):
            raise ContractError('locked_actor_not_visited')
        if set(acted) & set(point['actorIds']) or set(visited) & set(point['visitedIds']):
            raise ContractError('locked_slot_processed_twice')
        acted.extend(point['actorIds']); visited.extend(point['visitedIds'])
        points_by_id[pid] = point; previous = point
    exact_coverage(acted, context['actedIds'], 'locked_acted_coverage')
    exact_coverage(visited, context['visitedIds'], 'locked_visited_coverage')
    if any(head[key] != points[-1][key] for key in ('pointId', 'kind', 'version', 'stateDigest')):
        raise ContractError('locked_head_not_last_point')
    exact_coverage(context['frozenActions'], acted, 'locked_frozen_action_coverage')
    for actor, action in context['frozenActions'].items():
        require_fields(action, ('pointId', 'actionText', 'contentHash'))
        _text(action['actionText']); _text(action['contentHash'])
        if action['pointId'] not in points_by_id or actor not in points_by_id[action['pointId']]['actorIds']:
            raise ContractError('frozen_action_point_assignment_mismatch')
    if verify_prefix is None or verify_prefix(copy.deepcopy(context)) is not True:
        raise ContractError('segment_prefix_authority_unverified')
    # Prior actorIds include pulled reactions; they are not natural slot order.
    # Their legality is verified by A/B. Only the new suffix slots are ordered.
    return prefix, points_by_id, []


def propose_segments(session, context, allocate_point, *, verify_prefix=None):
    """Propose an initial plan or a verified remaining suffix; never move work.

    The existing pointPlan wire is unchanged. Remaining-suffix planning keeps
    complete prior actions/time in input, but the model may only append points
    covering slots not yet visited (including skips). A/B own authoritative
    verification, allocation, actual visits and all subsequent scheduling.
    """
    try:
        require_fields(context, ('world', 'roundId', 'order', 'actedIds', 'visitedIds', 'frozenActions'))
        _text(context['roundId'])
        for key in ('order', 'actedIds', 'visitedIds'):
            if not isinstance(context[key], list):
                raise ContractError('invalid_segment_slot_list')
            exact_coverage(context[key], context[key], 'segment_' + key)
            for actor in context[key]: _text(actor)
        if not set(context['actedIds']) <= set(context['visitedIds']) <= set(context['order']):
            raise ContractError('segment_progress_outside_order')
        if not isinstance(context['frozenActions'], dict):
            raise ContractError('invalid_frozen_action_registry')
        scope = context.get('planningScope', 'initial')
        prefix, old_points, ordinary_ranks = None, {}, []
        if scope == 'initial':
            if context['frozenActions'] or context['actedIds'] or context['visitedIds'] or context.get('lockedPrefix'):
                raise ContractError('initial_plan_cannot_resegment_confirmed_progress')
        elif scope == 'remaining_suffix':
            prefix, old_points, ordinary_ranks = _verified_segment_prefix(context, verify_prefix)
        else:
            raise ContractError('invalid_segment_planning_scope')
        proposal = _value(session, 'D08.2', copy.deepcopy(context))
        if not isinstance(proposal, list) or not proposal:
            raise ContractError('empty_segment_proposal')
        actors, validated = [], []
        previous_kind = None if prefix is None else prefix['head']['kind']
        for index, segment in enumerate(proposal):
            if not isinstance(segment, dict) or set(segment) != {'kind', 'timeAdvance', 'actorIds'}:
                raise ContractError('segment_model_cannot_assign_identity_or_visits')
            kind = segment['kind']
            if kind not in ('normal', 'instant', 'linked'):
                raise ContractError('invalid_segment_kind')
            if index == 0 and prefix is not None and kind not in prefix['allowedNextKinds']:
                raise ContractError('suffix_boundary_not_authority_allowed')
            if kind == 'normal' and index:
                raise ContractError('normal_inside_linked_round')
            if kind == 'linked' and previous_kind != 'instant':
                raise ContractError('linked_must_follow_verified_instant')
            validate_time(segment['timeAdvance'])
            if kind == 'normal' and segment['timeAdvance']['boundary'] != 'elapsed':
                raise ContractError('normal_point_requires_elapsed_boundary')
            if kind in ('instant', 'linked') and segment['timeAdvance'] != {'boundary': 'instant', 'duration': {'amount': 0, 'unit': 'second'}}:
                raise ContractError('associated_point_requires_zero_instant_duration')
            if not isinstance(segment['actorIds'], list):
                raise ContractError('invalid_segment_actors')
            for actor in segment['actorIds']:
                if actor not in context['order'] or actor in actors or actor in context['visitedIds']:
                    raise ContractError('segment_actor_invalid_repeated_or_visited')
                actors.append(actor)
            if kind != 'instant':
                ordinary_ranks.extend(context['order'].index(actor) for actor in segment['actorIds'])
                if ordinary_ranks != sorted(ordinary_ranks):
                    raise ContractError('segment_reorders_frozen_slots')
            validated.append(copy.deepcopy(segment)); previous_kind = kind
        # Allocate only after all proposal structure and prefix checks succeed.
        point_ids, output = set(old_points), []
        for index, segment in enumerate(validated):
            pid = _text(allocate_point(index))
            if pid in point_ids:
                raise ContractError('point_identity_reused')
            point_ids.add(pid); output.append(dict(segment, pointId=pid))
        return result({'pointPlan': output,
                       'unassignedActorIds': [a for a in context['order'] if a not in actors and a not in context['visitedIds']],
                       'orderHash': digest(context['order']), 'visitedIds': copy.deepcopy(context['visitedIds']),
                       'planningScope': scope, 'lockedPrefixHash': None if prefix is None else digest(prefix),
                       'frozenActionsHash': digest(context['frozenActions'])})
    except Exception as exc:
        return incomplete(str(exc))
