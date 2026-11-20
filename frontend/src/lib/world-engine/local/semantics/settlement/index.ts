/** Settlement lane entry point.
 *
 * Wiring (main agent, game-model.ts):
 *   const settlement = createSettlementHandlers({ engine, options: { onTask } });
 *   // task === 'results'      -> (await settlement.results(key, input)).value
 *   // task === 'updates'      -> (await settlement.updates(key, input)).value
 *   // task === 'continuation' -> (await settlement.continuation(key, input)).value
 * A null value means no committed candidate: the adapter must surface the
 * error/stop, not manufacture a handback. results/updates may return a
 * `fallback: true` conservative no-change candidate with an error in evidence.
 */
import type { Id, Json } from '../../../types';
import type { UpdatesCall } from '../../../schedule';
import { runResults } from './results';
import { createUpdatesRunner, UpdatesRunner } from './updates';
import { ContinuationRunner, continuationPolicy, ContinuationPolicy } from './continuation';
import type {
  ContinuationPolicyOptions, SettlementConfig, SettlementConclusion, SettlementHandlers,
  SettlementOptions, SettlementOutcome,
} from './types';

export { continuationPolicy, ContinuationPolicy };
export type {
  ContinuationPolicyOptions, ModelCallEvidence, SettlementConfig, SettlementConclusion,
  SettlementEvidence, SettlementHandlers, SettlementOptions, SettlementOutcome, SettlementTask,
  SettlementUpdates, ModelTaskDetail, UpdatesCall,
} from './types';
export { UpdatesRunner };

export function createContinuationPolicy(options: ContinuationPolicyOptions = {}): ContinuationPolicy {
  return new ContinuationPolicy(options);
}

export function requireSettlementValue<T>(outcome: SettlementOutcome<T>): T {
  if (outcome.value == null) {
    throw new Error(`settlement_failed:${outcome.evidence.task}:${outcome.error ?? 'no_candidate'}`);
  }
  return outcome.value;
}

export function createSettlementHandlers(config: SettlementConfig): SettlementHandlers {
  const { engine } = config;
  const options: SettlementOptions = config.options ?? {};
  const updates: UpdatesRunner = createUpdatesRunner(engine, options);
  const continuation: ContinuationRunner = new ContinuationRunner(engine, options);
  return {
    results: (key: Id, input: Json) => runResults(engine, key, input, options),
    updates: (key: Id, input: Json): Promise<SettlementOutcome<UpdatesCall[] | UpdatesCall>> => updates.run(key, input),
    continuation: (key: Id, input: Json): Promise<SettlementOutcome<SettlementConclusion>> => continuation.run(key, input),
    resetContinuation: () => continuation.reset(),
    reset: () => {
      updates.reset();
      continuation.reset();
    },
  };
}
