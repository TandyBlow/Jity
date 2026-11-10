'use client';

/** Browser-only playable loop. No HTTP game API: the page loads the static
 * world, creates the local transport/controller, runs the two GGUF engines
 * (semantic 0.6B + narration 0.5B) and stores the committed snapshot in
 * localStorage. The server, if present, is never called. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { WllamaInferenceEngine } from '@/lib/world-engine/runtime/wllama-engine';
import type { InferenceEngine } from '@/lib/world-engine/runtime/engine';
import { LocalGameModel } from '@/lib/world-engine/local/game-model';
import { LocalGameSession, type LocalGameSnapshot } from '@/lib/world-engine/local/session';
import { openLocalProgressStore, migrateLegacySnapshot, type LocalProgressStore } from '@/lib/world-engine/local/persistence';
import { SessionLeaseHeldError } from '@/lib/world-engine/local/persistence/types';
import type { GenerationEvidence, ModelLoadEvidence } from '@/lib/world-engine/local/runtime-diagnostics/types';
import { createProductSync, type ProductSync } from '@/lib/world-engine/local/progress-sync/product';
import { restoredEntries, type RestoredTurn } from '@/lib/world-engine/local/history';
import { locationName, roomOf, visibleCharacters } from '@/lib/world-engine/local/prompt';
import { loadStaticWorld, StaticWorldError } from '@/lib/world-engine/local/world-loader';
import { stateDigest } from '@/lib/world-engine/local/state';
import { STATIC_WORLD_ASSET, STATIC_WORLD_REGISTRATION } from '@/lib/world-engine/local/static-world-registration';
import type { WorldState } from '@/lib/world-engine/types';

const SAVE_KEY = 'jity.world.local.snapshot.v1';
const SEMANTIC_MODEL = '/models/Qwen3-0.6B-Q4_K_M.gguf';
// Sizes and hashes of the exact files this product serves (measured here). A
// truncated fetch is rejected before wllama parses it; the full SHA-256 check
// belongs to 09's host runner.
const SEMANTIC_MODEL_BYTES = 396_705_472;

/** Narration model variants the internal arm switch may select. The default is
 * the shipped LoRA checkpoint; `qwen3-1.7b` is lane 02's prose-facts arm model.
 * A variant is only a file the product serves, never a silent weight swap. */
const NARRATION_MODELS = {
  'qwen25-1.5b-narr': {
    url: '/models/qwen25-1.5b-narr-Q4_K_M.gguf', bytes: 986_048_096, contextSize: 3072,
    sha256: '6ed2268db2e1277933094c8b3af3348c18d6c0689244679a393c2008a1af5a0b',
  },
  'qwen3-1.7b': {
    url: '/models/Qwen3-1.7B-Q4_K_M.gguf', bytes: 1_107_409_472, contextSize: 4096,
    sha256: 'b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897',
  },
} as const;
type NarrationModelKey = keyof typeof NARRATION_MODELS;
const DEFAULT_NARRATION_MODEL: NarrationModelKey = 'qwen25-1.5b-narr';

type Phase = 'loading' | 'ready' | 'thinking' | 'streaming' | 'error';

/** Per-turn evidence record, mirrored on window.__worldTurns so an automated
 * acceptance run reads timings from the product instead of scraping DOM text. */
interface WorldTurnRecord {
  index: number; input: string;
  acceptedMs: number | null; draftMs: number | null; programMs: number | null;
  /** Time to a scene that mixed verified model sentences with program
   * realizations. Never counted as fully model-written. */
  mixedMs: number | null;
  segments?: Array<{ id: string; source: string }>;
  /** Committed prose per point in this turn (player point first). Appending by
   * point keeps a later automatic round from replacing the player's text. */
  points?: Array<{ pointId: string; text: string; source?: 'model' | 'program' | 'mixed' | 'draft' }>;
  /** Per-point narration provenance in this turn (player point first). */
  narrations?: Array<{ pointId: string; source: 'model' | 'program' | 'mixed' | 'draft'; atMs: number }>;
  /** Scheduling clocks, relative to submit. pointCommittedAtMs is recorded when
   * the driver starts narrating that committed point (no transport timestamp
   * exists); narrationStartedAtMs is the first narration progress callback. */
  clocks?: {
    inputAtMs: number; inputAt: string;
    pointCommittedAtMs: number | null;
    narrationStartedAtMs: number | null;
    firstReadableAtMs: number | null;
    firstReadableSource: 'model' | 'program' | 'mixed' | 'draft' | null;
  };
  cancelled: boolean; source: 'model' | 'program' | 'mixed' | 'draft' | null;
  /** Settlement ledger for this turn (results/updates/continuation calls,
   * six-stage coverage/stageMs, policy stops). Attached when the submission
   * closes, so one turn record carries both narration and settlement evidence. */
  submission?: unknown;
  /** Action-family calls for this turn (action/targets/reaction), kept out of
   * the settlement ledger so its coverage/stage counts stay one defined thing. */
  actions?: Array<{ task: string; key: string; ms: number; fallback: boolean; error: string | null }>;
  /** Narration attempt evidence for the last point of this turn: the draft the
   * model saw, every raw attempt, why it was rejected and the echo ratio. 02
   * needs the raw text to fix wrong_person/low_support, and the turn record must
   * carry it without reading worker internals. Capped; no prompt. */
  narration?: {
    pointId: string; violations: string[]; attempts: number[]; rawAttempts: string[];
    draft: string; text: string; draftEcho: number; programFallback: boolean;
  } | null;
  modelId: string | null;
  /** Requested narration variant and prompt shape, copied from window.__worldArm
   * at submit so one evidence file cannot mix two arms unknowingly. */
  narrationModel: string | null;
  promptShape: string | null;
  engines: Array<{
    label: string; loadCount: number; workersCreated: number; workersExited: number; generations: number;
    contextSize?: number; lastLoadMs?: number | null; lastLoadFetchMs?: number | null;
    lastLoadCompileMs?: number | null; lastLoadFromCache?: boolean | null;
    /** Full runtime record of the last generation (engine.runtime().lastGeneration):
     * outcome, first token/readable, stream chunks/gap, prompt+completion tokens,
     * wllama prefill/decode timings, hard stop. No raw text. */
    lastGeneration?: {
      outcome: 'completed' | 'incomplete' | 'aborted' | 'timeout' | 'error'; finishReason: string | null; wallMs: number;
      firstChunkMs: number | null; firstTokenMs: number | null; firstReadableMs: number | null;
      maxStreamGapMs: number; streamChunks: number;
      promptTokens: number | null; cachedPromptTokens: number | null;
      timings?: { prompt_ms: number; predicted_ms: number; cache_n: number; prompt_n: number; predicted_n: number } | null;
      hardStopped: boolean; stoppedMs: number | null; abortCause: 'caller' | 'timeout' | 'dispose' | null;
    } | null;
  }>;
  /** Last generation evidence per engine: prompt tokens vs context size tells a
   * context overflow apart from a model failure. */
  generations?: GenerationNote[];
}

interface TurnEntry {
  key: number; input: string; text: string; note: string | null; ms: number | null;
  /** Committed prose per point in this turn (player point first). */
  points?: Array<{ pointId: string; text: string; source?: 'model' | 'program' | 'mixed' | 'draft' }>;
  /** Wall time from submit to the first streamed character. A draft stream is
   * shown for reading, but it is NOT the acceptance number: a draft is not
   * fact-checked yet and can still be replaced or cancelled. */
  draftMs: number | null;
  /** Wall time from submit to the model text the candidate's own gate accepted.
   * `accepted` is that gate's verdict, not independent quality review: 02's arm
   * run shows accepted scenes with invented current events, so this number is
   * readable-text latency, not a quality claim. Program prose and drafts never
   * fill it. */
  acceptedMs: number | null;
  /** Wall time to a program-composed passage (settled facts only). It is read-
   * able text, but it is a labelled downgrade, so it is reported separately. */
  programMs: number | null;
  mixedMs?: number | null;
  cancelled?: boolean;
  failed?: boolean;
  /** Shown after a reload for a submitted turn that never committed. */
  unfinished?: boolean;
  /** True for a turn rebuilt from the saved snapshot after a reload. */
  restored?: boolean;
}

interface ViewState {
  time: string;
  place: string;
  name: string;
  sanity: number;
  tasks: { goal: string; done: boolean }[];
  visible: string[];
}

