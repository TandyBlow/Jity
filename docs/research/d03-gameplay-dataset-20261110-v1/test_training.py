import copy
import hashlib
import json
import unittest
from train import DATA, load_data, metrics, pair_text

class TrainingChecks(unittest.TestCase):
    def test_accepted_subset_and_split(self):
        root=DATA.parent
        manifest=json.loads((root/'data-manifest.json').read_text())
        self.assertEqual(hashlib.sha256(DATA.read_bytes()).hexdigest(),manifest['datasetSha256'])
        rows=load_data()
        excluded={json.loads(x)['sceneId'] for x in (root/'review-queue.jsonl').read_text().splitlines()}
        self.assertEqual(len(rows),17)
        self.assertFalse({r['sceneId'] for r in rows}&excluded)
        for s,n,gs in [('train',7,{'game-01','game-02'}),('development',4,{'game-03'}),('test',6,{'game-04'})]:
            subset=[r for r in rows if r['split']==s]
            self.assertEqual(len(subset),n)
            self.assertEqual({r['sourceGroup'] for r in subset},gs)

    def test_no_labels_or_audit_in_input(self):
        row=load_data()[0]; c=row['input']['characters'][0]
        original=pair_text(row,c)
        modified=copy.deepcopy(row)
        modified.update(targetIds=[],auditOnly={'future':'CANARY'},labelNote='CANARY',provenance={'answer':'CANARY'})
        self.assertEqual(original,pair_text(modified,c))
        self.assertNotIn('CANARY',''.join(original))
        self.assertIn('已行动编号：未知',original[0])
        self.assertIn(row['input']['world'],original[0])

    def test_set_scoring(self):
        records=[{'sourceGroup':'g','targetIds':['n0'],'scores':{'player':.1,'n0':.8}},
                 {'sourceGroup':'g','targetIds':[],'scores':{'player':.1,'n0':.7}}]
        m=metrics(records,.5)
        self.assertEqual((m['exactCount'],m['fn'],m['fp'],m['emptyCorrect']),(1,0,1,0))

if __name__=='__main__':unittest.main()
