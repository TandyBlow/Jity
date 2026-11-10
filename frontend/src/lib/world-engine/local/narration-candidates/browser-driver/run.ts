/** Browser-side driver for the shared candidate queue.
 *
 * The Node script (scripts/quality-candidates/run-browser-candidates.mjs) owns
 * the server, the browser, the resource lease and the evidence file. This
 * module owns only what must run inside the page: one real engine per model
 * (cached across calls so a queue shares one cold start), one candidate module
 * import, and one scenario at a time.
 *
 * It never authors prose, never edits a candidate's result and never scores
 * quality. Contract violations and errors are returned as evidence.
 */
import { isAbortError } from '../../../runtime/engine';
import { WllamaInferenceEngine } from '../../../runtime/wllama-engine';
import type { InferenceEngine } from '../../../runtime/engine';
import { buildScenarios, type FreeDayWorldAsset, type ScenarioSet } from './scenarios';
import type {
  AttemptEvidence, CandidateResult, CandidateScenario, CandidateSpec, EngineEvidence,
  GenerateCandidate, ProgressEvent, RunEvidence,
} from './types';

interface EngineSlot {
  engine: InferenceEngine;
  evidence: EngineEvidence;
  dispose: () => Promise<void>;
  /** A hard-stopped worker drops the loaded model (08's abort path nulls
   * `info.modelId` and `instance`). A reused dead engine would make the next
   * candidate fail for a reason that belongs to the previous one. */
  dead: boolean;
}

interface DriverState {
  engines: Map<string, EngineSlot>;
  candidates: Map<string, CandidateSpec>;
  scenarios: Map<string, CandidateScenario>;
  /** Last accepted text per `candidateId::scenarioId`, used for continuations. */
  accepted: Map<string, string>;
  /** Last non-empty text shown for a scenario (accepted or fallback). A page
   * displays fallback prose too, so a later turn may legitimately continue
   * from it; the evidence says which source was used. */
  displayed: Map<string, string>;
  /** Module import cache so repeated runs do not re-import the candidate. */
  modules: Map<string, Record<string, unknown>>;
}

const GLOBAL_KEY = '__jityBrowserCandidateDriver';
const globalStore = globalThis as unknown as Record<string, DriverState | undefined>;

function state(): DriverState {
  let existing = globalStore[GLOBAL_KEY];
  if (!existing) {
    existing = { engines: new Map(), candidates: new Map(), scenarios: new Map(), accepted: new Map(), displayed: new Map(), modules: new Map() };
    globalStore[GLOBAL_KEY] = existing;
  }
  return existing;
}

export interface PrepareConfig {
  set: ScenarioSet;
  freeDay?: FreeDayWorldAsset | null;
  include?: string[] | null;
  exclude?: string[] | null;
  candidates: CandidateSpec[];
  /** Lane 01's `narration-input` module. When given, scenario input is built by
   * the shipped renderer (`result-v2` by default) instead of the legacy prompt,
   * so the queue feeds candidates the same text the page does. */
  productInput?: {
    moduleUrl: string;
    format?: 'result-v2' | 'legacy';
    exportName?: string;
  } | null;
}

export interface ScenarioSummary {
  id: string;
  label: string;
  note: string;
  inputChars: number;
  identity: CandidateScenario['identity'];
  scenePresent: number;
  sceneObjects: number;
}

/** Build and register the scenario set; returns only what the queue needs to
 * decide what to run (no world state is copied into evidence here). */
