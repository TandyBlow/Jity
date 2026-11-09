"""Tiny random Qwen numerical export fixture; no game capability evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import short_qwen_export as export


class QwenExportTests(unittest.TestCase):
    def test_fresh_worker_registers_qwen_export_config_without_prior_export(self):
        import subprocess
        code="import sys;sys.path.insert(0,sys.argv[1]);import short_qwen_export as e;from transformers import Qwen3Config,Qwen3ForCausalLM;m=Qwen3ForCausalLM(Qwen3Config(vocab_size=64,hidden_size=16,intermediate_size=32,num_hidden_layers=1,num_attention_heads=2,num_key_value_heads=1,head_dim=8));c=e.qwen_onnx_config(m,'text-generation-with-past');assert 'past_key_values.0.key' in c.inputs"
        result=subprocess.run([sys.executable,'-c',code,str(Path(export.__file__).parent)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_historical_mask_recovery_matches_bytes_only(self):
        import hashlib,struct
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);values=[1,0,0,0,1,1,1,1]
            receipt={'inputShapes':{'attention_mask':[1,8]},'inputArraysSha256':{'attention_mask':hashlib.sha256(struct.pack('<8q',*values)).hexdigest()}}
            (root/'strict-float-validation.json').write_text(json.dumps(receipt))
            self.assertEqual(export.replay_input_config(root/'model.onnx')['validationAttentionMask'],[values])
            receipt['inputArraysSha256']['attention_mask']='wrong'
            (root/'strict-float-validation.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'cannot be uniquely recovered'):export.replay_input_config(root/'model.onnx')

    def test_numeric_mismatch_missing_outputs_and_nonfinite_are_fatal(self):
        import numpy as np
        good=export.compare_output('logits',np.array([1.0]),np.array([1.0]),export.CONFIG)
        receipt={'expectedOutputNames':['logits'],'checks':[good]}
        export.require_strict_validation(receipt)
        for value in (1.001,float('nan')):
            receipt['checks']=[export.compare_output('logits',np.array([1.0]),np.array([value]),export.CONFIG)]
            with self.assertRaisesRegex(ValueError,'numerical_validation_failed'):export.require_strict_validation(receipt)
        receipt['checks']=[good];receipt['expectedOutputNames'].append('present.0.key')
        with self.assertRaisesRegex(ValueError,'numerical_validation_failed'):export.require_strict_validation(receipt)

    def test_codec_comes_from_actual_training_identity_not_current_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'plan.json'
            path.write_text(json.dumps({'config':{'codec':'historical-v2'},'codeSha256':{'short_qwen_codec.py':'old-bytes'}}))
            model={'planPath':str(path),'planSha256':export.sha256_file(path),'codec':'historical-v2',
                   'codeSha256':{'short_qwen_codec.py':'old-bytes'}}
            self.assertEqual(export.training_codec_identity(model)['codecSha256'],'old-bytes')
            model['codeSha256']['short_qwen_codec.py']='current-bytes'
            with self.assertRaisesRegex(ValueError,'source identity'):export.training_codec_identity(model)
            model['codeSha256']['short_qwen_codec.py']='old-bytes';model['codec']='v3'
            with self.assertRaisesRegex(ValueError,'version mismatch'):export.training_codec_identity(model)

    def test_registered_disk_reserve_and_workspace_budget_fail_closed(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'fixture').write_bytes(b'123')
            config={**export.CONFIG,'maxAdditionalDiskBytes':200,'minFreeDiskBytes':100}
            with patch.object(export.shutil,'disk_usage',return_value=SimpleNamespace(free=400)):
                self.assertEqual(export.disk_state(root,config,initial=True)['observedWorkspaceBytes'],3)
            with patch.object(export.shutil,'disk_usage',return_value=SimpleNamespace(free=299)):
                with self.assertRaisesRegex(ValueError,'disk_reserve'):export.disk_state(root,config,initial=True)
            (root/'fixture').write_bytes(b'x'*201)
            with patch.object(export.shutil,'disk_usage',return_value=SimpleNamespace(free=400)):
                with self.assertRaisesRegex(ValueError,'workspace_budget'):export.disk_state(root,config)

    def test_browser_cache_dtype_uses_actual_graph_and_preserves_model_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.json';path.write_text(json.dumps({'model_type':'qwen3','hidden_size':16}))
            graph={'inputs':[{'name':'past_key_values.0.key','dtype':'FLOAT'},
                             {'name':'past_key_values.0.value','dtype':'FLOAT'}]}
            self.assertEqual(export.bind_cache_dtype(tmp,graph),'float32')
            result=json.loads(path.read_text())
            self.assertEqual(result['model_type'],'qwen3')
            self.assertEqual(result['transformers.js_config']['kv_cache_dtype']['q4f16'],'float32')
            graph['inputs'][1]['dtype']='FLOAT16'
            with self.assertRaisesRegex(ValueError,'inconsistent'):export.bind_cache_dtype(tmp,graph)

    def test_actual_tiny_causal_export_quantizes_and_executes_with_empty_cache(self):
        try:
            import torch,numpy as np,onnxruntime as ort
            from transformers import Qwen3Config,Qwen3ForCausalLM
            from optimum.exporters.onnx import main_export
        except ImportError:raise unittest.SkipTest('isolated export dependencies not installed')
        torch.set_num_threads(1);torch.manual_seed(7)
        cfg=Qwen3Config(vocab_size=128,hidden_size=16,intermediate_size=32,num_hidden_layers=1,
          num_attention_heads=2,num_key_value_heads=1,head_dim=8,max_position_embeddings=128,
          attention_dropout=0.0,bos_token_id=1,eos_token_id=2,pad_token_id=0)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);model=Qwen3ForCausalLM(cfg).eval().to(torch.bfloat16);model.save_pretrained(root/'source');model.to(torch.float32)
            raw=export.export_float(root/'source',root/'float',export.CONFIG)
            from optimum.exporters.tasks import TasksManager
            reference_eager=Qwen3ForCausalLM.from_pretrained(root/'source',torch_dtype=torch.float32,attn_implementation='eager').eval()
            constructor=TasksManager.get_exporter_config_constructor(model=reference_eager,exporter='onnx',task=export.CONFIG['task'])
            no_opt=export.validate_float(reference_eager,constructor(reference_eager.config,use_past=True,use_past_in_inputs=True),raw,
                {**export.CONFIG,'validationOptimization':'ORT_DISABLE_ALL'},receipt_path=root/'disable-receipt.json')
            basic=json.loads((raw.parent/'strict-float-validation.json').read_text())
            self.assertEqual(no_opt['inputArraysSha256'],basic['inputArraysSha256'])
            self.assertEqual(no_opt['expectedOutputNames'],basic['expectedOutputNames'])
            dest=root/'model_q4f16.onnx';graph=export.quantize_q4f16(raw,dest,export.CONFIG)
            self.assertGreater(graph['operators'].get('MatMulNBits',0),0)
            options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
            # Basic passes remove identity casts without the optional fp16
            # layernorm fusion that failed in the retained first CPU attempts.
            # WebGPU runtime and its own optimizations are verified separately.
            options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            session=ort.InferenceSession(str(dest),sess_options=options,providers=['CPUExecutionProvider'])
            values={}
            for value in session.get_inputs():
                if value.name=='input_ids':values[value.name]=np.array([[1,3]],dtype=np.int64)
                elif value.name=='attention_mask':values[value.name]=np.ones((1,2),dtype=np.int64)
                elif value.name=='position_ids':values[value.name]=np.array([[0,1]],dtype=np.int64)
                elif value.name.startswith('past_key_values.'):
                    values[value.name]=np.zeros((1,1,0,8),dtype=np.float16 if value.type=='tensor(float16)' else np.float32)
                else:self.fail('unexpected model input:'+value.name)
            outputs=session.run(None,values)
            self.assertEqual(outputs[0].shape,(1,2,128));self.assertTrue(np.isfinite(outputs[0]).all())
            with torch.no_grad():reference=model(input_ids=torch.tensor([[1,3]]),use_cache=False).logits.numpy()
            self.assertLess(float(np.max(np.abs(reference-outputs[0]))),0.05)


if __name__=='__main__':unittest.main()
