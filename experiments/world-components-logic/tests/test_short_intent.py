"""New synthetic engineering fixtures only; no model capability evidence."""
import copy
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from short_contracts import Completion, ContractError, ModelIdentity, ModelSession, result, empty, incomplete
import short_intent as m


def context():
    people = [{'id': id, 'name': name, 'position': 'room', 'appearance': '穿着便服。',
               'personality': ['谨慎。'], 'sanity': 50,
               'tasks': [{'id': 'task-' + id, 'text': '保管资料。', 'status': 'pending', 'parentId': None}]}
              for id, name in [('a', '安禾'), ('b', '贝青'), ('c', '池远')]]
    return {'world': {'time': '0', 'places': [{'id': 'room', 'name': '工房', 'parentId': None}],
                      'items': [{'id': 'brush', 'name': '软刷', 'position': 'a'},
                                {'id': 'sheet', 'name': '图纸', 'position': 'room'}], 'characters': people},
            'actorId': 'a', 'protagonistId': 'a', 'advance': {'inputText': '先取软刷，再轻刷图纸；若贝青同意则交给他。', 'intentStatus': 'pending'},
            'confirmedPrefix': []}


def canonical_context():
    """Synthetic A/B WorldState shape, never a source of model labels."""
    old = context()
    time = {'calendar': 'gregorian', 'dateTime': '2026-11-09T12:00:00', 'instantOrdinal': 0}
    initial = {'engineVersion': 'world-engine-v1', 'schemaVersion': 1, 'worldId': 'world',
               'protagonistId': 'a', 'initialTime': time, 'locations': {}, 'items': {}, 'characters': {}}
    state = {'engineVersion': 'world-engine-v1', 'schemaVersion': 1, 'worldId': 'world',
             'protagonistId': 'a', 'time': time, 'initial': initial, 'locations': {}, 'items': {}, 'characters': {}}
    for place in old['world']['places']:
        initial['locations'][place['id']] = {'id': place['id'], 'name': place['name'],
                    'initialAppearance': '有窗户。', 'parentLocationId': place['parentId'], 'slots': []}
        state['locations'][place['id']] = {'id': place['id'], 'appearanceChanges': []}
    for kind in ('items', 'characters'):
        for item in old['world'][kind]:
            identity = {'id': item['id'], 'name': item['name'], 'initialAppearance': '便于辨认。',
                        'initialPosition': {'containerId': item['position'], 'slotId': None, 'relativeTo': None}, 'slots': []}
            current = {'id': item['id'], 'position': copy.deepcopy(identity['initialPosition']), 'appearanceChanges': []}
            if kind == 'characters':
                tasks = {t['id']: {'id': t['id'], 'ownerId': item['id'], 'parentTaskId': t['parentId'],
                                  'goal': t['text'], 'status': t['status']} for t in item['tasks']}
                identity.update(initialPersonality='谨慎。', initialSanity=item['sanity'], tasks=copy.deepcopy(tasks))
                current.update(sanity=item['sanity'], tasks=tasks, personalityChanges=[])
            initial[kind][item['id']] = identity
            state[kind][item['id']] = current
    old['world'] = state
    return old


def bindings(text, actor='a', representation='natural'):
    names = {'a': '安禾', 'b': '贝青', 'c': '池远', 'brush': '软刷', 'sheet': '图纸'}
    rows = []
    for id, name in names.items():
        surface = name if representation == 'natural' else '[[' + id + ']]'
        start = text.find(surface)
        if start >= 0:
            role = 'subject' if id == actor else 'recipient' if id in ('a', 'b', 'c') else 'tool' if id == 'brush' else 'object'
            rows.append({'role': role, 'entityId': id, 'start': start, 'end': start + len(surface)})
    return {'verdict': 'pass', 'references': rows}


def audit(component, ids):
    return {'verdict': 'pass', 'fragmentIds': ids, 'checks': {k: 'pass' for k in m.CHECKS[component]}, 'issues': []}


def sequence(texts, actor='a', representation='natural', decision=True):
    rows = [('D02.1', result('act'))] if decision else []
    for text in texts:
        rows += [('D02.2', result({'kind': 'fragment', 'text': text})),
                 ('D02.3', result(bindings(text, actor, representation)))]
    rows += [('D02.2', result({'kind': 'end'}))]
    ids = ['fragment-' + str(i + 1) for i in range(len(texts))]
    rows += [(component, result(audit(component, ids))) for component in m.CHECKS]
    return rows


