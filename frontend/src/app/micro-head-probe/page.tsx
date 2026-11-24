'use client';

/** Browser latency probe for the trained task heads (int8, ORT-WASM). */
import { useEffect } from 'react';
import { createBertTokenizer } from '@/lib/world-engine/local/micro/tokenizer';
import { createMicroRuntime } from '@/lib/world-engine/local/micro/runtime';

const ACT = ['act', 'skip'];
const RESULT = ['achieved', 'partial', 'not_achieved', 'blocked', 'no_change'];

export default function MicroHeadProbePage() {
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result: Record<string, unknown> = { ok: false };
      try {
        const ort = await import('onnxruntime-web/wasm');
        const tokenizer = createBertTokenizer(await (await fetch('/micro/minirbt-vocab.txt')).text());
        const runtime = createMicroRuntime({ threads: 1 });
        const heads = await runtime.load('/micro/task-heads-int8.onnx');
        const move = await runtime.load('/micro/movement-head-int8.onnx');
        const samples = await (await fetch('/micro/head-samples.json')).json() as Array<{ kind: string; input: string; label: string }>;
        const run = async (session: typeof heads, ids: number[]) => {
          const data = BigInt64Array.from(ids, (value) => BigInt(value));
          const mask = BigInt64Array.from(ids, () => 1n);
          const started = performance.now();
          const out = await session.run({
            input_ids: new ort.Tensor('int64', data, [1, ids.length]),
            attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
          });
          return { out, ms: Math.round((performance.now() - started) * 100) / 100 };
        };
        const rows: unknown[] = [];
        const timings: Record<string, number[]> = { act: [], result: [], move: [] };
        for (const sample of samples) {
          const ids = tokenizer.encode(sample.input, 64);
          const session = sample.kind === 'move' ? move : heads;
          const { out, ms } = await run(session, ids);
          let pred: string;
          if (sample.kind === 'move') {
            const logits = out.move?.data ?? [];
            pred = Number(logits[1] ?? 0) > Number(logits[0] ?? 0) ? '1' : '0';
          } else if (sample.kind === 'act') {
            const logits = out.act?.data ?? [];
            pred = ACT[Number(logits[1] ?? 0) > Number(logits[0] ?? 0) ? 1 : 0];
          } else {
            const logits = Array.from((out.result?.data ?? []) as Float32Array);
            pred = RESULT[logits.indexOf(Math.max(...logits))];
          }
          (timings[sample.kind] ??= []).push(ms);
          rows.push({ ...sample, pred, ms, ok: pred === sample.label });
        }
        const summary: Record<string, { n: number; ms_p50: number; ms_p95: number }> = {};
        for (const [kind, values] of Object.entries(timings)) {
          if (!values.length) continue;
          const sorted = [...values].sort((a, b) => a - b);
          summary[kind] = {
            n: values.length,
            ms_p50: sorted[Math.floor(sorted.length * 0.5)],
            ms_p95: sorted[Math.floor(sorted.length * 0.95)] ?? sorted[sorted.length - 1],
          };
        }
        result.ok = true;
        result.loadMs = Math.round(runtime.stats().loadMs);
        result.summary = summary;
        result.rows = rows;
      } catch (error) {
        result.error = String(error instanceof Error ? error.stack ?? error.message : error);
      }
      if (!cancelled) (window as unknown as { __probeResult?: unknown }).__probeResult = result;
    })();
    return () => { cancelled = true; };
  }, []);
  return <main style={{ padding: 24, fontFamily: 'monospace' }}>head probe running…</main>;
}
