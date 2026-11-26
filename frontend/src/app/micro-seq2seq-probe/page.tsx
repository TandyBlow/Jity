'use client';

/** Browser token-by-token probe for the fixed 96/64 int8 seq2seq pair. */
import { useEffect } from 'react';
import { createMicroRuntime } from '@/lib/world-engine/local/micro/runtime';

const SAMPLE = '事件|角色=lu；行动=目标：我把门厅长桌拖到侧墙让出楼梯口。';
const PREFIX = 'EV|actor=lu|';
const MAX_SOURCE = 96;
const MAX_TARGET = 64;
const MAX_TOKENS = 32;

type Vocab = { itos: string[]; pad: number; bos: number; eos: number; unk: number; tokenPattern: string };

export default function MicroSeq2SeqProbePage() {
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result: Record<string, unknown> = { ok: false };
      try {
        const vocab = await (await fetch('/micro/probe-vocab.json')).json() as Vocab;
        const stoi = new Map(vocab.itos.map((token, index) => [token, index]));
        const regex = new RegExp(vocab.tokenPattern, 'g');
        const tokens = (text: string) => Array.from(text.matchAll(regex), (match) => match[0]);
        const encode = (text: string, maxLen: number) => {
          const ids = tokens(text).slice(0, maxLen - 2).map((token) => stoi.get(token) ?? vocab.unk);
          return [vocab.bos, ...ids, vocab.eos];
        };
        const ort = await import('onnxruntime-web/wasm');
        const runtime = createMicroRuntime({ threads: 1 });
        const encoder = await runtime.load('/micro/probe-encoder-int8.onnx');
        const decoder = await runtime.load('/micro/probe-decoder-int8.onnx');
        const srcIds = encode(SAMPLE, MAX_SOURCE);
        const source = new BigInt64Array(MAX_SOURCE).fill(BigInt(vocab.pad));
        srcIds.forEach((id, index) => { source[index] = BigInt(id); });
        const mask = new BigInt64Array(MAX_SOURCE);
        for (let index = 0; index < MAX_SOURCE; index += 1) mask[index] = source[index] === BigInt(vocab.pad) ? 0n : 1n;
        const srcTensor = new ort.Tensor('int64', source, [1, MAX_SOURCE]);
        const maskTensor = new ort.Tensor('int64', mask, [1, MAX_SOURCE]);
        const runOnce = async () => {
          const encodeStart = performance.now();
          const memory = (await encoder.run({ src: srcTensor })).memory;
          const encodeMs = performance.now() - encodeStart;
          const seed = tokens(PREFIX).slice(-30).map((token) => stoi.get(token) ?? vocab.unk);
          const out = [vocab.bos, ...seed];
          const tokenMs: number[] = [];
          for (let step = 0; step < MAX_TOKENS; step += 1) {
            const target = new BigInt64Array(MAX_TARGET).fill(BigInt(vocab.pad));
            out.slice(-MAX_TARGET).forEach((id, index) => { target[index] = BigInt(id); });
            const targetTensor = new ort.Tensor('int64', target, [1, MAX_TARGET]);
            const start = performance.now();
            const logits = (await decoder.run({ memory, tgt: targetTensor, src_mask: maskTensor })).logits;
            tokenMs.push(performance.now() - start);
            const data = logits.data as Float32Array;
            const width = vocab.itos.length;
            const offset = (out.length - 1) * width;
            let best = 0;
            for (let index = 1; index < width; index += 1) {
              if (data[offset + index] > data[offset + best]) best = index;
            }
            out.push(best);
            if (best === vocab.eos) break;
          }
          const continuation = out.slice(1 + seed.length)
            .filter((id) => id !== vocab.pad && id !== vocab.bos && id !== vocab.eos)
            .map((id) => vocab.itos[id]).join('');
          return { continuation, encodeMs, tokenMs };
        };
        const runs = [];
        for (let index = 0; index < 5; index += 1) {
          const start = performance.now();
          const run = await runOnce();
          runs.push({ ...run, fullMs: performance.now() - start });
        }
        const full = runs.map((run) => run.fullMs).sort((a, b) => a - b);
        const p50 = full[Math.floor(full.length * 0.5)];
        const p95 = full[Math.min(full.length - 1, Math.floor(full.length * 0.95))];
        result.ok = true;
        result.loadMs = Math.round(runtime.stats().loadMs);
        result.sampleInput = SAMPLE;
        result.samplePrefix = PREFIX;
        result.output = runs[0].continuation;
        result.tokens = runs[0].tokenMs.length;
        result.encodeMs = Math.round(runs[0].encodeMs * 100) / 100;
        result.perTokenMs = Math.round((runs[0].tokenMs.reduce((a, b) => a + b, 0) / runs[0].tokenMs.length) * 100) / 100;
        result.fullP50Ms = Math.round(p50 * 100) / 100;
        result.fullP95Ms = Math.round(p95 * 100) / 100;
        result.runs = runs.map((run) => ({ fullMs: Math.round(run.fullMs * 100) / 100, tokens: run.tokenMs.length }));
        await runtime.dispose();
      } catch (error) {
        result.error = String(error instanceof Error ? error.stack ?? error.message : error);
      }
      if (!cancelled) (window as unknown as { __probeResult?: unknown }).__probeResult = result;
    })();
    return () => { cancelled = true; };
  }, []);
  return <main style={{ padding: 24, fontFamily: 'monospace' }}>seq2seq probe running…</main>;
}
