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

export interface GenerationResult {
  value: Json;
  timing: QueueTiming;
}

export interface ModelPortOptions {
  maxTokens?: number;
  seed?: number;
  temperature?: number;
}

/** B3 replaces this with the real prompt layer; until then the prompt is a
 * deterministic function of the declared call so test replays stay stable. */
export function encodePrompt(task: ModelTask, key: string, input: Json): string {
  return `TASK: ${task}\nKEY: ${key}\nINPUT: ${JSON.stringify(input)}\nOUTPUT: `;
}

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
    const prompt = encodePrompt(task, key, input);
    const completion = await this.queue.run({
      label: `${task}:${key}`,
      signal,
      start: (runSignal) => this.engine.complete(prompt, {
        signal: runSignal,
        maxTokens: this.options.maxTokens,
        temperature: this.options.temperature ?? 0,
        seed: this.options.seed,
      }),
    });
    // The declared call input decides the updates shape: a split call
    // (input carries stage) must yield ONE call, a batch call an array —
    // the wrong shape rejects here instead of in the controller.
    const constraints = task === 'updates' ? { updatesSplitMode: (input as { stage?: unknown }).stage !== undefined } : undefined;
    return { value: decodeTaskOutput(task, completion.value, constraints), timing: completion.timing };
  }

  /** Aborts the in-flight generation, rejects the queued ones and disposes
   * the engine. The session-level stop path (B4/H2 takeover) builds on this. */
  async dispose(): Promise<void> {
    this.queue.dispose();
    await this.engine.dispose();
  }
}
