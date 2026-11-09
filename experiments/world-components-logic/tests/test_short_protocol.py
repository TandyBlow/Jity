"""Run NEW candidate adapters through the actual unchanged B TypeScript consumers."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(BASE / 'tests'))
from short_contracts import result, empty
from short_intent import produce_intent, action_wire, targets_wire
from short_lifecycle import continuation, continuation_wire, propose_time, propose_segments
from short_settlement import settle_joint, run_updates
from test_short_intent import Script, sequence, canonical_context
from test_short_settlement import FixtureSession, FixturePreview, context_fixture
import test_short_lifecycle as lifecycle_tests


def protocol_packet():
    """All prose/decisions below are declared test doubles, no model results."""
    action = produce_intent(Script(sequence(['安禾尝试拿软刷。', '安禾尝试轻刷图纸。'])), canonical_context(), 'op')
    assert action.status == 'result', action.reason
    context = context_fixture()
    settled = settle_joint(FixtureSession(effects=True), context)
    assert settled.status == 'result', settled.reason
    updates = run_updates(FixtureSession(effects=True), context, settled.value, FixturePreview(context['world']),
                          lambda kind, key: kind + ':' + key.replace(':', '-'))
    assert updates.status == 'result', updates.reason
    complete_round = lifecycle_tests.LifecycleTests().context()
    candidate = continuation(Script([('D07.1', result({'kind': 'candidate', 'characterId': 'a', 'text': '尝试检查图纸。'})),
                                    ('D07.1', result({'kind': 'end'})), ('D07.2', result('likely')), ('D07.3', result('related'))]),
                             complete_round, lambda: 'round-next', verify_round=lambda _: True)
    assert candidate.status == 'result', candidate.reason
    no_candidate = continuation(Script([('D07.1', result({'kind': 'end'}))]), complete_round, lambda: 'unused', verify_round=lambda _: True)
    time_value = {'boundary': 'elapsed', 'duration': {'amount': 1, 'unit': 'minute'}}
    time = propose_time(Script([('D08.1', result(time_value))]),
                        {'world': canonical_context()['world'], 'pointId': 'point', 'timeLocked': False, 'timeAdvance': None})
    segments = propose_segments(Script([('D08.2', result([{'kind': 'normal', 'timeAdvance': time_value, 'actorIds': ['a']}]))]),
                                {'world': canonical_context()['world'], 'roundId': 'round', 'order': ['a', 'b', 'c'],
                                 'actedIds': [], 'visitedIds': [], 'frozenActions': {}}, lambda index: 'point-' + str(index))
    assert segments.status == 'result', segments.reason
    rows = [
        {'id': 'D02-multifragment-action', 'task': 'action', 'value': action_wire(action)},
        {'id': 'D02-explicit-skip', 'task': 'action', 'value': action_wire(empty())},
        {'id': 'D03-target-set', 'task': 'targets', 'value': targets_wire(result(['b', 'c']))},
        {'id': 'D03-completed-empty-set', 'task': 'targets', 'value': targets_wire(empty())},
        {'id': 'D04-reaction-text', 'task': 'reaction', 'value': action.value.text},
        {'id': 'D05-member-results', 'task': 'results', 'value': settled.value['results']},
        {'id': 'D06-six-stage-batch', 'task': 'updates', 'value': updates.value['updates'], 'constraints': {'updatesSplitMode': False}},
        {'id': 'D07-continue', 'task': 'continuation', 'value': continuation_wire(candidate)},
        {'id': 'D07-completed-handback', 'task': 'continuation', 'value': continuation_wire(no_candidate)},
        {'id': 'D08-time', 'task': 'time', 'value': time.value},
        {'id': 'D08-point-plan', 'task': 'pointPlan', 'value': segments.value['pointPlan']},
        {'id': 'reject-incomplete-envelope-as-action', 'task': 'action', 'value': {'status': 'incomplete', 'reason': 'timeout'}, 'expectReject': True},
        {'id': 'reject-target-dice-from-model', 'task': 'targets', 'value': {'targets': [{'targetId': 'b', 'result': 20}]}, 'expectReject': True},
        {'id': 'reject-update-wrong-mode', 'task': 'updates', 'value': updates.value['updates'], 'constraints': {'updatesSplitMode': True}, 'expectReject': True},
    ]
    rows += [{'id': 'D06-split-' + call['stage'], 'task': 'updates', 'value': call,
              'constraints': {'updatesSplitMode': True, 'updatesStage': call['stage']}} for call in updates.value['updates']]
    world = context['world']
    task_ids = [key for person in world['characters'].values() for key in person['tasks']]
    change_ids = [r['id'] for kind in ('locations', 'items', 'characters') for entity in world[kind].values()
                  for field in ('appearanceChanges', 'personalityChanges') for r in entity.get(field, [])]
    return {'scope': 'synthetic_engineering_only', 'cases': rows, 'updatesComparison': {
        'calls': updates.value['updates'], 'groupId': context['group']['groupId'],
        'actorIds': context['group']['memberIds'], 'roster': list(world['characters']),
        'expected': updates.value['candidates'], 'taskIds': task_ids, 'changeIds': change_ids}}


class ActualConsumerTests(unittest.TestCase):
    def test_new_adapters_match_actual_decoder_and_scheduler(self):
        root = BASE.parents[1]
        candidates = [root / 'frontend/node_modules/typescript',
                      Path('/Users/davidz/Documents/GitHub/Jity/frontend/node_modules/typescript')]
        typescript = next((p for p in candidates if (p / 'lib/typescript.js').is_file()), None)
        if not shutil.which('node') or typescript is None:
            self.skipTest('Node/TypeScript local runtime unavailable; actual consumer remains unverified')
        done = subprocess.run(['node', str(BASE / 'tests/short_protocol_probe.cjs'), '--typescript', str(typescript)],
                              input=json.dumps(protocol_packet(), ensure_ascii=False), capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        report = json.loads(done.stdout)
        self.assertTrue(report['passed'])
        self.assertEqual(len(report['checks']), 22)
        self.assertFalse(report['semanticEvidence'])
        self.assertEqual(len(report['sourceIdentity']), 3)


if __name__ == '__main__':
    unittest.main()
