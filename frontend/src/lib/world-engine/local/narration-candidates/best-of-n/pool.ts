/** Bounded candidate-pool execution.
 *
 * This is transport accounting, not a retry policy. It runs the caller's
 * generation function for each preregistered seed, records every call's real
 * wall clock and outcome, and enforces a whole-pool budget so N calls cannot
 * silently exceed the turn budget. The caller owns retries; when it retries
 * inside `generate`, that time is inside `totalMs` and therefore counted.
 *
 * A failed or timed-out call stays in the result as a failed sample. Nothing is
 * silently re-run, padded or replaced with a longer generation.
 */
import type { PoolCallResult, PoolConfig, PoolRun, PoolSample } from './types';

export type PoolGenerate = (
  seed: number,
  signal: AbortSignal,
  index: number,
) => Promise<PoolCallResult>;

const nowMs = (): number =>
  typeof performance !== 'undefined' && typeof performance.now === 'function' ? performance.now() : Date.now();

function describeError(error: unknown): string {
  if (error instanceof Error) return `${error.name}:${error.message}`;
  return String(error);
}

function validate(config: PoolConfig): void {
  if (!Array.isArray(config.seeds) || config.seeds.length === 0) throw new Error('pool_seeds_empty');
  if (new Set(config.seeds).size !== config.seeds.length) throw new Error('pool_seeds_duplicate');
  if (!Number.isInteger(config.concurrency) || config.concurrency < 1) throw new Error('pool_concurrency_invalid');
  if (!(config.perCallTimeoutMs > 0)) throw new Error('pool_call_timeout_invalid');
  if (!(config.totalBudgetMs > 0)) throw new Error('pool_total_budget_invalid');
}

export async function runCandidatePool(
  config: PoolConfig,
  generate: PoolGenerate,
): Promise<PoolRun> {
  validate(config);
  const start = nowMs();
  const samples: Array<PoolSample | undefined> = new Array(config.seeds.length).fill(undefined);
  const controllers = new Set<AbortController>();
  let nextIndex = 0;
  let active = 0;
  let peakConcurrency = 0;
  let completed = 0;
  let failed = 0;
  let budgetExceeded = false;

  const budgetTimer = setTimeout(() => {
    budgetExceeded = true;
    for (const controller of controllers) controller.abort('pool_budget_exceeded');
  }, config.totalBudgetMs);

  const worker = async (): Promise<void> => {
    for (;;) {
      // Once the pool budget is gone, no new call may start: filling the rest
      // with `cancelled` is the honest record, not a post-deadline generation.
      if (budgetExceeded) return;
      const index = nextIndex;
      nextIndex += 1;
      if (index >= config.seeds.length) return;
      const seed = config.seeds[index];
      const id = `seed-${seed}`;
      const controller = new AbortController();
      controllers.add(controller);
      active += 1;
      peakConcurrency = Math.max(peakConcurrency, active);
      const startedAtMs = nowMs() - start;
      let callTimedOut = false;
      const timer = setTimeout(() => {
        callTimedOut = true;
        controller.abort('pool_call_timeout');
      }, config.perCallTimeoutMs);
      try {
        const result = await generate(seed, controller.signal, index);
        const text = result.text ?? '';
        const endedAtMs = nowMs() - start;
        const status = !text.trim()
          ? 'empty'
          : controller.signal.aborted
            ? budgetExceeded ? 'cancelled' : callTimedOut ? 'timeout' : 'cancelled'
            : result.finishReason === 'length' ? 'truncated' : 'ok';
        samples[index] = {
          id,
          seed,
          text,
          status,
          error: status === 'ok' || status === 'truncated'
            ? null
            : !text.trim() ? 'empty_output' : 'aborted_after_partial_output',
          totalMs: result.totalMs,
          firstTokenMs: result.firstTokenMs ?? null,
          tokens: result.tokens ?? null,
          startedAtMs,
          endedAtMs,
        };
        // A call the model finished is counted even if a budget abort arrived
        // at the same moment; the text exists and is preserved.
        if (status === 'ok' || status === 'truncated') completed += 1;
        else failed += 1;
      } catch (error) {
        const endedAtMs = nowMs() - start;
        const abortedByUs = controller.signal.aborted;
        const status: PoolSample['status'] = callTimedOut
          ? 'timeout'
          : budgetExceeded || abortedByUs
            ? 'cancelled'
            : (error as { name?: unknown } | null)?.name === 'AbortError' ? 'cancelled' : 'error';
        samples[index] = {
          id,
          seed,
          text: '',
          status,
          error: status === 'timeout'
            ? `pool_call_timeout:${describeError(error)}`
            : status === 'cancelled'
              ? `pool_cancelled:${describeError(error)}`
              : describeError(error),
          totalMs: endedAtMs - startedAtMs,
          firstTokenMs: null,
          tokens: null,
          startedAtMs,
          endedAtMs,
        };
        failed += 1;
      } finally {
        clearTimeout(timer);
        controllers.delete(controller);
        active -= 1;
      }
    }
  };

  const workers = Array.from(
    { length: Math.min(config.concurrency, config.seeds.length) },
    () => worker(),
  );
  await Promise.all(workers);
  clearTimeout(budgetTimer);

  const wallMs = nowMs() - start;
  const finalSamples: PoolSample[] = config.seeds.map((seed, index) => samples[index] ?? {
    id: `seed-${seed}`,
    seed,
    text: '',
    status: 'cancelled' as const,
    error: budgetExceeded ? 'pool_budget_exceeded' : 'pool_not_started',
    totalMs: null,
    firstTokenMs: null,
    tokens: null,
    startedAtMs: wallMs,
    endedAtMs: wallMs,
  });

  return {
    samples: finalSamples,
    wallMs,
    requested: config.seeds.length,
    completed,
    failed,
    peakConcurrency,
    budgetExceeded,
  };
}
