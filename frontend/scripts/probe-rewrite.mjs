import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
const require = createRequire(resolve('package.json'));
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
const { chromium } = require('@playwright/test');
const server = await createServer({ root: process.cwd(), configFile:false, logLevel:'warn', server:{host:'127.0.0.1',port:0}, plugins:[{name:'p',configureServer(v){v.middlewares.use((req,res,next)=>{if(req.url!=='/__r')return next();res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>r</title>');});}}]});
await server.listen();
const browser = await chromium.launch({headless:true,channel:'msedge',args:['--enable-unsafe-webgpu']});
const page = await browser.newPage();
await page.goto(`http://127.0.0.1:${server.config.server.port}/__r`);
const out = await page.evaluate(async () => {
  const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
  const e = new WllamaInferenceEngine({modelUrl:'/models/qwen25-0.5b-narration-Q4_K_M.gguf',contextSize:2048,nGpuLayers:99999});
  await e.load();
  const prompts = [
    '把下面这句话改写成小说里的一个动作句。只允许出现句中已有的人物、地点和方向，不能新增人物、物品、动作、声音、时间或心理判断。写 20 到 50 个字。\n句子：路明非从西侧服务巷走到西回廊。\n改写：',
    '用小说笔法写一句场景。事实只有：路明非从西侧服务巷走到西回廊。不能写其他人物、物品、事件、声音、时间或心理。20 到 50 字。\n正文：',
  ];
  const res=[];
  for (const p of prompts) {
    const t=performance.now(); const text=await e.complete(p,{maxTokens:160,temperature:0.6,timeoutMs:120000});
    res.push({ms:performance.now()-t,text});
  }
  await e.dispose(); return res;
});
console.log(JSON.stringify(out,null,2));
await browser.close(); await server.close();
