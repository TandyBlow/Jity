"""Bounded evidence recovery; no neural models or synthetic capability scores."""
import copy
import gzip
import json
from pathlib import Path
import sys
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import experiment as common


class BoundedJournalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'events.jsonl'
        self.sha = '1' * 64
        self.slot = {'arm': 'model', 'caseId': 'case', 'repeat': 0, 'status': 'not_started'}

    def report(self):
        return {'runId': 'fixture', 'planSha256': self.sha, 'status': 'diagnostic_completed',
                'attempts': [], 'attemptSlots': [copy.deepcopy(self.slot)], 'activeAttempt': None}

    def event(self, name='output', payload=None):
        return {**{k: self.slot[k] for k in ('arm', 'caseId', 'repeat')}, 'name': name,
                'payload': payload if payload is not None else {'inputIds': [1, 2], 'rawText': '原始首次输出'}}

    def start(self, journal, referenced=True):
        header = {'runId': 'fixture', 'slots': [self.slot]}
        if referenced: header['checkpointStorage'] = common.CHECKPOINT_STORAGE
        journal.append('begin', header)
        attempt = {**self.slot, 'status': 'started', 'checkpoints': [], 'startedMonotonicNs': 1}
        journal.append('attempt_start', attempt)
        return attempt

    def finish(self, journal, attempt):
        journal.append('attempt_result', {**attempt, 'status': 'complete'})
        journal.append('attempt_settled', {**{k: self.slot[k] for k in ('arm', 'caseId', 'repeat')},
                       'resultJournalMs': 0., 'snapshotEndMs': 0., 'elapsedThroughResultMs': 1.})

    def test_large_raw_events_stay_on_disk_and_recovery_is_bounded(self):
        payload = {'inputIds': list(range(4096)), 'rawText': 'x' * (256 * 1024)}
        with common.AppendJournal(self.path, self.sha) as journal:
            attempt = self.start(journal)
            for _ in range(64):
                attempt['checkpoints'].append(common.append_checkpoint(journal, self.event(payload=payload)))
            self.finish(journal, attempt)
        self.assertGreater(self.path.stat().st_size, 16 * 1024 * 1024)
        before = common.sha256_file(self.path)
        report = self.report()
        tracemalloc.start()
        try:
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('must stream journal')):
                common.reconcile_journal(report, self.path, 'completed')
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 8 * 1024 * 1024)
        self.assertLess(len(json.dumps(report)), 100 * 1024)
        self.assertNotIn('inputIds', json.dumps(report))
        self.assertEqual(common.sha256_file(self.path), before)
        observed = 0
        for event in common.iter_checkpoint_events(report, self.path):
            self.assertEqual(event['payload'], payload)
            observed += 1
        self.assertEqual(observed, 64)

    def test_correct_outer_hash_cannot_hide_wrong_result_reference(self):
        for mutation in ('sha256', 'sequence', 'name', 'omit'):
            with self.subTest(mutation=mutation):
                path = self.path.with_name(mutation + '.jsonl')
                with common.AppendJournal(path, self.sha) as journal:
                    attempt = self.start(journal)
                    ref = common.append_checkpoint(journal, self.event())
                    if mutation == 'sha256': ref['checkpointRef']['sha256'] = '0' * 64
                    elif mutation == 'sequence': ref['checkpointRef']['sequence'] += 1
                    elif mutation == 'name': ref['name'] = 'other'
                    attempt['checkpoints'] = [] if mutation == 'omit' else [ref]
                    self.finish(journal, attempt)
                with self.assertRaisesRegex(ValueError, 'checkpoint history mismatch'):
                    common.reconcile_journal(self.report(), path, 'completed')

    def test_inflight_first_output_and_partial_tail_are_preserved(self):
        with common.AppendJournal(self.path, self.sha) as journal:
            self.start(journal)
            common.append_checkpoint(journal, self.event())
        with self.path.open('ab') as stream: stream.write(b'{"unfinished":')
        report = self.report()
        common.reconcile_journal(report, self.path, 'wall_limit')
        self.assertEqual(report['status'], 'stopped_incomplete')
        self.assertEqual(report['attempts'][0]['status'], 'interrupted')
        self.assertEqual(report['journalRecovery']['partialTailBytes'], len(b'{"unfinished":'))
        self.assertEqual(list(common.iter_checkpoint_events(report, self.path)), [self.event()])

    def test_empty_or_partial_header_never_preserves_a_complete_status(self):
        for raw in (b'', b'{"sequence":0'):
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                report = self.report()
                common.reconcile_journal(report, self.path, 'interrupted_before_header')
                self.assertEqual(report['status'], 'stopped_incomplete')
                self.assertEqual(report['unexecutedAttempts'], 1)
                self.assertEqual(report['journalRecovery']['partialTailBytes'], len(raw))

    def test_resolver_checks_hash_chain_and_record_reference_and_gzip(self):
        with common.AppendJournal(self.path, self.sha) as journal:
            attempt = self.start(journal)
            attempt['checkpoints'].append(common.append_checkpoint(journal, self.event()))
            self.finish(journal, attempt)
        report = self.report()
        common.reconcile_journal(report, self.path, 'done')
        compressed = self.path.with_suffix('.jsonl.gz')
        compressed.write_bytes(gzip.compress(self.path.read_bytes(), mtime=0))
        self.assertEqual(list(common.iter_checkpoint_events(report, compressed)), [self.event()])
        altered = copy.deepcopy(report)
        altered['attempts'][0]['checkpoints'][0]['checkpointRef']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'reference mismatch'):
            list(common.iter_checkpoint_events(altered, compressed))
        raw = self.path.read_bytes().replace('原始首次输出'.encode(), '篡改首次输出'.encode())
        self.path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'identity/sequence/hash'):
            list(common.iter_checkpoint_events(report, self.path))

    def test_legacy_v1_is_readable_and_can_be_recovered_as_refs_without_rewriting(self):
        with common.AppendJournal(self.path, self.sha) as journal:
            attempt = self.start(journal, referenced=False)
            event = self.event()
            journal.append('attempt_checkpoint', event)
            attempt['checkpoints'] = [event]
            self.finish(journal, attempt)
        before = self.path.read_bytes()
        legacy = self.report()
        common.reconcile_journal(legacy, self.path, 'done')
        self.assertEqual(legacy['attempts'][0]['checkpoints'], [self.event()])
        bounded = self.report()
        common.reconcile_journal(bounded, self.path, 'done', bounded=True)
        self.assertIn('checkpointRef', bounded['attempts'][0]['checkpoints'][0])
        self.assertEqual(list(common.iter_checkpoint_events(bounded, self.path)), [self.event()])
        self.assertEqual(self.path.read_bytes(), before)

    def test_interrupted_window_keeps_reference_without_token_arrays(self):
        with common.AppendJournal(self.path, self.sha) as journal:
            self.start(journal)
            window = {**{k: self.slot[k] for k in ('arm', 'caseId', 'repeat')}, 'eventId': 0,
                      'windowIndex': 0, 'status': 'running', 'inputIds': [1, 2], 'tokenTypeIds': [0, 0], 'factSpans': []}
            journal.append('window', window)
        report = self.report()
        common.reconcile_journal(report, self.path, 'cancelled')
        self.assertEqual(report['forwardAttempts'][0]['status'], 'interrupted')
        self.assertIn('journalRef', report['forwardAttempts'][0])
        self.assertNotIn('inputIds', report['forwardAttempts'][0])


if __name__ == '__main__': unittest.main()
