"""CPU checks for full training sequences and the EOS/timeout decoder."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import torch
from transformers.models.t5.configuration_t5 import T5Config
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

import sequence_policy as policy


HERE = Path(__file__).resolve().parent


class SequencePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)
        cls.tokenizer = T5Tokenizer.from_pretrained(
            str(HERE.parent / "assets" / "randeng-t5-77m"),
            legacy=False, local_files_only=True)

    def model(self):
        torch.manual_seed(17)
        model = T5ForConditionalGeneration(T5Config(
            vocab_size=16, d_model=16, d_kv=4, d_ff=32,
            num_layers=1, num_decoder_layers=1, num_heads=2,
            dropout_rate=0, decoder_start_token_id=0,
            eos_token_id=1, pad_token_id=0))
        model.eval()
        return model

    def encoded(self):
        return {"input_ids": torch.tensor([[4, 7, 9, 1, 0]]),
                "attention_mask": torch.tensor([[1, 1, 1, 1, 0]])}

    def test_real_long_sample_keeps_input_target_and_eos(self):
        rows = [json.loads(line) for line in
                (HERE.parent / "n4_rewrite60" / "corpus140.jsonl")
                .read_text(encoding="utf-8").splitlines() if line.strip()]
        long_row = next(r for r in rows if r["id"] == "r02")
        short_row = min(rows, key=lambda r: len(r["target"]))
        enc, labels = policy.encode_training_batch(
            self.tokenizer, [long_row, short_row])
        expected_input = self.tokenizer(long_row["input"], truncation=False).input_ids
        expected_target = self.tokenizer(long_row["target"], truncation=False).input_ids
        self.assertGreater(len(expected_input), 512)
        self.assertGreater(len(expected_target), 128)
        self.assertEqual(enc.input_ids[0][enc.attention_mask[0].bool()].tolist(),
                         expected_input)
        self.assertEqual(labels.input_ids[0][labels.attention_mask[0].bool()].tolist(),
                         expected_target)
        self.assertEqual(expected_target[-1], self.tokenizer.eos_token_id)
        self.assertTrue(torch.all(labels.input_ids[labels.attention_mask == 0] == -100))

    def test_cached_greedy_matches_hf_before_eos(self):
        model = self.model()
        projected = model.lm_head.forward
        raw_runs = []

        def scheduled_head():
            raw = []
            raw_runs.append(raw)

            def forward(hidden):
                logits = projected(hidden)
                raw.append(logits.detach().clone())
                forced = torch.full_like(logits, -float("inf"))
                forced[..., [4, 5, 6, 1][len(raw) - 1]] = 0
                return forced
            return forward

        with patch.object(model.lm_head, "forward", side_effect=scheduled_head()):
            with torch.inference_mode():
                expected = model.generate(**self.encoded(), max_new_tokens=8,
                                          num_beams=1, do_sample=False)
        # The new decoder must ignore both generate() length defaults.
        model.generation_config.max_length = 2
        model.generation_config.max_new_tokens = 1
        with patch.object(model.lm_head, "forward", side_effect=scheduled_head()):
            actual, meta = policy.generate_greedy(model, self.encoded(), 10)
        self.assertEqual(actual.tolist(), expected.tolist())
        self.assertEqual(actual.tolist(), [[0, 4, 5, 6, 1]])
        self.assertTrue(meta["complete"])
        self.assertEqual(meta["stopReason"], "eos")
        for hf_logits, our_logits in zip(*raw_runs):
            torch.testing.assert_close(hf_logits, our_logits, rtol=1e-5, atol=1e-6)

    def test_timeout_preserves_partial_output_and_marks_incomplete(self):
        model = self.model()

        def no_eos(hidden):
            logits = torch.full((*hidden.shape[:-1], 16), -float("inf"))
            logits[..., 4] = 0
            return logits

        with patch.object(model.lm_head, "forward", side_effect=no_eos):
            with patch.object(policy.time, "perf_counter",
                              side_effect=[0, 0, 0.5, 1.5, 2]):
                actual, meta = policy.generate_greedy(model, self.encoded(), 1)
        self.assertEqual(actual.tolist(), [[0, 4, 4]])
        self.assertFalse(meta["complete"])
        self.assertEqual(meta["stopReason"], "timeout")
        self.assertEqual(meta["newTokens"], 2)

    def test_invalid_timeouts_rejected(self):
        for value in (0, -1, float("inf"), float("nan")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    policy.generation_timeout(value)

    def test_optional_logits_processor_is_applied(self):
        def force_eos(ids, scores):
            self.assertEqual(ids.tolist(), [[0]])
            scores.fill_(-float("inf"))
            scores[:, 1] = 0
            return scores

        actual, meta = policy.generate_greedy(
            self.model(), self.encoded(), 10, logits_processor=force_eos)
        self.assertEqual(actual.tolist(), [[0, 1]])
        self.assertTrue(meta["complete"])


if __name__ == "__main__":
    unittest.main()
