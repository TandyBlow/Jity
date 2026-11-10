"""Engineering tests for the candidate D02 checkers; no model capability claim."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import short_d02_checkers as m


def world():
    return {'entities': {
        'a': {'type': 'character', 'name': '林澈', 'aliases': ['小澈']},
        'b': {'type': 'character', 'name': '周岚'},
        'key': {'type': 'item', 'name': '铜钥匙', 'aliases': ['钥匙']},
        'door': {'type': 'item', 'name': '铁门'},
        'warehouse': {'type': 'location', 'name': '仓库'},
        'lamp': {'type': 'item', 'name': '提灯'},
    }}


def steps_of(*texts):
    text = '\n'.join(texts)
    steps, cursor = [], 0
    for index, value in enumerate(texts):
        steps.append({'stepId': 's' + str(index + 1), 'start': cursor,
                      'end': cursor + len(value)})
        cursor += len(value) + 1
    return text, steps


def span(text, surface, occurrence=0):
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(surface, start + 1)
    return start, start + len(surface)


def mention(text, surface, roles, *, status='bound', entity=None, basis='name',
            diagnostic=None, occurrence=0, candidates=None, scope='main'):
    start, end = span(text, surface, occurrence)
    row = {'mentionId': 'm' + str(start) + '_' + str(end),
           'start': start, 'end': end, 'surface': surface, 'roles': roles,
           'diagnosticRoles': diagnostic or [], 'status': status,
           'bindingBasis': basis, 'scope': scope}
    if entity is not None:
        row['entityId'] = entity
    if candidates is not None:
        row['candidates'] = candidates
    return row


def role_audit(text, steps, mentions, *, issues=None, role_override=None):
    rows = []
    for step in steps:
        own = [x for x in mentions if step['start'] <= x['start'] < step['end']]
        role_status = {}
        for role in m.ROLES:
            ids = [x['mentionId'] for x in own if role in x['roles']]
            if not ids:
                role_status[role] = {'status': 'absent', 'mentionIds': []}
                continue
            statuses = {x['status'] for x in own if x['mentionId'] in ids}
            status = ('ambiguous' if 'ambiguous' in statuses else
                      'unknown_entity' if 'unknown_entity' in statuses else
                      'insufficient' if 'insufficient' in statuses else 'bound')
            role_status[role] = {'status': status, 'mentionIds': ids}
        if role_override:
            role_status.update(role_override.get(step['stepId'], {}))
        rows.append({'stepId': step['stepId'], 'mentions': own,
                     'roleStatus': role_status})
    return {'schema': m.ROLE_SCHEMA, 'textSha256': m.digest(text),
            'steps': rows, 'issues': issues or []}


def expression(text, label='attempt', issues=None, abstain=None):
    return {'schema': m.EXPRESSION_SCHEMA, 'textSha256': m.digest(text),
            'label': label, 'issues': issues or [], 'abstain': abstain}


def check(text, steps, role, expr=None):
    return m.check_once(text, steps, role, expr or expression(text), world(), 'a')


def codes(result):
    return {row['code'] for row in result.issues}


class RoleValidationTests(unittest.TestCase):
    def test_natural_name_attempt_without_the_word_attempt_is_accepted(self):
        text, steps = steps_of('林澈用铜钥匙开铁门。')
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '铜钥匙', ['tool'], entity='key'),
            mention(text, '铁门', ['object'], entity='door'),
        ])
        result = check(text, steps, audit)
        self.assertEqual(result.decision, 'accept')
        self.assertEqual(codes(result), set())

    def test_reference_marker_is_accepted(self):
        text, steps = steps_of('[[a]]用[[key]]开[[door]]。')
        audit = role_audit(text, steps, [
            mention(text, '[[a]]', ['subject'], entity='a', basis='marker'),
            mention(text, '[[key]]', ['tool'], entity='key', basis='marker'),
            mention(text, '[[door]]', ['object'], entity='door', basis='marker'),
        ])
        result = m.check_once(text, steps, audit, expression(text), world(), 'a',
                              representation='references')
        self.assertEqual(result.decision, 'accept')

    def test_surface_mismatch_is_incomplete_not_a_semantic_failure(self):
        text, steps = steps_of('林澈用铜钥匙开铁门。')
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='b'),
            mention(text, '铜钥匙', ['tool'], entity='key'),
            mention(text, '铁门', ['object'], entity='door'),
        ])
        result = check(text, steps, audit)
        self.assertEqual(result.decision, 'incomplete')
        self.assertIn('surface_name_mismatch', codes(result))

    def test_actor_mismatch_is_upgraded_and_text_is_not_rewritten(self):
        text, steps = steps_of('周岚用铜钥匙开铁门。')
        audit = role_audit(text, steps, [
            mention(text, '周岚', ['subject'], entity='b'),
            mention(text, '铜钥匙', ['tool'], entity='key'),
            mention(text, '铁门', ['object'], entity='door'),
        ])
        result = check(text, steps, audit)
        self.assertEqual(result.decision, 'upgrade')
        self.assertIn('actor_mismatch', codes(result))
        self.assertEqual(text, '周岚用铜钥匙开铁门。')

    def test_pronoun_binding_requires_api_review_even_when_bound(self):
        text, steps = steps_of('他拿起铜钥匙。')
        audit = role_audit(text, steps, [
            mention(text, '他', ['subject'], entity='b', basis='pronoun'),
            mention(text, '铜钥匙', ['object'], entity='key'),
        ])
        result = check(text, steps, audit)
        self.assertIn('reference_requires_review', codes(result))

    def test_alias_is_outside_first_auto_accept_scope(self):
        text, steps = steps_of('林澈拿起钥匙。')
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '钥匙', ['object'], entity='key', basis='alias'),
        ])
        result = check(text, steps, audit)
        self.assertEqual(result.decision, 'upgrade')
        self.assertIn('alias_requires_review', codes(result))

    def test_unregistered_mention_is_not_null_absence(self):
        text, steps = steps_of('林澈拿起黑匣子。')
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '黑匣子', ['object'], status='unknown_entity'),
        ])
        result = check(text, steps, audit)
        self.assertEqual(result.decision, 'upgrade')
        self.assertIn('unresolved_role_object', codes(result))

    def test_ambiguous_entity_is_upgraded(self):
        text, steps = steps_of('林澈拿起钥匙。')
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '钥匙', ['object'], status='ambiguous',
                    basis='alias', candidates=['key', 'lamp']),
        ])
        result = check(text, steps, audit)
        self.assertEqual(result.decision, 'upgrade')
        self.assertIn('unresolved_role_object', codes(result))

    def test_implicit_subject_is_insufficient_not_absent(self):
        text, steps = steps_of('拿起铜钥匙。')
        issue = {'code': 'implicit_subject', 'message': 'subject omitted',
                 'blocking': True, 'stepId': 's1', 'scope': 'main'}
        audit = role_audit(text, steps, [
            mention(text, '铜钥匙', ['object'], entity='key'),
        ], issues=[issue], role_override={'s1': {
            'subject': {'status': 'insufficient', 'mentionIds': []}}})
        result = check(text, steps, audit)
        self.assertEqual(result.decision, 'upgrade')
        self.assertIn('unresolved_role_subject', codes(result))

    def test_same_entity_can_shift_from_object_to_tool(self):
        text, steps = steps_of('林澈拿起铜钥匙。', '林澈用铜钥匙开铁门。')
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '铜钥匙', ['object'], entity='key'),
            mention(text, '林澈', ['subject'], entity='a', occurrence=1),
            mention(text, '铜钥匙', ['tool'], entity='key', occurrence=1),
            mention(text, '铁门', ['object'], entity='door'),
        ])
        result = check(text, steps, audit)
        self.assertEqual(result.decision, 'accept')

    def test_recipient_is_public_but_source_is_diagnostic_only(self):
        text, steps = steps_of('林澈把铜钥匙交给周岚。')
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '铜钥匙', ['object'], entity='key'),
            mention(text, '周岚', ['recipient'], entity='b'),
        ])
        self.assertEqual(check(text, steps, audit).decision, 'accept')
        source_text, source_steps = steps_of('林澈从周岚那里取回铜钥匙。')
        source_audit = role_audit(source_text, source_steps, [
            mention(source_text, '林澈', ['subject'], entity='a'),
            mention(source_text, '周岚', [], diagnostic=['source'], entity='b'),
            mention(source_text, '铜钥匙', ['object'], entity='key'),
        ])
        result = check(source_text, source_steps, source_audit)
        self.assertEqual(result.decision, 'upgrade')
        self.assertIn('diagnostic_role_requires_review', codes(result))

    def test_static_location_in_waiting_is_not_disguised_as_destination(self):
        text, steps = steps_of('林澈在仓库等待。')
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '仓库', [], diagnostic=['static_location'], entity='warehouse'),
        ])
        result = check(text, steps, audit)
        self.assertEqual(result.decision, 'upgrade')
        self.assertIn('diagnostic_role_requires_review', codes(result))

    def test_role_type_mismatch_is_reported_after_assignment(self):
        text, steps = steps_of('林澈用周岚开铁门。')
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '周岚', ['tool'], entity='b'),
            mention(text, '铁门', ['object'], entity='door'),
        ])
        result = check(text, steps, audit)
        self.assertEqual(result.decision, 'upgrade')
        self.assertIn('role_type_mismatch', codes(result))

    def test_missing_role_status_is_a_contract_error(self):
        text, steps = steps_of('林澈用铜钥匙开铁门。')
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '铜钥匙', ['tool'], entity='key'),
            mention(text, '铁门', ['object'], entity='door'),
        ])
        del audit['steps'][0]['roleStatus']['recipient']
        result = check(text, steps, audit)
        self.assertEqual(result.decision, 'incomplete')
        self.assertIn('invalid_role_status', codes(result))


class ExpressionValidationTests(unittest.TestCase):
    def test_unsettled_result_is_upgraded(self):
        text, steps = steps_of('林澈用铜钥匙开锁，门已经打开了。')
        issue = {'code': 'unsettled_result', 'message': 'result stated as done',
                 'blocking': True, 'stepId': 's1', 'scope': 'main',
                 'start': span(text, '门已经打开了。')[0],
                 'end': span(text, '门已经打开了。')[1]}
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '铜钥匙', ['tool'], entity='key'),
        ])
        result = check(text, steps, audit, expression(text, 'mixed', [issue]))
        self.assertEqual(result.decision, 'upgrade')
        self.assertIn('unsettled_result', codes(result))

    def test_condition_success_word_is_not_an_asserted_result(self):
        text, steps = steps_of('如果开锁成功，林澈就进入房间。')
        issue = {'code': 'success_word_in_condition', 'message': 'inside condition',
                 'blocking': False, 'stepId': 's1', 'scope': 'condition',
                 'start': span(text, '成功')[0], 'end': span(text, '成功')[1]}
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
        ])
        result = check(text, steps, audit, expression(text, 'attempt', [issue]))
        self.assertEqual(result.decision, 'accept')

    def test_quoted_result_is_not_world_fact(self):
        text, steps = steps_of('林澈喊道：“我已经拿到铜钥匙了！”')
        issue = {'code': 'success_word_in_quote', 'message': 'quoted speech',
                 'blocking': False, 'stepId': 's1', 'scope': 'quote',
                 'start': span(text, '我已经拿到铜钥匙了')[0],
                 'end': span(text, '我已经拿到铜钥匙了')[1]}
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '铜钥匙', ['object'], entity='key'),
        ])
        result = check(text, steps, audit, expression(text, 'attempt', [issue]))
        self.assertEqual(result.decision, 'accept')

    def test_background_fact_is_not_a_new_result(self):
        text, steps = steps_of('铁门已经打开，林澈尝试进入。')
        issue = {'code': 'success_word_in_background', 'message': 'known background',
                 'blocking': False, 'stepId': 's1', 'scope': 'background',
                 'start': span(text, '铁门已经打开')[0],
                 'end': span(text, '铁门已经打开')[1]}
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '铁门', ['object'], entity='door'),
        ])
        result = check(text, steps, audit, expression(text, 'attempt', [issue]))
        self.assertEqual(result.decision, 'accept')

    def test_non_action_and_uncertain_upgrade_without_skip(self):
        for label in ('non_action', 'uncertain'):
            text, steps = steps_of('林澈希望铁门自己打开。')
            audit = role_audit(text, steps, [
                mention(text, '林澈', ['subject'], entity='a'),
                mention(text, '铁门', ['object'], entity='door'),
            ])
            result = check(text, steps, audit, expression(text, label))
            self.assertEqual(result.decision, 'upgrade')
            self.assertNotEqual(result.decision, 'skip')

    def test_low_confidence_abstain_upgrades_but_oversize_input_is_incomplete(self):
        text, steps = steps_of('林澈用铜钥匙开铁门。')
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '铜钥匙', ['tool'], entity='key'),
            mention(text, '铁门', ['object'], entity='door'),
        ])
        low = expression(text, None, abstain={'reason': 'low_confidence',
                                             'detail': '别名的指代不稳'})
        self.assertEqual(check(text, steps, audit, low).decision, 'upgrade')
        long = expression(text, None, abstain={'reason': 'input_too_long',
                                             'detail': '超出支持范围'})
        self.assertEqual(check(text, steps, audit, long).decision, 'incomplete')

    def test_result_label_without_main_scope_problem_is_an_explicit_upgrade(self):
        text, steps = steps_of('林澈用铜钥匙开铁门。')
        audit = role_audit(text, steps, [
            mention(text, '林澈', ['subject'], entity='a'),
            mention(text, '铜钥匙', ['tool'], entity='key'),
            mention(text, '铁门', ['object'], entity='door'),
        ])
        result = check(text, steps, audit, expression(text, 'result_assertion'))
        self.assertEqual(result.decision, 'upgrade')
        self.assertIn('inconsistent_result_label', codes(result))


class LoopTests(unittest.TestCase):
    def _result(self, decision, code):
        return m.CheckResult(decision, ({'code': code, 'message': code,
            'blocking': True, 'scope': 'main', 'stepId': None, 'start': None,
            'end': None, 'source': 'program'},))

    def test_repair_acceptance_is_recorded_as_api_path(self):
        calls = []

        def check(text):
            calls.append(('check', text))
            return self._result('accept', 'ok') if text == 'fixed' else self._result('upgrade', 'actor_mismatch')

        def repair(issues, text):
            calls.append(('repair', text, len(issues)))
            return 'fixed'

        out = m.run_bounded_check('broken', check, repair=repair)
        self.assertEqual(out['decision'], 'accept')
        self.assertEqual(out['acceptedVia'], 'api_repair')
        self.assertEqual(calls[1][2], 1)

    def test_repair_must_change_text_and_stops_after_one_round(self):
        out = m.run_bounded_check('same', lambda text: self._result('upgrade', 'x'),
                                  repair=lambda issues, text: text)
        self.assertEqual(out['decision'], 'incomplete')
        self.assertEqual(out['reason'], 'repair_no_change')

    def test_failure_after_repair_does_not_get_a_second_round(self):
        out = m.run_bounded_check('broken', lambda text: self._result('upgrade', 'x'),
                                  repair=lambda issues, text: text + '!')
        self.assertEqual(out['decision'], 'incomplete')
        self.assertEqual(out['reason'], 'unresolved_after_repair')
        self.assertEqual(len(out['rounds']), 2)

    def test_coverage_regression_blocks_acceptance(self):
        out = m.run_bounded_check('broken',
            lambda text: self._result('accept', 'ok') if text == 'fixed' else self._result('upgrade', 'x'),
            repair=lambda issues, text: 'fixed', coverage=lambda text: False)
        self.assertEqual(out['decision'], 'incomplete')
        self.assertEqual(out['reason'], 'coverage_regressed_after_repair')

    def test_api_skip_is_not_produced_by_a_checker(self):
        out = m.run_bounded_check('anything', lambda text: self._result('accept', 'ok'),
                                  skip=True)
        self.assertEqual(out['decision'], 'skip')
        self.assertEqual(out['acceptedVia'], 'api_skip')


class IndexTests(unittest.TestCase):
    def test_utf16_boundaries_round_trip_with_astral_characters(self):
        text = '甲🔑𠮷乙'
        for index in range(len(text) + 1):
            utf16 = m.codepoint_to_utf16(text, index)
            self.assertEqual(m.utf16_to_codepoint(text, utf16), index)

    def test_utf16_boundary_inside_surrogate_pair_is_rejected(self):
        with self.assertRaises(m.CheckError):
            m.utf16_to_codepoint('甲🔑乙', 2)


if __name__ == '__main__':
    unittest.main()
