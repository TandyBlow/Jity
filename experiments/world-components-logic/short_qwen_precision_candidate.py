"""New-identity candidate: retain original FP32 RMSNorm and rotary arithmetic.

No tolerance change or promotion. A candidate must repeat CPU/WebGPU behavior.
"""
import argparse,copy,json,shutil
from pathlib import Path
import onnx
from onnxruntime.quantization.matmul_nbits_quantizer import MatMulNBitsQuantizer
from onnxruntime.transformers.float16 import convert_float_to_float16
from onnxruntime.transformers.onnx_model import OnnxModel
import short_qwen_diagnostic as d
import short_qwen_export as e
from short_qwen_precision import convert_qwen_float16


def preserve_fp32(name):
 return any(x in name for x in ('/input_layernorm/','/post_attention_layernorm/','/q_norm/','/k_norm/','/model/norm/','/model/rotary_emb/'))


def candidate(parent_path,run_id):
 parent=d.verify(parent_path);root=Path(parent_path).parent
 plan_path=d.freeze(run_id,Path(parent['modelManifest']['path']));dest=plan_path.parent
 protocol={'schema':'jity-qwen-precision-candidate-v1','plan':d.entry(plan_path),'parent':d.entry(parent_path),'code':d.entry(__file__),
  'recipe':'same original FP32 graphs and MatMulNBits quantizer; retain FP32 for every RMSNorm and rotary node in connected precision islands with no intermediate FP16 casts; other eligible nodes FP16',
  'rationale':'observed layer 3 normalization square overflow in real WebGPU, CPU intermediate precision masks downstream effect',
  'thresholds':{'atol':1e-4,'rtol':1e-5},'qualification':'conversion_unqualified','worldWriteAllowed':False,'formalEvaluationAllowed':False,
  'precisionImplementation':d.entry(Path(__file__).parent/'short_qwen_precision.py'),
  'sources':[d.entry(root/k/'float/model.onnx') for k in ('base','trained')]}
 d.save(dest/'precision-protocol.json',protocol);shutil.copyfile(__file__,dest/'precision-candidate.py');shutil.copyfile(Path(__file__).parent/'short_qwen_precision.py',dest/'short_qwen_precision.py')
 for kind in ('base','trained'):
  target=dest/kind;target.mkdir();shutil.copytree(root/kind/'float',target/'float',copy_function=lambda a,b:Path(b).hardlink_to(a))
  packaged=target/'webgpu';(packaged/'onnx').mkdir(parents=True)
  for f in (root/kind/'webgpu').iterdir():
   if f.is_file():shutil.copyfile(f,packaged/f.name)
  model=onnx.load(target/'float/model.onnx');q=MatMulNBitsQuantizer(model,block_size=e.CONFIG['blockSize'],is_symmetric=e.CONFIG['symmetric'],op_types_to_quantize=('MatMul',));q.process()
  blocked=[n.name for n in q.model.model.graph.node if preserve_fp32(n.name)]
  model,precision=convert_qwen_float16(q.model.model,keep_io_types=True)
  OnnxModel(model).topological_sort();onnx.checker.check_model(model)
  graph=packaged/'onnx/model_q4f16.onnx';onnx.save_model(model,graph)
  validated=d.session(graph,True);del validated
  # Keep the same external FP32 KV contract, as in the parent candidate.
  d.save(target/'recipe.json',{'protocol':d.entry(dest/'precision-protocol.json'),'blockedNodes':blocked,'precision':precision,'graph':d.entry(graph),'qualification':'conversion_unqualified'})
  d.save(target/'assets.json',{'schema':'jity-qwen-unqualified-diagnostic-assets-v1','qualification':'conversion_unqualified','worldWriteAllowed':False,'label':'转换未合格',
    'plan':d.entry(plan_path),'precisionProtocol':d.entry(dest/'precision-protocol.json'),'kind':kind,'files':[d.entry(p) for p in sorted(target.rglob('*')) if p.is_file()]})
  print('PRECISION_CANDIDATE',kind,graph,flush=True)
 # Reuse only explicitly completed unchanged stages; no rerun claim.
 completed=[]
 for engine in ('base_fp32','base_float','merged_fp32','trained_float','adapter_bf16','merged_bf16'):
  source=root/'runs'/engine
  if source.exists() and all((source/f'{ci}.free.json').exists() for ci in range(len(parent['cases']))):
   shutil.copytree(source,dest/'runs'/engine,copy_function=lambda a,b:Path(b).hardlink_to(a));completed.append({'engine':engine,'source':str(source),'files':[d.entry(p) for p in source.glob('*') if p.is_file()]})
 d.save(dest/'inherited-unchanged-stages.json',{'parent':d.entry(parent_path),'stages':completed,'casesEqual':parent['cases']==d.read(plan_path)['cases'],'settingsEqual':parent['settings']==d.read(plan_path)['settings']})
 for name in ('ort.mjs','ort-build.json'):
  if (root/name).exists():shutil.copyfile(root/name,dest/name)
 print('PLAN',plan_path,flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('parent',type=Path);p.add_argument('--run-id',required=True);a=p.parse_args();candidate(a.parent,a.run_id)
