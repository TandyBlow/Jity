"""Supplemental frozen probe: derived masks and first RMSNorm arithmetic.

Uses the completed conversion graph and the exact recorded external input arrays.
Does not change conversion recipes, thresholds, predictions, or qualification.
"""
import argparse,json
from pathlib import Path
import numpy as np
import torch,onnx
from transformers import AutoModelForCausalLM
import short_qwen_diagnostic as d
import short_qwen_export as e


def probe(plan_path,kind,scenarios=None):
 plan=d.verify(plan_path);root=Path(plan_path).parent;dest=root/kind/'controls';dest.mkdir(exist_ok=False)
 torch.set_num_threads(1)
 source=plan['model']['sourceModel' if kind=='base' else 'merged']['directory']
 scenarios=scenarios or ['old_export_r4','historical_random','full_prefill','shared_cache_decode']
 input_paths={s:root/kind/'trace'/(s+'.inputs.npz') for s in scenarios}
 input_paths['old_export_r4']=e.LOCAL/'exports/qwen-short-time-export-20261109-r4/strict-float-validation.inputs.npz'
 protocol={'plan':d.entry(plan_path),'code':d.entry(__file__),'kind':kind,'scenarios':scenarios,
  'settings':{'atol':1e-4,'rtol':1e-5,'dtype':'float32','device':'cpu','attention':'eager'},
  'inputs':[{'scenario':s,**d.entry(input_paths[s])} for s in scenarios],
  'method':'native vs export-patched derived mask/rotary fingerprints; first norm decomposition on identical embedding input',
  'worldWriteAllowed':False,'qualification':'conversion_unqualified'}
 d.save(dest/'protocol.json',protocol)
 model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,torch_dtype=torch.float32,attn_implementation='eager').eval()
 config=e.qwen_onnx_config(model,e.CONFIG['task'])
 source_graph=root/kind/'float/model.onnx'
 # Reuse validated relocation for all external tensors, then append scalar ops.
 taps=e.diagnostic_graph(source_graph,dest/'norm.onnx',model.config.num_hidden_layers)
 graph=onnx.load(dest/'norm.onnx',load_external_data=False)
 existing={o.name for o in graph.graph.output};operators=[]
 for n in graph.graph.node:
  if n.name.startswith('/model/layers.0/input_layernorm/') and n.op_type in ('Pow','ReduceMean','Add','Sqrt','Div','Mul','Cast'):
   operators.append({'name':n.name,'op':n.op_type,'output':n.output[0]})
   if n.output[0] not in existing:graph.graph.output.append(onnx.helper.make_tensor_value_info(n.output[0],onnx.TensorProto.FLOAT,[None,None,None]))
 nodes={n.name:n for n in graph.graph.node}
 control_outputs={'causalMask':nodes['/model/layers.0/self_attn/Add_2'].input[1],
                  'rotaryCos':nodes['/model/rotary_emb/Mul_1'].output[0],
                  'rotarySin':nodes['/model/rotary_emb/Mul_2'].output[0]}
 for name,value in control_outputs.items():
  graph.graph.output.append(onnx.helper.make_tensor_value_info(value,onnx.TensorProto.FLOAT,[None]*(4 if name=='causalMask' else 3)))
 onnx.save_model(graph,dest/'norm.onnx');ort=d.session(dest/'norm.onnx')
 for scenario in scenarios:
  values=dict(np.load(input_paths[scenario]))
  masks={};first={};handles=[]
  def hook(module,args,kwargs):
   name=module.layer_idx
   masks[str(name)]={k:e.array_identity(v.detach().cpu().numpy()) for k,v in kwargs.items() if k in ('attention_mask','position_ids','cache_position') and isinstance(v,torch.Tensor)}
   if 'position_embeddings' in kwargs:masks[str(name)]['rotary']=[e.array_identity(v.detach().cpu().numpy()) for v in kwargs['position_embeddings']]
   if name==0:
    first['causalMask']=kwargs['attention_mask'].detach().cpu().numpy().copy()
    first['rotaryCos'],first['rotarySin']=[v.detach().cpu().numpy().copy() for v in kwargs['position_embeddings']]
  for layer in model.model.layers:handles.append(layer.self_attn.register_forward_pre_hook(hook,with_kwargs=True))
  def norm_hook(module,args):first['input']=args[0].detach().clone()
  handles.append(model.model.layers[0].input_layernorm.register_forward_pre_hook(norm_hook))
  try:
   if scenario=='old_export_r4':
    tap_handles,old_layers=e.capture_modules(model,taps)
    try:old_reference=d.torch_forward(model,values,full=True)
    finally:
     for h in tap_handles:h.remove()
   else:d.torch_forward(model,values)
   native=json.loads(json.dumps(masks));native_controls={k:first[k] for k in control_outputs}
   with config.patch_model_for_export(model):d.torch_forward(model,values,patched=True)
   patched=json.loads(json.dumps(masks));x=first['input'];w=model.model.layers[0].input_layernorm.weight
  finally:
   for h in handles:h.remove()
  # Only fetch norm nodes, not full logits or all layer activations.
  fetches=[o['output'] for o in operators]+list(control_outputs.values())
  if scenario=='old_export_r4':fetches=list(dict.fromkeys(fetches+[t['output'] for t in taps]+list(old_reference)))
  outs=dict(zip(fetches,ort.run(fetches,values)))
  controls=[e.compare_diagnostic(k,native_controls[k],outs[v]) for k,v in control_outputs.items()]
  variance=x.pow(2).mean(-1,keepdim=True);added=variance+model.config.rms_norm_eps;sqrt=torch.sqrt(added);recip=1/sqrt
  manual={'Cast':x,'Pow':x.pow(2),'ReduceMean':variance,'Add':added,'Sqrt':sqrt,'Div':recip,
          'Mul':x*recip,'Cast_1':x*recip,'Mul_1':w*(x*recip)}
  checks=[e.compare_diagnostic(o['name'],manual[o['name'].rsplit('/',1)[1]].detach().numpy(),outs[o['output']]) for o in operators]
  native_norm=w*(x*torch.rsqrt(added));alternative=w*(x*recip)
  result={'scenario':scenario,'nativeDerivedInputs':native,'patchedDerivedInputs':patched,'derivedInputsExactlyEqual':native==patched,
          'actualOnnxDerivedInputs':controls,'arithmetic':checks,'rsqrtVsReciprocalSqrt':e.compare_diagnostic('norm',native_norm.detach().numpy(),alternative.detach().numpy()),
          'firstNonzeroArithmetic':next((c['name'] for c in checks if c['maxAbsError']),None),
          'interpretation':'identifies observed arithmetic boundaries; does not prove every later error has this sole cause',
          'qualification':'conversion_unqualified','worldWriteAllowed':False}
  if scenario=='old_export_r4':
   result['layers']=[e.compare_diagnostic(t['module'],old_layers[t['module']],outs[t['output']]) for t in taps]
   result['outputs']=[e.compare_diagnostic(k,v,outs[k]) for k,v in old_reference.items()]
   result['firstToleranceBreach']=next((c['name'] for c in result['layers'] if not c['valuesClose']),None)
   result['inputArrays']={k:e.array_identity(v) for k,v in values.items()}
  d.save(dest/(scenario+'.json'),result);print(kind,scenario,'masks',native==patched,'first',result['firstNonzeroArithmetic'],flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('plan',type=Path);p.add_argument('--kind',choices=['base','trained'],required=True);p.add_argument('--scenario',action='append',choices=['old_export_r4','historical_random','full_prefill','shared_cache_decode']);a=p.parse_args();probe(a.plan,a.kind,a.scenario)
