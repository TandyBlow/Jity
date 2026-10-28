/** The real WorldModelPort over an InferenceEngine: encode → queued
 * complete → decode/validate. The ENCODE half is a placeholder — a
 * deterministic wrapper that B3's prompt layer replaces; the DECODE half is
 * this batch's deliverable: no output reaches controller memory without
 * passing the task's structural validation. Model loading is itself queued,
 * so load and inference share the device slot. The optional signal on
 * generate keeps the WorldModelPort interface intact for the controller
 * (structural typing) while the runtime can cancel in-flight generations. */
import type { WorldModelPort } from '../controller';
import type { Json } from '../types';
import type { ModelTask } from '../schedule';
import { type InferenceEngine } from './engine';
import { SerialInferenceQueue, type QueueTiming } from './inference-queue';
import { decodeTaskOutput } from './structured-output';
import { taskOutputSchema } from './output-schema';
import type { CompletionEvidence } from './engine';
import type { CommittedRead } from './committed-narration';

export interface GenerationResult {
  value: Json;
  timing: QueueTiming;
  completion?: CompletionEvidence;
}

/** The member surface WorldSession actually consumes. A structural interface
 * instead of the RuntimeWorldModelPort class so deterministic compositions
 * (the rule page runtime) can satisfy it without a real engine. */
export interface RuntimePortLike {
  generate(task: ModelTask, key: string, input: Json, signal?: AbortSignal): Promise<Json>;
  dispose(): Promise<void>;
}

export interface ModelPortOptions {
  maxTokens?: number;
  seed?: number;
  temperature?: number;
  timeoutMs?: number;
  inputMode?: 'full' | 'focused';
  cachePrompt?: boolean;
  committedReads?: { before: CommittedRead | null; after: CommittedRead };
  taskMaxTokens?: Partial<Record<ModelTask, number>>;
  onProgress?: (task: ModelTask, key: string, progress: { raw: string; elapsedMs: number }) => void;
  onCompletion?: (task: ModelTask, key: string, completion: CompletionEvidence) => void;
}
/** The real B3 prompt layer (prompts.ts); also re-exported so existing
 * imports and determinism tests stay stable. */
import { buildTaskPrompt as encodePrompt } from './prompts';
export { buildTaskPrompt as encodePrompt } from './prompts';

export class RuntimeWorldModelPort implements WorldModelPort {
  private readonly queue: SerialInferenceQueue;

  constructor(
    private readonly engine: InferenceEngine,
    queue?: SerialInferenceQueue,
    private readonly options: ModelPortOptions = {},
  ) {
    this.queue = queue ?? new SerialInferenceQueue();
  }

  get info(): { engine: { backend: string; modelId: string | null }; queueDepth: number; runningLabel: string | null } {
    return { engine: this.engine.info, queueDepth: this.queue.depth, runningLabel: this.queue.runningLabel };
  }

  generate(task: ModelTask, key: string, input: Json, signal?: AbortSignal): Promise<Json> {
    return this.generateDetailed(task, key, input, signal).then((result) => result.value);
  }

  async generateDetailed(task: ModelTask, key: string, input: Json, signal?: AbortSignal): Promise<GenerationResult> {
    await this.queue.run({ label: `load:${this.engine.info.backend}`, signal, start: (runSignal) => this.engine.load({ signal: runSignal }) });
    const prompt = encodePrompt(task, key, input, { inputMode: this.options.inputMode, committedReads: this.options.committedReads });
    let evidence: CompletionEvidence | undefined;
    const completion = await this.queue.run({
      label: `${task}:${key}`,
      signal,
      start: (runSignal) => this.engine.complete(prompt, {
        signal: runSignal,
        maxTokens: this.options.taskMaxTokens?.[task] ?? this.options.maxTokens ??
          ({ action: 80, updates: 192, narration: 128, reaction: 80 } as Partial<Record<ModelTask, number>>)[task] ?? 256,
        temperature: this.options.temperature ?? 0,
        seed: this.options.seed,
        timeoutMs: this.options.timeoutMs,
        cachePrompt: this.options.cachePrompt,
        jsonSchema: taskOutputSchema(task, input),
        onProgress: (progress) => this.options.onProgress?.(task, key, progress),
        onCompletion: (completion) => {
          evidence = completion;
          this.options.onCompletion?.(task, key, completion);
        },
      }),
    });
    // The declared call input decides the updates shape: a split call
    // (input carries stage) must yield ONE call, a batch call an array —
    // the wrong shape rejects here instead of in the controller. A decode
    // failure keeps the completion's timing: the generation cost was paid.
    const constraints = task === 'updates' ? { updatesSplitMode: (input as { stage?: unknown }).stage !== undefined,
      updatesStage: (input as { stage?: string }).stage } : undefined;
    try {
      return { value: decodeTaskOutput(task, completion.value, constraints), timing: completion.timing, completion: evidence };
    } catch (error) {
      (error as { timing?: QueueTiming }).timing = completion.timing;
      throw error;
    }
  }

  /** Aborts the in-flight generation, rejects the queued ones and disposes
   * the engine. The session-level stop path (B4/H2 takeover) builds on this. */
  async dispose(): Promise<void> {
    this.queue.dispose();
    await this.engine.dispose();
  }
}
