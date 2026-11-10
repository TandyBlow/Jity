import collections
import copy
import json
import unittest
from train_r2 import DATA, load_data, pair_text, sha, metrics

class R2Tests(unittest.TestCase):
    def test_frozen_data_groups_and_counts(self):
        rows=load_data()
        manifest=json.loads((DATA.parent/'data-manifest.json').read_text())
        self.assertEqual(sha(DATA),manifest['datasetSha256'])
        self.assertEqual(len(rows),144)
        groups=collections.defaultdict(list)
        for row in rows:
            groups[row['sourceGroup']].append(row)
            roster={c['id'] for c in row['input']['characters']}
            self.assertEqual(len(roster),row['characterCount'])
            self.assertIn(len(roster),(2,3))
            self.assertIn(row['input']['actorId'],roster)
            self.assertNotIn(row['input']['actorId'],row['targetIds'])
            self.assertLessEqual(set(row['input']['alreadyActedIds']),roster)
        for group in groups.values():
            self.assertEqual(len(group),6)
            self.assertEqual(len({r['split'] for r in group}),1)
            self.assertEqual(sorted(len(r['targetIds']) for r in group),[0,0,1,1,1,2])
        for split,scenes,pairs in [('train',96,256),('development',24,64),('test',24,64)]:
            subset=[r for r in rows if r['split']==split]
            self.assertEqual(len(subset),scenes)
            self.assertEqual(sum(r['characterCount'] for r in subset),pairs)

    def test_metadata_and_gold_do_not_enter_input(self):
        row=load_data()[0]
        c=row['input']['characters'][0]
        before=pair_text(row,c)
        other=copy.deepcopy(row)
        other.update(targetIds=[],variant='secret',characterCount=99,split='secret')
        self.assertEqual(before,pair_text(other,c))

    def test_all_empty_baseline_and_group_scoring(self):
        records=[{'sourceGroup':r['sourceGroup'],'targetIds':r['targetIds'],
                  'scores':{c['id']:0 for c in r['input']['characters']}}
                 for r in load_data() if r['split']=='test']
        score=metrics(records,.5)
        self.assertEqual(score['exactCount'],8)
        self.assertEqual(score['fn'],20)
        self.assertEqual(score['groupExactMatch'],0)

if __name__=='__main__':
    unittest.main()
