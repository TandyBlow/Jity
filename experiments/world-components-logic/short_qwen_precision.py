"""Preserve complete FP32 precision islands for Qwen RMSNorm and RoPE."""

def preserve_fp32(name):
 return any(x in name for x in ('/input_layernorm/','/post_attention_layernorm/','/q_norm/','/k_norm/','/model/norm/','/model/rotary_emb/'))


def convert_qwen_float16(model,keep_io_types=True):
 import onnx
 from onnxruntime.transformers.float16 import convert_float_to_float16
 from onnxruntime.transformers.onnx_model import OnnxModel
 blocked=[n.name for n in model.graph.node if preserve_fp32(n.name)]
 result=convert_float_to_float16(model,keep_io_types=keep_io_types,disable_shape_infer=False,node_block_list=blocked)
 # ORT's converter surrounds EACH blocked op with casts. Merely listing all
 # norm ops therefore still rounds/overflows between Pow and ReduceMean.
 # Reconnect only edges whose original producer and consumer are BOTH in a
 # protected FP32 island. External FP16 boundaries remain explicit casts.
 producers={v:n for n in result.graph.node for v in n.output};protected=set(blocked);rewired=[]
 def target(n):return next((a.i for a in n.attribute if a.name=='to'),None)
 for node in result.graph.node:
  if node.name not in protected:continue
  for i,value in enumerate(node.input):
   up=producers.get(value)
   if up is None or up.op_type!='Cast' or target(up)!=onnx.TensorProto.FLOAT:continue
   down=producers.get(up.input[0])
   if down is None or down.op_type!='Cast' or target(down)!=onnx.TensorProto.FLOAT16:continue
   origin=producers.get(down.input[0])
   if origin is None or origin.name not in protected:continue
   node.input[i]=down.input[0];rewired.append({'consumer':node.name,'producer':origin.name,'removedLossyEdge':[down.name,up.name]})
 OnnxModel(result).topological_sort()
 # Remove now-unused casts/constant branches; preserve every public output.
 required={o.name for o in result.graph.output};kept=[]
 for node in reversed(result.graph.node):
  if any(x in required for x in node.output):kept.append(node);required.update(node.input)
 kept.reverse();del result.graph.node[:];result.graph.node.extend(kept)
 info=[v for v in result.graph.value_info if v.name in required];del result.graph.value_info[:];result.graph.value_info.extend(info)
 onnx.checker.check_model(result)
 return result,{'protectedNodes':blocked,'preservedEdges':rewired,'fp32Islands':['RMSNorm','RoPE']}
