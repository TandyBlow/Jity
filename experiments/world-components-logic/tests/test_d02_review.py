"""Tests for the local human-review packet; no human approval is granted."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import d02_review as review


class ReviewPacketTests(unittest.TestCase):
    def test_packet_has_all_samples_and_no_expected_answer(self):
        packet = review.packet()
        self.assertEqual(packet['schema'], 'jity-d02-human-review-packet-v1')
        self.assertEqual(packet['batch']['sampleCount'], 120)
        self.assertEqual(len(packet['samples']), 120)
        for sample in packet['samples']:
            self.assertNotIn('expected', sample)
            self.assertNotIn('expected', sample['draft'])
            self.assertTrue(sample['text'])
            self.assertTrue(sample['steps'])

    def test_batch_hashes_match_current_files(self):
        packet = review.packet()
        self.assertEqual(packet['batch']['samplesSha256'],
                         review.sha(review.DATA / 'samples.jsonl'))
        self.assertEqual(packet['batch']['manifestSha256'],
                         review.sha(review.DATA / 'manifest.json'))
        self.assertEqual(packet['batch']['worldsSha256'],
                         review.sha(review.DATA / 'worlds.json'))

    def test_review_html_is_generated_with_inert_packet(self):
        review.build()
        html = (review.OUT / 'pilot-review.html').read_text()
        self.assertIn('jity-d02-human-review-packet-v1', html)
        self.assertIn('120 条 · 20 组', html)
        self.assertNotIn('__PACKET__', html)

    def test_scale_batch_has_400_samples_and_40_groups(self):
        packet = review.packet('scale-v2')
        self.assertEqual(packet['batchName'], 'scale-v2')
        self.assertEqual(packet['batch']['sampleCount'], 400)
        self.assertEqual(packet['batch']['groupCount'], 40)
        self.assertTrue(all('expected' not in sample for sample in packet['samples']))
        review.build('scale-v2')
        html = (review.OUT / 'scale-v2-review.html').read_text()
        self.assertIn('400 条 · 40 组', html)
        self.assertNotIn('__PACKET__', html)


if __name__ == '__main__':
    unittest.main()
