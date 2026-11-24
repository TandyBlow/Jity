/** Reusable browser micro-model runtime: ORT-WASM sessions, cache, release,
 * and load/inference timing. One runtime serves every task.
 *
 * ORT is imported dynamically: its ESM bundle builds URLs from import.meta at
 * module load, which breaks Next's prerender pass. The chunk is only fetched
 * in the browser, on the first model call. */
type Ort = typeof import('onnxruntime-web/wasm');

export type MicroSession = import('onnxruntime-web/wasm').InferenceSession;

let ortPromise: Promise<Ort> | null = null;
let configured = false;
let wasmPaths = '/ort/';

async function getOrt(): Promise<Ort> {
  if (!ortPromise) ortPromise = import('onnxruntime-web/wasm');
  const ort = await ortPromise;
  if (!configured) {
    ort.env.wasm.wasmPaths = wasmPaths;
    configured = true;
  }
  return ort;
}

export interface MicroRuntimeOptions {
  wasmPaths?: string;
  threads?: number;
}

export interface MicroRuntime {
  load(url: string): Promise<MicroSession>;
  dispose(): Promise<void>;
  stats(): { loads: number; loadMs: number };
}

export function createMicroRuntime(options: MicroRuntimeOptions = {}): MicroRuntime {
  if (options.wasmPaths) wasmPaths = options.wasmPaths;
  const threads = options.threads ?? 1;
  const sessions = new Map<string, Promise<MicroSession>>();
  let loads = 0;
  let loadMs = 0;
  return {
    load(url) {
      let pending = sessions.get(url);
      if (!pending) {
        const started = performance.now();
        pending = getOrt().then((ort) => {
          ort.env.wasm.numThreads = threads;
          return ort.InferenceSession.create(url, { executionProviders: ['wasm'] });
        });
        sessions.set(url, pending);
        pending
          .then(() => {
            loads += 1;
            loadMs += performance.now() - started;
          })
          .catch(() => sessions.delete(url));
      }
      return pending;
    },
    async dispose() {
      for (const pending of sessions.values()) {
        try {
          const session = await pending;
          await session.release?.();
        } catch {
          // A failed load has nothing to release.
        }
      }
      sessions.clear();
    },
    stats: () => ({ loads, loadMs }),
  };
}

/** Logits of a single-text classifier head (first model output). */
export async function scoreSingle(session: MicroSession, ids: number[]): Promise<number[]> {
  const ort = await getOrt();
  const data = BigInt64Array.from(ids, (value) => BigInt(value));
  const mask = BigInt64Array.from(ids, () => 1n);
  const out = await session.run({
    input_ids: new ort.Tensor('int64', data, [1, ids.length]),
    attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
  });
  const first = Object.values(out)[0];
  return Array.from((first?.data ?? []) as Float32Array);
}

export async function scorePair(session: MicroSession, ids: number[]): Promise<number> {
  const ort = await getOrt();
  const data = BigInt64Array.from(ids, (value) => BigInt(value));
  const mask = BigInt64Array.from(ids, () => 1n);
  const out = await session.run({
    input_ids: new ort.Tensor('int64', data, [1, ids.length]),
    attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
  });
  const value = out.score?.data?.[0];
  if (typeof value !== 'number') throw new Error('pair_scorer_output_missing');
  return value;
}
