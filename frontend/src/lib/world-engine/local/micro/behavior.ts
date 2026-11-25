/** NPC behavior category head: one of seven routine categories, or null when
 * the model is unsure or says `other` (the LLM then writes the action). */
import { createBertTokenizer, type BertTokenizer } from './tokenizer';
import { createMicroRuntime } from './runtime';

const LABELS = ['move', 'assist', 'guard', 'communicate', 'observe', 'use', 'other'];

export interface MicroBehaviorOptions {
  vocabUrl?: string;
  modelUrl?: string;
  threshold?: number;
  onStats?: (record: { category: string; inferences?: number; ms: number; loadMs: number }) => void;
}

export function createMicroBehavior(options: MicroBehaviorOptions = {}) {
  let tokenizer: Promise<BertTokenizer> | null = null;
  const runtime = createMicroRuntime({ threads: 1 });
  async function ensure() {
    if (!tokenizer) {
      tokenizer = (async () => {
        const response = await fetch(options.vocabUrl ?? '/micro/minirbt-vocab.txt');
        if (!response.ok) throw new Error('micro_vocab_fetch_failed');
        return createBertTokenizer(await response.text());
      })();
    }
    return {
      tok: await tokenizer,
      session: await runtime.load(options.modelUrl ?? '/micro/behavior-head-int8.onnx'),
    };
  }
  return async (request: { input: string }): Promise<string | null> => {
    const started = performance.now();
    try {
      const { tok, session } = await ensure();
      const ort = await import('onnxruntime-web/wasm');
      const ids = tok.encode(request.input, 96);
      const data = BigInt64Array.from(ids, (value) => BigInt(value));
      const mask = BigInt64Array.from(ids, () => 1n);
      const out = await session.run({
        input_ids: new ort.Tensor('int64', data, [1, ids.length]),
        attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
      });
      const logits = Array.from((out.logits?.data ?? []) as Float32Array);
      if (logits.length !== LABELS.length) return null;
      const max = Math.max(...logits);
      const exps = logits.map((value) => Math.exp(value - max));
      const best = logits.indexOf(max);
      const p = exps[best] / exps.reduce((a, b) => a + b, 0);
      if (p < (options.threshold ?? 0.4)) return null;
      const label = LABELS[best];
      options.onStats?.({
        category: label, inferences: 1, ms: Math.round(performance.now() - started),
        loadMs: Math.round(runtime.stats().loadMs),
      });
      return label === 'other' ? null : label;
    } catch {
      return null;
    }
  };
}
