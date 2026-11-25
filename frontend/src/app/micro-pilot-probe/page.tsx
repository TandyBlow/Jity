'use client';

/** Browser latency probe for the two pilot heads (act/skip, appearance). */
import { useEffect } from 'react';
import { createBertTokenizer } from '@/lib/world-engine/local/micro/tokenizer';
import { createMicroRuntime } from '@/lib/world-engine/local/micro/runtime';

export default function MicroPilotProbePage() {
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result: Record<string, unknown> = { ok: false };
      try {
        const ort = await import('onnxruntime-web/wasm');
        const tokenizer = createBertTokenizer(await (await fetch('/micro/minirbt-vocab.txt')).text());
        const runtime = createMicroRuntime({ threads: 1 });
        const act = await runtime.load('/micro/act-skip-head-int8.onnx');
        const look = await runtime.load('/micro/appearance-head-int8.onnx');
        const samples = await (await fetch('/micro/pilot-samples.json')).json() as Array<{ kind: string; input: string; label: string }>;
        const rows: unknown[] = [];
        const timings: Record<string, number[]> = { act: [], appearance: [] };
        for (const sample of samples) {
          const ids = tokenizer.encode(sample.input, 192);
          const data = BigInt64Array.from(ids, (value) => BigInt(value));
          const mask = BigInt64Array.from(ids, () => 1n);
          const started = performance.now();
          const out = await (sample.kind === 'act' ? act : look).run({
            input_ids: new ort.Tensor('int64', data, [1, ids.length]),
            attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
          });
          const ms = Math.round((performance.now() - started) * 100) / 100;
          const logits = (out.logits?.data ?? []) as Float32Array;
          const pred = sample.kind === 'act' ? (Number(logits[1] ?? 0) > Number(logits[0] ?? 0) ? 'skip' : 'act') : (Number(logits[1] ?? 0) > Number(logits[0] ?? 0) ? '1' : '0');
          (timings[sample.kind] ??= []).push(ms);
          rows.push({ ...sample, pred, ms, ok: pred === sample.label });
        }
        const summary: Record<string, { n: number; ms_p50: number; ms_p95: number; ok: number }> = {};
        for (const [kind, values] of Object.entries(timings)) {
          const sorted = [...values].sort((a, b) => a - b);
          summary[kind] = {
            n: values.length,
            ms_p50: sorted[Math.floor(sorted.length * 0.5)],
            ms_p95: sorted[Math.floor(sorted.length * 0.95)] ?? sorted[sorted.length - 1],
            ok: rows.filter((row) => (row as { kind: string; ok: boolean }).kind === kind && (row as { ok: boolean }).ok).length,
          };
        }
        result.ok = true;
        result.loadMs = Math.round(runtime.stats().loadMs);
        result.summary = summary;
        result.rows = rows;
      } catch (error) {
        result.error = String(error instanceof Error ? error.stack ?? error.message : error);
      }
      if (!cancelled) (window as unknown as { __pilotProbe?: unknown }).__pilotProbe = result;
    })();
    return () => { cancelled = true; };
  }, []);
  return <main style={{ padding: 24, fontFamily: 'monospace' }}>pilot probe running…</main>;
}
