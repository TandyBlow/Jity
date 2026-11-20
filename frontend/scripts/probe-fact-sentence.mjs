import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
const require = createRequire(resolve('package.json'));
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
const { chromium } = require('@playwright/test');
const model = process.argv[2] ?? '/models/qwen25-0.5b-narration-Q4_K_M.gguf';
const server = await createServer({ root: process.cwd(), configFile:false, logLevel:'warn', server:{host:'127.0.0.1',port:0}, plugins:[{name:'p',configureServer(v){v.middlewares.use((req,res,next)=>{if(req.url!=='/__f')return next();res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>f</title>');});}}]});
await server.listen();
const browser = await chromium.launch({headless:true,channel:'msedge',args:['--enable-unsafe-webgpu']});
const page = await browser.newPage(); await page.goto(`http://127.0.0.1:${server.config.server.port}/__f`);
const out = await page.evaluate(async ({model}) => {
  const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
  const e = new WllamaInferenceEngine({modelUrl:model,contextSize:2048,nGpuLayers:99999}); await e.load();
  const facts = [
    '路明非从西侧服务巷走到西回廊。',
    '林亦舟在西回廊，背靠第三根廊柱坐着。',
    '路明非的精神值是72。',
  ];
  const res=[];
  for (const fact of facts) {
    const prompt = `写一句中文小说里的叙述句，必须包含下面的事实，不能增加其他人物、地点、事件、声音、数字或心理判断。只输出一句话。\n事实：${fact}\n句子：`;
    const t=performance.now(); const text=await e.complete(prompt,{maxTokens:80,temperature:0.5,timeoutMs:60000});
    res.push({fact,ms:performance.now()-t,text});
  }
  await e.dispose(); return res;
}, {model});
console.log(JSON.stringify(out,null,2)); await browser.close(); await server.close();