export async function prepare(config: PrepareConfig): Promise<ScenarioSummary[]> {
  const store = state();
  let inputBuilder: import('./scenarios').InputBuilder | null = null;
  let productInputError: string | null = null;
  if (config.productInput) {
    try {
      const module = await import(/* @vite-ignore */ config.productInput.moduleUrl) as Record<string, unknown>;
      const build = (module.buildNarrationInput ?? module.projectNarrationInput) as
        ((args: unknown, options?: unknown) => Record<string, unknown>) | undefined;
      if (typeof build !== 'function') throw new Error('buildNarrationInput_missing');
      const format = config.productInput.format ?? 'result-v2';
      inputBuilder = (args) => {
        const built = build({
          before: args.before ?? args.after,
          after: args.after,
          delta: args.delta.entityDeltas,
          timeAdvance: args.delta.timeAdvance ?? { boundary: 'instant', duration: { amount: 0, unit: 'second' } },
          viewpointId: args.viewpointId,
        }, { model: format });
        const rendered = (built.rendered ?? built) as { text?: unknown } | undefined;
        const text = typeof rendered?.text === 'string' ? rendered.text : null;
        if (!text) throw new Error('product_input_render_empty');
        return text;
      };
    } catch (error) {
      productInputError = error instanceof Error ? error.message : String(error);
      throw new Error(`product_input_failed:${productInputError}`);
    }
  }
  const scenarios = await buildScenarios({
    set: config.set,
    freeDay: config.freeDay ?? null,
    include: config.include ?? null,
    exclude: config.exclude ?? null,
    inputBuilder,
  });
  store.scenarios = new Map(scenarios.map((scenario) => [scenario.id, scenario]));
  store.candidates = new Map(config.candidates.map((candidate) => [candidate.id, candidate]));
  return scenarios.map((scenario) => ({
    id: scenario.id,
    label: scenario.label,
    note: scenario.note,
    inputChars: scenario.inputText.length,
    identity: scenario.identity,
    scenePresent: scenario.scene.present.length,
    sceneObjects: scenario.scene.objects.length,
  }));
}

export interface LoadConfig {
  modelUrl: string;
  contextSize: number;
  threads: number;
  gpu: boolean;
  /** Reuse an already-loaded engine for the same URL (default true). */
  reuse: boolean;
  /** Candidate-owned loader; when present it builds the engine so the real
   * chat template is used. */
  loader?: import('./types').EngineLoaderSpec | null;
}

/** Engine slots are keyed by model AND loader: an engine built by team A's
 * loader is not the same engine as the shared wllama one. */
function engineKey(modelUrl: string, loader?: import('./types').EngineLoaderSpec | null): string {
  return loader ? `${modelUrl}::${loader.moduleUrl}::${loader.exportName}::${loader.modelId ?? ''}` : modelUrl;
}

/** Load one model, or return the cached slot when the queue already loaded it.
 * `coldStart` tells the evidence whether this run paid the load. */
