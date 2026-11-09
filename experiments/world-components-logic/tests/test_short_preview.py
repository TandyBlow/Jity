"""Engineering evidence using pinned A source. No trained-model quality claim."""
import copy
import hashlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from short_contracts import ContractError, digest
import short_preview as preview_module
from short_preview import offline_preview, _load_kernel, A_COMMIT, authority_identity
from short_settlement import STAGES, settle_joint, run_updates
from test_short_settlement import context_fixture, FixtureSession, allocate


def complete_context():
    context = context_fixture()
    world = context['world']
    time = {'calendar': 'gregorian', 'dateTime': '2026-11-09T12:00:00', 'instantOrdinal': 0}
    world.update(engineVersion='world-engine-v1', schemaVersion=1, protagonistId='a', time=copy.deepcopy(time))
    world['initial'].update(engineVersion='world-engine-v1', schemaVersion=1, worldId=world['worldId'],
                            protagonistId='a', initialTime=time)
    for kind in ('items', 'characters'):
        for key, current in world[kind].items():
            world['initial'][kind][key]['initialPosition'] = copy.deepcopy(current['position'])
            if kind == 'characters':
                world['initial'][kind][key]['tasks'] = copy.deepcopy(current['tasks'])
            for field in ('appearanceChanges', 'personalityChanges'):
                for row in current.get(field, []):
                    row.update(sourcePointId='previous', sourceSequence=1)
    return context


def registered_point(context):
    return {'worldId': context['world']['worldId'], 'id': context['binding']['pointId'],
            'sequence': 2, 'kind': 'instant', 'previousPointId': 'previous',
            'roundId': 'round', 'advanceId': 'advance', 'trigger': 'player',
            'linkedFromPointId': 'previous',
            'timeAdvance': {'boundary': 'instant', 'duration': {'amount': 0, 'unit': 'second'}}}


def callback(context):
    return offline_preview(context['world'], context['binding'], point=registered_point(context),
                           group_id='group', actor_ids=['a', 'b'])


def request(context, calls):
    return {'binding': context['binding'], 'baseWorldHash': digest(context['world']),
            'candidateHash': digest(calls), 'stage': calls[-1]['stage'], 'completedStages': calls}


def empty_calls(count=6):
    return [{'stage': stage, 'changes': {}} for stage in STAGES[:count]]


