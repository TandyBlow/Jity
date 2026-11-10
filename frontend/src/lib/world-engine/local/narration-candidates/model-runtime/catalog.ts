/** The local checkpoints that exist on this machine and are realistic A-group
 * candidates. Every hash/size below was computed from the actual file
 * (2026-11-10); the GGUF metadata (architecture, context length, chat
 * template) comes from the same files via `scripts/candidate-model/gguf-meta.mjs`.
 *
 * No file is copied into this worktree: `gguf` is a file name resolved
 * against read-only shared model roots by the run scripts. When a checkpoint
 * moves, the probe fails loudly instead of silently loading another model.
 */
import type { ModelSpec } from './types';

export const MODEL_CATALOG: readonly ModelSpec[] = [
  {
    id: 'qwen3-4b-instruct-2507-q4km',
    label: 'Qwen3-4B-Instruct-2507（Q4_K_M，2.50 GB）',
    gguf: 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf',
    sha256: '3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597',
    bytes: 2497281120,
    family: 'qwen3-2507',
    architecture: 'qwen3',
    parametersB: 4,
    base: 'Qwen3-4B-Instruct-2507',
    thinking: 'none',
    template: {
      id: 'qwen3-instruct-2507-chatml-v1',
      systemMessage: true,
      templateKwargs: {},
      stop: [],
    },
    recommended: { contextSize: 4096, numThreads: 6, gpuLayers: 99999 },
  },
  {
    id: 'qwen3-1.7b-q4km',
    label: 'Qwen3-1.7B（Q4_K_M，1.11 GB，可关思考）',
    gguf: 'Qwen3-1.7B-Q4_K_M.gguf',
    sha256: 'b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897',
    bytes: 1107409472,
    family: 'qwen3',
    architecture: 'qwen3',
    parametersB: 1.7,
    base: 'Qwen3-1.7B',
    thinking: 'hybrid',
    template: {
      id: 'qwen3-hybrid-chatml-no-thinking-v1',
      systemMessage: true,
      templateKwargs: { enable_thinking: false },
      stop: [],
    },
    recommended: { contextSize: 4096, numThreads: 6, gpuLayers: 99999 },
  },
  {
    id: 'qwen2.5-1.5b-instruct-q4km',
    label: 'Qwen2.5-1.5B-Instruct（Q4_K_M，1.12 GB）',
    gguf: 'qwen2.5-1.5b-instruct-q4_k_m.gguf',
    sha256: '6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e',
    bytes: 1117320736,
    family: 'qwen2.5',
    architecture: 'qwen2',
    parametersB: 1.5,
    base: 'Qwen2.5-1.5B-Instruct',
    thinking: 'none',
    template: {
      id: 'qwen2.5-instruct-chatml-v1',
      systemMessage: true,
      templateKwargs: {},
      stop: [],
    },
    recommended: { contextSize: 4096, numThreads: 6, gpuLayers: 99999 },
  },
  {
    id: 'qwen3-0.6b-q4km',
    label: 'Qwen3-0.6B（Q4_K_M，397 MB，可关思考）',
    gguf: 'Qwen3-0.6B-Q4_K_M.gguf',
    sha256: 'ac2d97712095a558e31573f62f466a3f9d93990898b0ec79d7c974c1780d524a',
    bytes: 396705472,
    family: 'qwen3',
    architecture: 'qwen3',
    parametersB: 0.6,
    base: 'Qwen3-0.6B',
    thinking: 'hybrid',
    template: {
      id: 'qwen3-hybrid-chatml-no-thinking-v1',
      systemMessage: true,
      templateKwargs: { enable_thinking: false },
      stop: [],
    },
    recommended: { contextSize: 4096, numThreads: 6, gpuLayers: 99999 },
  },
  {
    id: 'qwen2.5-0.5b-instruct-q4km',
    label: 'Qwen2.5-0.5B-Instruct（Q4_K_M，491 MB）',
    gguf: 'qwen2.5-0.5b-instruct-q4_k_m.gguf',
    sha256: '74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db',
    bytes: 491400032,
    family: 'qwen2.5',
    architecture: 'qwen2',
    parametersB: 0.5,
    base: 'Qwen2.5-0.5B-Instruct',
    thinking: 'none',
    template: {
      id: 'qwen2.5-instruct-chatml-v1',
      systemMessage: true,
      templateKwargs: {},
      stop: [],
    },
    recommended: { contextSize: 4096, numThreads: 6, gpuLayers: 99999 },
  },
];

export const DEFAULT_MODEL_ID = 'qwen2.5-1.5b-instruct-q4km';

export function modelSpec(id: string): ModelSpec {
  const spec = MODEL_CATALOG.find((entry) => entry.id === id);
  if (!spec) throw new Error(`unknown candidate model: ${id} (known: ${MODEL_CATALOG.map((entry) => entry.id).join(', ')})`);
  return spec;
}

export function modelSpecByFile(file: string): ModelSpec {
  const name = file.split(/[\\/]/).pop() ?? file;
  const spec = MODEL_CATALOG.find((entry) => entry.gguf === name);
  if (!spec) throw new Error(`no catalog entry for ${name}`);
  return spec;
}
