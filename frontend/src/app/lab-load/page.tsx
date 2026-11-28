'use client';

/** Lab-only staged load probe: page, GGUF fetch, wllama init, first inference.
 * Each stage is reported through window.__labStage so a headless runner can
 * sample memory at the exact boundary. Never linked from the product. */
import { useEffect } from 'react';

const MODEL = '/models/Qwen3-0.6B-Q4_K_M.gguf';

declare global {
  interface Window { __labStage?: string; __labTimings?: Record<string, number>; __labError?: string } }

export default function LabLoadPage() {
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const stage = q.get('stage') ?? 'page';
    const ctx = Math.min(32768, Math.max(512, Number(q.get('ctx') ?? 2048)));
    const gpuLayers = q.get('cpu') === '0' ? 99999 : 0;
    const nBatch = Number(q.get('nb') ?? 0) || undefined;
    const mark = (name: string) => {
      window.__labStage = name;
      (window.__labTimings ??= {})[name] = Math.round(performance.now());
    };
    mark('page');
    (async () => {
      try {
        if (stage === 'page') { mark('done'); return; }
        mark('fetch-start');
        const response = await fetch(MODEL, { cache: 'force-cache' });
        const blob = await response.blob();
        mark('fetched');
        if (stage === 'fetch') { mark('done'); return; }
        const { createWllama } = await import('@/lib/benchmark/wllama-loader');
        const wllama = await createWllama();
        mark('init-start');
        await wllama.loadModel([new File([blob], 'model.gguf', { type: 'application/octet-stream' })], {
          n_ctx: ctx, n_gpu_layers: gpuLayers, cache_type_k: 'q8_0', cache_type_v: 'q8_0', ...(nBatch ? { n_batch: nBatch } : {}),
        });
        mark('inited');
        if (stage === 'init') { await wllama.exit(); mark('done'); return; }
        mark('infer-start');
        await wllama.createCompletion({ prompt: '你好', max_tokens: 8 });
        mark('inferred');
        await wllama.exit();
        mark('done');
      } catch (error) {
        window.__labError = String(error);
        mark('error');
      }
    })();
  }, []);
  return (
    <main style={{ padding: 24, fontFamily: 'monospace' }}>
      <h1>lab-load probe</h1>
      <p>stage is exposed on window.__labStage</p>
    </main>
  );
}
