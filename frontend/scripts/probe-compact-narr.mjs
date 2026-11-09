import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
const require = createRequire(resolve('package.json'));
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
const { chromium } = require('@playwright/test');
const model = process.argv[2] ?? '/models/qwen2.5-1.5b-instruct-q4_k_m.gguf';
const server = await createServer({ root: process.cwd(), configFile:false, logLevel:'warn', server:{host:'127.0.0.1',port:0}, plugins:[{name:'p',configureServer(v){v.middlewares.use((req,res,next)=>{if(req.url!=='/__c')return next();res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>c</title>');});}}]});
await server.listen();
const browser = await chromium.launch({headless:true,channel:'msedge',args:['--enable-unsafe-webgpu']});
const page = await browser.newPage();
await page.goto(`http://127.0.0.1:${server.config.server.port}/__c`);
const out = await page.evaluate(async ({model}) => {
  const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
  const e = new WllamaInferenceEngine({modelUrl:model,contextSize:4096,nGpuLayers:99999});
  await e.load();
  const prompt = [
    '你是中文小说叙事者。根据下面已经结算的事实，写 300 到 400 字正文。',
    '规则：只写事实；可以写环境、动作、对白、心理，但不得新增人物、地点、物品、往事、数字或事件；不要写字段名、状态清单或标题；视角贴着路明非。',
    '事实：',
    '- 路明非从西侧服务巷走到西回廊。',
    '- 西回廊里只有林亦舟，他站在第三根廊柱旁。',
    '- 时间过去一分钟，没有别的事发生。',
    '示例（只学句子长短和分段，不要抄人物或事件）：',
    '门开了一条缝。风从走廊那头灌进来，吹得纸页轻轻翻动。',
    '「你来了。」他说。',
    '「嗯。」她把伞收起来，靠在墙边，没有马上坐下。',
    '两个人都没有再说话。远处有人关窗，声音很轻。',
    '正文：',
  ].join('\n');
  const t=performance.now(); let first=null; let raw='';
  const text=await e.complete(prompt,{maxTokens:700,temperature:0.65,timeoutMs:180000,onProgress:(p)=>{if(first===null&&p.raw.length)first=performance.now()-t;raw=p.raw;}});
  await e.dispose(); return {load:'',ms:performance.now()-t,first,text};
}, {model});
console.log(JSON.stringify({ms:out.ms,first:out.first,chars:out.text.length},null,2));
console.log(out.text);
await browser.close(); await server.close();
