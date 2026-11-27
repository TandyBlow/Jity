/** Candidate extraction head: score appearance clauses for a read action.
 *
 * The input string mirrors training (`动作：…\n分句：…`); the output is one
 * sigmoid per clause. A null answer means the head is unavailable and the
 * caller must fall back to the program channel. */
import { getMicroTokenizer } from './shared';
import { createMicroRuntime } from './runtime';

export interface MicroClauseScore {
  clause: string;
  score: number;
}

export interface MicroExtractionOptions {
  vocabUrl?: string;
  modelUrl?: string;
  /** Test/embedded scorer; the default runs the int8 ONNX head. */
  scoring?: (action: string, clauses: string[]) => Promise<MicroClauseScore[] | null> | MicroClauseScore[] | null;
}

function sigmoid(logit: number): number {
  return 1 / (1 + Math.exp(-logit));
}

export function createMicroExtraction(
  options: MicroExtractionOptions = {},
): (action: string, clauses: string[]) => Promise<MicroClauseScore[] | null> {
  const runtime = createMicroRuntime({ threads: 1 });
  async function ensure() {
    return {
      tok: await getMicroTokenizer(options.vocabUrl),
      session: await runtime.load(options.modelUrl ?? '/micro/extraction-head-int8.onnx'),
    };
  }

  async function scoreDefault(action: string, clauses: string[]): Promise<MicroClauseScore[] | null> {
    const { tok, session } = await ensure();
    const ort = await import('onnxruntime-web/wasm');
    const out: MicroClauseScore[] = [];
    for (const clause of clauses) {
      const ids = tok.encode(`动作：${action}\n分句：${clause}`, 192);
      if (!ids.length) return null;
      const data = BigInt64Array.from(ids, (value) => BigInt(value));
      const mask = BigInt64Array.from(ids, () => 1n);
      const result = await session.run({
        input_ids: new ort.Tensor('int64', data, [1, ids.length]),
        attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
      });
      const logit = (result.logits?.data as Float32Array | undefined)?.[1];
      if (logit == null) return null;
      out.push({ clause, score: sigmoid(logit) });
    }
    return out;
  }

  return async (action: string, clauses: string[]) => {
    try {
      if (options.scoring) return await options.scoring(action, clauses);
      return await scoreDefault(action, clauses);
    } catch {
      return null;
    }
  };
}