function viewOf(state: WorldState): ViewState {
  const me = state.characters[state.protagonistId];
  return {
    time: state.time.dateTime.replace('T', ' ').slice(0, 16),
    place: locationName(state, roomOf(state, state.protagonistId)),
    name: state.initial.characters[state.protagonistId]?.name ?? state.protagonistId,
    sanity: me?.sanity ?? 0,
    tasks: Object.values(me?.tasks ?? {}).sort((a, b) => Number(a.status === 'achieved') - Number(b.status === 'achieved')).slice(0, 5)
      .map((task) => ({ goal: task.goal, done: task.status === 'achieved' })),
    visible: visibleCharacters(state, state.protagonistId).filter((id) => id !== state.protagonistId).map((id) => state.initial.characters[id]?.name ?? id),
  };
}

/** Runtime generation evidence per engine, so 09 can distinguish a context
 * overflow from a model failure without reading worker internals. Bounded. */
/** Full GenerationEvidence passthrough plus which engine produced it: 09 can
 * separate prefill (prompt_ms/prompt_n) from decode (predicted_ms/predicted_n),
 * prove streaming (firstToken/firstReadable/streamChunks) and cancel latency
 * (stoppedMs/hardStopped) without reading worker internals. */
type GenerationNote = {
  engine: string;
  outcome: string | null;
  promptTokens: number | null;
  cachedPromptTokens: number | null;
  contextSize: number;
  maxTokens: number | null;
  cachePrompt: boolean | null;
  wallMs: number;
  finishReason: string | null;
  firstTokenMs: number | null;
  firstReadableMs: number | null;
  firstChunkMs: number | null;
  maxStreamGapMs: number | null;
  streamChunks: number | null;
  stoppedMs: number | null;
  hardStopped: boolean | null;
  abortCause: string | null;
  abortRequestedMs: number | null;
  promptMs: number | null;
  predictedMs: number | null;
  promptN: number | null;
  predictedN: number | null;
  cacheN: number | null;
  at: number;
};
function recordGeneration(note: GenerationNote): void {
  const w = globalThis as unknown as { __worldGenerations?: GenerationNote[] };
  (w.__worldGenerations ??= []).push(note);
  if (w.__worldGenerations.length > 200) w.__worldGenerations.splice(0, w.__worldGenerations.length - 200);
}
function lastGeneration(engine: string): GenerationNote | null {
  const list = (globalThis as unknown as { __worldGenerations?: GenerationNote[] }).__worldGenerations ?? [];
  for (let i = list.length - 1; i >= 0; i -= 1) if (list[i].engine === engine) return list[i];
  return null;
}

async function loadEngine(
  url: string,
  contextSize = 8192,
  expectedBytes?: number,
  label = 'engine',
  /** Hand the constructed engine out before the load starts, so the stop
   * button can reach a cold load that has no `current` engine yet. */
  onEngine?: (engine: WllamaInferenceEngine) => void,
): Promise<WllamaInferenceEngine> {
  const modelUrl = new URL(url, window.location.href).href;
  // A cold load is 32-46 s, so it is bounded and cancellable; a stuck compile
  // must not leave the first player turn waiting forever.
  const onEvidence = (evidence: ModelLoadEvidence | GenerationEvidence) => {
    if (evidence.kind !== 'generation') return;
    const record = evidence as unknown as Record<string, unknown>;
    const num = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);
    const bool = (value: unknown): boolean | null => (typeof value === 'boolean' ? value : null);
    const text = (value: unknown): string | null => (typeof value === 'string' ? value : null);
    const timings = (record.timings ?? null) as Record<string, unknown> | null;
    recordGeneration({
      engine: label,
      outcome: text(record.outcome),
      promptTokens: num(record.promptTokens),
      cachedPromptTokens: num(record.cachedPromptTokens),
      contextSize: num(record.contextSize) ?? contextSize,
      maxTokens: num(record.maxTokens),
      cachePrompt: bool(record.cachePrompt),
      wallMs: num(record.wallMs) ?? 0,
      finishReason: text(record.finishReason),
      firstTokenMs: num(record.firstTokenMs),
      firstReadableMs: num(record.firstReadableMs),
      firstChunkMs: num(record.firstChunkMs),
      maxStreamGapMs: num(record.maxStreamGapMs),
      streamChunks: num(record.streamChunks),
      stoppedMs: num(record.stoppedMs),
      hardStopped: bool(record.hardStopped),
      abortCause: text(record.abortCause),
      abortRequestedMs: num(record.abortRequestedMs),
      promptMs: timings ? num(timings.prompt_ms) : null,
      predictedMs: timings ? num(timings.predicted_ms) : null,
      promptN: timings ? num(timings.prompt_n) : null,
      predictedN: timings ? num(timings.predicted_n) : null,
      cacheN: timings ? num(timings.cache_n) : null,
      at: Date.now(),
    });
  };
  const engine = new WllamaInferenceEngine({ modelUrl, contextSize, nGpuLayers: 99999, abortGraceMs: 2500, loadTimeoutMs: 120_000, onEvidence, ...(expectedBytes ? { expectedBytes } : {}) });
  onEngine?.(engine);
  try { await engine.ensureLoaded(); return engine; } catch (gpuError) {
    // A user cancel or dispose is not a GPU failure: retrying on CPU would
    // start a second load after the player already stopped.
    if (gpuError instanceof DOMException && gpuError.name === 'AbortError') throw gpuError;
    if ((gpuError as { name?: string } | null)?.name === 'AbortError') throw gpuError;
    console.warn('[world-local] WebGPU load failed, retrying CPU', gpuError);
    await engine.dispose().catch(() => undefined);
    const cpu = new WllamaInferenceEngine({ modelUrl, contextSize, nGpuLayers: 0, abortGraceMs: 2500, loadTimeoutMs: 120_000, onEvidence, ...(expectedBytes ? { expectedBytes } : {}) });
    onEngine?.(cpu);
    await cpu.ensureLoaded();
    return cpu;
  }
}

function engineCounters(label: string, engine: ProductEnginePort | null): WorldTurnRecord['engines'][number] | null {
  const runtime = engine?.runtime?.();
  if (!runtime) return null;
  return {
    label, loadCount: runtime.loadCount, workersCreated: runtime.workersCreated, workersExited: runtime.workersExited,
    generations: runtime.generations, contextSize: runtime.contextSize,
    lastLoadMs: runtime.lastLoadMs ?? null, lastLoadFetchMs: runtime.lastLoadFetchMs ?? null,
    lastLoadCompileMs: runtime.lastLoadCompileMs ?? null, lastLoadFromCache: runtime.lastLoadFromCache ?? null,
    // Full engine record for the last generation: prefill (timings.prompt_ms/
    // prompt_n) vs decode (predicted_ms/predicted_n), streaming proof and cancel
    // latency. No raw text; the turn record keeps accepted prose separately.
    lastGeneration: runtime.lastGeneration ?? null,
  };
}

/** A model port that survives a hard-stopped generation. wllama terminates the
 * worker when an abort does not settle in time, which unloads the model; the
 * game must reload it instead of failing every later turn of the session. */
interface ProductEnginePort extends InferenceEngine {
  /** Forwarded to the real runtime so the stop button can cancel a cold load. */
  cancelActive(): number;
  runtime(): {
    needsReload: boolean; workersCreated: number; workersExited: number; generations: number; loadCount: number;
    contextSize?: number; modelId?: string | null;
    lastLoadMs?: number | null; lastLoadFetchMs?: number | null;
    lastLoadCompileMs?: number | null; lastLoadFromCache?: boolean | null;
    lastGeneration?: WorldTurnRecord['engines'][number]['lastGeneration'];
  } | null;
}