export async function loadEngine(config: LoadConfig): Promise<EngineEvidence & { coldStart: boolean }> {
  const store = state();
  const key = engineKey(config.modelUrl, config.loader);
  const cached = store.engines.get(key);
  if (cached && config.reuse && !cached.dead) return { ...cached.evidence, coldStart: false };
  let reloadReason: string | null = null;
  if (cached) {
    reloadReason = cached.dead ? 'engine_dead_after_previous_run' : 'reuse_disabled';
    await cached.dispose().catch(() => undefined);
    store.engines.delete(key);
  }
  const webgpuAvailable = typeof navigator !== 'undefined' && 'gpu' in navigator;
  if (config.loader) {
    const mod = await import(/* @vite-ignore */ config.loader.moduleUrl) as Record<string, unknown>;
    const load = mod[config.loader.exportName];
    if (typeof load !== 'function') throw new Error(`engine_loader_missing:${config.loader.exportName}`);
    const specFactory = mod.modelSpec;
    const spec = typeof specFactory === 'function' && config.loader.modelId
      ? (specFactory as (id: string) => unknown)(config.loader.modelId)
      : null;
    const started = performance.now();
    const loaded = await (load as (spec: unknown, options: Record<string, unknown>) => Promise<Record<string, unknown>>)(spec, {
      modelRoot: config.loader.modelRoot ?? '/models',
      preferGpu: config.gpu,
      forceCpu: !config.gpu,
      contextSize: config.contextSize,
      numThreads: config.threads,
    });
    const loadMs = typeof loaded.loadMs === 'number' ? loaded.loadMs : performance.now() - started;
    const engine = loaded.engine as InferenceEngine;
    if (!engine) throw new Error('engine_loader_returned_no_engine');
    const diagnostics = engine instanceof WllamaInferenceEngine ? engine.diagnostics : null;
    const backend = typeof loaded.backend === 'string' ? loaded.backend : 'unknown';
    const evidence: EngineEvidence = {
      modelUrl: config.modelUrl,
      loadMs,
      info: { backend: engine.info.backend, modelId: engine.info.modelId },
      diagnostics,
      webgpuAvailable,
      gpuRequested: config.gpu,
      backendNote: `${backend} backend reported by the candidate loader; requested gpu=${config.gpu}`,
      loader: {
        moduleUrl: config.loader.moduleUrl,
        exportName: config.loader.exportName,
        modelId: config.loader.modelId ?? null,
        backend,
        fallback: loaded.fallback ?? null,
        attempts: loaded.attempts ?? null,
      },
    };
    store.engines.set(key, { engine, evidence, dispose: () => engine.dispose(), dead: false });
    return { ...evidence, coldStart: true, reloadReason } as EngineEvidence & { coldStart: boolean; reloadReason: string | null };
  }
  const engine = new WllamaInferenceEngine({
    modelUrl: new URL(config.modelUrl, location.href).href,
    contextSize: config.contextSize,
    numThreads: config.threads,
    nGpuLayers: config.gpu ? 99999 : 0,
  });
  const started = performance.now();
  await engine.load();
  const loadMs = performance.now() - started;
  const diagnostics = engine instanceof WllamaInferenceEngine ? engine.diagnostics : null;
  const evidence: EngineEvidence = {
    modelUrl: config.modelUrl,
    loadMs,
    info: { backend: engine.info.backend, modelId: engine.info.modelId },
    diagnostics,
    webgpuAvailable,
    gpuRequested: config.gpu,
    backendNote: config.gpu
      ? (webgpuAvailable ? 'WebGPU layers requested; backend not independently verified' : 'WebGPU requested but navigator.gpu is unavailable; wllama will fall back')
      : 'CPU-only by explicit request (nGpuLayers=0); no WebGPU claim',
  };
  store.engines.set(key, { engine, evidence, dispose: () => engine.dispose(), dead: false });
  return { ...evidence, coldStart: true, reloadReason } as EngineEvidence & { coldStart: boolean; reloadReason: string | null };
}

/** Register an already-built engine for a model URL. The wllama loader is the
 * production path; this entry exists for injected engines (tests, a future
 * backend) so the queue mechanics do not depend on one loader. */
export function attachEngine(modelUrl: string, engine: InferenceEngine, evidence?: Partial<EngineEvidence>): EngineEvidence {
  const store = state();
  const resolved: EngineEvidence = {
    modelUrl,
    loadMs: evidence?.loadMs ?? 0,
    info: evidence?.info ?? { backend: engine.info.backend, modelId: engine.info.modelId },
    diagnostics: evidence?.diagnostics ?? null,
    webgpuAvailable: evidence?.webgpuAvailable ?? false,
    gpuRequested: evidence?.gpuRequested ?? false,
    backendNote: evidence?.backendNote ?? 'injected engine (no loader evidence)',
  };
  store.engines.set(modelUrl, { engine, evidence: resolved, dispose: () => engine.dispose(), dead: false });
  return resolved;
}

export interface EngineProbeConfig {
  /** Plain engine slot without a candidate loader. */
  modelUrl: string;
  prompt: string;
  maxTokens: number;
  timeoutMs: number;
  temperature?: number;
}

