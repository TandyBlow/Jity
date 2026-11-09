import argparse
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import retrain


class DataBoundaryTests(unittest.TestCase):
    def test_frozen_split_and_no_heldout_gradients(self):
        rows, summary = retrain.audit(retrain.DATASET, retrain.HERE/'splits.json')
        self.assertEqual(summary['splitCounts'], {'train': 3204, 'development': 693, 'test': 853})
        by_id = {r['exampleId']: r for r in rows}
        for kind in ('qwen', 'encoder'):
            args = argparse.Namespace(model=kind, device='cpu', dtype='float32', seed=42, steps=None)
            config = retrain.configure(args)
            selected = [r for r in rows if r['kind'] == 'text'] if kind == 'qwen' else [r for r in rows if r['kind'] in ('label','reference','number')]
            schedule = retrain.heads.training_schedule(selected, config)
            self.assertTrue(all(by_id[key]['split'] == 'train' for key in schedule['exampleIds']))

    def test_modified_data_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'changed.gz'; path.write_bytes(retrain.DATASET.read_bytes()+b'\x00')
            with self.assertRaises(ValueError): retrain.audit(path, retrain.HERE/'splits.json')

    def test_encoder_gpu_rejected_explicitly(self):
        args = argparse.Namespace(model='encoder',device='cuda',dtype='float32',seed=42,steps=None)
        with self.assertRaisesRegex(ValueError, 'CPU float32'): retrain.configure(args)


@unittest.skipUnless(importlib.util.find_spec('torch'), 'neural dependencies not installed')
class TinyCpuKernelTests(unittest.TestCase):
    def test_real_tiny_qwen_gradient_checkpoint_and_reload(self):
        # Random, one-layer test model: engineering coverage, not task quality evidence.
        import torch
        from transformers import Qwen3Config, Qwen3ForCausalLM
        torch.set_num_threads(1);torch.manual_seed(42)
        model = Qwen3ForCausalLM(Qwen3Config(vocab_size=32, hidden_size=16, intermediate_size=32,
                    num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=1, head_dim=8,
                    max_position_embeddings=64, eos_token_id=2, pad_token_id=2, attention_dropout=0.0))
        args=argparse.Namespace(model='qwen',device='cpu',dtype='float32',seed=42,steps=14)
        config=retrain.configure(args);config['maxNewTokens']=2
        rows=[{'exampleId':f'train-{i}','component':key,'sourceGroup':'train-group','split':'train','kind':'text','target':'x'} for i,key in enumerate(retrain.qwen.TASKS)]
        rows.append(dict(rows[0],exampleId='dev',sourceGroup='dev-group',split='development'))
        class Tokenizer:
            eos_token_id=2
            def decode(self,tokens,**kwargs): return 'fixture'
        def encode(tokenizer,row,config):
            return {k:row[k] for k in ('exampleId','component','sourceGroup','split')} | {'promptIds':[1,3,4], 'targetIds':[5,2]}
        base={k:v.detach().clone() for k,v in model.state_dict().items()}
        with tempfile.TemporaryDirectory() as d, patch.object(retrain.qwen,'tokenize_row',side_effect=encode):
            result=retrain.fit_qwen(torch,model,Tokenizer(),rows,config,Path(d),lambda *_:None)
            self.assertEqual(len(result['nonzeroGradientSteps']),14)
            saved=torch.load(Path(d)/'adapter.pt',map_location='cpu',weights_only=True)
            self.assertTrue(any(torch.any(v != 0) for k,v in saved['adapter'].items() if 'lora_B' in k))
            self.assertEqual(result['before']['examples'],1)
            self.assertEqual(result['after']['examples'],1)
            for name,tensor in model.state_dict().items():
                if 'lora_' not in name:
                    self.assertTrue(torch.equal(tensor,base[name.replace('.base_layer.','.')]),name)


if __name__=='__main__':unittest.main()
