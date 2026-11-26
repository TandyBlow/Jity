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

interface SharedSession {
  pending: Promise<MicroSession>;
  refs: number;
  lastUsed: number;
  loadMs: number;
}

/** One ORT session per model URL for the whole page. Ports that score the same
 * weights share the session instead of loading another copy. `shortcut: a
 * port keeps its refs until dispose; idle eviction needs a port-level release
 * signal, which the current stage lifecycle does not provide. */
const sharedSessions = new Map<string, SharedSession>();
let useClock = 0;

export function createMicroRuntime(options: MicroRuntimeOptions = {}): MicroRuntime {
  if (options.wasmPaths) wasmPaths = options.wasmPaths;
  const threads = options.threads ?? 1;
  const held = new Set<string>();
  let loads = 0;
  let loadMs = 0;
  return {
    load(url) {
      let entry = sharedSessions.get(url);
      if (!entry) {
        const started = performance.now();
        const pending = getOrt().then((ort) => {
          ort.env.wasm.numThreads = threads;
          return ort.InferenceSession.create(url, { executionProviders: ['wasm'] });
        });
        entry = { pending, refs: 0, lastUsed: 0, loadMs: 0 };
        sharedSessions.set(url, entry);
        pending
          .then(() => { entry!.loadMs = performance.now() - started; })
          .catch(() => sharedSessions.delete(url));
      }
      if (!held.has(url)) {
        held.add(url);
        entry.refs += 1;
        loads += 1;
        loadMs += entry.loadMs;
      }
      entry.lastUsed = ++useClock;
      return entry.pending;
    },
    async dispose() {
      for (const url of held) {
        const entry = sharedSessions.get(url);
        if (!entry) continue;
        entry.refs -= 1;
        if (entry.refs > 0) continue;
        sharedSessions.delete(url);
        try {
          const session = await entry.pending;
          await session.release?.();
        } catch {
          // A failed load has nothing to release.
        }
      }
      held.clear();
    },
    stats: () => ({ loads, loadMs }),
  };
}

/** Pack equal-shape classifier rows into one batched tensor call. Exported for
 * shape tests; the ORT call itself stays in runBatch. */
export function packBatch(rows: number[][]): { ids: BigInt64Array; mask: BigInt64Array; width: number; batch: number } {
  const batch = rows.length;
  const width = Math.max(1, ...rows.map((row) => row.length));
  const ids = new BigInt64Array(batch * width);
  const mask = new BigInt64Array(batch * width);
  rows.forEach((row, index) => {
    for (let offset = 0; offset < row.length; offset += 1) {
      ids[index * width + offset] = BigInt(row[offset]);
      mask[index * width + offset] = 1n;
    }
  });
  return { ids, mask, width, batch };
}

/** One session call for N tokenized rows; returns per-row logits of the first
 * output. Used by the task-condition proposer. */
export async function runBatch(session: MicroSession, rows: number[][]): Promise<number[][]> {
  if (!rows.length) return [];
  const ort = await getOrt();
  const { ids, mask, width, batch } = packBatch(rows);
  const out = await session.run({
    input_ids: new ort.Tensor('int64', ids, [batch, width]),
    attention_mask: new ort.Tensor('int64', mask, [batch, width]),
  });
  const first = Object.values(out)[0]?.data as Float32Array | undefined;
  if (!first || first.length % batch !== 0) throw new Error('batch_output_shape_mismatch');
  const classes = first.length / batch;
  return Array.from({ length: batch }, (_, index) => Array.from(first.slice(index * classes, (index + 1) * classes)));
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