function resilientEngine(url: string, contextSize: number, label: string, expectedBytes?: number): ProductEnginePort {
  let current: WllamaInferenceEngine | null = null;
  /** The engine a cold load is currently using. It is not `current` until the
   * load succeeds, but the stop button must still be able to cancel it. */
  let loadingEngine: WllamaInferenceEngine | null = null;
  /** Set by dispose(). A load that was already in flight may still land (for
   * example the CPU fallback after a real GPU failure); a closed port must
   * dispose that engine instead of adopting a worker nobody owns. */
  let closed = false;
  let loading: Promise<WllamaInferenceEngine> | null = null;
  const ensure = async (): Promise<WllamaInferenceEngine> => {
    if (current) return current;
    if (!loading) {
      loading = loadEngine(url, contextSize, expectedBytes, label, (engine) => {
        if (closed) { void engine.dispose().catch(() => undefined); return; }
        loadingEngine = engine;
      }).then((engine) => {
        if (closed) { void engine.dispose().catch(() => undefined); throw new DOMException('engine closed', 'AbortError'); }
        current = engine;
        loadingEngine = null;
        loading = null;
        return engine;
      }, (error) => {
        loading = null;
        loadingEngine = null;
        throw error;
      });
    }
    return loading;
  };
  const drop = async (engine: WllamaInferenceEngine) => {
    if (current === engine) current = null;
    try { await engine.dispose(); } catch { /* the worker may already be gone */ }
  };
  return {
    get info() { return { backend: current?.info.backend ?? 'wllama', modelId: current?.info.modelId ?? null }; },
    load: async () => { await ensure(); },
    dispose: async () => {
      closed = true;
      const inFlight = loadingEngine;
      loadingEngine = null;
      if (current) await drop(current);
      if (inFlight && inFlight !== current) { try { await inFlight.dispose(); } catch { /* already gone */ } }
    },
    // The stop button reaches the real runtime through this port, so a cold
    // load can be cancelled before the first turn ever starts.
    cancelActive: () => (current ?? loadingEngine)?.cancelActive() ?? 0,
    runtime: () => (current ?? loadingEngine)?.runtime ?? null,
    complete: async (prompt, options) => {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const engine = await ensure();
        // After a hard stop the worker is gone but the same weights can be
        // reloaded. Reload instead of constructing a second runtime or
        // switching models.
        if (engine.runtime.needsReload) {
          console.warn(`[world-local] ${label} worker exited; reloading the same weights`);
          await engine.ensureLoaded();
        }
        try {
          return await engine.complete(prompt, options);
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          if (attempt === 0 && /not loaded/i.test(message)) {
            console.warn(`[world-local] ${label} engine was unloaded; reloading once`, message);
            await drop(engine);
            continue;
          }
          throw error;
        }
      }
      throw new Error(`${label} engine could not be reloaded`);
    },
  };
}

/** localStorage key for an explicit lease takeover. After the player chooses
 * "continue in this tab", the reload must open with the same holder id that
 * took the lease, otherwise the fresh page would be blocked again. */
const LEASE_TAKEOVER_KEY = 'jity.world.local.lease.takeover';

/** Open the saved session, waiting briefly when a just-unloaded page has not
 * released its lease yet. A held lease is never treated as a corrupt save. */
async function openWithLease(
  store: LocalProgressStore,
  world: { worldId: string; template: Parameters<typeof LocalGameSession.create>[0] },
  model: LocalGameModel,
  alive: () => boolean,
  narrationSourceOf: () => Record<string, { source: 'model' | 'mixed' | 'program' | 'draft'; note?: string }> | undefined,
  attempts = 20,
  // The writer lease lives 30 s and a page that is being reloaded may not have
  // released it yet (its flush can still be running). Wait past that TTL before
  // telling the player another tab owns the save.
  delayMs = 2000,
): Promise<LocalGameSession> {
  const takeoverId = (() => {
    try { return sessionStorage.getItem(LEASE_TAKEOVER_KEY); } catch { return null; }
  })();
  let lastError: unknown = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (!alive()) throw new Error('page_unmounted');
    try {
      const opened = await LocalGameSession.open(
        store, { worldId: world.worldId, initial: world.template }, model,
        { ...(takeoverId ? { sessionId: takeoverId } : {}), narrationSourceOf },
      );
      if (opened.created) await opened.session.start();
      if (takeoverId) { try { sessionStorage.removeItem(LEASE_TAKEOVER_KEY); } catch { /* ignore */ } }
      return opened.session;
    } catch (error) {
      lastError = error;
      if (!(error instanceof SessionLeaseHeldError)) throw error;
      (window as unknown as { __worldLease?: unknown }).__worldLease = {
        blocked: true, holderId: error.holderId, expiresAtEpochMilli: error.expiresAtEpochMilli,
        attempt: attempt + 1, retriedMs: (attempt + 1) * delayMs, at: Date.now(),
      };
      await new Promise<void>((resolve) => { setTimeout(resolve, delayMs); });
    }
  }
  throw lastError;
}

