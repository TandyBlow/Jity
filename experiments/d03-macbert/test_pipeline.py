import copy
import json
from pathlib import Path
import tempfile
import unittest
from train import load_data, metrics, pair_text, DATA, sha

class PipelineTests(unittest.TestCase):
    def test_manifest_and_disjoint_scenes(self):
        rows = load_data()
        manifest = json.loads((DATA.parent / 'data-manifest.json').read_text())
        self.assertEqual(sha(DATA), manifest['datasetSha256'])
        self.assertEqual(len(rows), 96)
        for split, count in [('train',64),('development',16),('test',16)]:
            subset = [r for r in rows if r['split'] == split]
            self.assertEqual(len(subset), count)
            self.assertEqual(sum(not r['targetIds'] for r in subset), count//2)
        self.assertTrue(any(set(r['targetIds']) & set(r['input']['alreadyActedIds']) for r in rows))

    def test_leaked_split_rejected(self):
        rows = load_data()
        rows[1]['split'] = 'test' if rows[0]['split'] != 'test' else 'train'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.jsonl'
            path.write_text('\n'.join(json.dumps(r) for r in rows))
            with self.assertRaisesRegex(ValueError, 'crosses splits'):
                load_data(path)

    def test_label_independent_input_and_full_roster(self):
        row = load_data()[0]
        candidate = row['input']['characters'][0]
        original = pair_text(row,candidate)
        changed = copy.deepcopy(row)
        changed['targetIds'] = []
        changed['split'] = 'test'
        changed['sourceGroup'] = 'secret-answer'
        self.assertEqual(original, pair_text(changed,candidate))
        for person in row['input']['characters']:
            self.assertIn(person['name'], original[0])
            self.assertIn(person['id'], original[0])
        self.assertIn(row['input']['world'], original[0])
        self.assertIn(row['input']['action'], original[0])

    def test_set_metrics_expose_false_empty(self):
        records = [
            {'sourceGroup':'a','targetIds':['b','c'],'scores':{'a':.1,'b':.8,'c':.2}},
            {'sourceGroup':'a','targetIds':[],'scores':{'a':.1,'b':.1,'c':.1}},
            {'sourceGroup':'b','targetIds':[],'scores':{'a':.9,'b':.1,'c':.1}},
        ]
        result = metrics(records,.5)
        self.assertEqual((result['tp'],result['fp'],result['fn'],result['tn']),(1,1,1,6))
        self.assertEqual(result['exactCount'],1)
        self.assertEqual(result['groupExactMatch'],0.)
        self.assertEqual(result['emptyAccuracy'],.5)

if __name__ == '__main__':
    unittest.main()
