"""Read-only timeline freezing and replay evidence provenance."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from jity_eval.replay.dataset import DatasetError, discover_sessions, freeze_dataset, load_dataset


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReplayDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.jity = self.root / "Jity"
        self.jity.mkdir()
        self.db = self.jity / "source.sqlite3"
        self.out = self.root / "jity-eval" / "frozen"
        with sqlite3.connect(self.db) as connection:
            connection.executescript("""
                CREATE TABLE game_sessions(id TEXT PRIMARY KEY, game_name TEXT, active_turn_id INTEGER, campaign_filename TEXT, model TEXT);
                CREATE TABLE story_turns(id INTEGER PRIMARY KEY, session_id TEXT, parent_turn_id INTEGER, depth INTEGER, player_action TEXT, output_json TEXT, state_json TEXT, campaign_progress_json TEXT, model TEXT, source TEXT, model_output_id INTEGER, created_at TEXT);
                CREATE TABLE model_outputs(id INTEGER PRIMARY KEY, session_id TEXT, status TEXT, raw_output_text TEXT, output_json TEXT, prompt_text TEXT, prompt_sections_json TEXT, retrieved_chunks_json TEXT);
                INSERT INTO game_sessions VALUES('a','长剧情',3,'test.json','offline-history');
                INSERT INTO game_sessions VALUES('b','短活动分支',11,NULL,'offline-history');
            """)
            nodes = [(1, 'a', None, 0), (2, 'a', 1, 1), (3, 'a', 2, 2), (4, 'a', 2, 2),
                     (10, 'b', None, 0), (11, 'b', 10, 1), (12, 'b', 11, 2), (13, 'b', 12, 3)]
            for identifier, session, parent, depth in nodes:
                output = {'narration': '历史回复 %s' % identifier, 'action_check': {'roll': 13, 'outcome': 'success'} if identifier == 3 else None}
                state = {'turn': depth, 'items': ['钥匙'], '_memory_controller': {'pending': False, 'version': str(identifier)}}
                connection.execute('INSERT INTO story_turns VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (
                    identifier, session, parent, depth, '' if parent is None else '行动 %s' % identifier,
                    None if parent is None else json.dumps(output), json.dumps(state), '{}', 'offline-history',
                    'scripted' if parent is None else 'llm', None if parent is None else identifier, '2026-11-05'))
                if parent is not None:
                    connection.execute('INSERT INTO model_outputs VALUES(?,?,?,?,?,?,?,?)', (
                        identifier, session, 'ok', json.dumps(output, separators=(',', ':')), json.dumps(output),
                        '历史提示', '{"memory":"已知钥匙"}', '[]'))
        campaign = self.jity / 'backend/data/campaigns/test.json'
        campaign.parent.mkdir(parents=True)
        campaign.write_text('{"title":"测试剧情"}', encoding='utf-8')

    def tearDown(self):
        self.temporary.cleanup()

    def freeze(self, session='a', **kwargs):
        return freeze_dataset(self.jity, self.db, session, self.out, **kwargs)

    def test_freeze_active_ancestor_chain_preserves_action_dice_output_state(self):
        before = fingerprint(self.db)
        data = load_dataset(self.freeze())
        self.assertEqual(before, fingerprint(self.db))
        self.assertEqual([turn['turn_id'] for turn in data['turns']], [2, 3])
        self.assertEqual([turn['turn'] for turn in data['turns']], [1, 2])
        self.assertEqual(data['turns'][1]['action_check']['roll'], 13)
        self.assertEqual(data['turns'][1]['player_action'], '行动 3')
        self.assertEqual(data['turns'][1]['state']['items'], ['钥匙'])
        self.assertEqual(data['initial']['state']['_memory_controller']['version'], '1')
        self.assertEqual(data['source']['campaign_asset'], 'campaign.json')
        self.assertTrue((self.out / 'source.snapshot.sqlite3').is_file())

    def test_discovery_uses_active_chain_not_max_branch_depth(self):
        sessions = discover_sessions(self.db)
        self.assertEqual([(item['id'], item['active_turn_count']) for item in sessions], [('a', 2), ('b', 1)])
        data = load_dataset(self.freeze(session=None))
        self.assertEqual(data['source']['session_id'], 'a')
        self.assertEqual(data['source']['selection_reason'], 'longest_active_ancestor_chain')

    def test_explicit_head_freezes_its_branch_only(self):
        data = load_dataset(self.freeze(head_turn_id='4'))
        self.assertEqual([turn['turn_id'] for turn in data['turns']], [2, 4])
        self.assertEqual(data['source']['original_active_turn_id'], 3)

    def test_wrong_session_head_is_rejected(self):
        with self.assertRaisesRegex(DatasetError, 'does not belong'):
            self.freeze(head_turn_id='11')

    def test_successful_raw_column_is_not_fabricated_as_call_record(self):
        data = load_dataset(self.freeze())
        self.assertEqual(data['call_records'], [])
        self.assertFalse(data['call_completeness']['exact_replay_available'])
        row = data['turns'][0]['model_output']
        self.assertEqual(row['raw_output_text_provenance'], 'normalized_committed_output')
        self.assertFalse(row['usable_as_exact_model_response'])
        self.assertEqual(row['output']['narration'], '历史回复 2')
        self.assertIn('memory_nsb_summary', data['call_completeness']['known_missing_purposes'])

    def test_missing_model_record_is_explicit(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute('DELETE FROM model_outputs WHERE id=2')
        data = load_dataset(self.freeze())
        self.assertIsNone(data['turns'][0]['model_output'])
        self.assertEqual(data['call_completeness']['missing_model_output_turn_ids'], [2])

    def test_source_modification_after_freeze_does_not_change_frozen_data(self):
        path = self.freeze()
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE story_turns SET player_action='新行动' WHERE id=2")
        self.assertEqual(load_dataset(path)['turns'][0]['player_action'], '行动 2')

    def test_dataset_tampering_and_snapshot_tampering_are_rejected(self):
        path = self.freeze()
        original = path.read_bytes()
        path.write_bytes(original + b' ')
        with self.assertRaisesRegex(DatasetError, 'changed'):
            load_dataset(path)
        path.write_bytes(original)
        with (self.out / 'source.snapshot.sqlite3').open('ab') as stream:
            stream.write(b'tampered')
        with self.assertRaisesRegex(DatasetError, 'changed'):
            load_dataset(path)

    def test_malformed_chain_is_rejected_even_with_matching_file_hash(self):
        path = self.freeze()
        value = json.loads(path.read_text())
        value['turns'][1]['parent_turn_id'] = 1
        path.write_text(json.dumps(value), encoding='utf-8')
        manifest_path = self.out / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['files']['dataset.json'] = fingerprint(path)
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(DatasetError, 'continuous ancestor chain'):
            load_dataset(path)

    def test_cyclic_source_has_no_fallback_to_session_messages(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute('UPDATE story_turns SET parent_turn_id=3 WHERE id=2')
        session = next(item for item in discover_sessions(self.db) if item['id'] == 'a')
        self.assertFalse(session['replayable'])
        self.assertIn('cycle', session['error'])
        with self.assertRaisesRegex(DatasetError, 'cycle'):
            self.freeze()

    def test_no_overwrite_or_output_inside_jity(self):
        self.freeze()
        with self.assertRaisesRegex(DatasetError, 'overwrite'):
            self.freeze()
        with self.assertRaisesRegex(DatasetError, 'outside'):
            freeze_dataset(self.jity, self.db, 'a', self.jity / 'accidental-write')
        self.assertFalse((self.jity / 'accidental-write').exists())

    def test_committed_wal_data_is_included_without_changing_source_bytes(self):
        writer = sqlite3.connect(self.db)
        try:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute("UPDATE story_turns SET player_action='WAL中的行动' WHERE id=2")
            writer.commit()
            wal = Path(str(self.db) + '-wal')
            before = (fingerprint(self.db), fingerprint(wal))
            data = load_dataset(self.freeze())
            self.assertEqual(data['turns'][0]['player_action'], 'WAL中的行动')
            self.assertEqual(before, (fingerprint(self.db), fingerprint(wal)))
        finally:
            writer.close()

    def test_wal_header_without_sidecars_does_not_create_source_files(self):
        writer = sqlite3.connect(self.db)
        writer.execute('PRAGMA journal_mode=WAL')
        writer.close()
        self.assertFalse(Path(str(self.db) + '-wal').exists())
        before = fingerprint(self.db)
        self.assertEqual(len(load_dataset(self.freeze())['turns']), 2)
        self.assertEqual(before, fingerprint(self.db))
        self.assertFalse(Path(str(self.db) + '-wal').exists())
        self.assertFalse(Path(str(self.db) + '-shm').exists())


if __name__ == '__main__':
    unittest.main()