export default function WorldLocalPage() {
  const [phase, setPhase] = useState<Phase>('loading');
  const [message, setMessage] = useState('正在载入本地世界与模型…');
  const [entries, setEntries] = useState<TurnEntry[]>([]);
  /** The current turn's evidence record; the same object lives in the window
   * array, so later callbacks update it in place. */
  const turnRecordRef = useRef<WorldTurnRecord | null>(null);
  /** Internal evaluation arm selected by URL query (never rendered, never a
   * player setting): `?narrationCandidate=trained&narrationMode=scene&narrationShape=prose-facts`.
   * 09 uses it to run the same settled input through different prompt shapes. */
  const narrationArm = useRef(((): { candidate?: string; mode?: 'beats' | 'scene'; shape?: 'serialized' | 'prose-facts'; model?: NarrationModelKey } => {
    if (typeof window === 'undefined') return {};
    const q = new URLSearchParams(window.location.search);
    const candidate = q.get('narrationCandidate');
    const modelParam = q.get('narrationModel');
    const model = modelParam === 'qwen3-1.7b' || modelParam === 'qwen25-1.5b-narr' ? modelParam : undefined;
    const modeParam = q.get('narrationMode');
    const shapeParam = q.get('narrationShape');
    const mode = modeParam === 'beats' || modeParam === 'scene' ? modeParam : undefined;
    const shape = shapeParam === 'serialized' || shapeParam === 'prose-facts' ? shapeParam : undefined;
    return {
      ...(candidate ? { candidate } : {}),
      ...(mode ? { mode } : {}),
      ...(shape ? { shape } : {}),
      ...(model ? { model } : {}),
    };
  })());
  /** Submit wall-clock origin for this turn; the narration callbacks run outside
   * the submit closure, so the origin lives in a ref. */
  const submittedAtRef = useRef(0);
  /** Seconds since the page opened while the cold load is still running, so a
   * 120 s bounded load never looks like a frozen page. */
  const [loadSeconds, setLoadSeconds] = useState(0);
  const loadStartedRef = useRef(0);
  const [view, setView] = useState<ViewState | null>(null);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [stage, setStage] = useState<string>('');
  const sessionRef = useRef<LocalGameSession | null>(null);
  /** Product cap: one submit may wait 300 s at most. Automatic follow-up rounds
   * are stopped at 295 s so the player gets the committed point back inside the
   * cap instead of watching a chain of auto rounds. */
  const turnDeadlineRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const deadlineHitRef = useRef(false);
  /** pointId → how its committed narration was produced. Persisted inside the
   * same snapshot so a reload can label a program scene or a rejected draft
   * instead of showing it as accepted prose. */
  const narrationSourcesRef = useRef<Record<string, { source: 'model' | 'mixed' | 'program' | 'draft'; note?: string }>>({});
  const semanticRef = useRef<ProductEnginePort | null>(null);
  const narrationRef = useRef<ProductEnginePort | null>(null);
  const modelRef = useRef<LocalGameModel | null>(null);
  const storeRef = useRef<LocalProgressStore | null>(null);
  /** Optional remote copy of the same opaque snapshot. Play never waits for it;
   * the IndexedDB record is always written first. */
  const syncRef = useRef<ProductSync<LocalGameSnapshot> | null>(null);
  const [syncLabel, setSyncLabel] = useState<string | null>(null);
  const [durable, setDurable] = useState<boolean | null>(null);
  /** A live lease held by another tab (or by a reload that has not released
   * yet). The save is valid; it must never be archived or deleted for this. */
  const [leaseBlocked, setLeaseBlocked] = useState(false);
  const leaseWorldRef = useRef<string | null>(null);

  /** Fallback only: when the platform has no IndexedDB the session runs in
   * memory and the page keeps a best-effort localStorage copy so a refresh is
   * not a guaranteed loss. Durable sessions save through the store instead. */
  const save = useCallback((snapshot: LocalGameSnapshot) => {
    if (snapshot.transport.work) return; // never persist a half-settled point
    const sync = syncRef.current;
    if (sync) {
      // The session already wrote the durable record (it owns the revision CAS).
      // push() uploads that payload without writing the store again, so the
      // sync layer can never bump the revision behind the session's back.
      void sync.push(snapshot).then((result) => {
        const outcome = result.outcome;
        setSyncLabel(outcome?.status === 'synced' ? '已同步'
          : outcome?.status === 'queued' ? '已存本地，等待联网同步'
          : outcome?.status === 'conflict' ? '另一台设备也保存了：需要你选择保留哪份'
          : outcome?.status === 'local-only' ? '只存本地'
          : result.note ?? null);
      }).catch((e) => { console.warn('[world-local] sync save failed', e); });
      return;
    }
    if (storeRef.current?.durable) return;
    try { localStorage.setItem(SAVE_KEY, JSON.stringify(snapshot)); } catch (e) { console.warn('[world-local] save failed', e); }
  }, []);

  const refresh = useCallback(async () => {
    const session = sessionRef.current;
    if (!session) return;
    const state = await session.state();
    // Independent check: the state the page is about to render must hash to the
    // digest the transport recorded for the head point. A mismatch means the
    // in-memory state and the committed record disagree; refuse to continue
    // rather than play on a silently diverged world.
    const snapshot = session.snapshot;
    const expected = snapshot.transport.pointStates[snapshot.transport.headPointId]?.stateDigest ?? null;
    const actual = await stateDigest(state);
    if (expected && actual !== expected) {
      throw new Error(`state_digest_mismatch: head=${snapshot.transport.headPointId} expected=${expected.slice(0, 12)} actual=${actual.slice(0, 12)}`);
    }
    setView(viewOf(state));
    // Full committed record for independent state review (05) and replay: the
    // visible view alone cannot prove which task deltas reached the save.
    // A getter, not a captured object: a driver that reads it after a turn must
    // see the current record, not the restore-time snapshot.
    (window as unknown as { __worldSnapshot?: unknown }).__worldSnapshot =
      () => structuredClone(sessionRef.current?.snapshot ?? session.snapshot);
    const context = await session.transport.execute('get_context', {}, { worldId: session.worldId });
    setHistory(session.commandsPlayed);
    // A conflict-blocked session can leave flushPersistence waiting on its own
    // drain; the page must still paint. Bounded wait, then the snapshot save is
    // best effort.
    await Promise.race([
      session.flushPersistence().catch(() => undefined),
      new Promise<void>((resolve) => setTimeout(resolve, 8_000)),
    ]);
    save(session.snapshot);
    setPhase((current) => current === 'streaming' ? 'ready' : current);
    return context;
  }, [save]);

  useEffect(() => {
    let alive = true;
    // The evidence globals exist from page start, not only after the first
    // turn: an acceptance driver uses them to prove it is on the product page
    // before any turn runs. Existing arrays survive a StrictMode remount.
    {
      const w = window as unknown as { __worldTurns?: unknown[]; __worldGenerations?: unknown[]; __worldCandidate?: unknown[] };
      w.__worldTurns ??= [];
      w.__worldGenerations ??= [];
      w.__worldCandidate ??= [];
    }
    /** Cancels the StrictMode-probe cold-load timer if this mount is unmounted
     * before the real load starts. */
    let releaseLoadGate: (() => void) | null = null;
    loadStartedRef.current = performance.now();
    const ticker = setInterval(() => {
      setLoadSeconds(Math.max(0, Math.round((performance.now() - loadStartedRef.current) / 1000)));
    }, 1000);
    (async () => {
      try {
        // The static world is verified, not merely parsed: asset hash, initial
        // digest, canonical state digest and S0 equality must all match the
        // registration, or the game refuses to start.
        const assetUrl = new URL(STATIC_WORLD_ASSET, window.location.href).href;
        const assetResponse = await fetch(assetUrl, { cache: 'no-store' });
        if (!assetResponse.ok) throw new StaticWorldError('file_hash', `world asset HTTP ${assetResponse.status}`);
        const world = await loadStaticWorld(await assetResponse.text(), STATIC_WORLD_REGISTRATION);
        const arm = narrationArm.current;
        const narrationKey: NarrationModelKey = arm.model ?? DEFAULT_NARRATION_MODEL;
        const narrationSpec = NARRATION_MODELS[narrationKey];
        // The engines are constructed first but NOT loaded yet: the local save
        // must restore and paint before a ~100 s cold load, otherwise a reload
        // shows an empty history while the models load.
        setMessage('正在读取本地存档…');
        // 12288 covers the settlement's measured prompt (7877 chars) plus the
        // repair feedback; 8192 left a retry on the edge of the context.
        const semantic = resilientEngine(SEMANTIC_MODEL, 12_288, 'semantic', SEMANTIC_MODEL_BYTES);
        semanticRef.current = semantic;
        const narration = resilientEngine(narrationSpec.url, narrationSpec.contextSize, 'narration', narrationSpec.bytes);
        narrationRef.current = narration;
        const candidate = arm.candidate ?? (window as unknown as { __jityNarrationCandidate?: string }).__jityNarrationCandidate ?? 'auto';
        // Arm identity is evidence: 09 records it next to every turn, including
        // the exact narration file and its hash so no run can silently swap weights.
        (window as unknown as { __worldArm?: unknown }).__worldArm = {
          candidate, mode: arm.mode ?? null, shape: arm.shape ?? null,
          narrationModel: narrationKey, narrationFile: narrationSpec.url,
          narrationBytes: narrationSpec.bytes, narrationSha256: narrationSpec.sha256,
        };
        const model = new LocalGameModel(semantic, {
          narrationEngine: narration,
          narrationMode: 'instruct',
          narrationCandidate: candidate as 'auto' | 'trained' | 'instruct' | 'constrained' | 'builtin',
          ...(arm.mode ? { trainedMode: arm.mode } : {}),
          ...(arm.shape ? { trainedPromptShape: arm.shape } : {}),
          narrationMaxTokens: 200,
          narrationTemperature: 0.45,
          onTask: (task, key, detail) => {
            // stageMs/stages arrive on the updates task detail: printing them
            // here keeps the per-stage cost visible even when the turn times out
            // before the submission ledger is closed.
            const stageNote = detail.stageMs && typeof detail.stageMs === 'object'
              ? ` stages=${Object.entries(detail.stageMs).map(([name, ms]) => `${name}:${Math.round(Number(ms))}`).join(',')}`
              : '';
            const scope = detail.scope;
            const scopeNote = scope
              ? ` scope=${scope.mode ?? '?'} affected=${scope.affectedCharacters ?? '?'}/${(scope.affectedCharacters ?? 0) + (scope.unaffectedCharacters ?? 0)} taskIds=${scope.affectedTaskIds?.length ?? 0} rows=${scope.taskRows ?? '?'}`
              : '';
            console.info(`[world-local task] ${task} ${key} ${Math.round(detail.ms)}ms fallback=${detail.fallback} ${detail.error ?? ''}${stageNote}${scopeNote}`);
            if (task === 'action' || task === 'targets' || task === 'reaction') {
              const live = turnRecordRef.current;
              if (live) (live.actions ??= []).push({
                task, key, ms: Math.round(detail.ms), fallback: detail.fallback, error: detail.error ?? null,
              });
            }
            setStage(STAGE_LABEL[task] ?? task);
            if (task === 'narration') setStage('');
            // A driver that times out mid-turn must still see the engines that
            // actually ran. The finally block only runs when submit settles.
            {
              const liveRecord = turnRecordRef.current;
              if (liveRecord) {
                liveRecord.engines = [engineCounters('semantic', semanticRef.current), engineCounters('narration', narrationRef.current)]
                  .filter((entry): entry is NonNullable<typeof entry> => entry != null);
                (window as unknown as { __worldLive?: unknown }).__worldLive = {
                  turn: liveRecord.index, at: Date.now(), engines: liveRecord.engines,
                  modelId: liveRecord.modelId, generations: liveRecord.generations ?? null,
                };
              }
            }
            if (task !== 'narration') return;
            setEntries((list) => updateLast(list, (entry) => ({ ...entry, note: detail.fallback ? (detail.error ?? '正文已按已结算事实修正') : null, ms: Math.round(detail.ms) })));
          },
          onNarrationDebug: (debug) => {
            (window as unknown as { __worldDebug?: unknown }).__worldDebug = debug;
            const liveRecord = turnRecordRef.current;
            if (liveRecord) {
              liveRecord.narration = {
                pointId: debug.pointId, violations: debug.violations, attempts: debug.attempts,
                rawAttempts: debug.rawAttempts.map((text) => text.slice(0, 2000)),
                draft: debug.draft.slice(0, 2000), text: debug.text.slice(0, 2000),
                draftEcho: debug.draftEcho, programFallback: debug.programFallback,
              };
            }
          },
          // Candidate provenance (grade, per-sentence sources, attempts) is kept
          // apart from the in-model debug record and from the program draft.
          onNarrationEvidence: (record) => {
            const w = window as unknown as { __worldCandidate?: unknown[] };
            (w.__worldCandidate ??= []).push(record);
          },
          onNarrationProgress: (progress) => {
            const startRecord = turnRecordRef.current;
            if (startRecord?.clocks && startRecord.clocks.narrationStartedAtMs == null) {
              const at = Math.round(performance.now() - submittedAtRef.current);
              startRecord.clocks.narrationStartedAtMs = at;
              // The driver narrates the committed head point; no separate
              // commit timestamp exists in the transport, so this is the
              // earliest clock the page can honestly attribute to it.
              startRecord.clocks.pointCommittedAtMs = at;
            }
            setPhase('streaming');
            const text = progress.raw.split(String.fromCharCode(8251)).join(String.fromCharCode(10, 10));
            // Draft only: recorded separately from the accepted, fact-checked text.
            const draftMs = Math.round(performance.now() - submittedAtRef.current);
            const record = turnRecordRef.current;
            if (record && record.draftMs == null) record.draftMs = draftMs;
            setEntries((list) => updateLast(list, (entry) => {
              const points = [...(entry.points ?? [])];
              const index = points.findIndex((part) => part.pointId === progress.pointId);
              if (index < 0) points.push({ pointId: progress.pointId, text, source: 'draft' });
              else if (points[index].source === 'draft') points[index] = { ...points[index], text };
              return { ...entry, points, text: points.map((part) => part.text.trim()).filter(Boolean).join('\n\n'), draftMs: entry.draftMs ?? draftMs };
            }));
          },
          onNarrationComplete: (progress) => {
            const text = progress.raw.split(String.fromCharCode(8251)).join(String.fromCharCode(10, 10));
            const atMs = Math.round(performance.now() - submittedAtRef.current);
            // `model` means the candidate's own verifier accepted the text; it is
            // not independent review (the 02 arm run has accepted text with an
            // invented event). 'program' is the labelled downgrade and 'drafted'
            // was never accepted; neither fills the readable-text timing.
            const source = progress.source ?? (progress.fallback ? 'program' : 'draft');
            if (!text.trim()) {
              // An empty completion is a failure, not a silent blank paragraph.
              setEntries((list) => updateLast(list, (entry) => entry.acceptedMs == null
                ? { ...entry, text: '', failed: true, note: '这一回合没有写出正文；已结算的事实仍保留，可以再试一次。' }
                : entry));
              setPhase('ready');
              return;
            }
            narrationSourcesRef.current[progress.pointId] = { source };
            const clocks = turnRecordRef.current?.clocks;
            if (clocks && clocks.firstReadableAtMs == null) {
              clocks.firstReadableAtMs = atMs;
              clocks.firstReadableSource = source;
            }
            const record = turnRecordRef.current;
            if (record) {
              // One turn can narrate several points (player point, then automatic
              // rounds). Each gets its own provenance record; the turn-level
              // fields keep the FIRST point's numbers, so later auto prose can
              // neither replace the player point's accepted timing nor relabel it
              // as draft.
              record.narrations = record.narrations ?? [];
              record.narrations.push({ pointId: progress.pointId, source, atMs });
              if (record.source == null) {
                record.source = source;
                record.segments = progress.segments?.map((segment) => ({ id: segment.id, source: segment.source }));
              }
              if (source === 'model') record.acceptedMs = record.acceptedMs ?? atMs;
              else if (source === 'program') record.programMs = record.programMs ?? atMs;
              else if (source === 'mixed') record.mixedMs = record.mixedMs ?? atMs;
            }
            setEntries((list) => updateLast(list, (entry) => {
              const points = [...(entry.points ?? [])];
              const index = points.findIndex((part) => part.pointId === progress.pointId);
              if (index < 0) points.push({ pointId: progress.pointId, text, source });
              else points[index] = { pointId: progress.pointId, text, source };
              const joined = points.map((part) => part.text.trim()).filter(Boolean).join('\n\n');
              return source === 'model'
                ? { ...entry, points, text: joined, acceptedMs: atMs, ms: atMs }
                : source === 'program'
                  ? { ...entry, points, text: joined, programMs: entry.programMs ?? atMs, ms: null, note: entry.note ?? '程序按已结算事实成文' }
                  : source === 'mixed'
                    ? { ...entry, points, text: joined, mixedMs: entry.mixedMs ?? atMs, ms: null, note: entry.note ?? '这一段里混有程序按已结算事实写出的句子' }
                    : source === 'draft'
                    ? { ...entry, points, text: joined, note: entry.note ?? '这段没有通过事实自检，只是按已结算事实列出的草稿，不是成文正文。' }
                    : { ...entry, points, text: joined };
            }));
            setPhase('ready');
          },
        });
        modelRef.current = model;
        // Durable progress lives in IndexedDB with a writer lease; the old
        // single-slot localStorage snapshot is migrated non-destructively.
        const store = await openLocalProgressStore();
        storeRef.current = store;
        const syncBase = process.env.NEXT_PUBLIC_LOCAL_PROGRESS_URL ?? 'http://127.0.0.1:8000/local-progress';
        if (store.durable) {
          const sync = createProductSync<LocalGameSnapshot>({ store, worldId: world.worldId, baseUrl: syncBase });
          syncRef.current = sync;
          void sync.flush().then((outcome) => {
            if (outcome.remaining > 0) setSyncLabel(`还有 ${outcome.remaining} 段进度等待同步`);
          }).catch(() => undefined);
        }
        setDurable(store.durable);
        if (!store.durable) {
          setWarning('浏览器没有提供 IndexedDB：本局进度只保存在内存里，刷新会丢失。');
        }
        const migration = await migrateLegacySnapshot(store, { removeSource: true });
        if (migration.status === 'migrated') console.info('[world-local] migrated legacy snapshot', migration.revision);
        if (migration.status !== 'absent' && migration.status !== 'migrated') {
          console.warn('[world-local] legacy migration', migration.status, migration.backupKey ?? '');
        }
        let session: LocalGameSession;
        let restored = false;
        try {
          session = await openWithLease(store, world, model, () => alive, () => narrationSourcesRef.current);
          (window as unknown as { __worldLease?: unknown }).__worldLease = { blocked: false, at: Date.now() };
          // A save can carry an advance left open by a failed turn. The next
          // submit would be refused as turn_in_progress (2603 run: ready, then
          // submit_refused). Cancel it once at load and keep everything that
          // was already committed.
          if (session.snapshot.transport.advance) {
            try {
              await Promise.race([
                session.cancel('restored_unfinished'),
                new Promise((resolve) => setTimeout(resolve, 15_000)),
              ]);
            } catch (cancelError) { console.warn('[world-local] cancel of a restored unfinished turn failed', cancelError); }
          }
          restored = session.commandsPlayed.length > 0 || session.snapshot.transport.headPointId !== session.snapshot.transport.rootPointId;
        } catch (openError) {
          if (openError instanceof SessionLeaseHeldError) {
            // __worldLease already carries holder/expiry/attempts (set by the
            // helper on each retry). The save is not corrupt; a page from a
            // previous run may still be alive and renewing the lease.
            // The save is fine and another writer owns the lease (a second tab,
            // or the page that was just reloaded and has not released yet).
            // Offer a retry/takeover; never touch the record.
            leaseWorldRef.current = world.worldId;
            setLeaseBlocked(true);
            setPhase('error');
            setError('加载失败：另一个标签页（或刚刚关闭的页面）仍持有存档写入权。存档没有被改动，可以重试，或在这个标签页接管。');
            return;
          }
          console.error('[world-local] saved progress could not be opened', openError);
          const record = await store.load(world.worldId).catch(() => null);
          let archived = false;
          if (record) {
            try {
              await store.backupLegacy({
                key: `corrupt:${world.worldId}:${Date.now()}`,
                sourceKey: `progress:${world.worldId}`,
                raw: JSON.stringify(record.snapshot),
                capturedAtEpochMilli: Date.now(),
              });
              archived = true;
            } catch (archiveError) {
              console.error('[world-local] failed to archive the corrupt save', archiveError);
            }
          }
          if (!archived) throw openError;
          await store.delete(world.worldId, { force: true });
          setWarning('旧存档无法恢复，已保留原始副本并开始新的一局。');
          session = await LocalGameSession.create(world.template, model, { worldId: world.worldId, storage: store });
          await session.start();
        }
        sessionRef.current = session;
        let restoredCount = 0;
        let committedCount = 0;
        let unfinishedCount = 0;
        if (restored) {
          const history = restoredEntries(session.snapshot);
          setEntries(history);
          restoredCount = history.length;
          // A committed point whose text is an unadopted draft is visible but is
          // not counted as accepted/committed prose.
          committedCount = history.filter((entry) => entry.text.length > 0 && entry.source !== 'draft').length;
          unfinishedCount = history.filter((entry) => entry.unfinished).length;
          if (history.length > 0) console.info('[world-local] restored entries', history.length, 'with text', committedCount, 'unfinished', unfinishedCount);
        }
        // Field semantics for 09: state restoration and history restoration are
        // separate facts. `overallRestored` is only true when both hold and no
        // player input is left half-consumed.
        const hydrated = await session.state();
        const context = await session.transport.execute('get_context', {}, { worldId: session.worldId });
        (window as unknown as { __worldRestore?: unknown }).__worldRestore = {
          stateRestored: restored,
          // entriesTotal is every submitted turn in the save; entriesRestored is
          // what the page shows for them (committed prose or an explicit
          // unfinished entry). They are compared as player-visible history.
          entriesRestored: restoredCount,
          entriesTotal: session.snapshot.commands.length,
          committedEntries: committedCount,
          unfinishedEntries: unfinishedCount,
          narrationSources: session.snapshot.narrationSources ?? null,
          inputConsumptionRestored: context.world.advance.intentStatus !== 'pending',
          commandsPlayed: session.commandsPlayed,
          headPointId: session.snapshot.transport.headPointId,
          sanity: hydrated.characters[hydrated.protagonistId]?.sanity ?? null,
        };
        // State and history are on screen now. The cold load is the only thing
        // still pending, so the page can be read while it runs and the stop
        // button can cancel it. React StrictMode mounts this effect twice in
        // dev; starting the load after a short gate means the probe mount's
        // cleanup cancels its timer before any model fetch/compile, so only the
        // real mount loads (ready time reflects one round, not two).
        await new Promise<void>((resolve) => {
          const timer = setTimeout(() => { releaseLoadGate = null; resolve(); }, 200);
          releaseLoadGate = () => { clearTimeout(timer); resolve(); };
        });
        releaseLoadGate = null;
        if (!alive) return;
        setMessage('正在加载语义模型（Qwen3-0.6B）…');
        await semantic.load();
        if (!alive) { await semantic.dispose(); return; }
        setMessage(`正在加载叙事模型（${narrationKey}）…`);
        await narration.load();
        if (!alive) { await narration.dispose(); return; }
        await refresh();
        if (!alive) return;
        setPhase('ready');
        setMessage(restored ? '已恢复本地存档，继续上次的进度。' : '本地世界已就绪。');
      } catch (e) {
        // React StrictMode mounts the effect twice in dev: the first cleanup
        // aborts its own cold load, and this catch must not paint that abort
        // over the second, still-progressing load.
        if (!alive) return;
        console.error(e);
        setPhase('error');
        setError(e instanceof Error ? `${e.name}: ${e.message}` : String(e));
      }
    })();
    return () => {
      alive = false;
      releaseLoadGate?.();
      clearInterval(ticker);
      // A SPA route change unmounts this page; both workers must exit here
      // instead of living until the tab closes. Best effort, then log counters.
      const engines = [semanticRef.current, narrationRef.current];
      semanticRef.current = null;
      narrationRef.current = null;
      // Read the counters before dispose clears the port's engine; the log then
      // shows whether every created worker exited (no leak on route change).
      const before = engines.map((engine, index) => ({ index, runtime: engine?.runtime?.() ?? null }));
      void Promise.allSettled(engines.map((engine) => engine?.dispose())).then(() => {
        for (const entry of before) console.info('[world-local] worker counters before dispose', entry.index, JSON.stringify(entry.runtime));
      });
    };
  }, [refresh]);

  // Flush the queued save when the tab is hidden or closed, so a refresh after
  // the last write does not lose a settled point.
  useEffect(() => {
    const flush = () => { void sessionRef.current?.flushPersistence().catch(() => undefined); };
    // A real unload closes the session: it flushes the last settled point and
    // releases the writer lease immediately, so a reload does not have to wait
    // for the 30 s lease to expire. A bfcache freeze keeps the session alive.
    const onPageHide = (event: PageTransitionEvent) => {
      const session = sessionRef.current;
      if (!session) return;
      if (event.persisted) { void session.flushPersistence().catch(() => undefined); return; }
      void session.close().catch(() => undefined);
    };
    window.addEventListener('pagehide', onPageHide);
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush(); });
    return () => { window.removeEventListener('pagehide', onPageHide); };
  }, []);

  /** Explicit takeover after a "another tab owns this save" stop. The chosen
   * holder id is stored so the reload opens as that holder. */
  const takeOverLease = useCallback(async () => {
    const store = storeRef.current;
    const worldId = leaseWorldRef.current;
    if (!store || !worldId) return;
    const holderId = `session_takeover_${Date.now().toString(36)}`;
    try {
      sessionStorage.setItem(LEASE_TAKEOVER_KEY, holderId);
      await store.takeoverLease(worldId, holderId);
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? `${e.name}: ${e.message}` : String(e));
    }
  }, []);

  const submit = useCallback(async () => {
    const session = sessionRef.current;
    const text = input.trim();
    if (!session || !text || busy) return;
    setBusy(true); setError(null); setWarning(null); setPhase('thinking');
    const key = Date.now();
    const submittedAt = performance.now();
    submittedAtRef.current = submittedAt;
    const engines = [engineCounters('semantic', semanticRef.current), engineCounters('narration', narrationRef.current)]
      .filter((entry): entry is NonNullable<typeof entry> => entry != null);
    const record: WorldTurnRecord = {
      index: ((window as unknown as { __worldTurns?: WorldTurnRecord[] }).__worldTurns?.length ?? 0) + 1,
      input: text, acceptedMs: null, draftMs: null, programMs: null, mixedMs: null, cancelled: false, source: null,
      modelId: narrationRef.current?.info.modelId ?? semanticRef.current?.info.modelId ?? null,
      narrationModel: narrationArm.current.model ?? DEFAULT_NARRATION_MODEL,
      promptShape: narrationArm.current.shape ?? (narrationArm.current.mode === 'scene' ? 'prose-facts' : null),
      engines,
      clocks: {
        inputAtMs: 0, inputAt: new Date().toISOString(),
        pointCommittedAtMs: null, narrationStartedAtMs: null, firstReadableAtMs: null, firstReadableSource: null,
      },
    };
    turnRecordRef.current = record;
    const w = window as unknown as { __worldTurns?: WorldTurnRecord[] };
    (w.__worldTurns ??= []).push(record);
    setEntries((list) => [...list, { key, input: text, text: '', note: null, ms: null, draftMs: null, acceptedMs: null, programMs: null, mixedMs: null }]);
    setMessage('正在判断行动、结算并写正文…');
    setInput('');
    modelRef.current?.beginTurn();
    // The settlement side keeps its own per-submission ledger (which stages
    // ran, model calls, milliseconds). It is evidence, not page text.
    modelRef.current?.beginSubmission(text);
    deadlineHitRef.current = false;
    if (turnDeadlineRef.current) clearTimeout(turnDeadlineRef.current);
    turnDeadlineRef.current = setTimeout(() => {
      deadlineHitRef.current = true;
      console.info('[world-local] 295 s turn deadline: stopping automatic follow-up work');
      void session.cancel('turn_deadline').catch((error) => console.warn('[world-local] deadline cancel failed', error));
    }, 295_000);
    save(session.snapshot);
    const commandsAtStart = session.commandsPlayed;
    const playerPointsAtStart = Object.values(session.snapshot.transport.points ?? {}).filter((point) => point.trigger === 'player').length;
    try {
      const status = await session.submit(text);
      console.info('[world-local] turn status', status);
      await refresh();
      if (status.kind === 'stop' && status.reason === 'turn_in_progress') {
        // The previous turn is still settling; this input was not consumed.
        // Drop its placeholder and hand the text back instead of leaving an
        // empty "…" turn in the history.
        setEntries((list) => list.filter((entry) => entry.key !== key));
        setInput(text);
        setMessage('上一回合还在结算，等它结束再提交这一句。');
        return;
      }
      if (status.kind === 'stop') setMessage(`本轮停止：${status.reason}`);
      if (status.kind === 'stop' && status.reason === 'progress_conflict') {
        // The stored record was written by another writer/session. Play cannot
        // continue on a record whose revision the session does not own; the
        // honest recovery is an explicit reset (archives/deletes via reset()),
        // not silently playing on a diverged save.
        setError('本地存档被另一处写入过，本回合没有结算。请点右上角“重新开始”清掉这份存档（或回到原来的标签页继续）。');
      }
      setMessage(deadlineHitRef.current
        ? '本轮已到 295 秒时限：已停止后续自动推进；已结算的状态和已有文本都保留（未通过校验的文本会标明）。可以继续下一步行动。'
        : status.kind === 'stop' && status.reason === 'world_complete' ? '本轮已交还，继续输入下一步行动。' : status.kind === 'stop' ? `本轮停止：${status.reason}` : '本轮完成。');
    } catch (e) {
      console.error(e);
      const raw = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
      // The failure may come from a later automatic round after the player's
      // point committed. Refresh from the save first, so the committed view,
      // history count and entries are what the snapshot actually holds instead
      // of the pre-commit state the submit closure saw.
      try { await refresh(); } catch (refreshError) { console.warn('[world-local] refresh after failure failed', refreshError); }
      // A failed continuation can leave the advance open. Without this the
      // next submit is refused as turn_in_progress and the player waits with no
      // entry (3-turn d101 turn 2). Cancel it, then read the record again.
      if (session.snapshot.transport.advance) {
        try {
          await Promise.race([
            session.cancel('turn_failed'),
            new Promise((resolve) => setTimeout(resolve, 15_000)),
          ]);
        } catch (cancelError) { console.warn('[world-local] cancel after failure failed', cancelError); }
        try { await refresh(); } catch (refreshError) { console.warn('[world-local] refresh after cancel failed', refreshError); }
      }
      setEntries((list) => {
        const rebuilt = restoredEntries(session.snapshot);
        return rebuilt.length > list.length ? rebuilt : list;
      });
      // A submit can fail after its point was already committed: the player's
      // round settles and narrates, then an automatic follow-up round fails.
      // That committed prose must stay visible; wiping it and calling the whole
      // turn failed would hide a real state change.
      const committedPoints = Object.values(session.snapshot.transport.points ?? {}).filter((point) => point.trigger === 'player').length;
      const committed = committedPoints > playerPointsAtStart;
      if (committed) {
        setMessage('本轮已完成；后续自动回合没有结算，可以继续输入下一步行动。');
        setEntries((list) => updateLast(list, (entry) => ({
          ...entry,
          note: entry.note ?? '这一回合已结算并写入正文；随后系统自动推进的回合没有完成，状态仍以已结算部分为准。',
        })));
        setPhase('ready');
        setError(null);
        return;
      }
      // Settlement failures are typed (`settlement_failed:<task>:<reason>`) and
      // mean no point was committed; show a recoverable sentence instead of a
      // raw Error while keeping the technical detail in the console.
      const message = /settlement_failed/u.test(raw)
        ? '这一回合的结算没有完成，之前的历史和已结算状态都保留着。可以再试一次或换一句行动。'
        : raw;
      setError(message);
      setPhase('error');
      // The turn is over. Say so in the same words a completed turn uses, so
      // the player (and an automated reader) never waits on a turn that already
      // stopped with a settlement failure.
      setMessage('本轮停止：结算没有完成，可以重试。');
      // A failed turn is not a paragraph. Label the entry, never show "…" as
      // story text; if nothing was committed, give the sentence back so the
      // player can decide whether to retry.
      setEntries((list) => updateLast(list, (entry) => entry.acceptedMs == null
        ? { ...entry, text: '', failed: true, note: `本回合没有完成：${message}` }
        : entry));
      if (session.commandsPlayed === commandsAtStart) setInput(text);
    } finally {
      const live = turnRecordRef.current;
      if (live) {
        live.engines = [engineCounters('semantic', semanticRef.current), engineCounters('narration', narrationRef.current)]
          .filter((entry): entry is NonNullable<typeof entry> => entry != null);
        live.modelId = narrationRef.current?.info.modelId ?? semanticRef.current?.info.modelId ?? live.modelId;
        live.generations = [lastGeneration('semantic'), lastGeneration('narration')]
          .filter((note): note is GenerationNote => note != null);
      }
      if (turnDeadlineRef.current) { clearTimeout(turnDeadlineRef.current); turnDeadlineRef.current = null; }
      const submission = modelRef.current?.endSubmission() ?? null;
      if (submission && turnRecordRef.current) turnRecordRef.current.submission = submission;
      if (submission) {
        console.info('[world-local submission]', JSON.stringify({
          input: submission.inputText,
          ms: Math.round((submission.endedAtMs ?? 0) - submission.startedAtMs),
          resultsCalls: submission.resultsCalls,
          updatesCalls: submission.updatesCalls,
          continuationCalls: submission.continuationCalls,
          decision: submission.continuationDecision,
          stops: submission.stops,
          stageMs: submission.calls.map((call) => ({ task: call.task, key: call.key, stageMs: call.stageMs ?? null })),
        }));
        (window as unknown as { __worldSubmission?: unknown }).__worldSubmission = submission;
      }
      // Every exit from a submission clears the turn state, including an early
      // return for turn_in_progress; otherwise the page keeps painting a stage
      // that no longer exists while the harness waits for done.
      setStage('');
      setBusy(false);
    }
  }, [busy, input, refresh, save]);

  const cancelTurn = useCallback(async () => {
    const session = sessionRef.current;
    // During the cold load there is no session yet, but the stop button must
    // still cancel the model load. The device work is stopped either way.
    setMessage(session ? '正在取消本轮…' : '正在取消加载…');
    // Stop the device work first (including a cold load), then let the
    // controller conclude the round. The cancel gate discards any answer that
    // still arrives; the engine stays usable for the next turn.
    modelRef.current?.abortTurn();
    for (const engine of [semanticRef.current, narrationRef.current]) {
      const typed = engine as unknown as { cancelActive?: () => number } | null;
      try { typed?.cancelActive?.(); } catch { /* best effort: signal already aborts */ }
    }
    // A cancelled draft is not a committed turn: keep the text visible for
    // diagnosis but label it and drop any accepted timing.
    setEntries((list) => updateLast(list, (entry) => {
      const live = turnRecordRef.current;
      if (live && live.acceptedMs == null) live.cancelled = true;
      return entry.acceptedMs == null && entry.text
      ? { ...entry, cancelled: true, ms: null, note: entry.note ?? '本轮已取消，正文草稿未通过核对。' }
      : entry;
    }));
    if (!session) {
      // No round exists yet: nothing to conclude. The load is aborted; a reload
      // is the only honest next step because this page has no retry wiring yet.
      setPhase('error');
      setError('加载已取消。刷新页面可以重新开始。');
      setLoadSeconds(0);
      return;
    }
    try {
      const status = await session.cancel('player_cancelled');
      console.info('[world-local] cancel status', status);
      await refresh();
      setMessage('本轮已取消。可以重新输入行动。');
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? `${e.name}: ${e.message}` : String(e));
    } finally {
      setPhase('ready');
      setBusy(false);
    }
  }, [refresh]);

  const reset = useCallback(async () => {
    if (!confirm('清除本地存档并重新开始？')) return;
    const session = sessionRef.current;
    const store = storeRef.current;
    try {
      await session?.flushPersistence();
      if (store) await store.delete(session?.worldId ?? '', { force: true, sessionId: session?.sessionIdUsed });
    } catch (e) {
      console.warn('[world-local] could not delete the stored progress', e);
    }
    try { localStorage.removeItem(SAVE_KEY); } catch { /* ignored */ }
    window.location.reload();
  }, []);

  return (
    <main style={{ maxWidth: 920, margin: '0 auto', padding: '28px 20px 60px', fontFamily: 'system-ui, "Noto Serif CJK SC", serif', color: '#222', background: '#f7f3ea', minHeight: '100vh' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', borderBottom: '1px solid #d8ccb8', paddingBottom: 12, marginBottom: 18 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24, letterSpacing: 1 }}>龙族 · 自由一日</h1>
          <div style={{ fontSize: 12, color: '#7c6f5d', marginTop: 4 }}>全部在浏览器本地运行 · 服务器只负责存档</div>
        </div>
        <button onClick={reset} style={{ border: '1px solid #c9bda8', background: 'transparent', padding: '6px 10px', borderRadius: 6, cursor: 'pointer', color: '#6b5d4a' }}>重新开始</button>
      </header>

      <section style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 20 }}>
        <div>
          <div style={{ background: '#fffdf8', border: '1px solid #ded4c2', borderRadius: 10, padding: 18, minHeight: 280 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#7b6d59', marginBottom: 10 }}>
              <span>{view?.time ?? '—'} · {view?.place ?? '—'}</span>
              <span>
                {phase === 'thinking' ? (stage ? `结算中：${stage}` : '结算中…') : phase === 'streaming' ? '正在写正文…' : message}
                {busy && <button onClick={() => void cancelTurn()} style={{ marginLeft: 10, border: '1px solid #c9bda8', background: 'transparent', padding: '2px 8px', borderRadius: 6, cursor: 'pointer', color: '#6b5d4a' }}>取消本轮</button>}
                {phase === 'loading' && <button onClick={() => void cancelTurn()} style={{ marginLeft: 10, border: '1px solid #c9bda8', background: 'transparent', padding: '2px 8px', borderRadius: 6, cursor: 'pointer', color: '#6b5d4a' }}>取消加载</button>}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              {entries.length === 0 && <div style={{ color: '#8a7c68' }}>{phase === 'loading' ? `正在加载本地模型，第一次会久一些（已等待 ${loadSeconds}s，上限 120s）。` : '等待输入…'}</div>}
              {entries.map((entry) => (
                <article key={entry.key} style={{ borderLeft: '3px solid #e2d6c1', paddingLeft: 12 }}>
                  <div style={{ fontSize: 12, color: '#9a8b74', marginBottom: 6 }}>
                    你：{entry.input}
                    {entry.acceptedMs != null ? ` · 模型正文 ${(entry.acceptedMs / 1000).toFixed(1)}s（候选自检通过，未经独立复核）` : ''}
                    {entry.acceptedMs == null && entry.programMs != null ? ` · 程序成文 ${(entry.programMs / 1000).toFixed(1)}s（降级）` : ''}
                    {entry.acceptedMs == null && entry.mixedMs != null ? ` · 模型+程序句 ${(entry.mixedMs / 1000).toFixed(1)}s（部分降级）` : ''}
                    {entry.acceptedMs == null && entry.programMs == null && entry.draftMs != null ? ` · 草稿 ${(entry.draftMs / 1000).toFixed(1)}s（未核对）` : ''}
                  </div>
                  {entry.points && entry.points.length > 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {entry.points.map((part) => (
                        <div key={part.pointId}>
                          <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.9, fontSize: 16 }}>{part.text}</div>
                          <div style={{ fontSize: 11, color: part.source === 'model' ? '#6b7a5a' : '#a2762a', marginTop: 2 }}>
                            {part.source === 'model' ? '模型正文（候选自检通过，未经独立复核）'
                              : part.source === 'program' ? '程序按已结算事实成文（降级）'
                                : part.source === 'mixed' ? '模型句与程序句混合（部分降级）'
                                  : part.source === 'draft' ? '未通过自检的草稿，不是正文'
                                    : '来源未记录'}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.9, fontSize: 16 }}>{entry.text || (entry.failed || entry.cancelled || entry.restored ? '' : '…')}</div>
                  )}
                  {entry.failed && <div style={{ fontSize: 12, color: '#8b2a1e', marginTop: 6 }}>{entry.note ?? '本回合没有完成。'}</div>}
                  {entry.cancelled && <div style={{ fontSize: 12, color: '#8b2a1e', marginTop: 6 }}>本轮已取消，上方文字未通过核对，不计入正文。</div>}
                  {entry.note && <div style={{ fontSize: 12, color: '#a2762a', marginTop: 6 }}>{entry.cancelled ? '' : '正文已按已结算事实修正：'}{entry.note}</div>}
                </article>
              ))}
            </div>
          </div>

          {leaseBlocked && <div style={{ marginTop: 10, padding: '8px 10px', background: '#fff6e0', border: '1px solid #e6cf9d', borderRadius: 6, fontSize: 12, color: '#7a5a1c' }}>
            存档没有被改动。另一个标签页（或刚关闭的页面）还持有写入权。
            <button onClick={() => window.location.reload()} style={{ marginLeft: 8, border: '1px solid #c9bda8', background: 'transparent', padding: '2px 8px', borderRadius: 6, cursor: 'pointer', color: '#6b5d4a' }}>重试</button>
            <button onClick={() => void takeOverLease()} style={{ marginLeft: 6, border: '1px solid #c9bda8', background: 'transparent', padding: '2px 8px', borderRadius: 6, cursor: 'pointer', color: '#6b5d4a' }}>在这个标签页接管</button>
          </div>}
          {durable === false && <div style={{ marginTop: 10, padding: '8px 10px', background: '#fff6e0', border: '1px solid #e6cf9d', borderRadius: 6, fontSize: 12, color: '#7a5a1c' }}>这个浏览器没有可用的本地数据库，本局进度只保存在内存里，刷新会丢。</div>}
          {warning && <div style={{ marginTop: 10, padding: '8px 10px', background: '#fff6e0', border: '1px solid #e6cf9d', borderRadius: 6, fontSize: 12, color: '#7a5a1c', whiteSpace: 'pre-wrap' }}>{warning}</div>}
          {error && <div style={{ marginTop: 10, padding: '8px 10px', background: '#ffe8e5', border: '1px solid #e7b1a9', borderRadius: 6, fontSize: 12, color: '#8b2a1e', whiteSpace: 'pre-wrap' }}>{error}</div>}

          <div style={{ marginTop: 16 }}>
            <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void submit(); }} rows={3}
              placeholder="输入你要做的事，例如：我沿着车道向西回廊快走，贴着墙，注意听枪声。"
              style={{ width: '100%', boxSizing: 'border-box', padding: 12, font: 'inherit', lineHeight: 1.6, border: '1px solid #cfc3ae', borderRadius: 8, background: '#fffdf8', resize: 'vertical' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
              <span style={{ fontSize: 12, color: '#8a7c68' }}>Ctrl/⌘ + Enter 提交 · 模型只读取已结算状态</span>
              <button onClick={() => void submit()} disabled={busy || phase === 'loading' || !input.trim()}
                style={{ padding: '9px 20px', borderRadius: 7, border: 0, background: busy || phase === 'loading' ? '#b9ac96' : '#6d5232', color: '#fff', font: 'inherit', cursor: busy || phase === 'loading' ? 'default' : 'pointer' }}>
                {busy ? '结算中…' : '行动'}
              </button>
            </div>
          </div>
        </div>

        <aside style={{ fontSize: 13, color: '#5f5343' }}>
          <div style={{ background: '#fffdf8', border: '1px solid #ded4c2', borderRadius: 10, padding: 14 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: '#3b2f20', marginBottom: 8 }}>{view?.name ?? '路明非'}</div>
            <div>精神值：{view?.sanity ?? '—'}</div>
            <div style={{ marginTop: 4 }}>地点：{view?.place ?? '—'}</div>
            <div style={{ marginTop: 12, fontWeight: 600 }}>在附近</div>
            <div style={{ marginTop: 4 }}>{view?.visible.length ? view.visible.join('、') : '没有别人'}</div>
            <div style={{ marginTop: 12, fontWeight: 600 }}>当前任务</div>
            <ul style={{ paddingLeft: 18, margin: '6px 0 0', lineHeight: 1.6 }}>
              {(view?.tasks ?? []).map((task, index) => <li key={index} style={{ color: task.done ? '#9b8d78' : '#4b3d2b', textDecoration: task.done ? 'line-through' : 'none' }}>{task.goal}</li>)}
            </ul>
          </div>
          <div style={{ background: '#fffdf8', border: '1px solid #ded4c2', borderRadius: 10, padding: 14, marginTop: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>本地存档</div>
            <div style={{ fontSize: 12, color: '#7b6d59' }}>每次完整结算后写入浏览器 localStorage；刷新页面会恢复。中途刷新会回到上一次完整结算。</div>
            <div style={{ fontSize: 12, color: '#7b6d59', marginTop: 8 }}>已行动：{history.length} 次</div>
          </div>
        </aside>
      </section>
    </main>
  );
}

function updateLast(list: TurnEntry[], update: (entry: TurnEntry) => TurnEntry): TurnEntry[] {
  if (!list.length) return list;
  const copy = list.slice();
  copy[copy.length - 1] = update(copy[copy.length - 1]);
  return copy;
}


const STAGE_LABEL: Record<string, string> = {
  targets: '判断牵连',
  action: '角色行动',
  reaction: '即时反应',
  results: '结算',
  updates: '状态更新',
  continuation: '继续判断',
  narration: '写正文',
  pointPlan: '安排回合',
};
