"""Small index checks; no model imports, inference, or repository changes."""
import importlib.util
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'short_delivery_index.py'
SPEC = importlib.util.spec_from_file_location('delivery_index_tested', PATH)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class DeliveryIndexTests(unittest.TestCase):
    def test_raw_and_weights_cannot_be_classified_as_small_public_material(self):
        for name in ('run.record.json', 'run.record.json.gz', 'run.record.journal.jsonl',
                     'run.record.webgpu.jsonl.gz', 'run.record.process.log', 'run.unit-003.stderr.log',
                     'run.export-record.json', 'run.export-record.json.gz',
                     'run.record.process.log.gz', 'run.record.stderr.log.gz',
                     'run.export-record.journal.jsonl', 'run.export-record.process.log', 'browser-tokenizer-probe-v2.jsonl'):
            self.assertEqual(M.category(name), 'raw_evidence_local_only')
        for name in ('heads.pt', 'model_q4f16.onnx', 'model.safetensors'):
            self.assertEqual(M.category(name), 'model_weights_local_only')
        self.assertEqual(M.category('run.plan.json'), 'frozen_plan')
        self.assertEqual(M.category('run.export-plan.json'), 'frozen_plan')
        self.assertEqual(M.record_for_plan(Path('run.export-plan.json')), Path('run.export-record.json'))
        self.assertEqual(M.category('run.summary.json'), 'summary')
        self.assertEqual(list(M.manifest_assets(Path('counts.json'),
            {'files': 42, 'models': 3, 'dataSnapshot': None})), [])

    def test_weight_hash_is_explicit_and_missing_assets_remain_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            path = root / 'fake.pt'; path.write_bytes(b'explicit engineering fixture, no model')
            row = M.file_entry(path, root)
            self.assertIsNone(row['sha256'])
            self.assertEqual(row['verification'], 'size_only_model_bytes_not_read')
            row = M.file_entry(path, root, hash_weights=True)
            self.assertEqual(row['sha256'], M.sha256(path))
            self.assertTrue(row['stableDuringRead'])
            self.assertFalse(M.file_entry(root / 'missing.pt', root)['exists'])

    def test_new_model_and_source_encoder_assets_but_no_retired_generator(self):
        value = {'model': {'directory': '/new', 'files': [{'path': 'qwen.bin', 'sha256': 'q'}]},
                 'models': {'encoder': {'directory': '/encoder', 'files': [{'path': 'head.pt', 'observedSha256': 'e'}]},
                            'generator': {'directory': '/retired', 'files': [{'path': 'old.bin', 'sha256': 'old'}]}}}
        self.assertEqual(list(M.manifest_assets(Path('plan'), value)),
                         [(Path('/new/qwen.bin'), 'q'), (Path('/encoder/head.pt'), 'e')])

    def test_compact_record_keeps_failure_without_copying_raw_outputs(self):
        value = {'runId': 'test', 'status': 'failed', 'attempts': [{'status': 'incomplete', 'error': 'OOM',
            'rawText': 'fixture raw'}], 'attemptSlots': [{'status': 'not_started'}, {'status': 'incomplete'}]}
        result = M.compact_record(value)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['attempts'], [{'status': 'incomplete', 'error': 'OOM'}])
        self.assertEqual(result['slotsByStatus'], {'not_started': 1, 'incomplete': 1})

    def test_selection_covers_all_batches_time_migration_and_source_recheck(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); cache = root / 'cache'
            names = ['artifacts/world-components-logic/short-semantics/short-encoder-time-r7.plan.json',
                'artifacts/world-components-logic/short-semantics/short-encoder-time-r8.plan.json',
                'artifacts/world-components-logic/short-semantics/code/r1/source.py',
                'artifacts/world-components-logic/short-semantics-20261109/source-recheck.json',
                'artifacts/world-components-logic/qwen-short/quarantine-export-r1/index.json',
                'artifacts/world-components-logic/qwen-short/export.qualification-correction.json',
                'experiments/world-components-logic/data/short-semantics/time-choice-v2/migration-proof.json']
            for name in names:
                file = root / name; file.parent.mkdir(parents=True, exist_ok=True); file.write_text('{}')
            self.assertEqual(M.selected_paths(root, cache), {(root / name).resolve() for name in names})

    def test_raw_default_does_not_rehash_and_gzip_record_is_read_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); file = root / 'fixture.export-record.json.gz'
            with gzip.open(file, 'wt') as stream:
                json.dump({'status': 'failed_validation', 'attempts': [{'error': 'fixture', 'rawText': 'not copied'}]}, stream)
            row = M.file_entry(file, root)
            self.assertIsNone(row['sha256'])
            self.assertEqual(row['verification'], 'size_only_raw_bytes_not_rehashed')
            self.assertEqual(M.file_entry(file, root, hash_raw=True)['sha256'], M.sha256(file))
            metadata, reason = M.read_metadata(file)
            self.assertIsNone(reason)
            self.assertEqual(metadata['status'], 'failed_validation')
            self.assertNotIn('rawText', metadata['attempts'][0])
            with patch.object(M, 'cloud_placeholder', return_value=True):
                self.assertEqual(M.read_metadata(file), (None, 'cloud_placeholder_not_hydrated'))
                self.assertIsNone(M.file_entry(file, root, hash_raw=True)['sha256'])

    def test_superseded_plan_can_close_without_fabricating_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); plan = root / 'fixture.plan.json'; plan.write_text('{"runId":"fixture"}')
            record = M.record_for_plan(plan)
            record.write_text('{}')
            proof = {'status': 'superseded_before_execution', 'modelCalls': 0, 'reason': 'new registered identity',
                     'planSha256': M.sha256(plan)}
            documents = {plan: {'runId': 'fixture'}, record: proof}
            rows = [M.file_entry(plan, root), M.file_entry(record, root)]
            run = M.run_entries({plan, record}, documents, rows, root)[0]
            self.assertTrue(run['finalEvidence']); self.assertTrue(run['explainedWithoutExecution'])
            self.assertFalse(run['executionCompleted'])
            proof['modelCalls'] = True
            self.assertFalse(M.run_entries({plan, record}, documents, rows, root)[0]['finalEvidence'])
            proof['modelCalls'] = 0; proof['planSha256'] = 'wrong'
            self.assertFalse(M.run_entries({plan, record}, documents, rows, root)[0]['finalEvidence'])

    def test_export_correction_overrides_only_effective_status_and_gzip_counts_as_record(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); plan = root / 'fixture.export-plan.json'; plan.write_text('{"runId":"fixture"}')
            record = Path(str(M.record_for_plan(plan)) + '.gz')
            correction = root / 'fixture.qualification-correction.json'
            record.write_bytes(b'explicit fixture'); correction.write_text('{}')
            documents = {plan: {'runId': 'fixture'}, record: {'status': 'diagnostic_completed'},
                correction: {'runId': 'fixture', 'status': 'failed_validation', 'reason': 'strict atol failed',
                             'planSha256': M.sha256(plan)}}
            rows = [M.file_entry(p, root) for p in (plan, record, correction)]
            run = M.run_entries({plan, record, correction}, documents, rows, root)[0]
            self.assertEqual(run['status'], 'diagnostic_completed')
            self.assertEqual(run['effectiveDisposition'], 'failed_validation')
            self.assertEqual(run['record'], str(record)); self.assertTrue(run['finalEvidence'])
            self.assertFalse(run['executionCompleted'])

    def test_lossless_gzip_and_quarantine_relocation_preserve_missing_original_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); q = root / 'artifacts/world-components-logic/qwen-short'; q.mkdir(parents=True)
            original = q / 'fixture.record.json'; compressed = Path(str(original) + '.gz')
            with gzip.open(compressed, 'wt') as stream: stream.write('{"status":"failed"}')
            archive = {'lossless': True, 'files': [{'originalPath': str(original), 'originalSha256': 'o' * 64,
                'compressedPath': str(compressed), 'compressedSha256': M.sha256(compressed)}]}
            (q / 'fixture.raw-archive.json').write_text(json.dumps(archive))
            old = q / 'model.provider.json'; kept = q / 'quarantine-export-r1/model.provider.json'
            kept.parent.mkdir(); kept.write_text('{}')
            (kept.parent / 'relocation-index-v2.json').write_text(json.dumps({
                'schema': 'jity-quarantined-relocation-v2', 'status': 'quarantined_not_qualified',
                'files': [{'originalPath': str(old), 'retainedAs': str(kept), 'sha256': M.sha256(kept)}]}))
            with patch.object(M, 'git_state', return_value=(set(), {str(compressed.relative_to(root)), str(original.relative_to(root))})):
                index = M.build(root, root / 'cache')
            self.assertFalse([p for p in index['problems'] if p['kind'] == 'registered_asset_missing'])
            entries = {r['path']: r for r in index['files']}
            self.assertEqual(entries[str(old)]['retainedAs']['meaning'], 'quarantined_not_qualified')
            self.assertEqual(entries[str(original)]['retainedAs']['path'], str(compressed))


if __name__ == '__main__':
    unittest.main()
