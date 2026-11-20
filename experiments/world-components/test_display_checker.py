"""Cases that must not slip through the three-state check.

Each case is a pair: a fact and a sentence that looks close to it. The expected state is written
next to the case, so a regression in the patterns shows up as a named failure rather than a shift in
an aggregate.
"""
import unittest

from check_fact_display import check
from render_fact import render

MOVED = {'kind': 'moved', 'name': '沈砚', 'from': '潮渡', 'to': '雾堤', 'direction': '平'}
SANITY = {'kind': 'sanity_changed', 'name': '沈砚', 'from': 12, 'to': 9}
RELATION = {'kind': 'appearance_changed', 'name': '潮汐簿', 'relation': '压', 'other': '干纸',
            'role': 'locationReference', 'text': '滑开了'}
PLAIN = {'kind': 'appearance_changed', 'name': '沈砚', 'text': '指尖沾了墨'}
DIKE = {'kind': 'appearance_changed', 'name': '排水沟', 'text': '里面积了泥'}
NO_CHANGE = {'kind': 'no_change', 'name': None, 'text': ''}


class CheckCases(unittest.TestCase):
    def test_word_overlap_does_not_authorise_a_pass(self):
        # the archived false accept: subject present, part of the state text present, fact not kept
        state, why = check(DIKE, '排水沟里的泥在墙根上蹭了泥。')
        self.assertEqual(state, 'undetermined', why)

    def test_negated_change_is_a_mismatch(self):
        state, why = check(PLAIN, '沈砚的指尖没有沾墨。')
        self.assertEqual(state, 'mismatch', why)

    def test_reversed_relation_is_a_mismatch(self):
        state, why = check(RELATION, '潮汐簿压着的干纸滑开了。')
        self.assertEqual(state, 'mismatch', why)

    def test_correct_relation_passes(self):
        state, why = check(RELATION, '压在潮汐簿上的干纸滑开了。')
        self.assertEqual(state, 'pass', why)

    def test_relational_fact_without_fields_is_undetermined(self):
        bare = {'kind': 'appearance_changed', 'name': '石缸', 'text': '压在石缸上的木板裂了'}
        state, why = check(bare, '石缸压在石缸上的木板裂了。')
        self.assertEqual(state, 'undetermined', why)

    def test_arrival_with_an_added_object_is_a_mismatch(self):
        state, why = check(MOVED, '沈砚从潮渡过来,船头抵住雾堤的栈桥。')
        self.assertEqual(state, 'mismatch', why)
        self.assertIn('adds', why)

    def test_arrival_with_an_added_posture_is_a_mismatch(self):
        state, why = check(MOVED, '沈砚从潮渡过来,在雾堤站住。')
        self.assertEqual(state, 'mismatch', why)

    def test_plain_arrival_passes(self):
        state, why = check(MOVED, '沈砚从潮渡走到雾堤。')
        self.assertEqual(state, 'pass', why)

    def test_abbreviated_destination_passes_and_says_so(self):
        fact = dict(MOVED, to='潮汐档案馆')
        state, why = check(fact, '沈砚从潮渡走进档案馆。')
        self.assertEqual(state, 'pass', why)
        self.assertIn('abbreviated', why)

    def test_destination_named_but_never_reached(self):
        state, why = check(MOVED, '沈砚离开雾堤,沿着雾堤的墙边。')
        self.assertEqual(state, 'mismatch', why)

    def test_sanity_written_as_no_change_is_a_mismatch(self):
        state, why = check(SANITY, '沈砚的理智没有变化。')
        self.assertEqual(state, 'mismatch', why)

    def test_no_change_with_an_action_is_a_mismatch(self):
        state, why = check(NO_CHANGE, '韩渡推开档案馆的门,周围没有新的变化。')
        self.assertEqual(state, 'mismatch', why)

    def test_no_change_without_scope_is_not_rendered(self):
        result = render(NO_CHANGE)
        self.assertIsNone(result['sentence'])
        self.assertIn('scope', result['gap'])

    def test_plain_fact_renders_without_claiming_direction(self):
        result = render(PLAIN)
        self.assertTrue(result['complete'])
        self.assertIn('not verified', result['note'])


if __name__ == '__main__':
    unittest.main()
