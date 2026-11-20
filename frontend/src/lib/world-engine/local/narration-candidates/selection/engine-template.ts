/** Adapt the page's chat-templated engine to candidates that send plain text.
 *
 * The page loads an instruct/narration chat model and wraps every prompt as a
 * single user turn (`<|im_start|>user … <|im_end|><|im_start|>assistant`). The
 * candidates were written against a plain completion engine, so on the page
 * their prompts arrived without the template the model was trained to answer.
 * This decorator applies the same wrapper the in-model writer uses, and keeps
 * the stop token so the model does not continue into the next turn.
 *
 * It is a thin engine port: identity, load, dispose and the caller's abort
 * signal pass straight through; only the prompt and the stop list change.
 */
import type { CompleteOptions, EngineInfo, InferenceEngine } from '../../../runtime/engine';

export const CHATML_STOP = '<|im_end|>';

/** Same wrapper as the in-model narration writer (`chatml()` in game-model):
 * one user turn, then the assistant prefix. Kept identical so a candidate and
 * the in-model writer present the model the same shape. */
export function chatTemplate(prompt: string): string {
  return `<|im_start|>user\n${prompt}${CHATML_STOP}\n<|im_start|>assistant\n`;
}

/** Strip template artefacts that a streamed fragment may carry. */
export function stripChatTemplate(raw: string): string {
  let text = raw;
  const assistant = text.lastIndexOf('<|im_start|>assistant');
  if (assistant >= 0) text = text.slice(assistant + '<|im_start|>assistant'.length);
  return text.replace(/<\|im_end\|>/gu, '').replace(/^[\r\n]+/u, '');
}

export function createChatTemplatedEngine(engine: InferenceEngine): InferenceEngine {
  return {
    info: engine.info satisfies EngineInfo,
    load: (options) => engine.load(options),
    dispose: () => engine.dispose(),
    complete: (prompt, options?: CompleteOptions) => {
      const stops = options?.stop ? [...options.stop] : [];
      if (!stops.includes(CHATML_STOP)) stops.push(CHATML_STOP);
      return engine.complete(chatTemplate(prompt), {
        ...options,
        stop: stops,
        ...(options?.onProgress
          ? { onProgress: (progress) => options.onProgress?.({ ...progress, raw: stripChatTemplate(progress.raw) }) }
          : {}),
      });
    },
  };
}
