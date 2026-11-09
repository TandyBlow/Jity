"""Engineering counterexamples, not semantic or browser model evidence."""
import sys,tempfile,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import short_qwen_export as e
import short_qwen_diagnostic as d

class DiagnosticTests(unittest.TestCase):
 def test_missing_pair_is_explicit_and_never_dropped(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);plan=root/'plan.json';plan.write_text('{}')
   with patch.object(d,'verify',return_value={'cases':[{'caseId':'fixture','fixedTokenIds':[4]}]}):d.compare(plan)
   result=json.loads((root/'comparison.json').read_text())
   self.assertEqual(result['coverage']['expectedPairsTimesCases'],7)
   self.assertEqual(result['coverage']['incomplete'],7)
   self.assertEqual(len(result['comparisons']),7)
   self.assertFalse(result['coverage']['allArtifactsPresent'])
   self.assertTrue(all(r['missingArtifacts'] for r in result['comparisons']))
   self.assertFalse(result['worldWriteAllowed'])
 def test_nonfinite_browser_logits_are_preserved_before_rejection(self):
  import numpy as np
  from short_qwen_diagnostic_browser import received_logits
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);raw=np.array([1,float('inf')],dtype='<f4').tobytes()
   with self.assertRaisesRegex(ValueError,'retained'):received_logits(raw,2,root,0,0)
   file=root/'0.fixed.step-0.rejected-logits.bin';self.assertEqual(file.read_bytes(),raw)
   with self.assertRaisesRegex(ValueError,'retained'):received_logits(b'bad',2,root,0,0)
   self.assertEqual(file.read_bytes(),raw)
   self.assertFalse(json.loads((root/'0.fixed.step-0.rejected-logits.json').read_text())['accepted'])
 def test_equal_truncated_fixed_runs_do_not_count_as_complete(self):
  import numpy as np
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);plan=root/'plan.json';plan.write_text('{}')
   for engine in ('adapter_bf16','merged_bf16'):
    dest=root/'runs'/engine;dest.mkdir(parents=True)
    value={'rawTokenIds':[4],'rawText':'fixture','eosReached':True}
    for mode in ('free','fixed'):(dest/f'0.{mode}.json').write_text(json.dumps(value))
    np.savez(dest/'0.fixed.logits.npz',step_0=np.ones((1,1,5),dtype='float32'))
   with patch.object(d,'verify',return_value={'cases':[{'caseId':'fixture','fixedTokenIds':[4]}]}):
    with self.assertRaisesRegex(ValueError,'step coverage'):d.compare(plan)
 def test_numeric_breach_and_behavior_are_separate(self):
  import numpy as np
  result=e.compare_diagnostic('logits',np.array([[[2.,1.]]]),np.array([[[2.001,1.]]]))
  self.assertFalse(result['valuesClose']);self.assertTrue(result['top1Equal'])
  result=e.compare_diagnostic('logits',np.array([[[1.,1.00001]]]),np.array([[[1.00002,1.]]]))
  self.assertTrue(result['valuesClose']);self.assertFalse(result['top1Equal'])
 def test_streamed_error_matches_legacy_gate_across_chunks(self):
  import numpy as np
  rng=np.random.default_rng(7);a=rng.standard_normal(150000).astype('float32');b=a.copy();b[65536]+=0.01
  direct=e.compare_output('x',a,b,e.CONFIG);streamed=e.compare_diagnostic('x',a,b)
  for key in ('finite','shapesEqual','valuesClose','maxAbsError'):self.assertEqual(direct[key],streamed[key])
  self.assertEqual(streamed['outsideTolerance'],1)
 def test_input_identity_includes_shape_dtype_and_every_cache_byte(self):
  import numpy as np
  self.assertEqual(e.array_identity(np.zeros((1,8,0,128)))['sha256'],__import__('hashlib').sha256(b'').hexdigest())
  x=np.ones((2,2),dtype=np.float32)
  self.assertNotEqual(e.array_identity(x),e.array_identity(x.reshape(1,4)))
  self.assertNotEqual(e.array_identity(x),e.array_identity(x.astype(np.float64)))
  y=x.copy();y[-1,-1]=2;self.assertNotEqual(e.array_identity(x),e.array_identity(y))
 def test_normal_browser_rejects_diagnostic_schema(self):
  from short_webgpu import verified_manifest,MODEL_SCHEMA
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'assets.json';p.write_text(json.dumps({'schema':'jity-qwen-unqualified-diagnostic-assets-v1','qualification':'conversion_unqualified'}))
   with self.assertRaisesRegex(ValueError,'schema'):verified_manifest(p,MODEL_SCHEMA)
 def test_tiny_prefill_decode_and_taps_are_real_same_tensor_paths(self):
  import torch,numpy as np,onnx
  from transformers import Qwen3Config,Qwen3ForCausalLM
  torch.set_num_threads(1);torch.manual_seed(7)
  cfg=Qwen3Config(vocab_size=64,hidden_size=16,intermediate_size=32,num_hidden_layers=1,num_attention_heads=2,num_key_value_heads=1,head_dim=8,max_position_embeddings=128)
  model=Qwen3ForCausalLM(cfg).eval();model.config._attn_implementation='eager'
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);model.save_pretrained(root/'source')
   graph=e.export_float(root/'source',root/'float',e.CONFIG)
   external=onnx.load(graph)
   external_path=root/'float'/'external.onnx'
   onnx.save_model(external,external_path,save_as_external_data=True,all_tensors_to_one_file=True,location='external.data',size_threshold=1024,convert_attribute=True)
   graph=external_path
   taps=e.diagnostic_graph(graph,root/'trace.onnx',1)
   ort=d.session(root/'trace.onnx')
   values=d.feeds([1,3,5],{},cfg.to_dict());first=d.torch_forward(model,values)
   for values in [values,d.feeds([7],d.next_cache(first),cfg.to_dict())]:
    handles,captured=e.capture_modules(model,taps)
    try:reference=d.torch_forward(model,values,full=True)
    finally:
     for h in handles:h.remove()
    out=dict(zip([o.name for o in ort.get_outputs()],ort.run(None,values)))
    for tap in taps:
     np.testing.assert_allclose(captured[tap['module']],out[tap['output']],atol=1e-5,rtol=1e-4)
    np.testing.assert_allclose(reference['logits'],out['logits'],atol=1e-5,rtol=1e-4)
   full=d.torch_forward(model,d.feeds([1,3,5,7],{},cfg.to_dict()))
   np.testing.assert_allclose(reference['logits'][:,-1:,:],full['logits'],atol=1e-5)
   broken=onnx.load(graph,load_external_data=False);broken.graph.node[0].name='unexpected'
   # A missing mapped operator must fail, never select an approximate match.
   next(n for n in broken.graph.node if n.name=='/model/norm/Mul_1').name='changed'
   with self.assertRaisesRegex(ValueError,'unmapped'):e.diagnostic_taps(broken,1)
if __name__=='__main__':unittest.main()
