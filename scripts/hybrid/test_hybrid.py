import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('hybrid_runner', HERE/'run.py')
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

class HybridTests(unittest.TestCase):
    def setUp(self):
        self.value=json.loads((HERE/'example.json').read_text(encoding='utf-8'))

    def test_shadow_uses_identical_frozen_action_and_preserves_already_acted(self):
        calls=[]
        def api(instruction,value):
            calls.append(copy.deepcopy(value))
            return {'actorId':'actor','action':'林安伸手取走何川拿着的平板。'} if len(calls)==1 else {'targetIds':['owner','borrower']}
        def local(path,frozen):
            self.assertEqual(frozen,calls[1])
            self.assertIn('owner',frozen['alreadyActedIds'])
            return {'targetIds':['borrower'],'status':'experimental_shadow_not_approved'}
        result=runner.execute(self.value,'shadow','unused',call=api,predict=local)
        self.assertFalse(result['worldWritten'])
        self.assertFalse(result['agreement'])
        self.assertEqual(result['apiTargetProposal'],['owner','borrower'])

    def test_api_only_never_loads_local_model(self):
        calls=[]
        def api(instruction,value):
            calls.append(value)
            return {'actorId':'actor','action':'林安安静地查看自己的手表。'} if len(calls)==1 else {'targetIds':[]}
        result=runner.execute(self.value,call=api,predict=lambda *args:self.fail('local model loaded'))
        self.assertIsNone(result['localTargetProposal'])

    def test_unknown_targets_rejected(self):
        count=[0]
        def api(instruction,value):
            count[0]+=1
            return {'actorId':'actor','action':'行动'} if count[0]==1 else {'targetIds':['invented']}
        with self.assertRaisesRegex(ValueError,'target IDs'):
            runner.execute(self.value,call=api)

    def test_bad_input_rejected_before_api(self):
        self.value['characters'].append({'id':'extra','name':'第四人'})
        with self.assertRaisesRegex(ValueError,'2-3'):
            runner.execute(self.value,call=lambda *a:self.fail('API called'))

if __name__=='__main__':
    unittest.main()
