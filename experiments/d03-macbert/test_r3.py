import collections
import copy
import json
import unittest
from train_r3 import DATA, ROOT, load_data, pair_text, sha

class R3Tests(unittest.TestCase):
    def test_grouping_contrasts_and_replay(self):
        rows=load_data()
        manifest=json.loads((DATA.parent/'data-manifest.json').read_text())
        self.assertEqual(sha(DATA),manifest['datasetSha256'])
        self.assertEqual(len(rows),240)
        old=load_data(ROOT/'docs/research/d03-macbert/r2/scenes.jsonl')
        allowed={r['sceneId']:r for r in old if r['split']=='train'}
        groups=collections.defaultdict(list)
        for r in rows:
            self.assertIn(len(r['input']['characters']),(2,3))
            self.assertEqual(r['characterCount'],len(r['input']['characters']))
            self.assertNotIn(r['input']['actorId'],r['targetIds'])
            if r['origin']=='r2_train_replay':
                self.assertEqual(r['split'],'train')
                self.assertIn(r['sceneId'],allowed)
                self.assertEqual(r['input'],allowed[r['sceneId']]['input'])
                self.assertEqual(r['targetIds'],allowed[r['sceneId']]['targetIds'])
            else:
                groups[r['sourceGroup']].append(r)
        self.assertEqual(len(groups),24)
        for group in groups.values():
            self.assertEqual(len(group),6)
            self.assertEqual(len({r['split'] for r in group}),1)
            self.assertEqual({(r['contrastIndex'],r['paraphraseIndex']) for r in group},
                             {(i,j) for i in range(2) for j in range(3)})
            self.assertNotEqual(set(group[0]['targetIds']),set(group[3]['targetIds']))
        for s in ['development','test']:
            held=[r for r in rows if r['split']==s]
            self.assertEqual(len(held),24)
            self.assertEqual(set(r['category'] for r in held),{'ownership','reference','condition','isolation'})

    def test_label_free_input_and_all_facts(self):
        row=load_data()[0]
        candidate=row['input']['characters'][0]
        before=pair_text(row,candidate)
        changed=copy.deepcopy(row)
        changed.update(targetIds=[],category='secret',contrastIndex=100,paraphraseIndex=200)
        self.assertEqual(before,pair_text(changed,candidate))
        self.assertIn(row['input']['world'],before[0])
        self.assertIn(row['input']['action'],before[0])
        for person in row['input']['characters']:
            self.assertIn(person['name'],before[0])

if __name__=='__main__':
    unittest.main()