/** Minimal stack probe: one plain completion on the loaded engine. It proves
 * whether the browser/wllama/page path produces tokens at all, separately from
 * any candidate prompt. It is not a quality sample. */
export async function probeEngine(config: EngineProbeConfig): Promise<Record<string, unknown>> {
  const store = state();
  const slot = store.engines.get(engineKey(config.modelUrl, null));
  if (!slot) throw new Error(`engine_not_loaded_for:${config.modelUrl}`);
  const progress: string[] = [];
  const started = performance.now();
  const text = await slot.engine.complete(config.prompt, {
    maxTokens: config.maxTokens,
    temperature: config.temperature ?? 0.7,
    timeoutMs: config.timeoutMs,
    onProgress: (event) => { progress.push(event.raw); },
  });
  return {
    text,
    chars: [...text].length,
    wallMs: performance.now() - started,
    progressEvents: progress.length,
    lastProgressChars: progress.length ? [...progress.at(-1) ?? ''].length : 0,
    modelUrl: config.modelUrl,
  };
}

export interface RunOneConfig {
  candidateId: string;
  scenarioId: string;
  /** Runner-level safety net; the candidate still owns its own policy deadline. */
  hardTimeoutMs: number;
  maxTokens?: number;
  temperature?: number;
  /** Candidate-specific policy keys; copied over the shared policy. */
  policyOverride?: Record<string, unknown> | null;
  /** Program-only run: supply an engine that throws if the candidate asks for
   * inference, so a composer/realizer path can run without loading weights. */
  stubEngine?: boolean;
  /** Which earlier text a chained scenario continues from. `accepted` (default)
   * only carries verified prose; `displayed` carries whatever the page would
   * have shown, including fallback, and records that in `priorSource`. */
  continuation?: 'accepted' | 'displayed';
}

function createStubEngine(): InferenceEngine {
  return {
    info: { backend: 'stub', modelId: null },
    async load() { /* no weights */ },
    async complete() { throw new Error('engine_unavailable:stub_engine'); },
    async dispose() { /* nothing loaded */ },
  };
}

function splitParagraphs(text: string): string[] {
  const normalized = text.replace(/\r\n?/g, '\n').replace(/※/g, '\n\n');
  const blocks = normalized.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
  if (blocks.length > 1) return blocks;
  return normalized.split('\n').map((line) => line.trim()).filter(Boolean);
}

/** First readable segment from real streaming events. A paragraph break or
 * enough visible characters qualifies; a single partial clause does not. */
