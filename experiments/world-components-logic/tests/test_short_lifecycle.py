"""Engineering counterexamples only. Scripted providers are not model scores."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from short_contracts import (Completion, ContractError, CostLedger, FrozenValue,
                             ModelIdentity, ModelSession, digest, empty, incomplete, result)
from short_lifecycle import InitialDraft, continuation, continuation_wire, propose_segments, propose_time
from short_handoff import PointHandoff, committed_packet
from short_heads_lifecycle import LifecycleHeads


IDENTITY = ModelIdentity('engineering_test_double', 'fixture', 'fixture', 'fixture', 'none', 'fixture')
TIME = {'boundary': 'elapsed', 'duration': {'amount': 1, 'unit': 'minute'}}
INSTANT = {'boundary': 'instant', 'duration': {'amount': 0, 'unit': 'second'}}


def session(provider, **kw):
    return ModelSession(provider, binding={'worldId': 'w', 'version': 0}, identity=IDENTITY, **kw)


class CompletionTests(unittest.TestCase):
    def test_error_cannot_be_empty(self):
        with self.assertRaises(ContractError):
            Completion('empty', reason='timeout')
        self.assertEqual(session(None).call('D02.1', {}).status, 'incomplete')

    def test_timeout_not_negative(self):
        import time
        def slow(*_):
            time.sleep(.002)
            return empty()
        s = session(slow, timeout_ms=.01)
        self.assertEqual(s.call('D03', {}).reason, 'timeout')
        self.assertEqual(s.attempts[0]['rawOutput']['status'], 'empty')

    def test_cancelled_late_output_never_applied(self):
        s = session(None)
        def provider(*_):
            s.cancel()
            return result('act')
        s.provider = provider
        self.assertEqual(s.call('D02.1', {}).status, 'incomplete')
        self.assertEqual(s.call('D02.1', {}).reason, 'cancelled')

    def test_retries_keep_first_output(self):
        answers = iter([incomplete('truncated'), result('act')])
        s = session(lambda *_: next(answers), retries=1)
        self.assertEqual(s.call('D02.1', {}).value, 'act')
        self.assertEqual([x['status'] for x in s.attempts], ['incomplete', 'result'])

    def test_cache_binds_actual_state_and_identity(self):
        count = []
        s = session(lambda *_: (count.append(1) or result('act')), cache=True)
        for payload in ({'world': 1}, {'world': 1}, {'world': 2}):
            s.call('D02.1', payload)
        self.assertEqual(len(count), 2)
        self.assertEqual(len(s.cache_events), 1)
        self.assertFalse(s.cache_events[0]['modelCalled'])
        self.assertEqual(s.cache_events[0]['inputHash'], digest({'world': 1}))
        s.identity = ModelIdentity('other', 'fixture', 'fixture', 'fixture', 'none', 'fixture')
        s.call('D02.1', {'world': 2})
        s.binding['version'] = 1
        s.call('D02.1', {'world': 2})
        self.assertEqual(len(count), 4)

    def test_frozen_nested_values_are_not_mutable(self):
        original = {'a': [1]}
        frozen = FrozenValue(original)
        original['a'].append(2)
        frozen.read()['a'].append(3)
        self.assertEqual(frozen.read(), {'a': [1]})

    def test_budget_never_handback(self):
        s = session(lambda *_: empty(), max_calls=1)
        s.call('D07', {})
        self.assertEqual(s.call('D07', {}).reason, 'budget_paused')

    def test_timing_partial_or_stub_cannot_pass_full_500(self):
        ledger = CostLedger({'actors': 3, 'scope': 'complete_request'})
        ledger.record('gate_wait', 2)
        self.assertEqual(ledger.finish(scope='D02', completed=True, real_models=True, c_ready=True)['performance500ms'], 'unverified')
        self.assertEqual(ledger.finish(scope='complete_request', completed=True, real_models=False, c_ready=True)['performance500ms'], 'unverified')


class LifecycleTests(unittest.TestCase):
    def test_time_rejects_values_outside_existing_wire_safe_integer(self):
        for amount in (True, -1, 9007199254740992):
            value = {'boundary': 'elapsed', 'duration': {'amount': amount, 'unit': 'year'}}
            for locked in (False, True):
                context = {'world': {}, 'pointId': 'p', 'timeLocked': locked, 'timeAdvance': value}
                self.assertEqual(propose_time(session(lambda *_: result(value)), context).status, 'incomplete')

    def test_negative_budgets_do_not_skip_work(self):
        self.assertEqual(continuation(session(None), {}, lambda: 'r', max_candidates=-1).status, 'incomplete')
        self.assertEqual(InitialDraft('draft', 'world', {}).generate(session(None), max_tasks_per_character=-1).status, 'incomplete')

    def test_stale_world_and_ready_are_not_round_completion(self):
        c = self.context()
        c['world']['characters']['a']['changed'] = True
        self.assertEqual(continuation(session(None), c, lambda: 'r', verify_round=lambda _: True).reason, 'stale_continuation_world')
        c = self.context()
        c['readyReceipts'][0]['generation'] = 0
        self.assertEqual(continuation(session(None), c, lambda: 'r', verify_round=lambda _: True).reason, 'stale_ready_receipt')

    def test_cross_segment_reordered_slots_and_elapsed_instant_reject(self):
        c = {'world': {}, 'roundId': 'r', 'order': ['a', 'b', 'c'], 'actedIds': [], 'visitedIds': [], 'frozenActions': {}}
        proposals = [
            [{'kind': 'instant', 'timeAdvance': TIME, 'actorIds': ['a']}],
            [{'kind': 'normal', 'timeAdvance': TIME, 'actorIds': ['b']},
             {'kind': 'instant', 'timeAdvance': INSTANT, 'actorIds': ['c']},
             {'kind': 'linked', 'timeAdvance': INSTANT, 'actorIds': ['a']}]]
        for p in proposals:
            self.assertEqual(propose_segments(session(lambda *_: result(p)), c, lambda i: f'p{i}').status, 'incomplete')

    def context(self):
        return {'world': {'worldId': 'w', 'characters': {'a': {}}}, 'roundId': 'r', 'requiredPointIds': ['p', 'linked'],
                'completedPointIds': ['p', 'linked'], 'readyPointIds': ['p', 'linked'],
                'roundComplete': True, 'budgetPaused': False,
                'committedHead': {'worldId': 'w', 'pointId': 'linked', 'version': 2, 'stateDigest': 'd2'},
                'currentWorldHash': digest({'worldId': 'w', 'characters': {'a': {}}}),
                'requiredGates': {p: {'pointId': p, 'generation': 1} for p in ['p', 'linked']},
                'readyReceipts': [{'pointId': p, 'generation': 1, 'status': 'ready'} for p in ['p', 'linked']],
                'roundChanges': {'roundId': 'r', 'points': [
                    {'pointId': 'p', 'previousPointId': 'root', 'version': 1, 'stateDigest': 'd1', 'timeAdvance': TIME, 'entityDeltas': {}},
                    {'pointId': 'linked', 'previousPointId': 'p', 'version': 2, 'stateDigest': 'd2', 'timeAdvance': INSTANT, 'entityDeltas': {}}]}}

    def test_related_and_likely_are_both_required(self):
        outputs = iter([result({'kind': 'candidate', 'characterId': 'a', 'text': '尝试检查门闩。'}),
                        result({'kind': 'end'}), result('likely'), result('unrelated')])
        value = continuation(session(lambda *_: next(outputs)), self.context(), lambda: self.fail('round allocated'), verify_round=lambda _: True)
        self.assertEqual(value.status, 'empty')
        self.assertEqual(continuation_wire(value)['kind'], 'handback')

    def test_missing_linked_ready_blocks_before_models(self):
        ctx = self.context()
        ctx['readyPointIds'] = ['p']
        s = session(lambda *_: self.fail('model called before linked ready'))
        self.assertEqual(continuation(s, ctx, lambda: 'next').status, 'incomplete')

    def test_round_change_coverage_blocks_missing_segment(self):
        ctx = self.context()
        ctx['roundChanges']['points'].pop()
        self.assertEqual(continuation(session(None), ctx, lambda: 'next').status, 'incomplete')

    def test_unfinished_cannot_map_to_handback(self):
        with self.assertRaises(ContractError):
            continuation_wire(incomplete('cancelled'))

    def test_time_lock_reuses_value_without_model(self):
        s = session(lambda *_: self.fail('locked time resampled'))
        c = {'world': {}, 'pointId': 'p', 'timeLocked': True, 'timeAdvance': TIME}
        self.assertEqual(propose_time(s, c).value, TIME)

    def test_invalid_time_not_coerced(self):
        bad = {'boundary': 'elapsed', 'duration': {'amount': 1.2, 'unit': 'minute'}}
        c = {'world': {}, 'pointId': 'p', 'timeLocked': False, 'timeAdvance': None}
        self.assertEqual(propose_time(session(lambda *_: result(bad)), c).status, 'incomplete')

    def test_segment_suggestions_are_not_visits(self):
        c = {'world': {}, 'roundId': 'r', 'order': ['a', 'b'], 'actedIds': [], 'visitedIds': [], 'frozenActions': {}}
        s = session(lambda *_: result([{'kind': 'normal', 'timeAdvance': TIME, 'actorIds': ['a']}]))
        out = propose_segments(s, c, lambda _: 'newpoint')
        self.assertEqual(out.value['visitedIds'], [])
        self.assertEqual(out.value['unassignedActorIds'], ['b'])
        c['frozenActions'] = {'a': 'frozen'}
        self.assertEqual(propose_segments(s, c, lambda _: 'x').status, 'incomplete')

    def test_initial_missing_stage_cannot_seal(self):
        draft = InitialDraft('draft', '小型值班室', {'calendar': 'gregorian', 'dateTime': '2026-01-01T00:00:00Z', 'instantOrdinal': 0})
        self.assertEqual(draft.generate(session(None)).status, 'incomplete')
        self.assertEqual(draft.seal(lambda _: True).status, 'incomplete')

    def test_initial_full_stages_revision_and_seal(self):
        def provider(component, payload):
            if component == 'D01.1':
                return result({'entities': [{'kind': 'locations', 'name': '库房'}, {'kind': 'characters', 'name': '值守员'}], 'protagonistIndex': 1})
            w = payload['draft']
            l, p = next(iter(w['locations'])), next(iter(w['characters']))
            if component == 'D01.2': return result({l: None, p: {'containerId': l}})
            if component == 'D01.3': return result('衣袖干燥。' if payload['entityId'] == p else '窗边有灯。')
            if component == 'D01.4':
                return result({'kind': 'end'} if w['characters'][p]['tasks'] else {'kind': 'task', 'goal': '保管钥匙', 'parentTaskId': None})
            if component == 'D01.5': return result('倾向先核对再交接。')
            if component == 'D01.6': return result(63)
            self.fail(component)
        draft = InitialDraft('draft', '库房', {})
        first = draft.generate(session(provider)).value
        draft.revise('新的库房')
        second = draft.generate(session(provider)).value
        self.assertNotEqual(first['protagonistId'], second['protagonistId'])
        self.assertEqual(draft.seal(lambda _: False).status, 'incomplete')
        self.assertEqual(draft.seal(lambda _: True).status, 'result')
        with self.assertRaises(ContractError): draft.revise('不能改')


class SegmentSuffixTests(unittest.TestCase):
    """Authority callbacks here are declared fixtures, never service evidence."""
    def context(self, skipped=False):
        world = {'worldId': 'w', 'characters': {'a': {}, 'b': {}, 'c': {}}}
        frozen = {'a': {'pointId': 'p1', 'actionText': '尝试敲门。', 'contentHash': digest('frozen-a')}}
        visited = ['a', 'b'] if skipped else ['a']
        head = {'pointId': 'p1', 'kind': 'instant', 'version': 1, 'stateDigest': digest(world)}
        prefix = {'roundId': 'r', 'orderHash': digest(['a', 'b', 'c']),
                  'cursor': len(visited), 'actedIds': ['a'], 'visitedIds': visited,
                  'frozenActions': frozen, 'head': head, 'currentWorldHash': digest(world), 'allowedNextKinds': ['linked', 'instant'],
                  'points': [{'pointId': 'p1', 'previousPointId': 'root', 'kind': 'instant',
                              'version': 1, 'stateDigest': digest(world), 'timeAdvance': copy.deepcopy(INSTANT),
                              'actorIds': ['a'], 'visitedIds': visited}]}
        return {'planningScope': 'remaining_suffix', 'world': world, 'roundId': 'r',
                'order': ['a', 'b', 'c'], 'cursor': len(visited), 'actedIds': ['a'], 'visitedIds': visited,
                'frozenActions': frozen, 'head': head, 'currentWorldHash': digest(world), 'allowedNextKinds': ['linked', 'instant'], 'lockedPrefix': prefix}

    def test_verified_recovered_prefix_allows_linked_suffix_without_rewriting(self):
        context = self.context(); before = copy.deepcopy(context)
        seen = []
        def provider(component, payload):
            seen.append(copy.deepcopy(payload))
            return result([{'kind': 'linked', 'timeAdvance': INSTANT, 'actorIds': ['b', 'c']}])
        out = propose_segments(session(provider), context, lambda _: 'p2', verify_prefix=lambda proof: proof == before)
        self.assertEqual(out.status, 'result', out.reason)
        self.assertEqual(out.value['pointPlan'], [{'pointId': 'p2', 'kind': 'linked', 'timeAdvance': INSTANT, 'actorIds': ['b', 'c']}])
        self.assertEqual(out.value['visitedIds'], ['a'])
        self.assertEqual(out.value['lockedPrefixHash'], digest(before['lockedPrefix']))
        self.assertEqual(context, before)
        self.assertEqual(seen[0]['frozenActions'], before['frozenActions'])

    def test_prior_pulled_reaction_does_not_reorder_remaining_natural_slot(self):
        context = self.context()
        context['actedIds'] = context['visitedIds'] = ['a', 'c']; context['cursor'] = 1
        context['frozenActions']['c'] = {'pointId': 'p1', 'actionText': '尝试挡住门。', 'contentHash': digest('frozen-c')}
        context['head']['kind'] = 'normal'
        prefix = context['lockedPrefix']
        prefix.update(actedIds=['a', 'c'], visitedIds=['a', 'c'], cursor=1, allowedNextKinds=['normal'])
        prefix['points'][0].update(kind='normal', timeAdvance=copy.deepcopy(TIME), actorIds=['a', 'c'], visitedIds=['a', 'c'])
        proposed = result([{'kind': 'normal', 'timeAdvance': TIME, 'actorIds': ['b']}])
        out = propose_segments(session(lambda *_: proposed), context, lambda _: 'p2', verify_prefix=lambda _: True)
        self.assertEqual(out.status, 'result', out.reason)
        self.assertEqual(out.value['pointPlan'][0]['actorIds'], ['b'])
        self.assertEqual(out.value['visitedIds'], ['a', 'c'])

    def test_suffix_requires_verified_prefix_before_model(self):
        context = self.context()
        unused = session(lambda *_: self.fail('unverified prefix reached model'))
        for verifier in (None, lambda _: False):
            self.assertEqual(propose_segments(unused, context, lambda _: 'p2', verify_prefix=verifier).status, 'incomplete')
        for key in ('cursor', 'currentWorldHash', 'head', 'lockedPrefix'):
            bad = copy.deepcopy(context); del bad[key]
            self.assertEqual(propose_segments(unused, bad, lambda _: 'p2', verify_prefix=lambda _: True).status, 'incomplete')

    def test_changed_cursor_version_actions_and_world_reject_before_model(self):
        original = self.context()
        mutations = [lambda c: c.update(cursor=0),
                     lambda c: c['head'].update(version=2),
                     lambda c: c['frozenActions']['a'].update(actionText='已改写的行动'),
                     lambda c: c['world'].update(worldId='other'),
                     lambda c: c['lockedPrefix']['points'][0].update(timeAdvance=TIME)]
        unused = session(lambda *_: self.fail('stale prefix reached model'))
        for mutate in mutations:
            bad = copy.deepcopy(original)
            # Break object sharing: caller fields and proof are independent.
            bad['head'] = copy.deepcopy(bad['head']); bad['frozenActions'] = copy.deepcopy(bad['frozenActions'])
            mutate(bad)
            self.assertEqual(propose_segments(unused, bad, lambda _: 'p2', verify_prefix=lambda _: True).status, 'incomplete')

    def test_already_skipped_slot_cannot_return_and_is_not_unassigned(self):
        context = self.context(skipped=True)
        bad = session(lambda *_: result([{'kind': 'linked', 'timeAdvance': INSTANT, 'actorIds': ['b', 'c']}]))
        self.assertEqual(propose_segments(bad, context, lambda _: 'p2', verify_prefix=lambda _: True).status, 'incomplete')
        good = session(lambda *_: result([{'kind': 'linked', 'timeAdvance': INSTANT, 'actorIds': []}]))
        out = propose_segments(good, context, lambda _: 'p2', verify_prefix=lambda _: True)
        self.assertEqual(out.status, 'result', out.reason)
        self.assertEqual(out.value['unassignedActorIds'], ['c'])
        self.assertEqual(out.value['visitedIds'], ['a', 'b'])

    def test_suffix_cannot_reorder_reuse_prefix_id_or_reassign_frozen_actor(self):
        context = self.context()
        for actor_ids in (['c', 'b'], ['a'], ['b', 'b']):
            output = result([{'kind': 'linked', 'timeAdvance': INSTANT, 'actorIds': actor_ids}])
            self.assertEqual(propose_segments(session(lambda *_: output), context, lambda _: 'p2', verify_prefix=lambda _: True).status, 'incomplete')
        output = result([{'kind': 'linked', 'timeAdvance': INSTANT, 'actorIds': ['b']}])
        self.assertEqual(propose_segments(session(lambda *_: output), context, lambda _: 'p1', verify_prefix=lambda _: True).status, 'incomplete')

    def test_suffix_linked_needs_instant_predecessor_and_cannot_start_new_round(self):
        context = self.context()
        for kind in ('normal', 'linked'):
            bad = copy.deepcopy(context)
            bad['head']['kind'] = kind; bad['lockedPrefix']['points'][0]['kind'] = kind
            if kind == 'normal': bad['lockedPrefix']['points'][0]['timeAdvance'] = copy.deepcopy(TIME)
            output = result([{'kind': 'linked', 'timeAdvance': INSTANT, 'actorIds': ['b']}])
            self.assertEqual(propose_segments(session(lambda *_: output), bad, lambda _: 'p2', verify_prefix=lambda _: True).status, 'incomplete')
        new_round = result([{'kind': 'normal', 'timeAdvance': TIME, 'actorIds': ['b']}])
        self.assertEqual(propose_segments(session(lambda *_: new_round), context, lambda _: 'p2', verify_prefix=lambda _: True).status, 'incomplete')


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.binding = {'worldId': 'w', 'pointId': 'p', 'version': 0, 'requestId': 'request', 'epoch': 1, 'checkpointRevision': 0}
        state = {'worldId': 'w', 'initial': {'id': 'initial'}, 'characters': {}}
        self.before = {'pointId': 'root', 'version': 0, 'state': state, 'stateDigest': digest(state),
                       'previousPointId': None, 'timeAdvance': None, 'entityDeltas': {}}
        self.after = dict(copy.deepcopy(self.before), pointId='p', version=1, previousPointId='root', timeAdvance=TIME)

    def receipt(self, operation, **kw):
        binding = getattr(self, 'active_point', None)
        b = self.binding if binding is None else binding.binding
        return dict(b, operation=operation, accepted=True, nextCheckpointRevision=b['checkpointRevision'] + 1, **kw)

    def point(self):
        self.active_point = PointHandoff(self.binding, required_slots=['a', 'b'], required_units=['u'], time_scan_required=True)
        return self.active_point

    def test_binding_and_receipts_reject_boolean_or_unsafe_versions(self):
        for key in ('version', 'epoch', 'checkpointRevision'):
            for value in (True, 9007199254740992):
                with self.assertRaises(ContractError):
                    PointHandoff(dict(self.binding, **{key: value}), required_slots=[], required_units=[], time_scan_required=False)
        p = self.point()
        receipt = self.receipt('slot_completed', slotId='a')
        receipt['version'] = False  # Python equality to zero must not bypass a version fence.
        with self.assertRaises(ContractError):
            p.slot_completed('a', receipt)
        receipt = self.receipt('slot_completed', slotId='a')
        receipt['nextCheckpointRevision'] = 9007199254740992
        with self.assertRaises(ContractError):
            p.slot_completed('a', receipt)
        self.assertEqual(p.slots, [])

    def staged(self):
        p = self.point()
        p.freeze('action', 'a', {'text': '尝试推门'})
        p.freeze('roll', 'roll', {'result': 8})
        for slot in ['a', 'b']: p.slot_completed(slot, self.receipt('slot_completed', slotId=slot))
        p.unit_staged('u', ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity'], {},
                      self.receipt('checkpoint_stage_unit', unitId='u', candidateHash=digest({})))
        p.time_scan_staged({}, self.receipt('checkpoint_stage_time_scan', candidateHash=digest({})))
        return p

    def committed(self):
        p = self.staged()
        p.seal(self.receipt('checkpoint_seal_point'))
        p.commit(self.before, self.after, self.receipt('commit_point'), lambda *_: True)
        return p

    def ready_receipt(self, claim):
        return {**copy.deepcopy(claim), 'operation': 'narration_submit', 'accepted': True,
                'serviceClaim': {'fixture': 'engineering authority receipt; no C model'}}

    def test_model_completion_cannot_release_ready_without_authority_receipt(self):
        p = self.committed()
        self.assertEqual(p.binding['version'], self.after['version'])
        claim = p.claim_narration()
        p.narration_settled(claim, 'model_completed')
        self.assertFalse(p.ready)
        for field in ('generation', 'version', 'epoch'):
            changed = copy.deepcopy(claim)
            (changed if field == 'generation' else changed['binding'])[field] = True
            with self.assertRaises(ContractError):
                p.narration_settled(changed, 'ready', receipt=self.ready_receipt(changed), verify_receipt=lambda *_: True)
        with self.assertRaises(ContractError):
            p.narration_settled(claim, 'ready')
        with self.assertRaises(ContractError):
            p.narration_settled(claim, 'ready', receipt=self.ready_receipt(claim), verify_receipt=lambda *_: False)
        stale = self.ready_receipt(claim)
        stale['generation'] = True  # bool must not equal the numeric attempt generation.
        with self.assertRaises(ContractError):
            p.narration_settled(claim, 'ready', receipt=stale, verify_receipt=lambda *_: True)
        p.narration_settled(claim, 'ready', receipt=self.ready_receipt(claim), verify_receipt=lambda *_: True)
        self.assertTrue(p.ready)

    def test_authority_rebound_recovery_keeps_facts_and_fences_old_ready(self):
        p = self.committed()
        old_claim = p.claim_narration()
        p.narration_settled(old_claim, 'ready', receipt=self.ready_receipt(old_claim), verify_receipt=lambda *_: True)
        snapshot = p.snapshot()
        fresh = dict(p.binding, epoch=p.binding['epoch'] + 1, requestId='new-request',
                     checkpointRevision=p.binding['checkpointRevision'] + 1)
        rebind = {'operation': 'recover_point', 'accepted': True, 'previousBinding': p.binding,
                  'binding': fresh, 'snapshotHash': snapshot['sha256']}
        with self.assertRaises(ContractError):
            PointHandoff.restore(snapshot, expected_binding=fresh, verify_recovery=lambda _: True)
        with self.assertRaises(ContractError):
            PointHandoff.restore(snapshot, expected_binding=dict(fresh, pointId='different'),
                                 verify_recovery=lambda _: True, rebind_receipt=rebind, verify_rebind=lambda *_: True)
        recovered = PointHandoff.restore(snapshot, expected_binding=fresh, verify_recovery=lambda _: True,
                                         rebind_receipt=rebind, verify_rebind=lambda *_: True)
        self.assertFalse(recovered.ready)
        self.assertEqual(recovered.packet.hash, p.packet.hash)
        self.assertEqual(recovered.frozen_rolls['roll'].read(), p.frozen_rolls['roll'].read())
        with self.assertRaises(ContractError):
            recovered.narration_settled(old_claim, 'ready', receipt=self.ready_receipt(old_claim), verify_receipt=lambda *_: True)

    def test_unit_not_point_and_scan_required(self):
        p = self.point()
        p.unit_staged('u', ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity'], {},
                      self.receipt('checkpoint_stage_unit', unitId='u', candidateHash=digest({})))
        self.assertFalse(p.committed)
        with self.assertRaises(ContractError): p.seal(self.receipt('checkpoint_seal_point'))
        for slot in ['a', 'b']: p.slot_completed(slot, self.receipt('slot_completed', slotId=slot))
        with self.assertRaises(ContractError): p.seal(self.receipt('checkpoint_seal_point'))

    def test_candidate_cannot_be_narration(self):
        with self.assertRaises(ContractError):
            committed_packet(self.before, {'candidate': self.after}, verify_committed=lambda *_: True)
        with self.assertRaises(ContractError):
            committed_packet(self.before, self.after, verify_committed=lambda *_: False)

    def test_mixed_commit_lineage_rejected(self):
        after = dict(self.after, previousPointId='different')
        with self.assertRaises(ContractError): committed_packet(self.before, after, verify_committed=lambda *_: True)

    def test_narration_uses_raw_delta_no_candidates(self):
        p = self.committed()
        packet = p.claim_narration()['facts']
        self.assertEqual(packet['delta'], {'timeAdvance': TIME, 'entityDeltas': {}})
        self.assertNotIn('candidates', packet)

    def test_narration_failure_retries_same_facts_without_rollback(self):
        p = self.committed()
        claim = p.claim_narration()
        p.narration_settled(claim, 'timeout')
        retry = p.claim_narration()
        self.assertEqual(claim['packetHash'], retry['packetHash'])
        self.assertTrue(p.committed)
        self.assertEqual(p.frozen_rolls['roll'].read(), {'result': 8})
        with self.assertRaises(ContractError): p.narration_settled(claim, 'ready')
        self.assertFalse(p.ready)
        p.narration_settled(retry, 'ready', receipt=self.ready_receipt(retry), verify_receipt=lambda *_: True)
        self.assertTrue(p.ready)

    def test_recovery_rejects_old_narration_and_changed_snapshot(self):
        p = self.committed()
        old = p.claim_narration()
        snapshot = p.snapshot()
        restored = PointHandoff.restore(snapshot, expected_binding=p.binding, verify_recovery=lambda _: True)
        with self.assertRaises(ContractError): restored.narration_settled(old, 'ready')
        self.assertEqual(restored.frozen_actions['a'].read(), {'text': '尝试推门'})
        snapshot['state']['frozen_rolls']['roll']['result'] = 20
        with self.assertRaises(ContractError): PointHandoff.restore(snapshot, expected_binding=p.binding, verify_recovery=lambda _: True)

    def test_persistence_no_overwrite(self):
        p = self.staged()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'work.json'
            p.save(path)
            with self.assertRaises(FileExistsError): p.save(path)

    def test_frozen_rewrite_and_foreign_ready_reject(self):
        p = self.committed()
        claim = p.claim_narration()
        claim['binding']['requestId'] = 'other'
        with self.assertRaises(ContractError): p.narration_settled(claim, 'ready')
        self.assertFalse(p.ready)

    def test_same_receipt_cannot_cover_other_slot_or_revision(self):
        p = self.point()
        receipt = self.receipt('slot_completed', slotId='a')
        with self.assertRaises(ContractError): p.slot_completed('b', receipt)
        p.slot_completed('a', receipt)
        receipt['slotId'] = 'b'
        with self.assertRaises(ContractError): p.slot_completed('b', receipt)
        self.assertEqual(p.slots, ['a'])


class PrimitiveAssemblyTests(unittest.TestCase):
    def test_no_trained_primitive_is_incomplete_not_fixed_inventory(self):
        assembly = LifecycleHeads(lambda *_: incomplete('untrained'))
        self.assertEqual(assembly('D01.1', {'brief': '库房'}).status, 'incomplete')

    def test_inventory_names_slots_and_protagonist_are_model_outputs(self):
        kinds = iter(['locations', 'characters', 'end'])
        seen = []
        def primitive(name, payload):
            seen.append((name, payload))
            if name == 'D01.1.kind': return result(next(kinds))
            if name == 'D01.1.name': return result('南仓' if payload['entityKind'] == 'locations' else '孟禾')
            if name == 'D01.1.slot_next': return result('slot' if not payload['proposedSlots'] else 'end')
            if name == 'D01.1.slot_label': return result('靠窗层架')
            if name == 'D01.1.protagonist': return result('1')
            self.fail(name)
        out = LifecycleHeads(primitive)('D01.1', {'brief': '保管物资的仓库'})
        self.assertEqual(out.value['entities'][0]['name'], '南仓')
        self.assertEqual(out.value['entities'][0]['slots'], ['靠窗层架'])
        self.assertEqual(out.value['protagonistIndex'], 1)
        self.assertTrue(all(p['brief'] == '保管物资的仓库' for _, p in seen))

    def test_unfinished_inventory_not_completed_at_limit(self):
        def primitive(name, _):
            return result({'D01.1.kind': 'locations', 'D01.1.name': '仓', 'D01.1.slot_next': 'end'}[name])
        self.assertEqual(LifecycleHeads(primitive, max_entities=1)('D01.1', {}).reason, 'entity_budget_without_end')

    def test_time_large_number_not_clamped_and_invalid_rejected(self):
        values = {'D08.1.boundary': 'elapsed', 'D08.1.amount': '250', 'D08.1.unit': 'year'}
        assembly = LifecycleHeads(lambda n, _: result(values[n]))
        self.assertEqual(assembly('D08.1', {}).value['duration']['amount'], 250)
        values['D08.1.amount'] = '2.5'
        self.assertEqual(assembly('D08.1', {}).status, 'incomplete')

    def test_pending_initial_task_parent_selected_not_derived_from_goal(self):
        values = {'D01.4.next': 'task', 'D01.4.parent': 'root', 'D01.4.goal': '核对柜门封条'}
        payload = {'characterId': 'a', 'draft': {'characters': {'a': {'tasks': {'root': {'goal': '保管物资'}}}}}}
        out = LifecycleHeads(lambda n, _: result(values[n]))('D01.4', payload)
        self.assertEqual(out.value, {'kind': 'task', 'parentTaskId': 'root', 'goal': '核对柜门封条'})
        values['D01.4.parent'] = 'unknown'
        self.assertEqual(LifecycleHeads(lambda n, _: result(values[n]))('D01.4', payload).status, 'incomplete')


if __name__ == '__main__':
    unittest.main()
