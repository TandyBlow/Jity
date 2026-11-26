/** Shadow existence heads (env/info) on the shared MiniRBT encoder.
 *
 * Shadow-only: the caller records the scores as evidence and never changes a
 * program decision from them. A null answer means the heads are unavailable. */
import { getMicroTokenizer } from './shared';
import { createMicroRuntime } from './runtime';

export interface MicroExistenceScores {
  env: number;
  info: number;
}

export interface MicroExistenceOptions {
  vocabUrl?: string;
  envUrl?: string;
  infoUrl?: string;
  /** Test/embedded scorer; the default runs the int8 ONNX heads. */
  scoring?: (text: string) => Promise<MicroExistenceScores | null> | MicroExistenceScores | null;
}

function sigmoid(logit: number): number {
  return 1 / (1 + Math.exp(-logit));
}

export function createMicroExistence(options: MicroExistenceOptions = {}): (text: string) => Promise<MicroExistenceScores | null> {
  const runtime = createMicroRuntime({ threads: 1 });
  async function ensure() {
    return {
      tok: await getMicroTokenizer(options.vocabUrl),
      env: await runtime.load(options.envUrl ?? '/micro/existence-env-int8.onnx'),
      info: await runtime.load(options.infoUrl ?? '/micro/existence-info-int8.onnx'),
    };
  }

  async function scoreDefault(text: string): Promise<MicroExistenceScores | null> {
    const { tok, env, info } = await ensure();
    const ort = await import('onnxruntime-web/wasm');
    const ids = tok.encode(text, 192);
    if (!ids.length) return null;
    const data = BigInt64Array.from(ids, (value) => BigInt(value));
    const mask = BigInt64Array.from(ids, () => 1n);
    const input = {
      input_ids: new ort.Tensor('int64', data, [1, ids.length]),
      attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
    };
    const envOut = await env.run(input);
    const infoOut = await info.run(input);
    const envLogit = (envOut.logits?.data as Float32Array | undefined)?.[1];
    const infoLogit = (infoOut.logits?.data as Float32Array | undefined)?.[1];
    if (envLogit == null || infoLogit == null) return null;
    return { env: sigmoid(envLogit), info: sigmoid(infoLogit) };
  }

  return async (text: string) => {
    try {
      if (options.scoring) return await options.scoring(text);
      return await scoreDefault(text);
    } catch (error) {
      console.warn('[world-local existence] failed ' + String(error).slice(0, 160));
      return null;
    }
  };
}
