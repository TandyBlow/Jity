"""Explicitly unqualified, loopback-only first-block CPU/WebGPU operator probe."""
import argparse,copy,json,secrets,threading
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import numpy as np,onnx
import short_qwen_diagnostic as d
import short_qwen_export as e


def prepare(plan_path,dest,scope,case_index=0):
 plan=d.verify(plan_path);root=Path(plan_path).parent;dest.mkdir(exist_ok=False)
 graph=root/'trained/webgpu/onnx/model_q4f16.onnx';model=onnx.load(graph)
 types={v.name:v.type.tensor_type.elem_type for v in list(model.graph.value_info)+list(model.graph.output)}
 selected=[]
 for n in model.graph.node:
  if (n.name=='/model/embed_tokens/Gather' or n.name in ('/model/rotary_emb/Mul_1','/model/rotary_emb/Mul_2') or
      (n.name.startswith('/model/layers.0/') and (any(x in n.name for x in ('layernorm/','q_norm/','k_norm/','_proj/','mlp/')) and n.op_type in ('Pow','ReduceMean','Add','Sqrt','Div','Mul','MatMulNBits','Sigmoid') or n.name in ['/model/layers.0/self_attn/'+x for x in ('Mul','Mul_1','Mul_2','Mul_3','Add','Add_1','MatMul','Mul_8','Add_2','Softmax','MatMul_1')] or n.name in ('/model/layers.0/Add','/model/layers.0/Add_1')))):
   selected.append(n.output[0])
 if scope in ('all','scalars'):
  selected=[]
  for n in model.graph.node:
   if (n.name=='/model/embed_tokens/Gather' or n.name.startswith('/model/norm/') and n.op_type in ('Pow','ReduceMean','Sqrt','Div','Mul') or
       n.name.startswith('/model/layers.') and (n.name.rsplit('/',1)[-1] in ('Add','Add_1') and n.name.count('/')==3 or
       any(x in n.name for x in ('layernorm/','q_norm/','k_norm/')) and n.op_type in ('Pow','ReduceMean','Sqrt','Div','Mul') or
       n.name.endswith(('/o_proj/MatMul_Q4','/down_proj/MatMul_Q4')))):
    selected.append(n.output[0])
  if scope=='all':selected.append('logits')
  else:
   selected=[n.output[0] for n in model.graph.node if (n.name.startswith('/model/layers.') and (n.name.count('/')==3 and n.op_type=='Add' or any(x in n.name for x in ('layernorm/','q_norm/','k_norm/')) and n.op_type=='ReduceMean')) or n.name=='/model/norm/Mul_1']
   observed=list(dict.fromkeys(selected));selected=[];observers={};original_nodes=list(model.graph.node)
   for i,name in enumerate(observed):
    f=f'probe_float_{i}';a=f'probe_abs_{i}';mx=f'probe_max_{i}';sm=f'probe_sum_{i}'
    observers[name]=[onnx.helper.make_node('Cast',[name],[f],name=f,to=onnx.TensorProto.FLOAT),onnx.helper.make_node('Abs',[f],[a],name=a),onnx.helper.make_node('ReduceMax',[a],[mx],name=mx,keepdims=0),onnx.helper.make_node('ReduceSum',[f],[sm],name=sm,keepdims=0)]
    selected.extend([mx,sm]);types[mx]=types[sm]=onnx.TensorProto.FLOAT
   ordered=[]
   for node in original_nodes:
    ordered.append(node)
    for name in node.output:ordered.extend(observers.get(name,[]))
   del model.graph.node[:];model.graph.node.extend(ordered)
 # Backward slice preserves original operators, constants and weights exactly.
 required=set(selected);nodes=[]
 for n in reversed(model.graph.node):
  if any(x in required for x in n.output):nodes.append(n);required.update(n.input)
 nodes.reverse();del model.graph.node[:];model.graph.node.extend(nodes)
 initial=[v for v in model.graph.initializer if v.name in required];del model.graph.initializer[:];model.graph.initializer.extend(initial)
 inputs=[v for v in model.graph.input if v.name in required];del model.graph.input[:];model.graph.input.extend(inputs)
 del model.graph.output[:];del model.graph.value_info[:]
 for name in selected:model.graph.output.append(onnx.helper.make_tensor_value_info(name,types.get(name,onnx.TensorProto.FLOAT if name=='logits' else onnx.TensorProto.FLOAT16),None))
 onnx.save_model(model,dest/'probe.onnx')
 cfg=d.read(Path(plan['model']['merged']['directory'])/'config.json')
 values=d.feeds(plan['cases'][case_index]['inputIds'],{},cfg);values={v.name:values[v.name] for v in inputs}
 np.savez(dest/'inputs.npz',**values)
 sess=d.session(dest/'probe.onnx',True);outputs=dict(zip(selected,sess.run(None,values)))

 if 'logits' in outputs:outputs['logits']=outputs['logits'][:,-1:,:].copy()
 np.savez(dest/'cpu.npz',**outputs)
 config={'qualification':'conversion_unqualified','worldWriteAllowed':False,'source':d.entry(graph),'plan':d.entry(plan_path),
   'graph':d.entry(dest/'probe.onnx'),'pythonCode':d.entry(__file__),'javascriptCode':d.entry(Path(__file__).parent/'short_webgpu/operator_probe.mjs'),
   'note':'first-block backward slice; exposed outputs can affect runtime optimization, not a qualification run',
   'inputs':{k:{**e.array_identity(v),'data':v.reshape(-1).tolist()} for k,v in values.items()},
   'scope':scope,'caseIndex':case_index,'observedOutputs':observed if scope=='scalars' else [],'outputs':[{**e.array_identity(v),'name':k,'takeLastToken':k=='logits'} for k,v in outputs.items()]}
 d.save(dest/'config.json',config);print('PREPARED',dest,flush=True)


