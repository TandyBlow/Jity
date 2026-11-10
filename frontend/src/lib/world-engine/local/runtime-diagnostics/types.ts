/** Evidence records for the browser runtime. These extend the shared
 * CompletionEvidence with fields the page needs for trusted stage timing
 * (first token, first readable fragment, longest streaming gap, cancel-to-
 * stop latency, model load breakdown) without changing the public
 * InferenceEngine interface. Everything here is plain data: the recorder,
 * the wllama adapter and the inference queue all speak these shapes, and a
 * browser run can serialise them to JSON as-is. */
import type { CompletionEvidence } from '../../runtime/engine';

/** What asked for the stop. 'timeout' is the generation deadline; 'caller'
 * is the AbortSignal on the call; 'dispose' is engine teardown. */
export type AbortCause = 'caller' | 'timeout' | 'dispose';

export interface ModelLoadEvidence {
  kind: 'load';
  /** Normalised absolute URL (or the configured string outside a browser). */
  modelUrl: string;
  /** All shard URLs in load order; undefined for a single-file load. */
  modelUrls?: string[];
  modelId: string | null;
  contextSize: number;
  gpuLayers: number;
  numThreads: number | null;
  /** OPFS caching flag; false when the model was fetched into a blob. */
  useCache: boolean;
  directBlob: boolean;
  /** Time spent obtaining the bytes (fetch + blob). Null when OPFS served. */
  fetchMs: number | null;
  /** True when a hard-stop reload reused the previously fetched Blob. */
  fromCache?: boolean;
  /** Time spent inside wllama loadModel/loadModelFromUrl (parse + compile). */
  compileMs: number | null;
  totalMs: number;
  /** Abort budget for the load, null when the caller set none. */
  loadTimeoutMs?: number | null;
  outcome: 'loaded' | 'failed' | 'aborted' | 'discarded' | 'timeout';
  error?: string;
  /** Monotonic clock (performance.now) when the load finished. */
  at: number;
}

/** A generation record. Extends the shared CompletionEvidence so existing
 * onCompletion consumers keep working; the extra fields are additive. */
export interface GenerationEvidence extends CompletionEvidence {
  kind: 'generation';
  outcome: 'completed' | 'incomplete' | 'aborted' | 'timeout' | 'error';
  /** null before anything arrived. */
  firstChunkMs: number | null;
  firstTokenMs: number | null;
  /** First chunk with non-whitespace text: the first fragment a player can read. */
  firstReadableMs: number | null;
  /** Longest silence between two streamed chunks (device stall evidence). */
  maxStreamGapMs: number;
  streamChunks: number;
  /** Prompt tokens actually processed by llama.cpp (timings.prompt_n); a
   * warmed call reports only the uncached remainder. */
  promptTokens: number | null;
  contextSize: number;
  /** Prompt tokens reused from the KV cache (timings.cache_n). */
  cachedPromptTokens: number | null;
  maxTokens: number;
  cachePrompt: boolean;
  abortCause: AbortCause | null;
  /** Time from call start to the abort request. */
  abortRequestedMs: number | null;
  /** Abort request to confirmed stop (engine rejection or worker termination). */
  stoppedMs: number | null;
  /** True when the worker had to be terminated because abort did not settle. */
  hardStopped: boolean;
  error?: string;
  at: number;
}

export interface QueueEvidence {
  kind: 'queue';
  label: string;
  state: 'queued' | 'started' | 'resolved' | 'rejected' | 'aborted-queued'
    | 'aborted-running' | 'stopped' | 'disposed';
  queuedMs: number | null;
  runMs: number | null;
  /** For 'stopped': how long the device kept working after the caller abort. */
  stoppedAfterAbortMs?: number | null;
  depth: number;
  error?: string;
  at: number;
}

export type RuntimeDiagnosticsRecord = ModelLoadEvidence | GenerationEvidence | QueueEvidence;

export interface TimingStats {
  count: number;
  minMs: number | null;
  meanMs: number | null;
  p50Ms: number | null;
  p95Ms: number | null;
  maxMs: number | null;
}

export interface RuntimeDiagnosticsSummary {
  loads: {
    count: number;
    loaded: number;
    failed: number;
    aborted: number;
    discarded: number;
    timeout: number;
    lastModelId: string | null;
    lastContextSize: number | null;
    total: TimingStats;
    fetch: TimingStats;
    compile: TimingStats;
  };
  generations: {
    count: number;
    completed: number;
    incomplete: number;
    aborted: number;
    timeout: number;
    error: number;
    hardStops: number;
    firstChunk: TimingStats;
    firstToken: TimingStats;
    firstReadable: TimingStats;
    wall: TimingStats;
    maxStreamGap: TimingStats;
    promptTokens: TimingStats;
    /** cached / (processed + cached), averaged over calls that reported both. */
    meanCacheHitRatio: number | null;
  };
  cancellations: {
    count: number;
    caller: number;
    timeout: number;
    dispose: number;
    hardStops: number;
    stopLatency: TimingStats;
  };
  queue: {
    events: number;
    enqueued: number;
    started: number;
    resolved: number;
    rejected: number;
    abortedQueued: number;
    abortedRunning: number;
    stopped: number;
    maxDepth: number;
    queued: TimingStats;
    run: TimingStats;
  };
}

export interface RuntimeDiagnosticsSnapshot {
  generatedAt: string;
  records: RuntimeDiagnosticsRecord[];
  summary: RuntimeDiagnosticsSummary;
}
