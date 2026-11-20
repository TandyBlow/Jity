/**
 * Acceptance verdict for the 4-second trial runs.
 *
 * The load-completion condition is deliberately count-only: llama.cpp's
 * finish_reason defaults to "length" and only switches to "stop" for EOS or
 * stop-word terminations, so a generation halted by context exhaustion also
 * reports "length" without having delivered the requested token count.
 */

export const ACCEPT_TARGET_MS = 4000;

export type AcceptInput = {
  error?: string;
  predictedTokens?: number;
  finishReason?: string | null;
  wallMs: number;
};

export type AcceptVerdict = {
  /** Did generation actually deliver the requested token count? */
  completedLoad: boolean;
  /** Within the 4s target; undefined when the run cannot be rated at all. */
  withinTarget: boolean | undefined;
};

export function judgeAccept(
  input: AcceptInput,
  requestedTokens: number,
  targetMs: number = ACCEPT_TARGET_MS,
): AcceptVerdict {
  if (input.error) {
    return { completedLoad: false, withinTarget: undefined };
  }
  const completedLoad = (input.predictedTokens ?? 0) >= requestedTokens;
  return {
    completedLoad,
    withinTarget: completedLoad ? input.wallMs <= targetMs : undefined,
  };
}
