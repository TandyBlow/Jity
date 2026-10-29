// N2 selection arm M2: Qwen3-0.6B Q4_K_M through real Edge + wllama (CPU),
// the same runtime the B-side baseline uses. Offline (no backend, no page
// app code): a bare page imports /wllama/index.min.js directly, exactly the
// narration-sample harness shape.
//
// Task prompt = N2 variant "c": system instructions + numbered fact table +
// viewpoint rule; answer is a comma-separated id list. Raw text is stored
// verbatim; judging happens in python (judge_qwen.py) with the SAME judge as
// the other arms, so no score is produced here.
//
// Usage: node experiments/world-components/n2_selection/n2_qwen.mjs [--items path] [--out path]
// Output: experiments/world-components/n2_selection/qwen-raw.json

import { createServer } from 'vite';
import { chromium } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { cpus } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, '..', '..', '..');            // worktree root
const frontend = resolve(repo, '..', '..', 'frontend');  // B's frontend (assets only)
const arg = (name, fallback) => {
  const i = process.argv.indexOf(name);
  return i < 0 ? fallback : process.argv[i + 1];
};
const itemsPath = resolve(repo, arg('--items', 'experiments/world-components/n2_selection/items.jsonl'));
const outPath = resolve(repo, arg('--out', 'experiments/world-components/n2_selection/qwen-raw.json'));
const config = { model: '/models/Qwen3-0.6B-Q4_K_M.gguf', channel: 'msedge',
  contextSize: 4096, numThreads: 4, maxTokens: 24, timeoutMs: 120_000 };

const hash = (p) => createHash('sha256').update(readFileSync(p)).digest('hex');
const items = readFileSync(itemsPath, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));

function factLine(i, f) {
  const where = f.at == null ? '全局' : f.at;
  let body;
  switch (f.kind) {
    case 'moved': body = `位置：${f.name} 从${f.from}到${f.to}`; break;
    case 'task_achieved': body = `任务达成：${f.name}「${f.goal}」`; break;
    case 'personality_changed': body = `个性：${f.name}${f.text}`; break;
    case 'sanity_changed': {
      const d = f.to > f.from ? '上升' : f.to < f.from ? '下降' : '不变';
      body = `理智：${f.name} ${f.from}→${f.to}（${d}）`;
      break;
    }
    case 'appearance_changed': body = `外貌：${f.name} ${f.text}`; break;
    case 'positioned_at': body = `现状：${f.name} 已在${f.at}`; break;
    case 'time': body = `时间推进：约${f.amount}分钟`; break;
    case 'no_change': body = `无变化：${f.scope ?? f.at}`; break;
    default: throw new Error(`unknown kind ${f.kind}`);
  }
  return `${i}. [${where}] ${body}`;
}

const SYSTEM = '中文叙事编辑。给定事实表（方括号是事实发生地点）与视角人物、视角规则，只选出应当写进正文的事实编号。视角看不到的不要选。只输出编号，用逗号分隔，不要解释。';
const promptOf = (item) => {
  const v = item.viewpoint;
  const who = v.entityId ? `${v.name}（${v.entityId}）` : '全知叙述者';
  const where = v.at ?? '全局';
  return ['叙事选材任务。',
    `视角人物：${who}，当前在${where}。`,
    `视角规则：${v.rule}。`,
    '事实（方括号内是事实发生的地点）：',
    ...item.facts.map((f, i) => factLine(i + 1, f)),
    '任务：选出必须写进正文的事实编号，视角看不到的不要选。',
    '只输出编号，用逗号分隔，不要写其他文字。',
    '编号：'].join('\n');
};

