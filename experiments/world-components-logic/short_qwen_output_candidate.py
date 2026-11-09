"""Select the last hidden position BEFORE the vocabulary projection.

All input tokens, weights and KV outputs are retained. This
avoids materializing an unused [batch, entire_input, vocabulary] FP32 tensor.
"""
import argparse,gc,shutil
from pathlib import Path
import onnx,numpy as np
import short_qwen_diagnostic as d
import short_qwen_export as e


def select_last_logits(model):
 from onnxruntime.transformers.onnx_model import OnnxModel
 outputs={v:n for n in model.graph.node for v in n.output};cast=outputs['logits']
 if cast.op_type!='Cast' or next(a.i for a in cast.attribute if a.name=='to')!=onnx.TensorProto.FLOAT:raise ValueError('expected FP32 logits output cast')
 head=outputs[cast.input[0]]
 if head.name not in ('/lm_head/MatMul','/lm_head/MatMul_Q4') or head.op_type not in ('MatMul','MatMulNBits'):raise ValueError('unrecognized vocabulary projection')
 old=head.input[0];name='diagnostic_last_hidden';idx=name+'_index'
 if any(n.name==name for n in model.graph.node):raise ValueError('already selected last logits')
 model.graph.initializer.append(onnx.numpy_helper.from_array(np.array([-1],dtype=np.int64),name=idx))
 model.graph.node.append(onnx.helper.make_node('Gather',[old,idx],[name],name=name,axis=1));head.input[0]=name
 for value in list(model.graph.output)+list(model.graph.value_info):
  if value.name in ('logits',head.output[0]):value.type.tensor_type.shape.dim[1].Clear();value.type.tensor_type.shape.dim[1].dim_value=1
 model.graph.value_info.append(onnx.helper.make_tensor_value_info(name,onnx.TensorProto.FLOAT16,[None,1,None]))
 OnnxModel(model).topological_sort();onnx.checker.check_model(model)
 return model


def create(parent_path,run_id):
 p=d.verify(parent_path);old=Path(parent_path).parent;plan=d.freeze(run_id,Path(p['modelManifest']['path']));root=plan.parent
 d.save(root/'output-protocol.json',{'plan':d.entry(plan),'parent':d.entry(parent_path),'code':d.entry(__file__),
  'recipe':'keep connected FP32 norm/RoPE candidate; Gather [-1] axis 1 on final hidden states before vocabulary projection; unchanged full model input and KV outputs',
  'reason':'long input body probes finite through final norm; isolate full vocabulary output allocation and cast',
  'sourceGraphs':[d.entry(old/k/'webgpu/onnx/model_q4f16.onnx') for k in ('base','trained')],
  'numericThresholdsUnchanged':True,'qualification':'conversion_unqualified','worldWriteAllowed':False})
 shutil.copyfile(__file__,root/'output-candidate.py')
 for kind in ('base','trained'):
  target=root/kind;target.mkdir();shutil.copytree(old/kind/'float',target/'float',copy_function=lambda a,b:Path(b).hardlink_to(a))
  modeldir=target/'webgpu';(modeldir/'onnx').mkdir(parents=True)
  for f in (old/kind/'webgpu').iterdir():
   if f.is_file():shutil.copyfile(f,modeldir/f.name)
  source=old/kind/'webgpu/onnx/model_q4f16.onnx';model=select_last_logits(onnx.load(source))
  onnx.save_model(model,modeldir/'onnx/model_q4f16.onnx');del model;gc.collect()
  d.save(target/'assets.json',{'schema':'jity-qwen-unqualified-diagnostic-assets-v1','qualification':'conversion_unqualified','worldWriteAllowed':False,
   'plan':d.entry(plan),'inheritedPrecisionAssets':d.entry(old/kind/'assets.json'),'outputProtocol':d.entry(root/'output-protocol.json'),
   'files':[d.entry(f) for f in target.rglob('*') if f.is_file()]})
 for name in ('ort.mjs','ort-build.json'):
  if (old/name).exists():shutil.copyfile(old/name,root/name)
 # Completed unchanged non-quantized stages only; never copy another graph's outputs.
 inherited=[]
 for engine in ('adapter_bf16','merged_bf16','merged_fp32','base_fp32','base_float'):
  source=old/'runs'/engine
  if source.exists():shutil.copytree(source,root/'runs'/engine,copy_function=lambda a,b:Path(b).hardlink_to(a));inherited.append(engine)
 d.save(root/'inherited-stages.json',{'parent':d.entry(parent_path),'engines':inherited,'casesEqual':p['cases']==d.read(plan)['cases'],'noRerunClaim':True})
 print('PLAN',plan,flush=True)


def verify_long(plan_path):
 p=d.verify(plan_path);root=Path(plan_path).parent;proto=d.read(root/'output-protocol.json');cfg=d.read(Path(p['model']['merged']['directory'])/'config.json')
 case=p['cases'][4];values=d.feeds(case['inputIds'],{},cfg)
 d.save(root/'output-equivalence-protocol.json',{'plan':d.entry(plan_path),'caseIndex':4,'inputArrays':{k:e.array_identity(v) for k,v in values.items()},
  'settings':p['settings'],'sources':proto['sourceGraphs'],'code':d.entry(__file__),'method':'CPU original graph full prefill vs last-output Gather graph; compare last logits numerically and all KV output byte hashes; a different MatMul shape can change rounding'})
 results={}
 for kind in ('base','trained'):
  rows=[];last_logits=[]
  for source in (next(x['path'] for x in proto['sourceGraphs'] if '/'+kind+'/' in x['path']),str(root/kind/'webgpu/onnx/model_q4f16.onnx')):
   sess=d.session(source,True);out=dict(zip([o.name for o in sess.get_outputs()],sess.run(None,values)))
   last_logits.append(out['logits'][:,-1:,:].copy())
   rows.append({k:e.array_identity(v[:,-1:,:] if k=='logits' else v) for k,v in out.items()})
   if not np.isfinite(out['logits']).all():raise ValueError('nonfinite CPU reference')
   del out,sess;gc.collect()
  results[kind]={'all57ExactlyEqual':rows[0]==rows[1],'cacheExactlyEqual':{k:v for k,v in rows[0].items() if k!='logits'}=={k:v for k,v in rows[1].items() if k!='logits'},'logits':e.compare_diagnostic('logits',*last_logits),'reference':rows[0],'candidate':rows[1]}
  print('OUTPUT_EQUIVALENCE',kind,results[kind]['all57ExactlyEqual'],flush=True)
 d.save(root/'output-equivalence.json',{'cases':[4],'results':results,'qualification':'conversion_unqualified','worldWriteAllowed':False})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('operation',choices=['create','verify']);p.add_argument('plan',type=Path);p.add_argument('--run-id');a=p.parse_args()
 create(a.plan,a.run_id) if a.operation=='create' else verify_long(a.plan)