function firstReadableAt(progress: readonly (ProgressEvent & { atMs?: number })[]): number | null {
  for (const event of progress) {
    const text = typeof event.text === 'string' ? event.text : '';
    if (!text) continue;
    const normalized = text.replace(/\r\n?/g, '\n');
    const visible = normalized.replace(/\s/g, '').length;
    if (normalized.includes('※') || /\n\s*\n/.test(normalized) || visible >= 80) {
      return typeof event.atMs === 'number' ? event.atMs : null;
    }
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Normalize the many candidate attempt records without changing them: the
 * original object stays in `source`, the lifted fields are read with
 * fallbacks. A missing prompt is reported as null, never fabricated. */
function normalizeAttempts(raw: unknown[]): AttemptEvidence[] {
  return raw.map((entry, index) => {
    const attempt = isRecord(entry) ? entry : {};
    const prompt = typeof attempt.prompt === 'string' ? attempt.prompt : null;
    const cleaned = typeof attempt.cleaned === 'string' ? attempt.cleaned : null;
    const issues = Array.isArray(attempt.issues) ? attempt.issues : [];
    return {
      index: typeof attempt.attempt === 'number' ? attempt.attempt : index + 1,
      prompt,
      promptChars: typeof attempt.promptChars === 'number' ? attempt.promptChars : prompt?.length ?? null,
      raw: typeof attempt.raw === 'string' ? attempt.raw : null,
      cleaned,
      finishReason: typeof attempt.finishReason === 'string' ? attempt.finishReason : null,
      error: typeof attempt.error === 'string' ? attempt.error : null,
      durationMs: typeof attempt.durationMs === 'number' ? attempt.durationMs : null,
      firstTokenMs: typeof attempt.firstTokenMs === 'number' ? attempt.firstTokenMs : null,
      accepted: typeof attempt.accepted === 'boolean' ? attempt.accepted : null,
      issues,
      source: entry,
    };
  });
}

/** Public contract check: teams can run this on their own result object. */
export function validateCandidateResult(result: unknown): { ok: boolean; missing: string[]; notes: string[]; result: CandidateResult | null } {
  if (!isRecord(result)) {
    return { ok: false, missing: ['result_object'], notes: [], result: null };
  }
  const missing: string[] = [];
  const notes: string[] = [];
  if (typeof result.text !== 'string') missing.push('text');
  if (typeof result.accepted !== 'boolean') missing.push('accepted');
  if (!Array.isArray(result.rawAttempts)) missing.push('rawAttempts');
  if (!Array.isArray(result.issues)) missing.push('issues');
  if (!isRecord(result.timings)) missing.push('timings');
  if (typeof result.strategyVersion !== 'string') missing.push('strategyVersion');
  if (typeof result.text === 'string' && result.text.trim().length === 0) notes.push('empty_text');
  if (typeof result.accepted === 'boolean' && result.accepted && typeof result.text === 'string' && result.text.trim().length === 0) {
    notes.push('accepted_with_empty_text');
  }
  return { ok: missing.length === 0, missing, notes, result: result as CandidateResult };
}

/** Resolve a candidate export. Teams were told `generateCandidate`; 02's
 * existing arm exports `generateCommittedNarration`, which is accepted as a
 * compatibility fallback and recorded. */
function resolveGenerator(mod: Record<string, unknown>, exportName: string): { fn: GenerateCandidate; usedName: string } {
  const names = [exportName, 'generateCandidate', 'generateCommittedNarration'];
  for (const name of names) {
    const value = mod[name];
    if (typeof value === 'function') return { fn: value as GenerateCandidate, usedName: name };
  }
  throw new Error(`candidate_export_missing:${names.join('|')}`);
}

export interface InspectResult {
  candidateId: string;
  moduleUrl: string;
  usedExport: string;
  moduleExports: string[];
  hasDocumentedExport: boolean;
}

async function importCandidate(candidate: CandidateSpec): Promise<Record<string, unknown>> {
  const store = state();
  const cached = store.modules.get(candidate.moduleUrl);
  if (cached) return cached;
  const mod = await import(/* @vite-ignore */ candidate.moduleUrl) as Record<string, unknown>;
  store.modules.set(candidate.moduleUrl, mod);
  return mod;
}

/** Import a candidate module and resolve its generator without loading a model.
 * This is the fast contract check teams can run themselves before a queue
 * slot: it proves the module loads in the real browser and which export the
 * driver will call. */
export async function inspectCandidate(candidate: CandidateSpec): Promise<InspectResult> {
  const mod = await importCandidate(candidate);
  const { usedName } = resolveGenerator(mod, candidate.exportName);
  return {
    candidateId: candidate.id,
    moduleUrl: candidate.moduleUrl,
    usedExport: usedName,
    moduleExports: Object.keys(mod).sort(),
    hasDocumentedExport: typeof mod.generateCandidate === 'function',
  };
}

export async function runOne(config: RunOneConfig): Promise<RunEvidence> {
  const store = state();
  const candidate = store.candidates.get(config.candidateId);
  if (!candidate) throw new Error(`candidate_not_registered:${config.candidateId}`);
  const scenario = store.scenarios.get(config.scenarioId);
  if (!scenario) throw new Error(`scenario_not_prepared:${config.scenarioId}`);
  const modelUrl = candidate.modelUrl ?? '';
  const slot: EngineSlot = config.stubEngine
    ? {
      engine: createStubEngine(),
      evidence: {
        modelUrl: '', loadMs: 0, info: { backend: 'stub', modelId: null }, diagnostics: null,
        webgpuAvailable: false, gpuRequested: false,
        backendNote: 'no engine loaded (--no-engine); program-only candidate path',
      },
      dispose: async () => undefined,
      dead: false,
    }
    : store.engines.get(engineKey(modelUrl, candidate.loader))!;
  if (!slot) throw new Error(`engine_not_loaded_for:${modelUrl || 'unset'}`);

  const mod = await importCandidate(candidate);
  const { fn, usedName } = resolveGenerator(mod, candidate.exportName);

  const continuationKey = scenario.continuesFrom ? `${candidate.id}::${scenario.continuesFrom}` : null;
  const continuationMode = config.continuation ?? 'accepted';
  const priorAccepted = continuationKey ? store.accepted.get(continuationKey) ?? null : null;
  const priorDisplayed = continuationKey ? store.displayed.get(continuationKey) ?? null : null;
  const priorText = continuationMode === 'displayed' ? priorDisplayed : priorAccepted;
  const priorSource = !continuationKey ? null
    : priorText === null ? 'none'
      : priorText === priorAccepted ? 'accepted' : 'displayed_fallback';
  // Candidates that project from state (C's constrained entry) receive the
  // settled before/after alongside the fact packet. The packet stays the
  // authority; these are the same reads it was derived from.
  const committedForCandidate = {
    ...structuredClone(scenario.committed),
    state: structuredClone(scenario.after),
    beforeState: scenario.before ? structuredClone(scenario.before) : null,
    timeAdvance: scenario.delta.timeAdvance,
    entityDeltas: structuredClone(scenario.delta.entityDeltas),
  };
  const effectivePolicy = structuredClone({
    ...scenario.policy,
    ...(config.maxTokens !== undefined ? { maxTokens: config.maxTokens } : {}),
    ...(config.temperature !== undefined ? { temperature: config.temperature } : {}),
    ...(config.policyOverride ?? {}),
  });
  const progress: (ProgressEvent & { atMs?: number })[] = [];
  const startedAt = new Date().toISOString();
  const started = performance.now();
  const controller = new AbortController();
  let runnerTimedOut = false;
  const timer = setTimeout(() => { runnerTimedOut = true; controller.abort(); }, Math.max(1000, config.hardTimeoutMs));
  let rawResult: unknown = null;
  let error: string | null = null;
  try {
    rawResult = await fn({
      engine: slot.engine,
      committed: committedForCandidate,
      // The same settled read is offered in the shapes teams already use
      // (03 takes state/before/delta; 02/04/08 read committed/inputText).
      state: structuredClone(scenario.after),
      before: scenario.before ? structuredClone(scenario.before) : null,
      delta: structuredClone({ timeAdvance: scenario.delta.timeAdvance, entityDeltas: scenario.delta.entityDeltas }),
      inputText: scenario.inputText,
      priorText,
      policy: effectivePolicy,
      signal: controller.signal,
      onProgress: (event) => {
        progress.push({ ...event, atMs: Math.round(performance.now() - started) });
      },
    });
  } catch (caught) {
    error = runnerTimedOut
      ? `runner_timeout:${config.hardTimeoutMs}ms`
      : isAbortError(caught)
        ? 'runner_aborted'
        : caught instanceof Error ? `${caught.name}: ${caught.message}` : String(caught);
  } finally {
    clearTimeout(timer);
  }
  const wallMs = performance.now() - started;

  // Duck-typed liveness: both the shared adapter and candidate-owned engines
  // keep `instance` and null it on a hard stop / dispose. Missing field means
  // an injected engine, which has no such lifecycle.
  const rawEngine = slot.engine as unknown as { instance?: unknown };
  const hasInstanceField = 'instance' in rawEngine;
  const engineAlive = hasInstanceField ? rawEngine.instance != null : true;
  if (!engineAlive) slot.dead = true;

  const contract = validateCandidateResult(rawResult);
  const result = contract.result;
  const text = typeof result?.text === 'string' ? result.text : '';
  const paragraphs = splitParagraphs(text);
  const accepted = result?.accepted === true && text.trim().length > 0;
  const acceptedButEmpty = result?.accepted === true && text.trim().length === 0;
  if (accepted) store.accepted.set(`${candidate.id}::${scenario.id}`, text);
  if (text.trim()) store.displayed.set(`${candidate.id}::${scenario.id}`, text);
  const attempts = Array.isArray(result?.rawAttempts) ? normalizeAttempts(result.rawAttempts) : [];
  const timings = isRecord(result?.timings) ? result.timings as RunEvidence['result']['timings'] : null;
  const extras = result ? Object.keys(result).filter((key) => !['text', 'accepted', 'rawAttempts', 'issues', 'timings', 'strategyVersion'].includes(key)) : [];

  return {
    runId: `${candidate.id}::${scenario.id}::${Date.now().toString(36)}`,
    candidateId: candidate.id,
    owner: candidate.owner,
    moduleUrl: candidate.moduleUrl,
    exportName: usedName,
    modelUrl,
    scenarioId: scenario.id,
    startedAt,
    wallMs,
    coldStart: false,
    loadMs: slot.evidence.loadMs,
    identity: scenario.identity,
    input: {
      textChars: scenario.inputText.length,
      text: scenario.inputText,
      scene: scenario.scene,
      policy: effectivePolicy,
      priorText,
      priorSource,
      committedExtras: ['state', 'beforeState', 'timeAdvance', 'entityDeltas'],
    },
    result: {
      text,
      chars: [...text].length,
      paragraphs,
      firstParagraph: paragraphs[0] ?? '',
      lastParagraph: paragraphs.at(-1) ?? '',
      accepted,
      status: typeof result?.status === 'string' ? result.status : null,
      strategyVersion: typeof result?.strategyVersion === 'string' ? result.strategyVersion : null,
      timings,
      issues: Array.isArray(result?.issues) ? result.issues : [],
      attempts,
      extraKeys: extras,
    },
    progress: {
      count: progress.length,
      firstAtMs: progress.length ? progress[0].atMs ?? null : null,
      lastAtMs: progress.length ? progress.at(-1)?.atMs ?? null : null,
      firstReadableAtMs: firstReadableAt(progress),
      tail: progress.slice(-6).map((event) => ({ ...event, atMs: undefined })),
    },
    engineAfter: { alive: engineAlive, modelId: slot.engine.info.modelId },
    contract: {
      // A candidate must never turn an empty accepted result into evidence of
      // success. Keep the raw accepted flag out of the verdict and fail the
      // contract, so the queue records a failure for the owner.
      ok: contract.ok && error === null && !acceptedButEmpty,
      missing: contract.missing,
      notes: [
        ...contract.notes,
        ...(acceptedButEmpty && !contract.notes.includes('accepted_with_empty_text') ? ['accepted_with_empty_text'] : []),
        ...(continuationKey && !priorText ? ['continuation_source_missing'] : []),
        ...(error ? [`error:${error}`] : []),
      ],
    },
    error,
  };
}

/** Dispose every cached engine (called once at the end of a queue). */
export async function disposeEngines(): Promise<string[]> {
  const store = state();
  const disposed: string[] = [];
  for (const [url, slot] of store.engines) {
    await slot.dispose();
    disposed.push(url);
  }
  store.engines.clear();
  return disposed;
}

/** Introspection for a dry check: which engines are currently loaded. */
export function loadedModels(): string[] {
  return [...state().engines.keys()];
}