class PinnedPreviewTests(unittest.TestCase):
    def test_official_partial_u5_preview_and_complete_u6_validation(self):
        context = complete_context()
        session = FixtureSession(effects=True)
        settlement = settle_joint(session, context)
        preview = callback(context)
        updates = run_updates(session, context, settlement.value, preview, allocate)
        self.assertEqual(updates.status, 'result', updates.reason)
        self.assertEqual(len(preview.events), 6)
        self.assertFalse(preview.events[4]['completeUnitValidated'])
        self.assertTrue(preview.events[5]['completeUnitValidated'])
        fifth = preview(request(context, preview.events[5]['request']['completedStages'][:5]))
        self.assertEqual(fifth.status, 'result', fifth.reason)
        self.assertEqual(fifth.value['world']['characters']['off']['sanity'], 60)
        self.assertGreater(len(fifth.value['world']['characters']['off']['personalityChanges']), 1)
        sixth = preview(request(context, preview.events[5]['request']['completedStages']))
        self.assertEqual(sixth.value['world']['characters']['off']['sanity'], 48)
        self.assertEqual(sixth.value['world']['time']['instantOrdinal'], 1)
        self.assertEqual(fifth.value['world']['time'], sixth.value['world']['time'])
        self.assertEqual(sixth.value['world']['initial'], context['world']['initial'])
        self.assertEqual(sixth.value['authority']['sourceCommit'], A_COMMIT)
        self.assertFalse(sixth.value['committed'])
        self.assertEqual(len(sixth.value['world']['characters']['b']['tasks']), 3)
        changes = sixth.value['world']['items']['tool']['appearanceChanges']
        self.assertFalse(changes[0]['active'])
        self.assertIsNone(changes[1]['text'])
        self.assertEqual(changes[1]['sourcePointId'], context['binding']['pointId'])

    def test_partial_is_not_complete_unit_adoption(self):
        context = complete_context(); calls = empty_calls()
        calls[2]['changes'] = {'a': {'entityId': 'a', 'tasksAchieved': ['at']}}
        calls[4]['changes'] = {'off': {'entityId': 'off', 'personalityChanges': [
            {'id': 'new-preference', 'text': '更愿协作。', 'supersedes': []}]}}
        preview = callback(context)
        self.assertEqual(preview(request(context, calls[:5])).status, 'result')
        out = preview(request(context, calls))
        self.assertEqual(out.status, 'incomplete')
        self.assertIn('must pair', out.reason)

    def test_official_merge_rejects_conflicting_shared_unit_positions(self):
        kernel = _load_kernel(); context = complete_context()
        state = kernel.contracts.WorldState.model_validate(context['world'])
        point = kernel.contracts.TimelinePoint.model_validate({**registered_point(context), 'entityDeltas': {}})
        unit = dict(groupId='group1', actorIds=['a'], positions={'tool': {'containerId': 'a'}},
                    appearances={}, tasksAchieved={}, subtasksAdded={}, personalities={}, sanities={},
                    taskCoverageIds=['a', 'b', 'off'], personalityCoverageIds=[])
        first = kernel.SettlementGroup.model_validate(unit)
        second = kernel.SettlementGroup.model_validate({**unit, 'groupId': 'group2', 'actorIds': ['b'],
                                                       'positions': {'tool': {'containerId': 'b'}}})
        with self.assertRaisesRegex(Exception, 'conflicting positions'):
            kernel.preview_point(state, point, [first, second])
        duplicate_actor = kernel.SettlementGroup.model_validate({**unit, 'groupId': 'group2'})
        self.assertTrue(kernel.validate_commit_groups([first, duplicate_actor], frozenset(state.characters)))

    def test_missing_identity_and_stale_or_rewritten_candidate_are_incomplete(self):
        context = complete_context(); calls = empty_calls(1)
        missing = offline_preview(context['world'], context['binding'])
        self.assertEqual(missing(request(context, calls)).status, 'incomplete')
        preview = callback(context)
        wrong = request(context, calls); wrong['binding'] = {**context['binding'], 'version': 999}
        self.assertEqual(preview(wrong).status, 'incomplete')
        self.assertEqual(preview(request(context, calls)).status, 'result')
        calls[0]['changes'] = {'tool': {'entityId': 'tool', 'positionSet': {'containerId': 'a'}}}
        self.assertIn('frozen_stage', preview(request(context, calls)).reason)

    def test_official_positions_and_unique_new_ids_are_enforced(self):
        context = complete_context()
        calls = empty_calls(1)
        calls[0]['changes'] = {'tool': {'entityId': 'tool', 'positionSet': {'containerId': 'box'}},
                               'box': {'entityId': 'box', 'positionSet': {'containerId': 'tool'}}}
        self.assertEqual(callback(context)(request(context, calls)).status, 'incomplete')
        calls = empty_calls(2)
        calls[1]['changes'] = {'tool': {'entityId': 'tool', 'appearanceChanges': [
            {'id': 'scar', 'text': '被非法覆盖。', 'supersedes': []}]}}
        self.assertIn('identity_collision', callback(context)(request(context, calls)).reason)

    def test_pure_time_is_projected_once_and_does_not_invent_movement(self):
        context = complete_context()
        preview = offline_preview(context['world'], context['binding'], point=registered_point(context),
                                  group_id=None, actor_ids=[])
        for count in range(1, 7):
            out = preview(request(context, empty_calls(count)))
            self.assertEqual(out.status, 'result', out.reason)
            self.assertEqual(out.value['world']['time']['instantOrdinal'], 1)
        forbidden = empty_calls(1)
        forbidden[0]['changes'] = {'tool': {'entityId': 'tool', 'positionSet': {'containerId': 'a'}}}
        new_preview = offline_preview(context['world'], context['binding'], point=registered_point(context),
                                      group_id=None, actor_ids=[])
        self.assertIn('time-scan', new_preview(request(context, forbidden)).reason)

    def test_source_identity_has_no_service_or_database_access(self):
        identity = authority_identity()
        self.assertEqual(len(identity['sourceFiles']), 13)
        self.assertFalse(identity['serviceOrDatabaseAccess'])
        self.assertFalse(identity['productionIntegration'])
        self.assertIn('preview_point', identity['mode'])


