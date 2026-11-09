import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from short_contracts import digest
from short_data_migration import CHANGED, SCHEMA, verify_migration


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.before = [{'exampleId': 'time', 'component': 'D08.1.amount', 'sourceGroup': 'same-source',
                        'split': 'train', 'kind': 'text', 'input': {'world': {'all': 'facts'}}, 'target': '2'},
                       {'exampleId': 'focus', 'component': 'D02.1', 'sourceGroup': 'another-source',
                        'split': 'test', 'kind': 'label', 'input': {'complete': 'world'}, 'target': 'act'}]
        self.after = copy.deepcopy(self.before)
        self.after[0]['input']['timeChoice'] = {'boundary': 'elapsed', 'unit': 'minute'}
        for suffix, target in [('unit', 'minute'), ('boundary', 'elapsed')]:
            row = {'exampleId': suffix, 'component': 'D08.1.' + suffix, 'sourceGroup': 'same-source',
                   'split': 'train', 'kind': 'label', 'input': {'world': {'all': 'facts'}}, 'target': target}
            self.before.append(row); self.after.append(copy.deepcopy(row))
        self.after[2]['input']['timeChoice'] = {'boundary': 'elapsed'}

    def write(self):
        specs = []
        for name, rows in [('source', self.before), ('target', self.after)]:
            for row in rows:
                row['contentSha256'] = digest({k: v for k, v in row.items() if k != 'contentSha256'})
            raw = b''.join((json.dumps(row, sort_keys=True) + '\n').encode() for row in rows)
            p = self.root / (name + '.jsonl.gz'); p.write_bytes(gzip.compress(raw, mtime=0))
            specs.append({'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                          'uncompressedSha256': hashlib.sha256(raw).hexdigest()})
        records = []
        for i, (a, b) in enumerate(zip(self.before, self.after)):
            records.append({'rowIndex': i, 'oldExampleId': a['exampleId'], 'newExampleId': b['exampleId'],
                'component': a['component'], 'sourceGroup': a['sourceGroup'], 'split': a['split'],
                'oldInputSha256': digest(a['input']), 'newInputSha256': digest(b['input']),
                'oldTargetSha256': digest(a['target']), 'newTargetSha256': digest(b['target']),
                'oldContentSha256': a['contentSha256'], 'newContentSha256': b['contentSha256'],
                'oldFullRowSha256': digest(a), 'newFullRowSha256': digest(b), 'changed': a != b,
                'unchangedFieldsExact': True})
        proof = {'schema': SCHEMA, 'sourceDataset': specs[0], 'targetDataset': specs[1],
            'allowedChangedComponents': sorted(CHANGED), 'allowedChangedFields': ['input', 'contentSha256'],
            'rows': records, 'rowCount': len(records), 'changedRows': sum(r['changed'] for r in records),
            'unaffectedRowsExactEquality': sum(not r['changed'] for r in records),
            'unaffectedRawLinesByteIdentical': sum(not r['changed'] for r in records)}
        path = self.root / 'proof.json'; path.write_text(json.dumps(proof)); return path

    def test_unchanged_focus_retains_original_training_identity(self):
        report = verify_migration(self.write(), unchanged_components=['D02.1'])
        self.assertEqual(report['verifiedUnchangedComponents'], ['D02.1'])
        self.assertFalse(report['semanticApproval'])

    def test_changed_time_task_cannot_claim_inherited_qualification(self):
        with self.assertRaisesRegex(ValueError, 'requires_new_training'):
            verify_migration(self.write(), unchanged_components=['D08.1.amount'])

    def test_changed_label_split_or_source_rejected_even_with_rehashed_proof(self):
        for key, value in [('target', '99'), ('split', 'train'), ('sourceGroup', 'renamed-source')]:
            original = self.after[1][key]; self.after[1][key] = value
            with self.assertRaisesRegex(ValueError, 'noninput_field_changed'):
                verify_migration(self.write())
            self.after[1][key] = original

    def test_world_change_cannot_hide_behind_time_choice(self):
        self.after[0]['input']['world']['all'] = 'truncated facts'
        with self.assertRaisesRegex(ValueError, 'original_input_changed'):
            verify_migration(self.write())

    def test_bool_integer_and_integer_float_are_distinct_input_values(self):
        for original, changed in [(1, True), (70, 70.0)]:
            self.before[0]['input']['world']['typed'] = original
            self.after[0]['input']['world']['typed'] = changed
            with self.assertRaisesRegex(ValueError, 'original_input_changed'):
                verify_migration(self.write())

    def test_legal_but_different_unit_cannot_replace_previous_choice(self):
        self.after[0]['input']['timeChoice']['unit'] = 'hour'
        with self.assertRaisesRegex(ValueError, 'previous_choice_reference_mismatch:unit'):
            verify_migration(self.write())

    def test_noninput_and_proof_cannot_confuse_booleans_with_integers(self):
        self.before[0]['metadataVersion'] = 1
        self.after[0]['metadataVersion'] = True
        with self.assertRaisesRegex(ValueError, 'noninput_field_changed'):
            verify_migration(self.write())
        self.after[0]['metadataVersion'] = 1
        path = self.write(); proof = json.loads(path.read_text())
        proof['rows'][0]['changed'] = 1; path.write_text(json.dumps(proof))
        with self.assertRaisesRegex(ValueError, 'row_proof_mismatch'):
            verify_migration(path)

    def test_forged_per_row_claim_and_duplicate_coverage_rejected(self):
        path = self.write(); proof = json.loads(path.read_text())
        proof['rows'][1] = copy.deepcopy(proof['rows'][0]); path.write_text(json.dumps(proof))
        with self.assertRaisesRegex(ValueError, 'row_proof_mismatch'):
            verify_migration(path)

    def test_frozen_source_identity_required(self):
        with self.assertRaisesRegex(ValueError, 'source_identity_mismatch'):
            verify_migration(self.write(), source_sha='different_model_training_data')

    def test_unchanged_time_task_and_extra_choice_fields_rejected(self):
        self.after[0]['input']['timeChoice']['modelAnswer'] = '2'
        with self.assertRaisesRegex(ValueError, 'time_choice_shape'):
            verify_migration(self.write())
        self.after[0] = copy.deepcopy(self.before[0])
        with self.assertRaisesRegex(ValueError, 'time_task_not_updated'):
            verify_migration(self.write())


if __name__ == '__main__': unittest.main()
