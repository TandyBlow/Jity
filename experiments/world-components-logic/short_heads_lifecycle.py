"""Program assembly for D01/D07/D08 from learned primitive predictions.

No aggregate JSON generation or authored semantic answers are used at runtime.
The low-level backend must have independently trained each requested task.
"""
from __future__ import annotations

import copy
import re
from short_contracts import Completion, ContractError, incomplete, result


COMPONENTS = {'D01.1', 'D01.2', 'D01.4', 'D07.1', 'D08.1', 'D08.2'}


class LifecycleHeads:
    def __init__(self, predict, *, max_entities=64, max_slots=32, max_segments=32):
        for value in (max_entities, max_slots, max_segments):
            if type(value) is not int or value < 1:
                raise ContractError('invalid_lifecycle_assembly_budget')
        self.predict = predict
        self.max_entities, self.max_slots, self.max_segments = max_entities, max_slots, max_segments

    def scalar(self, component, payload, choices=None):
        answer = self.predict(component, copy.deepcopy(payload))
        if not isinstance(answer, Completion) or answer.status != 'result':
            raise ContractError(f'{component}: {getattr(answer, "reason", "incomplete")}')
        if choices is not None and answer.value not in choices:
            raise ContractError(component + ': unknown_label')
        return answer.value

    def text(self, component, payload):
        value = self.scalar(component, payload)
        if not isinstance(value, str) or not value.strip():
            raise ContractError(component + ': missing_text')
        return value

    def select(self, component, payload, candidates):
        if not candidates or len({x['id'] for x in candidates}) != len(candidates):
            raise ContractError('empty_or_duplicate_reference_candidates')
        value = self.scalar(component, dict(payload, candidates=candidates))
        if value not in {x['id'] for x in candidates}:
            raise ContractError(component + ': unknown_reference')
        return value

    def time(self, prefix, payload):
        boundary = self.scalar(prefix + '.boundary', payload, ('elapsed', 'instant'))
        # Instant is a deterministic wire form. Elapsed choices are dependent:
        # the amount model must see the actual selected boundary and unit.
        if boundary == 'instant':
            return {'boundary': 'instant', 'duration': {'amount': 0, 'unit': 'second'}}
        unit = self.scalar(prefix + '.unit',
            dict(payload, timeChoice={'boundary': boundary}),
            ('second', 'minute', 'hour', 'day', 'month', 'year'))
        raw = self.scalar(prefix + '.amount',
            dict(payload, timeChoice={'boundary': boundary, 'unit': unit}))
        if type(raw) is int:
            amount = raw
        elif isinstance(raw, str) and re.fullmatch(r'0|[1-9][0-9]*', raw):
            amount = int(raw)
        else:
            raise ContractError('time_amount_not_integer')
        if amount < 0 or amount > 9007199254740991:
            raise ContractError('time_amount_outside_wire_range')
        return {'boundary': boundary, 'duration': {'amount': amount, 'unit': unit}}

    def __call__(self, component, payload):
        try:
            if component == 'D01.1':
                entities = []
                for index in range(self.max_entities + 1):
                    p = dict(payload, proposedEntities=entities)
                    kind = self.scalar('D01.1.kind', p, ('locations', 'items', 'characters', 'end'))
                    if kind == 'end':
                        break
                    if index == self.max_entities:
                        raise ContractError('entity_budget_without_end')
                    name = self.text('D01.1.name', dict(p, entityKind=kind))
                    slots = []
                    for slot_index in range(self.max_slots + 1):
                        sp = dict(p, entityKind=kind, entityName=name, proposedSlots=slots)
                        decision = self.scalar('D01.1.slot_next', sp, ('slot', 'end'))
                        if decision == 'end':
                            break
                        if slot_index == self.max_slots:
                            raise ContractError('slot_budget_without_end')
                        slots.append(self.text('D01.1.slot_label', sp))
                    entities.append({'kind': kind, 'name': name, 'slots': slots})
                candidates = [{'id': str(i), **entity} for i, entity in enumerate(entities) if entity['kind'] == 'characters']
                protagonist = self.select('D01.1.protagonist', dict(payload, proposedEntities=entities), candidates)
                return result({'entities': entities, 'protagonistIndex': int(protagonist)})
            if component == 'D01.2':
                w = payload['draft']
                entities = {**w['locations'], **w['items'], **w['characters']}
                topology = {}
                for eid in entities:
                    p = dict(payload, entityId=eid, topologyCandidates=topology)
                    if eid in w['locations']:
                        candidates = [{'id': key, 'entity': value} for key, value in w['locations'].items()]
                        chosen = self.select('D01.2.parent', p, [{'id': '__none__'}] + candidates)
                        topology[eid] = None if chosen == '__none__' else chosen
                    else:
                        container = self.select('D01.2.container', p, [{'id': k, 'entity': v} for k, v in entities.items()])
                        slot = self.select('D01.2.slot', dict(p, containerId=container),
                            [{'id': '__none__'}] + copy.deepcopy(entities[container].get('slots', [])))
                        relative = self.select('D01.2.relative', dict(p, containerId=container),
                            [{'id': '__none__'}] + [{'id': k, 'entity': v} for k, v in entities.items()])
                        position = {'containerId': container, 'slotId': None if slot == '__none__' else slot, 'relativeTo': None}
                        if relative != '__none__':
                            relation = self.scalar('D01.2.relation', dict(p, containerId=container,
                                slotId=None if slot == '__none__' else slot, relativeEntityId=relative),
                                ('under', 'above', 'beside', 'in_front_of', 'behind'))
                            position['relativeTo'] = {'entityId': relative, 'relation': relation}
                        topology[eid] = position
                return result(topology)
            if component == 'D01.4':
                label = self.scalar('D01.4.next', payload, ('task', 'end'))
                if label == 'end': return result({'kind': 'end'})
                tasks = payload['draft']['characters'][payload['characterId']]['tasks']
                parent = self.select('D01.4.parent', payload,
                    [{'id': '__none__'}] + [{'id': k, 'task': v} for k, v in tasks.items()])
                goal = self.text('D01.4.goal', dict(payload, parentTaskId=None if parent == '__none__' else parent))
                return result({'kind': 'task', 'parentTaskId': None if parent == '__none__' else parent, 'goal': goal})
            if component == 'D07.1':
                label = self.scalar('D07.1.next', payload, ('candidate', 'end'))
                if label == 'end': return result({'kind': 'end'})
                w = payload['world']
                who = self.select('D07.1.character', payload, [{'id': k, 'character': v} for k, v in w['characters'].items()])
                text = self.text('D07.1.text', dict(payload, characterId=who))
                return result({'kind': 'candidate', 'characterId': who, 'text': text})
            if component == 'D08.1':
                return result(self.time('D08.1', payload))
            if component == 'D08.2':
                segments = []
                for index in range(self.max_segments + 1):
                    p = dict(payload, proposedSegments=segments)
                    kind = self.scalar('D08.2.next_kind', p, ('normal', 'instant', 'linked', 'end'))
                    if kind == 'end': break
                    if index == self.max_segments: raise ContractError('segment_budget_without_end')
                    p['proposedKind'] = kind
                    time = self.time('D08.2.time', p)
                    p['proposedTimeAdvance'] = copy.deepcopy(time)
                    actors = []
                    for actor in payload['order']:
                        selected = self.scalar('D08.2.actor', dict(p, actorId=actor, currentActors=list(actors)), ('include', 'exclude'))
                        if selected == 'include': actors.append(actor)
                    segments.append({'kind': kind, 'timeAdvance': time, 'actorIds': actors})
                return result(segments)
            return incomplete('unknown_lifecycle_composite:' + component)
        except Exception as exc:
            return incomplete(str(exc))


def assemble_lifecycle_head(provider, component, payload):
    return LifecycleHeads(provider)(component, payload)
