import unittest
from unittest.mock import Mock
import serve

class BridgeTests(unittest.TestCase):
    def value(self):
        return {'sourceId':'a','actionText':'尝试拿钥匙','alreadyActedIds':['b'],
                'workingState':{'time':{},'characters':{'a':{},'b':{}},'items':{},'locations':{},
                                'initial':{'characters':{'a':{'name':'田'},'b':{'name':'孙'}}}}}
    def test_preserves_state_action_and_acted(self):
        predict=Mock(return_value={'targetIds':['b']})
        self.assertEqual(serve.predict_targets(self.value(),'local',predict)['targetIds'],['b'])
        frozen=predict.call_args.args[1]
        self.assertEqual(frozen['alreadyActedIds'],['b'])
        self.assertEqual(frozen['action'],'尝试拿钥匙')
        self.assertIn('definitions',frozen['world'])
    def test_rejects_actor_and_unknown_target(self):
        for target in ['a','missing']:
            with self.assertRaises(ValueError):
                serve.predict_targets(self.value(),'local',lambda *_:{'targetIds':[target]})
    def test_model_failure_propagates_without_api(self):
        with self.assertRaisesRegex(ValueError,'too long'):
            serve.predict_targets(self.value(),'local',Mock(side_effect=ValueError('too long')))

if __name__ == '__main__': unittest.main()
