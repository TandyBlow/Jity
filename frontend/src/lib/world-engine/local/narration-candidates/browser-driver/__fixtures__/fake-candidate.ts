/** Test fixture candidate: exercises the queue plumbing (progress, contract,
 * continuation) without a model. It is not a product candidate and is never
 * registered by a real queue invocation. */
export async function generateCandidate(args: {
  inputText: string;
  priorText: string | null;
  onProgress?: (state: { status: string; text: string; verified: boolean; elapsedMs: number }) => void;
}) {
  const first = '周宁没有动，只把手按在门框上。';
  const second = '走廊尽头传来一声轻响，像有人把盒子放回了地上。';
  args.onProgress?.({ status: 'streaming', text: first, verified: false, elapsedMs: 1 });
  await Promise.resolve();
  args.onProgress?.({ status: 'streaming', text: `${first}※${second}`, verified: false, elapsedMs: 2 });
  const continuity = args.priorText ? '上一轮的动静还在她耳边。' : '';
  const text = [first, second, continuity].filter(Boolean).join('\n\n');
  const started = performance.now();
  return {
    text,
    accepted: true,
    rawAttempts: [{
      attempt: 1,
      prompt: `fixture prompt (${args.inputText.length} chars)`,
      promptChars: args.inputText.length,
      raw: text,
      cleaned: text,
      finishReason: 'stop',
      error: null,
      durationMs: performance.now() - started,
      firstTokenMs: 1,
      accepted: true,
      issues: [],
    }],
    issues: [],
    timings: { totalMs: performance.now() - started, attemptMs: [1], attemptsMs: 1, firstTokenMs: 1 },
    strategyVersion: 'fixture-v1',
  };
}

/** Missing every optional-looking field the contract requires. */
export async function generateBroken() {
  return { text: '   ' };
}

/** Throws before producing anything. */
export async function generateThrows(): Promise<never> {
  throw new Error('fixture_failure');
}
