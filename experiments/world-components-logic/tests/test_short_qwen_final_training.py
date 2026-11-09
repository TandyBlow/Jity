"""Validate final-attempt bookkeeping without executing a real training run."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import short_qwen_final_training as f


class FinalAttemptTests(unittest.TestCase):
    def test_parent_local_cursor_is_not_cumulative_optimizer_step(self):
        adapter={'weight':'retained'};rng=object()
        parent={'nextSchedulePosition':32,'optimizerCumulativeSteps':144,
                'optimizer':{'state':{0:{'step':144},1:{'step':144}}},'adapter':adapter,'cpuRngState':rng}
        normalized=f.normalized_parent_state(parent,144)
        self.assertEqual(parent['nextSchedulePosition'],32)
        self.assertEqual(normalized['nextSchedulePosition'],144)
        self.assertIs(normalized['adapter'],adapter)
        self.assertIs(normalized['optimizer'],parent['optimizer'])
        self.assertIs(normalized['cpuRngState'],rng)
        with self.assertRaisesRegex(ValueError,'optimizer history'):
            f.normalized_parent_state(parent,32)
        parent['optimizer']['state'][1]['step']=143
        with self.assertRaisesRegex(ValueError,'optimizer history'):
            f.normalized_parent_state(parent,144)

    def test_final_budget_is_single_fixed_continuation(self):
        c=f.configuration()
        self.assertEqual(c['steps'],224);self.assertEqual(c['retries'],0)
        self.assertFalse(c['automaticAdditionalTraining'])
        self.assertEqual(set(c['trainingComponents']),set(f.q.TASKS))
        self.assertEqual(c['maxInputTokens'],8192)
        self.assertEqual(c['maxNewTokens'],128)
        self.assertFalse(c['doSample'])


if __name__=='__main__':unittest.main()
