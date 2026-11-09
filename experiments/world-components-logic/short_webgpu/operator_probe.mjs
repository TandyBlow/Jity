import * as ort from '/ort.mjs';
const status=document.querySelector('#status'),token=location.hash.slice(1);
async function post(path,value,binary=false){const r=await fetch(path,{method:'POST',headers:{'X-Diagnostic-Token':token},body:binary?value:JSON.stringify(value)});if(!r.ok)throw Error(await r.text());}
document.querySelector('#start').onclick=async()=>{
 document.querySelector('#start').disabled=true;
 try{
  const c=await(await fetch('/config',{headers:{'X-Diagnostic-Token':token}})).json();
  if(c.qualification!=='conversion_unqualified'||c.worldWriteAllowed!==false)throw Error('unqualified diagnostic scope required');
  const adapter=await navigator.gpu.requestAdapter({powerPreference:'high-performance'});
  if(!adapter||(adapter.info?.isFallbackAdapter??adapter.isFallbackAdapter)!==false)throw Error('hardware adapter required');
  ort.env.wasm.wasmPaths='/runtime/ort/';ort.env.wasm.numThreads=1;ort.env.webgpu.adapter=adapter;
  const proof={positiveWeightKernelCount:0,kernels:[],userAgent:navigator.userAgent,adapter:{vendor:adapter.info.vendor,architecture:adapter.info.architecture},features:[...adapter.features]};
  ort.env.webgpu.profiling={mode:'default',ondata:r=>{proof.kernels.push(r);if(r.kernelType==='MatMulNBits'&&Number(r.endTime)>Number(r.startTime))proof.positiveWeightKernelCount++;}};
  status.textContent='转换未合格：运行首层算子…';
  const session=await ort.InferenceSession.create('/probe.onnx',{executionProviders:['webgpu'],graphOptimizationLevel:'basic'}),inputs={};
  for(const [k,v]of Object.entries(c.inputs))inputs[k]=new ort.Tensor(v.dtype==='int64'?'int64':'float32',v.dtype==='int64'?BigInt64Array.from(v.data,BigInt):Float32Array.from(v.data),v.shape);
  const out=await session.run(inputs);
  for(let i=0;i<c.outputs.length;i++){
   const v=out[c.outputs[i].name];let data=await v.getData();
   if(c.outputs[i].takeLastToken)data=data.slice(data.length-c.outputs[i].shape.at(-1));
   if(!c.outputs[i].takeLastToken&&JSON.stringify(v.dims)!==JSON.stringify(c.outputs[i].shape))throw Error('shape mismatch');
   await post('/output/'+i,new Uint8Array(data.buffer,data.byteOffset,data.byteLength),true);
   status.textContent=`转换未合格：已保存 ${i+1}/${c.outputs.length} 个算子结果`;
  }
  await ort.env.webgpu.device.queue.onSubmittedWorkDone();
  await post('/complete',proof);await session.release();status.textContent='首层算子对照已保存；仍为转换未合格，未写入世界。';
 }catch(e){status.textContent=String(e.stack||e);await post('/failed',{error:String(e.stack||e)}).catch(()=>{});}
};
