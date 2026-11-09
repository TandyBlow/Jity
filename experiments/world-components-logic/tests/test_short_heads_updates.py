"""Primitive-provider engineering fixtures; zero trained-model capability claims."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from short_contracts import result, incomplete, empty, digest
from short_heads_updates import assemble_update_head
from test_short_intent import canonical_context


class PrimitiveFixture:
    def __init__(self, rows):
        self.rows = list(rows); self.calls = []
    def __call__(self, component, payload):
        self.calls.append((component, deepcopy(payload)))
        wanted, answer = self.rows.pop(0)
        if wanted != component:
            raise AssertionError((wanted, component))
        return answer if hasattr(answer, 'status') else result(answer)


def payload():
    return {'world': canonical_context()['world'], 'facts': [{'id': 'fact', 'text': '图纸留在原处。'}],
            'candidates': [{'stage': 'position', 'changes': {}}], 'context': {'binding': {'pointId': 'point', 'version': 1}},
            'candidateRefs': []}


def positions(container, *, slot=None, relative=None):
    rows = [('U1.2.container', container), ('U1.2.slot_mode', 'none' if slot is None else 'select')]
    if slot is not None:
        rows += [('U1.2.slot', slot)]
    rows += [('U1.2.relative_mode', 'none' if relative is None else 'select')]
    if relative is not None:
        rows += [('U1.2.relative_entity', relative[0]), ('U1.2.relation', relative[1])]
    return rows


def record(id):
    return {'id': id, 'text': '旧局部状态。', 'active': True, 'sourcePointId': 'old', 'sourceSequence': 1, 'supersedes': []}


class NarrowUpdateHeadTests(unittest.TestCase):
    def test_positions_are_legal_references_and_preserve_entire_payload(self):
        p = payload(); p['entityIds'] = ['brush']
        p['world']['initial']['characters']['b']['slots'] = [{'id': 'pocket-b', 'label': '右口袋'}]
        provider = PrimitiveFixture(positions('b', slot='pocket-b', relative=('sheet', 'beside')) + [('U1.2.audit', 'pass')])
        answer = assemble_update_head(provider, 'U1.2', p)
        self.assertEqual(answer.status, 'result', answer.reason)
        self.assertEqual(answer.value['positions'][0]['position'], {'containerId': 'b', 'slotId': 'pocket-b', 'relativeTo': {'entityId': 'sheet', 'relation': 'beside'}})
        for _, incoming in provider.calls:
            self.assertEqual(incoming['originalPayload'], p)
        container_input = provider.calls[0][1]
        self.assertEqual(set(c['id'] for c in container_input['candidates']), {'room', 'sheet', 'a', 'b', 'c'})
        self.assertIn('initial', container_input['candidates'][0])
        self.assertEqual(container_input['originalPayload']['candidates'], p['candidates'])

    def test_position_choices_validate_final_simultaneous_graph(self):
        p = payload(); p['entityIds'] = ['a', 'b']
        # b currently carried by a; moving a into b is legal only after b leaves a.
        p['world']['characters']['b']['position'] = {'containerId': 'a'}
        provider = PrimitiveFixture(positions('b') + positions('room') + [('U1.2.audit', 'pass')])
        answer = assemble_update_head(provider, 'U1.2', p)
        self.assertEqual(answer.status, 'result', answer.reason)
        self.assertEqual([r['position']['containerId'] for r in answer.value['positions']], ['b', 'room'])

    def test_joint_cycle_rejected_without_patching_model_choices(self):
        p = payload(); p['entityIds'] = ['a', 'b']
        provider = PrimitiveFixture(positions('b') + positions('a'))
        answer = assemble_update_head(provider, 'U1.2', p)
        self.assertEqual(answer.status, 'incomplete')
        self.assertIn('cyclic', answer.reason)

    def test_container_or_slot_choice_cannot_invent_entities(self):
        p = payload(); p['entityIds'] = ['brush']
        bad = assemble_update_head(PrimitiveFixture([('U1.2.container', 'new-container')]), 'U1.2', p)
        self.assertEqual(bad.status, 'incomplete')
        bad = assemble_update_head(PrimitiveFixture([('U1.2.container', 'b'), ('U1.2.slot_mode', 'select')]), 'U1.2', p)
        self.assertEqual(bad.status, 'incomplete')

    def test_multiope_and_pure_remove_need_no_generated_json_or_text(self):
        p = payload(); p.update(entityIds=['a'], activeRecords={'a': {'old': record('old')}})
        rows = [('U2.1.next_op', 'remove'), ('U2.1.record_more', 'more'), ('U2.1.record', 'old'), ('U2.1.record_more', 'end'),
                ('U2.1.next_op', 'add'), ('U2.1.next_op', 'add'), ('U2.1.next_op', 'end'), ('U2.1.audit', 'pass')]
        provider = PrimitiveFixture(rows)
        answer = assemble_update_head(provider, 'U2.1', p)
        self.assertEqual(answer.status, 'result', answer.reason)
        self.assertEqual([r['op'] for r in answer.value['operations']], ['remove', 'add', 'add'])
        self.assertEqual(answer.value['checkedRecordIds'], ['old'])
        self.assertEqual(answer.value['operations'][0]['recordIds'], ['old'])
        self.assertFalse(any('text' in row for row in answer.value['operations']))
        self.assertTrue(all(c[0] != 'U2.2' for c in provider.calls))

    def test_keep_remove_replace_require_all_active_records_once(self):
        p = payload(); p.update(entityIds=['a'], activeRecords={'a': {'r1': record('r1'), 'r2': record('r2')}})
        rows = [('U5.1.next_op', 'keep'), ('U5.1.record_more', 'more'), ('U5.1.record', 'r1'), ('U5.1.record_more', 'end'),
                ('U5.1.next_op', 'replace'), ('U5.1.record_more', 'more'), ('U5.1.record', 'r2'), ('U5.1.record_more', 'end'),
                ('U5.1.next_op', 'end'), ('U5.1.audit', 'pass')]
        provider = PrimitiveFixture(rows)
        answer = assemble_update_head(provider, 'U5.1', p)
        self.assertEqual(answer.status, 'result', answer.reason)
        second_pointer = [q for c, q in provider.calls if c == 'U5.1.record'][1]
        self.assertEqual([r['id'] for r in second_pointer['candidates']], ['r2'])
        self.assertEqual(set(second_pointer['originalPayload']['activeRecords']['a']), {'r1', 'r2'})

    def test_unchecked_record_or_missing_entity_operation_cannot_be_no_change(self):
        p = payload(); p.update(entityIds=['a'], activeRecords={'a': {'old': record('old')}})
        for rows in [[('U2.1.next_op', 'end')],
                     [('U2.1.next_op', 'keep'), ('U2.1.record_more', 'end'), ('U2.1.next_op', 'end')]]:
            answer = assemble_update_head(PrimitiveFixture(rows), 'U2.1', p)
            self.assertEqual(answer.status, 'incomplete')

    def test_explicit_empty_keep_allowed_for_entity_without_records(self):
        p = payload(); p.update(entityIds=['a'], activeRecords={'a': {}})
        rows = [('U5.1.next_op', 'keep'), ('U5.1.record_more', 'end'), ('U5.1.next_op', 'end'), ('U5.1.audit', 'pass')]
        answer = assemble_update_head(PrimitiveFixture(rows), 'U5.1', p)
        self.assertEqual(answer.value['operations'], [{'entityId': 'a', 'op': 'keep', 'recordIds': []}])

    def test_record_budget_is_incomplete_not_partial_success(self):
        p = payload(); p.update(entityIds=['a'], activeRecords={'a': {}})
        provider = PrimitiveFixture([('U2.1.next_op', 'add'), ('U2.1.next_op', 'add')])
        answer = assemble_update_head(provider, 'U2.1', p, max_operations=1)
        self.assertEqual(answer.status, 'incomplete')
        self.assertIn('budget_pause', answer.reason)

    def test_mapping_references_selected_by_model_and_audited(self):
        p = payload()
        p['facts'] += [{'id': 'f2', 'text': '袖口留下油迹。'}]
        ref = {'stage': 'appearance', 'entityId': 'a', 'operationId': 'change-1'}
        p['candidateRefs'] = [ref]
        provider = PrimitiveFixture([('D06.P.mapping.kind', 'unchanged'), ('D06.P.mapping.kind', 'state'),
            ('D06.P.mapping.more', 'more'), ('D06.P.mapping.target', 'candidate:' + digest(ref)),
            ('D06.P.mapping.more', 'end'), ('D06.P.mapping.audit', 'pass')])
        answer = assemble_update_head(provider, 'D06.P.mapping', p)
        self.assertEqual(answer.status, 'result', answer.reason)
        self.assertEqual(answer.value['mappings'], [{'factId': 'fact', 'kind': 'unchanged', 'targets': []},
                                                    {'factId': 'f2', 'kind': 'state', 'targets': [ref]}])
        for _, incoming in provider.calls:
            self.assertEqual(incoming['originalPayload'], p)

    def test_mapping_gap_missing_consequence_and_audit_reject_stay_incomplete(self):
        p = payload(); p['candidateRefs'] = [{'stage': 'appearance', 'entityId': 'a', 'operationId': 'change'}]
        for rows in [[('D06.P.mapping.kind', 'gap')], [('D06.P.mapping.kind', 'unchanged')]]:
            self.assertEqual(assemble_update_head(PrimitiveFixture(rows), 'D06.P.mapping', p).status, 'incomplete')
        p['candidateRefs'] = []
        answer = assemble_update_head(PrimitiveFixture([('D06.P.mapping.kind', 'transient'), ('D06.P.mapping.audit', 'reject')]), 'D06.P.mapping', p)
        self.assertEqual(answer.status, 'incomplete')

    def test_mapping_preserves_pure_time_source(self):
        p = payload(); p['facts'] = []; p['timeFact'] = {'id': 'time-fact', 'text': '一分钟过去了。'}
        answer = assemble_update_head(PrimitiveFixture([('D06.P.mapping.kind', 'transient'), ('D06.P.mapping.audit', 'pass')]), 'D06.P.mapping', p)
        self.assertEqual(answer.value['mappings'][0]['factId'], 'time-fact')

    def test_untrained_empty_error_and_json_primitive_never_default_to_keep(self):
        p = payload(); p.update(entityIds=['a'], activeRecords={'a': {}})
        for bad in (incomplete('untrained_component'), empty(), result({'op': 'keep'})):
            answer = assemble_update_head(PrimitiveFixture([('U2.1.next_op', bad)]), 'U2.1', p)
            self.assertEqual(answer.status, 'incomplete')


if __name__ == '__main__':
    unittest.main()