const report = {
  purpose: 'N2 arm M2: Qwen3-0.6B zero-shot id selection (real Edge + wllama)',
  status: 'IN_PROGRESS', recordedAt: new Date().toISOString(), config,
  promptShape: { system: SYSTEM, answerSlot: '编号：' },
  assets: {
    modelSha256: hash(resolve(frontend, 'public', config.model.replace(/^\//, ''))),
    bundleSha256: hash(resolve(frontend, 'public/wllama/index.min.js')),
    wasmSha256: hash(resolve(frontend, 'public/wasm/wllama.wasm')),
    packageVersion: JSON.parse(readFileSync(resolve(frontend, 'node_modules/@wllama/wllama/package.json'), 'utf8')).version,
  },
  items: { file: itemsPath, sha256: hash(itemsPath), count: items.length },
  device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length },
  rows: [],
};
const save = () => {
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, JSON.stringify(report, null, 2) + '\n');
};
save();

const server = await createServer({
  root: frontend, configFile: false, logLevel: 'warn',
  cacheDir: resolve(repo, '.local/n2-qwen-vite'),
  server: { host: '127.0.0.1', port: 0, hmr: false, headers: {
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Cross-Origin-Embedder-Policy': 'require-corp',
  } },
  plugins: [{ name: 'n2-page', configureServer(vite) {
    vite.middlewares.use((req, res, next) => {
      if (req.url !== '/__n2') return next();
      res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
      res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
      res.setHeader('Content-Type', 'text/html');
      res.end('<!doctype html><title>N2 selection probe</title>');
    });
  } }],
});

let browser;
try {
  await server.listen();
  const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
  browser = await chromium.launch({ headless: true, channel: config.channel });
  report.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (e) => console.error('[pageerror]', e.message));
  await page.goto(`${origin}/__n2`);
  const load = await page.evaluate(async ({ modelUrl, ctx, threads }) => {
    if (!crossOriginIsolated) throw new Error('page must be cross-origin isolated');
    const { Wllama } = await import('/wllama/index.min.js');
    const instance = new Wllama({ default: '/wasm/wllama.wasm' },
      { logger: { ...console, debug: () => undefined } });
    const t0 = performance.now();
    await instance.loadModelFromUrl(modelUrl, { useCache: false, n_ctx: ctx,
      n_batch: 512, n_ubatch: 128, n_gpu_layers: 0, warmup: false, n_threads: threads });
    window.__n2 = instance;
    return { loadMs: Math.round(performance.now() - t0) };
  }, { modelUrl: `${origin}${config.model}`, ctx: config.contextSize, threads: config.numThreads });
  report.load = load;
  save();
  console.log(`[n2-qwen] loaded in ${load.loadMs}ms`);

  for (const item of items) {
    const prompt = promptOf(item);
    const row = await page.evaluate(async ({ system, user, maxTokens, seed, ctxSize }) => {
      let watchdog;
      const run = (async () => {
        const t0 = performance.now();
        const r = await window.__n2.createChatCompletion({
          messages: [{ role: 'system', content: system }, { role: 'user', content: user }],
          max_tokens: maxTokens, temperature: 0, top_p: 1, seed,
          cache_prompt: false, chat_template_kwargs: { enable_thinking: false },
        });
        return { wallMs: Math.round(performance.now() - t0),
          text: r.choices?.[0]?.message?.content ?? '',
          finishReason: r.choices?.[0]?.finish_reason ?? null,
          promptTokens: r.usage?.prompt_tokens, completionTokens: r.usage?.completion_tokens };
      })();
      const guard = new Promise((_res, rej) => {
        watchdog = setTimeout(() => rej(new Error('watchdog')), 150_000);
      });
      try { return await Promise.race([run, guard]); }
      finally { clearTimeout(watchdog); }
    }, { system: SYSTEM, user: prompt, maxTokens: config.maxTokens, seed: 20261029, ctxSize: config.contextSize });
    report.rows.push({ itemId: item.itemId, prompt, ...row });
    save();
    console.log(`[n2-qwen] ${item.itemId} ${row.wallMs}ms -> ${JSON.stringify(row.text.slice(0, 40))}`);
  }
  report.status = 'COMPLETED';
  report.completedAt = new Date().toISOString();
  save();
  await page.evaluate(async () => { await window.__n2.exit(); });
} catch (error) {
  report.status = 'INTERRUPTED';
  report.error = String(error);
  save();
  console.error('[n2-qwen] failed:', error);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  await server.close();
}
