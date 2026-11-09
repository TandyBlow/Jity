import * as ort from '/ort.mjs';
import {runtimeDeviceBinding} from './core.mjs';
const status=document.querySelector('#status'),button=document.querySelector('#start');
const token=location.hash.slice(1);
async function post(path,value,binary=false){
  const r=await fetch(path,{method:'POST',headers:{'X-Diagnostic-Token':token,'Content-Type':binary?'application/octet-stream':'application/json'},body:binary?value:JSON.stringify(value)});
  if(!r.ok)throw Error(await r.text());
}
async function hash(data){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',data))].map(x=>x.toString(16).padStart(2,'0')).join('');}
async function ident(t){const d=await t.getData();return {shape:t.dims,dtype:t.type,sha256:await hash(new Uint8Array(d.buffer,d.byteOffset,d.byteLength))};}
function argmax(x){let best=0;for(let i=1;i<x.length;i++)if(x[i]>x[best])best=i;return best;}
button.onclick=async()=>{
 button.disabled=true;
 try{
  const response=await fetch('/config',{headers:{'X-Diagnostic-Token':token}});if(!response.ok)throw Error('configuration refused');
  const config=await response.json(),cfg=config.modelConfig;
  if(config.qualification!=='conversion_unqualified'||config.worldWriteAllowed!==false)throw Error('diagnostic scope required');
  status.textContent='转换未合格：核对分词并加载独立模型…';
  const {AutoTokenizer,env}=await import('/runtime/transformers.web.min.js');
  env.allowRemoteModels=false;env.allowLocalModels=true;env.localModelPath='/model/';env.useBrowserCache=false;
  const tokenizer=await AutoTokenizer.from_pretrained('qwen',{local_files_only:true});
  for(const row of config.cases){
   const ids=tokenizer.apply_chat_template(row.packet.messages,{tokenize:true,add_generation_prompt:true,enable_thinking:false});
   const actual=Array.isArray(ids)?ids:ids.tolist()[0].map(Number);
   if(JSON.stringify(actual.map(Number))!==JSON.stringify(row.inputIds))throw Error('tokenizer mismatch:'+row.caseId);
  }
  const adapter=await navigator.gpu?.requestAdapter({powerPreference:'high-performance'});
  if(!adapter||!(adapter.info?.isFallbackAdapter===false||adapter.isFallbackAdapter===false))throw Error('hardware adapter required');
  for(const feature of ['shader-f16','timestamp-query'])if(!adapter.features.has(feature))throw Error('missing '+feature);
  ort.env.wasm.wasmPaths='/runtime/ort/';ort.env.wasm.numThreads=1;ort.env.webgpu.adapter=adapter;
  let proof=null;
  ort.env.webgpu.profiling={mode:'default',ondata:row=>{
    if(!proof)return;proof.kernelCount++;
    if(row.kernelType==='MatMulNBits'&&Number(row.endTime)>Number(row.startTime)){
      proof.positiveWeightKernelCount++;if(proof.witnesses.length<16)proof.witnesses.push(row);
    }
  }};
  const session=await ort.InferenceSession.create('/model/qwen/onnx/model_q4f16.onnx',{
    executionProviders:['webgpu'],graphOptimizationLevel:'basic',extra:{session:{disable_cpu_ep_fallback:'0'}}});
  const runtime=await runtimeDeviceBinding(ort.env.webgpu,adapter,['shader-f16','timestamp-query']);
  const device={...runtime.evidence,features:[...runtime.device.features],userAgent:navigator.userAgent,deviceSessionId:crypto.randomUUID()};
  let lost=false;runtime.device.lost.then(()=>lost=true);
  await post('/event',{kind:'loaded',device,modelSha256:config.modelSha256,planSha256:config.planSha256});
  for(let ci=0;ci<config.cases.length;ci++)for(const mode of ['fixed','free']){
   const row=config.cases[ci],start=performance.now();let cache={},past=0,ids=row.inputIds,tokens=[],steps=[];
   proof={kernelCount:0,positiveWeightKernelCount:0,witnesses:[],CPU:'unknown',placement:'webgpu_preferred_cpu_nodes_allowed'};
   const limit=mode==='fixed'?row.fixedTokenIds.length+1:config.settings.maxNewTokens;
   for(let step=0;step<limit;step++){
    if(lost)throw Error('GPU device lost');
    const tensor=(xs)=>new ort.Tensor('int64',BigInt64Array.from(xs,BigInt),[1,xs.length]);
    const inputs={input_ids:tensor(ids),attention_mask:tensor(Array(past+ids.length).fill(1)),position_ids:tensor(ids.map((_,i)=>past+i))};
    for(let i=0;i<cfg.num_hidden_layers;i++)for(const kind of ['key','value']){
      const name=`past_key_values.${i}.${kind}`;inputs[name]=cache[name]??new ort.Tensor('float32',new Float32Array(0),[1,cfg.num_key_value_heads,0,cfg.head_dim]);
    }
    const inputIdentity={};for(const [k,v]of Object.entries(inputs))inputIdentity[k]=await ident(v);
    const outputs=await session.run(inputs);await runtime.device.queue.onSubmittedWorkDone();
    const data=await outputs.logits.getData();const last=Float32Array.from(data.slice(data.length-cfg.vocab_size));const chosen=argmax(last);
    if(mode==='fixed')await post(`/logits/${ci}/${step}`,last.buffer,true);
    steps.push({step,phase:step===0?'prefill':'decode',top1:chosen,inputs:inputIdentity,logitsSha256:await hash(last.buffer)});
    for(const v of Object.values(inputs))v.dispose();
    cache={};for(const [k,v]of Object.entries(outputs)){if(k.startsWith('present.'))cache[k.replace('present.','past_key_values.')]=v;else v.dispose();}
    past+=ids.length;
    if(mode==='fixed'&&step===limit-1)break;
    const next=mode==='fixed'?row.fixedTokenIds[step]:chosen;tokens.push(next);ids=[next];
    status.textContent=`转换未合格 · ${ci+1}/${config.cases.length} · ${mode} · ${step+1} 步\n${tokenizer.decode(tokens,{skip_special_tokens:true})}`;
    if(mode==='free'&&config.generation.eosTokenIds.includes(next))break;
    if(performance.now()-start>600000)throw Error('diagnostic case deadline');
   }
   await runtime.device.queue.onSubmittedWorkDone();
   for(const v of Object.values(cache))v.dispose();
   if(!proof.positiveWeightKernelCount)throw Error('no actual GPU weight kernel evidence');
   const result={caseIndex:ci,mode,planSha256:config.planSha256,modelSha256:config.modelSha256,inputIds:row.inputIds,
    rawTokenIds:tokens,rawText:tokenizer.decode(tokens,{skip_special_tokens:true}),eosReached:config.generation.eosTokenIds.includes(tokens.at(-1)),
    steps,gpuEvidence:proof,device,elapsedSeconds:(performance.now()-start)/1000,qualification:'conversion_unqualified',worldWriteAllowed:false};
   await post('/result',result);proof=null;
  }
  await session.release();await post('/event',{kind:'complete'});
  status.textContent='隔离 WebGPU 对照已完成。全部原始输出和数值已保存。\n仍为「转换未合格」，待逐项比较和语义审查；未写入世界。';
 }catch(e){status.textContent='诊断失败（不准入）：'+String(e.stack||e);await post('/event',{kind:'failed',error:String(e.stack||e)}).catch(()=>{});}
};
