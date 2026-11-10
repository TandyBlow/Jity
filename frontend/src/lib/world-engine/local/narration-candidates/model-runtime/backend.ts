/** Loading a catalog checkpoint on this machine, with an honest record of
 * which backend actually ran.
 *
 * wllama exposes no public "ggml backend in use" flag, so this module does
 * not invent one. It records what was requested (n_gpu_layers), whether the
 * browser exposes WebGPU, whether the WebGPU attempt loaded, and on which
 * attempt the engine became usable. The probe script adds per-call timings
 * and the page console's backend log lines as separate evidence.
 *
 * A WebGPU load failure falls back to CPU by creating a NEW engine: the
 * failed engine already exited its worker, and its n_gpu_layers setting is
 * fixed at construction.
 */
import { WllamaInferenceEngine, type ChatMessage, type WllamaEngineOptions } from '../../../runtime/wllama-engine';
import type { GenerationEvidence, ModelLoadEvidence } from '../../runtime-diagnostics/types';
import type { ModelSpec } from './types';

export interface LoadCandidateOptions {
  /** URL prefix for the GGUF. Default '/models'. */
  modelRoot?: string;
  /** Try WebGPU first (default yes when the browser exposes navigator.gpu). */
  preferGpu?: boolean;
  /** Force CPU regardless of WebGPU availability. */
  forceCpu?: boolean;
  signal?: AbortSignal;
  contextSize?: number;
  numThreads?: number;
  abortGraceMs?: number;
  /** Load records always; generation records too when an observer wants
   * them (the adapter's load path never generates, so typically only loads). */
  onEvidence?: (record: ModelLoadEvidence | GenerationEvidence) => void;
}

export interface BackendAttempt {
  backend: 'webgpu' | 'cpu';
  gpuLayers: number;
  ok: boolean;
  loadMs: number;
  error?: string;
}

export interface LoadedCandidateModel {
  spec: ModelSpec;
  engine: WllamaInferenceEngine;
  backend: 'webgpu' | 'cpu';
  /** Null when the first attempt succeeded. */
  fallback: { from: 'webgpu'; reason: string } | null;
  attempts: BackendAttempt[];
  loadMs: number;
  evidence: ModelLoadEvidence[];
  webgpuAvailable: boolean;
}

export function webgpuAvailable(): boolean {
  return typeof navigator !== 'undefined' && Boolean((navigator as Navigator & { gpu?: unknown }).gpu);
}

export function modelUrlFor(spec: ModelSpec, modelRoot = '/models'): string {
  return `${modelRoot.replace(/\/$/, '')}/${spec.gguf}`;
}

function engineOptions(spec: ModelSpec, options: LoadCandidateOptions, backend: 'webgpu' | 'cpu'): WllamaEngineOptions {
  return {
    modelUrl: modelUrlFor(spec, options.modelRoot ?? '/models'),
    contextSize: options.contextSize ?? spec.recommended.contextSize,
    numThreads: options.numThreads ?? spec.recommended.numThreads,
    nGpuLayers: backend === 'webgpu' ? spec.recommended.gpuLayers : 0,
    abortGraceMs: options.abortGraceMs ?? 2500,
    useCache: false,
    directBlob: true,
  };
}

async function attemptLoad(
  spec: ModelSpec,
  options: LoadCandidateOptions,
  backend: 'webgpu' | 'cpu',
  evidence: ModelLoadEvidence[],
): Promise<{ engine: WllamaInferenceEngine; attempt: BackendAttempt }> {
  const engine = new WllamaInferenceEngine({
    ...engineOptions(spec, options, backend),
    onEvidence: (record) => {
      if (record.kind === 'load') evidence.push(record);
      options.onEvidence?.(record);
    },
  });
  const started = performance.now();
  try {
    await engine.load({ signal: options.signal });
    return {
      engine,
      attempt: { backend, gpuLayers: backend === 'webgpu' ? spec.recommended.gpuLayers : 0, ok: true, loadMs: performance.now() - started },
    };
  } catch (error) {
    await engine.dispose().catch(() => undefined);
    return {
      engine: null as unknown as WllamaInferenceEngine,
      attempt: {
        backend, gpuLayers: backend === 'webgpu' ? spec.recommended.gpuLayers : 0, ok: false,
        loadMs: performance.now() - started,
        error: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
      },
    };
  }
}

export async function loadCandidateModel(spec: ModelSpec, options: LoadCandidateOptions = {}): Promise<LoadedCandidateModel> {
  const evidence: ModelLoadEvidence[] = [];
  const gpu = !options.forceCpu && (options.preferGpu ?? true) && webgpuAvailable();
  const attempts: BackendAttempt[] = [];
  if (gpu) {
    const first = await attemptLoad(spec, options, 'webgpu', evidence);
    attempts.push(first.attempt);
    if (first.attempt.ok) {
      return { spec, engine: first.engine, backend: 'webgpu', fallback: null, attempts, loadMs: first.attempt.loadMs, evidence, webgpuAvailable: true };
    }
    const fallback = await attemptLoad(spec, options, 'cpu', evidence);
    attempts.push(fallback.attempt);
    if (!fallback.attempt.ok) {
      throw new Error(`model ${spec.id} failed on both backends: webgpu=${first.attempt.error}; cpu=${fallback.attempt.error}`);
    }
    return {
      spec, engine: fallback.engine, backend: 'cpu',
      fallback: { from: 'webgpu', reason: first.attempt.error ?? 'unknown webgpu load failure' },
      attempts, loadMs: fallback.attempt.loadMs, evidence, webgpuAvailable: true,
    };
  }
  const only = await attemptLoad(spec, options, 'cpu', evidence);
  attempts.push(only.attempt);
  if (!only.attempt.ok) throw new Error(`model ${spec.id} failed to load on cpu: ${only.attempt.error}`);
  return { spec, engine: only.engine, backend: 'cpu', fallback: null, attempts, loadMs: only.attempt.loadMs, evidence, webgpuAvailable: webgpuAvailable() };
}

export type { ChatMessage };