class Script:
    """Exact protocol fixture, deliberately not exposed as a model provider."""
    def __init__(self, rows):
        self.rows, self.calls = list(rows), []

    def call(self, component, payload):
        self.calls.append((component, copy.deepcopy(payload)))
        wanted, output = self.rows.pop(0)
        if component != wanted:
            raise AssertionError((component, wanted))
        return copy.deepcopy(output)


class ShortIntentTests(unittest.TestCase):
    def test_multistep_conditional_preserves_raw_order_and_full_context(self):
        texts = ['安禾尝试拿起软刷。', '安禾尝试用软刷轻刷图纸。', '若贝青同意，安禾尝试把图纸交给贝青。']
        session = Script(sequence(texts))
        c = context()
        answer = m.produce_intent(session, c, 'op')
        self.assertEqual(answer.status, 'result')
        self.assertEqual(m.action_wire(answer), {'kind': 'act', 'text': '\n'.join(texts)})
        self.assertEqual(answer.value.opportunity_id, 'op')
        for component, payload in session.calls:
            self.assertEqual(payload['context'], c)
        next_calls = [p for key, p in session.calls if key == 'D02.2']
        self.assertEqual([len(p['fragments']) for p in next_calls], [0, 1, 2, 3])
        self.assertEqual(next_calls[-1]['fragments'][0]['text'], texts[0])

    def test_unsplittable_complete_intention_remains_one_fragment(self):
        text = '若贝青同意，安禾尝试一边用软刷轻刷图纸，一边把图纸递给贝青。'
        answer = m.produce_intent(Script(sequence([text])), context(), 'op')
        self.assertEqual(answer.value.text, text)
        self.assertEqual(len(answer.value.material()['fragments']), 1)

    def test_only_explicit_skip_adapts_to_skip(self):
        good = m.produce_intent(Script([('D02.1', result('skip'))]), context(), 'op')
        self.assertEqual(good.status, 'empty')
        self.assertEqual(m.action_wire(good), {'kind': 'skip'})
        for raw in (empty(), incomplete('timeout'), result('unknown')):
            bad = m.produce_intent(Script([('D02.1', raw)]), context(), 'op')
            self.assertEqual(bad.status, 'incomplete')
            with self.assertRaises(ContractError):
                m.action_wire(bad)

    def test_missing_player_input_is_not_skip(self):
        c = context(); c['advance']['inputText'] = None
        session = Script([])
        answer = m.produce_intent(session, c, 'op')
        self.assertEqual(answer.status, 'incomplete')
        self.assertEqual(session.calls, [])

    def test_semantic_incomplete_is_explicit_and_never_skip_or_fragment(self):
        for raw in (result('incomplete'), incomplete('semantic_incomplete:D02.1')):
            session = Script([('D02.1', raw)])
            answer = m.produce_intent(session, context(), 'op')
            self.assertEqual(answer.status, 'incomplete')
            self.assertEqual(answer.reason, 'semantic_incomplete:D02.1')
            self.assertEqual([c for c, _ in session.calls], ['D02.1'])
            with self.assertRaises(ContractError):
                m.action_wire(answer)

    def test_timeout_is_not_semantic_incomplete(self):
        answer = m.produce_intent(Script([('D02.1', incomplete('timeout'))]), context(), 'op')
        self.assertEqual(answer.status, 'incomplete')
        self.assertEqual(answer.reason, 'timeout')

    def test_consumed_input_is_retained_for_model_judgment(self):
        c = context(); c['advance']['intentStatus'] = 'consumed'
        session = Script([('D02.1', result('skip'))])
        self.assertEqual(m.produce_intent(session, c, 'op').status, 'empty')
        self.assertEqual(session.calls[0][1]['context']['advance'], c['advance'])

    def test_no_end_and_fragment_budget_cannot_become_first_step_success(self):
        texts = ['安禾尝试拿起软刷。', '安禾尝试轻刷图纸。']
        session = Script(sequence(texts))
        answer = m.produce_intent(session, context(), 'op', max_fragments=1)
        self.assertEqual(answer.status, 'incomplete')
        self.assertIn('budget_pause', answer.reason)
        self.assertFalse(any(c == 'D02.4' for c, _ in session.calls))

    def test_end_without_fragment_is_not_empty_action(self):
        answer = m.produce_intent(Script([('D02.1', result('act')), ('D02.2', result({'kind': 'end'}))]), context(), 'op')
        self.assertEqual(answer.status, 'incomplete')

    def test_wrong_tool_recipient_or_unknown_id_rejected_without_repair(self):
        for field, wrong in [('entityId', 'b'), ('entityId', 'new-person'), ('start', 1000)]:
            rows = sequence(['安禾尝试用软刷轻刷图纸。'])
            rows[2][1].value['references'][1][field] = wrong
            answer = m.produce_intent(Script(rows), context(), 'op')
            self.assertEqual(answer.status, 'incomplete')

    def test_model_role_and_step_audits_cannot_be_replaced_by_legal_ids(self):
        for component in m.CHECKS:
            rows = sequence(['安禾已经把图纸交给贝青。'])
            for c, completion in rows:
                if c == component:
                    completion.value['verdict'] = 'issue'
                    completion.value['issues'] = [{'fragmentId': 'fragment-1', 'code': 'asserted_success'}]
            answer = m.produce_intent(Script(rows), context(), 'op')
            self.assertEqual(answer.status, 'incomplete')

    def test_incomplete_fragment_audit_coverage_rejects(self):
        rows = sequence(['安禾尝试拿软刷。', '安禾尝试轻刷图纸。'])
        rows[-2][1].value['fragmentIds'] = ['fragment-1']
        answer = m.produce_intent(Script(rows), context(), 'op')
        self.assertEqual(answer.status, 'incomplete')

    def test_reference_replacement_is_single_pass_and_opt_in(self):
        text = '[[a]]尝试把[[sheet]]递给[[b]]。'
        answer = m.produce_intent(Script(sequence([text], representation='references')), context(), 'op', representation='references')
        self.assertEqual(answer.value.text, '安禾尝试把图纸递给贝青。')
        self.assertEqual(answer.value.material()['fragments'][0]['text'], text)
        bad = m.produce_intent(Script(sequence([text], representation='references')), context(), 'op')
        self.assertEqual(bad.status, 'incomplete')

    def test_frozen_candidate_has_no_mutable_text_or_reference_alias(self):
        answer = m.produce_intent(Script(sequence(['安禾尝试拿软刷。'])), context(), 'op')
        with self.assertRaises(FrozenInstanceError):
            answer.value.text = 'already succeeded'
        material = answer.value.material(); material['fragments'][0]['text'] = 'tampered'
        self.assertEqual(answer.value.verify().text, '安禾尝试拿软刷。')

    def test_full_roster_includes_distant_and_already_acted(self):
        c = context(); c['confirmedPrefix'] = [{'memberId': 'c', 'actionText': '池远尝试等待。'}]
        frozen = m.produce_intent(Script(sequence(['安禾尝试把图纸递给贝青。'])), c, 'op').value
        session = Script([('D03.1', result([{'candidateId': id, 'relation': 'target' if id == 'c' else 'none'} for id in ('a', 'b', 'c')])),
                          ('D03.2', result({'verdict': 'pass', 'candidateIds': ['a', 'b', 'c'], 'targetIds': ['c']}))])
        answer = m.analyze_targets(session, c, frozen, confirmed_group=[{'memberId': 'a', 'actionText': frozen.text}], already_acted_ids=['c'], judgments=[])
        self.assertEqual(answer.value, ['c'])
        self.assertEqual(session.calls[0][1]['source']['actionText'], frozen.text)
        self.assertEqual(session.calls[0][1]['candidateIds'], ['a', 'b', 'c'])

    def test_empty_targets_require_both_completed_full_checks(self):
        c = context(); action = m.produce_intent(Script(sequence(['安禾尝试拿软刷。'])), c, 'op').value
        rows = [('D03.1', result([{'candidateId': id, 'relation': 'none'} for id in ('a', 'b', 'c')])),
                ('D03.2', result({'verdict': 'pass', 'candidateIds': ['a', 'b', 'c'], 'targetIds': []}))]
        answer = m.analyze_targets(Script(rows), c, action, confirmed_group=[{'memberId': 'a', 'actionText': action.text}], already_acted_ids=[], judgments=[])
        self.assertEqual(answer.status, 'empty')
        self.assertEqual(m.targets_wire(answer), {'targets': []})
        rows[0][1].value.pop()
        failed = m.analyze_targets(Script(rows), c, action, confirmed_group=[{'memberId': 'a', 'actionText': action.text}], already_acted_ids=[], judgments=[])
        self.assertEqual(failed.status, 'incomplete')

    def test_stale_action_is_rejected_before_target_model(self):
        c = context(); action = m.produce_intent(Script(sequence(['安禾尝试拿软刷。'])), c, 'op').value
        c['world']['time'] = '1'
        answer = m.analyze_targets(Script([]), c, action, confirmed_group=[{'memberId': 'a', 'actionText': action.text}], already_acted_ids=[], judgments=[])
        self.assertEqual(answer.status, 'incomplete')

    def test_admitted_reaction_uses_constraints_and_never_ordinary_skip(self):
        c = context(); source = m.produce_intent(Script(sequence(['安禾尝试把图纸递给贝青。'])), c, 'op').value
        rows = [('D04.1', result({'threatSourceIds': ['a'], 'constraint': '回应安禾递来的图纸。'}))]
        rows += sequence(['贝青尝试接住图纸。'], actor='b', decision=False)
        session = Script(rows)
        answer = m.produce_reaction(session, c, 'react-b', member_id='b', confirmed_actions=[source],
                                   threats=[{'memberId': 'a', 'actionText': source.text}],
                                   judgments=[receipt('a', 'b')])
        self.assertEqual(answer.status, 'result')
        self.assertFalse(any(key == 'D02.1' for key, _ in session.calls))
        self.assertEqual(answer.value.actor_id, 'b')
        self.assertEqual(session.calls[1][1]['context']['actualJudgments'], [receipt('a', 'b')])

    def test_reaction_requires_full_actual_threats_and_does_not_use_dice_as_success(self):
        c = context(); source = m.produce_intent(Script(sequence(['安禾尝试把图纸递给贝青。'])), c, 'op').value
        answer = m.produce_reaction(Script([]), c, 'r', member_id='b', confirmed_actions=[source], threats=[], judgments=[receipt('a', 'b')])
        self.assertEqual(answer.status, 'incomplete')
        answer = m.produce_reaction(Script([]), c, 'r', member_id='b', confirmed_actions=[source],
                                   threats=[{'memberId': 'a', 'actionText': source.text}], judgments=[receipt('a', 'b', value=2)])
        self.assertEqual(answer.status, 'incomplete')

    def test_confirmed_reaction_is_reused_without_model_call(self):
        c = context(); a = m.produce_intent(Script(sequence(['安禾尝试拿软刷。'])), c, 'op').value
        bc = context(); bc['actorId'] = 'b'
        b = m.produce_intent(Script(sequence(['贝青尝试接住图纸。'], actor='b')), bc, 'op-b').value
        session = Script([])
        answer = m.produce_reaction(session, c, 'r', member_id='b', confirmed_actions=[a, b],
                                   threats=[{'memberId': 'a', 'actionText': a.text}], judgments=[receipt('a', 'b')])
        self.assertEqual(answer.value, b)
        self.assertEqual(session.calls, [])

    def test_actual_upstream_chain_expands_reaction_and_keeps_failed_judgment(self):
        rows = sequence(['安禾尝试把图纸递给贝青。'])
        rows += target_rows(['b', 'c'])
        rows += [('D04.1', result({'threatSourceIds': ['a'], 'constraint': '回应安禾递来的图纸。'}))]
        rows += sequence(['贝青尝试接住图纸。'], actor='b', decision=False)
        rows += target_rows([])
        rolls = []
        def actual_receipts(source, targets):
            rolls.append((source.text, targets))
            return [receipt(source.actor_id, target, value=18 if target == 'b' else 3) for target in targets]
        answer = m.run_action_chain(Script(rows), context(), 'op', roll_targets=actual_receipts)
        self.assertEqual(answer.status, 'result', answer.reason)
        self.assertEqual([x['memberId'] for x in answer.value['members']], ['a', 'b'])
        self.assertEqual(len(answer.value['judgments']), 2)
        self.assertFalse(answer.value['judgments'][1]['admitted'])
        self.assertEqual(rolls, [('安禾尝试把图纸递给贝青。', ('b', 'c'))])
        self.assertTrue(answer.value['closed'])

    def test_target_failure_prevents_any_dice(self):
        rows = sequence(['安禾尝试拿软刷。']) + [('D03.1', incomplete('timeout'))]
        answer = m.run_action_chain(Script(rows), context(), 'op', roll_targets=lambda *_: self.fail('dice ran'))
        self.assertEqual(answer.status, 'incomplete')

    def test_chain_budget_pause_is_not_handback_or_closed_group(self):
        rows = sequence(['安禾尝试把图纸递给贝青。']) + target_rows(['b'])
        rows += [('D04.1', result({'threatSourceIds': ['a'], 'constraint': '回应递纸。'}))]
        rows += sequence(['贝青尝试接住图纸。'], actor='b', decision=False)
        answer = m.run_action_chain(Script(rows), context(), 'op', roll_targets=lambda *_: [receipt('a', 'b')], max_sources=1)
        self.assertEqual(answer.status, 'incomplete')
        self.assertIn('budget_pause', answer.reason)

    def test_restore_rejects_another_opportunity_and_modified_text(self):
        c = context()
        action = m.produce_intent(Script(sequence(['安禾尝试拿软刷。'])), c, 'op').value
        restored = m.restore_action(asdict(action), c, 'op')
        self.assertEqual(restored, action)
        with self.assertRaises(ContractError):
            m.restore_action(asdict(action), c, 'another-op')
        record = asdict(action); record['text'] += '动作成功。'
        with self.assertRaises(ContractError):
            m.restore_action(record, c, 'op')

    def test_target_source_and_roll_receipt_identity_is_checked(self):
        c = context(); action = m.produce_intent(Script(sequence(['安禾尝试拿软刷。'])), c, 'op').value
        for group, judgments in [([], []),
                                  ([{'memberId': 'a', 'actionText': '改写的行动。'}], []),
                                  ([{'memberId': 'a', 'actionText': action.text}], [receipt('a', 'b')])]:
            answer = m.analyze_targets(Script([]), c, action, confirmed_group=group,
                                       already_acted_ids=[], judgments=judgments)
            self.assertEqual(answer.status, 'incomplete')

    def test_already_acted_target_still_gets_judgment_without_second_action(self):
        c = context(); c['confirmedPrefix'] = [{'memberId': 'c', 'actionText': '池远尝试等待。'}]
        rows = sequence(['安禾尝试把图纸递给贝青。']) + target_rows(['c'])
        calls = []
        def roll(source, targets):
            calls.append(targets)
            return [receipt('a', 'c', eligible=False)]
        answer = m.run_action_chain(Script(rows), c, 'op', roll_targets=roll)
        self.assertEqual(answer.status, 'result', answer.reason)
        self.assertEqual(calls, [('c',)])
        self.assertEqual(len(answer.value['members']), 1)
        self.assertFalse(answer.value['judgments'][0]['eligible'])

    def test_actual_worldstate_is_preserved_without_flattening_initial_or_records(self):
        c = canonical_context()
        c['world']['initial']['characters']['a']['slots'] = [{'id': 'pocket', 'label': '左口袋'}]
        c['world']['items']['brush']['position']['slotId'] = 'pocket'
        c['world']['characters']['a']['appearanceChanges'] = [
            {'id': 'record-1', 'text': '袖口湿了。', 'supersedes': [], 'sourcePointId': 'point-old', 'sourceSequence': 1, 'active': False},
            {'id': 'record-2', 'text': None, 'supersedes': ['record-1'], 'sourcePointId': 'point-current', 'sourceSequence': 2, 'active': True}]
        session = Script(sequence(['安禾尝试拿软刷。']) + target_rows([]))
        answer = m.run_action_chain(session, c, 'op', roll_targets=lambda *_: self.fail('no targets'))
        self.assertEqual(answer.status, 'result', answer.reason)
        self.assertEqual(answer.value['memberIds'], ['a'])
        self.assertEqual(answer.value['members'][0]['fragments'], [{'id': 'a:fragment-1', 'text': '安禾尝试拿软刷。'}])
        for _, payload in session.calls:
            self.assertEqual(payload['context']['world'], c['world'])

    def test_author_answer_metadata_rejected_but_legitimate_slot_labels_preserved(self):
        for key in ('ExpectedOutput', 'goldLabel', 'draft_target', 'review'):
            c = canonical_context(); c[key] = 'scripted answer'
            answer = m.produce_intent(Script([]), c, 'op')
            self.assertEqual(answer.status, 'incomplete')
            self.assertIn('leakage', answer.reason)

    def test_real_session_missing_provider_is_incomplete_no_fixed_answer(self):
        session = ModelSession(None, binding={'pointId': 'p', 'version': 1},
                               identity=ModelIdentity('missing', 'missing', 'missing', 'missing', 'fp32', 'test'))
        answer = m.produce_intent(session, context(), 'op')
        self.assertEqual(answer.status, 'incomplete')
        self.assertIn('model_unavailable', answer.reason)
        self.assertEqual(len(session.attempts), 1)


def receipt(source, target, value=18, eligible=True):
    return {'rollId': 'roll-' + source + '-' + target, 'sourceId': source, 'targetId': target,
            'result': value, 'target': 11, 'eligible': eligible, 'admitted': eligible and value >= 11,
            'ruleVersion': 'reaction-d20-v1', 'groupId': 'group', 'triggerKey': 'trigger-' + source + '-' + target,
            'eligibilityBaselineDigest': '0' * 64}


def target_rows(targets):
    return [('D03.1', result([{'candidateId': id, 'relation': 'target' if id in targets else 'none'} for id in ('a', 'b', 'c')])),
            ('D03.2', result({'verdict': 'pass', 'candidateIds': ['a', 'b', 'c'], 'targetIds': targets}))]


if __name__ == '__main__':
    unittest.main()