def serve(dest):
 config=d.read(dest/'config.json');d.check(config['graph']);d.check(config['pythonCode']);d.check(config['javascriptCode'])
 root=Path(config['plan']['path']).parent;runtime=Path.home()/'.cache/jity-d-short-semantics-20261109/webgpu/runtime-r2/served'
 paths={'/probe.onnx':dest/'probe.onnx','/ort.mjs':root/'ort.mjs','/probe.mjs':Path(__file__).parent/'short_webgpu/operator_probe.mjs'}
 for f in (runtime/'ort').glob('*'):
  if f.is_file():paths['/runtime/ort/'+f.name]=f
 token=secrets.token_urlsafe(32);finished=threading.Event();cpu=np.load(dest/'cpu.npz');received={}
 html='<meta charset="utf-8"><h1>转换未合格 · 首层算子定位</h1><p>原始权重只用于隔离诊断，不准入、不写入世界。</p><button id="start">开始首层 CPU / WebGPU 对照</button><pre id="status">等待运行</pre><script type="module" src="/probe.mjs"></script>'
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def reply(self,status,data,kind='application/json'):
   self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
  def authorized(self):return self.headers.get('X-Diagnostic-Token')==token and self.headers.get('Origin',f'http://127.0.0.1:{self.server.server_port}')==f'http://127.0.0.1:{self.server.server_port}'
  def do_GET(self):
   if self.path=='/':return self.reply(200,html.encode(),'text/html; charset=utf-8')
   if self.path=='/config':return self.reply(200,json.dumps(config).encode()) if self.authorized() else self.reply(403,b'{}')
   if self.path not in paths:return self.reply(404,b'{}')
   p=paths[self.path];return self.reply(200,p.read_bytes(),{'.mjs':'text/javascript','.wasm':'application/wasm'}.get(p.suffix,'application/octet-stream'))
  def do_POST(self):
   if not self.authorized():return self.reply(403,b'{}')
   try:
    size=int(self.headers['Content-Length']);assert 0<size<=32*1024*1024
    raw=self.rfile.read(size)
    if self.path.startswith('/output/'):
     i=int(self.path.split('/')[-1]);meta=config['outputs'][i];assert i not in received
     v=np.frombuffer(raw,dtype=meta['dtype']).copy().reshape(meta['shape']);np.save(dest/f'gpu-{i}.npy',v)
     received[i]=e.compare_diagnostic(meta['name'],cpu[meta['name']],v)
    elif self.path=='/complete':
     proof=json.loads(raw);assert len(received)==len(config['outputs']) and proof['positiveWeightKernelCount']>0
     d.save(dest/'comparison.json',{'outputs':[received[i] for i in sorted(received)],'gpuEvidence':proof,'qualification':'conversion_unqualified','worldWriteAllowed':False})
     finished.set()
    elif self.path=='/failed':d.save(dest/'failed.json',json.loads(raw));finished.set()
    else:raise ValueError('unknown route')
    self.reply(200,b'{}')
   except Exception as error:self.reply(400,json.dumps({'error':str(error)}).encode())
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 print(f'PROBE_URL=http://127.0.0.1:{server.server_port}/#{token}',flush=True)
 finished.wait(600);server.shutdown();server.server_close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('operation',choices=['prepare','serve']);p.add_argument('directory',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--scope',choices=['first','all','scalars'],default='first');p.add_argument('--case-index',type=int,default=0);a=p.parse_args()
 if a.operation=='prepare':prepare(a.plan,a.directory,a.scope,a.case_index)
 else:serve(a.directory)
