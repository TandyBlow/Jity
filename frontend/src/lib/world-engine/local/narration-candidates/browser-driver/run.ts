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
}

interface DriverState {
  engines: Map<string, EngineSlot>;
  candidates: Map<string, CandidateSpec>;
  scenarios: Map<string, CandidateScenario>;
  /** Last accepted text per `candidateId::scenarioId`, used for continuations. */
  accepted: Map<string, string>;
  /** Module import cache so repeated runs do not re-import the candidate. */
  modules: Map<string, Record<string, unknown>>;
}

const GLOBAL_KEY = '__jityBrowserCandidateDriver';
const globalStore = globalThis as unknown as Record<string, DriverState | undefined>;

function state(): DriverState {
  let existing = globalStore[GLOBAL_KEY];
  if (!existing) {
    existing = { engines: new Map(), candidates: new Map(), scenarios: new Map(), accepted: new Map(), modules: new Map() };
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
  const scenarios = await buildScenarios({
    set: config.set,
    freeDay: config.freeDay ?? null,
    include: config.include ?? null,
    exclude: config.exclude ?? null,
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
}

/** Load one model, or return the cached slot when the queue already loaded it.
 * `coldStart` tells the evidence whether this run paid the load. */
export async function loadEngine(config: LoadConfig): Promise<EngineEvidence & { coldStart: boolean }> {
  const store = state();
  const cached = store.engines.get(config.modelUrl);
  if (cached && config.reuse) return { ...cached.evidence, coldStart: false };
  if (cached) {
    await cached.dispose();
    store.engines.delete(config.modelUrl);
  }
  const webgpuAvailable = typeof navigator !== 'undefined' && 'gpu' in navigator;
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
  store.engines.set(config.modelUrl, { engine, evidence, dispose: () => engine.dispose() });
  return { ...evidence, coldStart: true };
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
  store.engines.set(modelUrl, { engine, evidence: resolved, dispose: () => engine.dispose() });
  return resolved;
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
  const slot = store.engines.get(modelUrl);
  if (!slot) throw new Error(`engine_not_loaded_for:${modelUrl || 'unset'}`);

  const mod = await importCandidate(candidate);
  const { fn, usedName } = resolveGenerator(mod, candidate.exportName);

  const continuationKey = scenario.continuesFrom ? `${candidate.id}::${scenario.continuesFrom}` : null;
  const priorText = continuationKey ? store.accepted.get(continuationKey) ?? null : null;
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
      committed: structuredClone(scenario.committed),
      inputText: scenario.inputText,
      priorText,
      policy: structuredClone({
        ...scenario.policy,
        ...(config.maxTokens !== undefined ? { maxTokens: config.maxTokens } : {}),
        ...(config.temperature !== undefined ? { temperature: config.temperature } : {}),
        ...(config.policyOverride ?? {}),
      }),
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

  const contract = validateCandidateResult(rawResult);
  const result = contract.result;
  const text = typeof result?.text === 'string' ? result.text : '';
  const paragraphs = splitParagraphs(text);
  if (result?.accepted && text.trim()) store.accepted.set(`${candidate.id}::${scenario.id}`, text);
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
      policy: scenario.policy,
      priorText,
    },
    result: {
      text,
      chars: [...text].length,
      paragraphs,
      firstParagraph: paragraphs[0] ?? '',
      lastParagraph: paragraphs.at(-1) ?? '',
      accepted: result?.accepted === true,
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
    contract: {
      ok: contract.ok && error === null,
      missing: contract.missing,
      notes: [
        ...contract.notes,
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