class AuthoritySourceTests(unittest.TestCase):
    """Source transport fixtures are engineering evidence, never A semantics."""
    @contextmanager
    def bundle(self):
        contents = {path: ('fixture source for ' + path).encode() for path in preview_module.A_FILES}
        hashes = {path: hashlib.sha256(raw).hexdigest() for path, raw in contents.items()}
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory) / 'retained'; cache = Path(directory) / 'cache'
            for path, raw in contents.items():
                destination = root / path; destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            for name, value in (('A_FILES', hashes), ('AUTHORITY_SNAPSHOT', root), ('AUTHORITY_CACHE', cache),
                                ('_SNAPSHOT_CACHE', None), ('_SOURCE_READS', {})):
                stack.enter_context(patch.object(preview_module, name, value))
            stack.enter_context(patch.object(preview_module, '_read_file_bounded', side_effect=lambda p: Path(p).read_bytes()))
            yield root, cache, contents

    def test_default_verifies_all_thirteen_and_never_reads_git(self):
        with self.bundle() as (_, cache, contents), \
             patch.object(preview_module.subprocess, 'check_output', side_effect=AssertionError('no Git/network')):
            name = next(iter(contents))
            self.assertEqual(preview_module.read_authority_source(name), contents[name])
            self.assertEqual(len(preview_module._SNAPSHOT_CACHE[1]), 13)
            self.assertTrue(all((cache / path).read_bytes() == raw for path, raw in contents.items()))
            receipt = preview_module.authority_source_reads()[name]
            self.assertEqual(receipt['sourceCommit'], A_COMMIT)
            self.assertEqual(receipt['retrieval']['acquisition']['source'], 'retained_verified_snapshot')

    def test_unknown_path_or_expected_hash_never_touches_sources(self):
        with patch.object(preview_module, '_verified_snapshot', side_effect=AssertionError('no source access')):
            for path in ('../contracts.py', '/backend/app/schemas/world/contracts.py', 'backend/app/new.py'):
                with self.assertRaisesRegex(ContractError, 'unregistered'): preview_module.read_authority_source(path)
            with self.assertRaisesRegex(ContractError, 'expected_hash'):
                preview_module.read_authority_source(next(iter(preview_module.A_FILES)), expected_sha256='wrong')

    def test_git_is_bounded_and_identity_is_recorded(self):
        with self.bundle() as (_, _, contents):
            name = next(iter(contents))
            with patch.object(preview_module.subprocess, 'check_output', return_value=contents[name]) as process:
                self.assertEqual(preview_module._git_source(name), contents[name])
            args, kwargs = process.call_args
            self.assertEqual(args[0], ['git', 'show', A_COMMIT + ':' + name])
            self.assertEqual(kwargs['timeout'], 5)
            self.assertEqual(preview_module.authority_source_reads()[name]['source'], 'git')

    def test_git_timeout_falls_back_only_to_complete_verified_bytes(self):
        with self.bundle() as (_, _, contents):
            name = next(iter(contents))
            with patch.object(preview_module.subprocess, 'check_output', side_effect=subprocess.TimeoutExpired('git', 5)):
                self.assertEqual(preview_module._git_source(name), contents[name])
            receipt = preview_module.authority_source_reads()[name]
            self.assertEqual(receipt['gitFailure']['type'], 'TimeoutExpired')
            self.assertEqual(receipt['retrieval']['acquisition']['source'], 'retained_verified_snapshot')

    def test_corrupt_snapshot_refuses_without_remote_or_partial_bundle(self):
        with self.bundle() as (root, _, contents):
            names = list(contents); (root / names[-1]).write_bytes(b'changed authority code')
            with patch.object(preview_module, '_fetch_pinned_source', side_effect=AssertionError('must not bypass mismatch')):
                with self.assertRaisesRegex(ContractError, 'hash_mismatch'):
                    preview_module.read_authority_source(names[0])
            self.assertIsNone(preview_module._SNAPSHOT_CACHE)

    def test_missing_snapshot_and_remote_failure_cannot_synthesize_authority(self):
        with self.bundle() as (root, _, contents):
            name = next(iter(contents)); (root / name).unlink()
            with patch.object(preview_module, '_fetch_pinned_source', side_effect=OSError('unavailable')):
                with self.assertRaisesRegex(ContractError, 'source_unavailable'):
                    preview_module.read_authority_source(name)
            self.assertIsNone(preview_module._SNAPSHOT_CACHE)

    def test_snapshot_timeout_uses_only_fixed_hash_remote_then_local_cache(self):
        with self.bundle() as (_, _, contents):
            original = preview_module._read_file_bounded
            def read(p):
                if preview_module.AUTHORITY_SNAPSHOT in Path(p).parents: raise subprocess.TimeoutExpired('read', 5)
                return Path(p).read_bytes()
            with patch.object(preview_module, '_read_file_bounded', side_effect=read), \
                 patch.object(preview_module, '_fetch_pinned_source', side_effect=lambda p: contents[p]) as remote:
                name = next(iter(contents))
                self.assertEqual(preview_module.read_authority_source(name), contents[name])
            self.assertEqual(remote.call_count, 13)
            receipt = preview_module.authority_source_reads()[name]
            self.assertEqual(receipt['retrieval']['acquisition']['source'], 'pinned_remote_sha256')
            self.assertEqual(receipt['retrieval']['acquisition']['url'], preview_module.AUTHORITY_REMOTE + name)

    def test_wrong_remote_hash_is_rejected(self):
        with self.bundle() as (root, _, contents):
            name = next(iter(contents)); (root / name).unlink()
            with patch.object(preview_module, '_fetch_pinned_source', return_value=b'wrong source'):
                with self.assertRaisesRegex(ContractError, 'hash_mismatch'):
                    preview_module.read_authority_source(name)

    def test_cache_reload_identity_is_stable_and_changed_cached_bytes_fail(self):
        with self.bundle() as (_, cache, contents):
            first = preview_module.authority_identity()
            preview_module._SNAPSHOT_CACHE = None
            self.assertEqual(first, preview_module.authority_identity())
            name = next(iter(contents)); (cache / name).write_bytes(b'changed cache')
            preview_module._SNAPSHOT_CACHE = None
            with self.assertRaisesRegex(ContractError, 'hash_mismatch'):
                preview_module.read_authority_source(name)

    def test_same_bytes_via_git_change_read_receipt_but_not_execution_identity(self):
        with self.bundle() as (_, _, contents):
            identity = preview_module.authority_identity(); name = next(iter(contents))
            with patch.object(preview_module.subprocess, 'check_output', return_value=contents[name]):
                preview_module._git_source(name)
            self.assertEqual(preview_module.authority_source_reads()[name]['source'], 'git')
            self.assertEqual(preview_module.authority_identity(), identity)
            self.assertNotIn('files', identity['sourceRetrieval'])

    def test_file_and_exact_remote_reads_have_bounded_time_and_size(self):
        path = next(iter(preview_module.A_FILES))
        with patch.object(preview_module.subprocess, 'check_output', return_value=b'fixture') as process:
            preview_module._read_file_bounded(Path('/tmp/fixture'))
            self.assertEqual(process.call_args.kwargs['timeout'], 5)
            self.assertIn('1048577', process.call_args.args[0][4])
            preview_module._fetch_pinned_source(path)
            args, kwargs = process.call_args
            self.assertEqual(args[0][-1], preview_module.AUTHORITY_REMOTE + path)
            self.assertEqual(kwargs['timeout'], 6)
            self.assertIn('--max-filesize', args[0])


if __name__ == '__main__':
    unittest.main()
