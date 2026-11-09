"""Regression for the real WebGPU RMSNorm square-overflow mechanism."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from short_qwen_precision import convert_qwen_float16

class PrecisionTests(unittest.TestCase):
 def test_large_norm_values_survive_quantized_matmul_boundary(self):
  import numpy as np,onnx,onnxruntime as ort
  from onnx import helper as h,numpy_helper as nh,TensorProto as T
  from onnxruntime.quantization.matmul_nbits_quantizer import MatMulNBitsQuantizer
  prefix='/model/layers.3/input_layernorm/'
  def node(op,ins,out,**kw):return h.make_node(op,ins,[out],name=prefix+op,**kw)
  nodes=[node('Cast',['input'],'x',to=T.FLOAT),node('Pow',['x','two'],'square'),
   node('ReduceMean',['square','axis'],'mean',keepdims=1),node('Add',['mean','eps'],'variance'),
   node('Sqrt',['variance'],'root'),node('Div',['one','root'],'reciprocal'),node('Mul',['x','reciprocal'],'norm'),
   h.make_node('MatMul',['norm','weight'],['output'],name='/model/layers.3/self_attn/q_proj/MatMul')]
  initial=[nh.from_array(np.array(v,dtype=t),name=k) for k,v,t in [('two',2.,'float32'),('one',1.,'float32'),('eps',1e-6,'float32'),('axis',[-1],'int64'),('weight',np.eye(4),'float32')]]
  model=h.make_model(h.make_graph(nodes,'overflow',[h.make_tensor_value_info('input',T.FLOAT,[1,4])],[h.make_tensor_value_info('output',T.FLOAT,[1,4])],initial),opset_imports=[h.make_opsetid('',18)]);model.ir_version=10
  q=MatMulNBitsQuantizer(model,block_size=32,is_symmetric=True);q.process()
  converted,proof=convert_qwen_float16(q.model.model)
  self.assertTrue(any(x['producer']==prefix+'Pow' and x['consumer']==prefix+'ReduceMean' for x in proof['preservedEdges']))
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'model.onnx';onnx.save_model(converted,path)
   opts=ort.SessionOptions();opts.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_BASIC;opts.intra_op_num_threads=1
   session=ort.InferenceSession(str(path),sess_options=opts,providers=['CPUExecutionProvider'])
   x=np.array([[7752.,1.,2.,3.]],dtype='float32');actual=session.run(None,{'input':x})[0]
   expected=x/np.sqrt(np.square(x).mean(-1,keepdims=True)+1e-6)
   self.assertTrue(np.isfinite(actual).all());self.assertGreater(abs(actual[0,0]),1.9)
   np.testing.assert_allclose(actual,expected,atol=.002,rtol=.002)
 def test_last_logits_selection_preserves_full_input_and_cache(self):
  import copy,numpy as np,onnx,onnxruntime as ort
  from onnx import helper as h,TensorProto as T,numpy_helper as nh
  from short_qwen_output_candidate import select_last_logits
  model=h.make_model(h.make_graph([
   h.make_node('MatMul',['input','weight'],['head'],name='/lm_head/MatMul'),
   h.make_node('Cast',['head'],['logits'],name='public_logits',to=T.FLOAT),
   h.make_node('Identity',['input'],['present.0.key'],name='cache')],
   'last_logits',[h.make_tensor_value_info('input',T.FLOAT16,[1,'sequence',4])],
   [h.make_tensor_value_info('logits',T.FLOAT,[1,'sequence',5]),h.make_tensor_value_info('present.0.key',T.FLOAT16,[1,'sequence',4])],
   [nh.from_array(np.arange(20,dtype='float16').reshape(4,5)/20,name='weight')]),opset_imports=[h.make_opsetid('',18)]);model.ir_version=10
  sliced=select_last_logits(copy.deepcopy(model))
  with tempfile.TemporaryDirectory() as tmp:
   sessions=[]
   for i,g in enumerate((model,sliced)):
    f=Path(tmp)/f'{i}.onnx';onnx.save_model(g,f);o=ort.SessionOptions();o.intra_op_num_threads=1;o.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    sessions.append(ort.InferenceSession(str(f),sess_options=o,providers=['CPUExecutionProvider']))
   for length in (1,7,31):
    x=np.arange(length*4,dtype='float16').reshape(1,length,4)/100
    a,b=[ss.run(None,{'input':x}) for ss in sessions]
    np.testing.assert_array_equal(a[0][:,-1:,:].astype('float16'),b[0].astype('float16')); np.testing.assert_array_equal(a[1],b[1]);self.assertEqual(b[1].shape[1],length)
if __name__=='__main__':unittest.main()
