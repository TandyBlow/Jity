/** Copy-ready wiring for the main integration.
 *
 * The main tree's `local/prompt.ts` currently builds the legacy string in
 * `legacyNarrationInput`. Replace that body with this call so the page,
 * training and offline generation share one projection:
 *
 *   const { text } = narrationInputForPoint({
 *     before, after, delta: delta.entityDeltas ?? {}, timeAdvance: delta.timeAdvance,
 *     viewpointId: view,
 *   });
 *
 * `model: 'legacy'` is the existing YuYan checkpoint (no result block).
 * `model: 'result-v2'` is the new format; do not feed it to the old weights.
 */
import {
  projectNarrationInput, renderLegacyInput, renderResultInput,
} from '../../src/lib/world-engine/local/narration-input';
import type { EntityDelta, Id, TimeAdvance, WorldState } from '../../src/lib/world-engine/types';

export interface NarrationInputForPointArgs {
  before: WorldState;
  after: WorldState;
  delta: Record<Id, EntityDelta>;
  timeAdvance: TimeAdvance;
  viewpointId: Id;
  model?: 'legacy' | 'result-v2';
  maxChars?: number;
  maxUtf8Bytes?: number;
}

export function narrationInputForPoint(args: NarrationInputForPointArgs) {
  const { projection, includedEntities, visibleEntities, omittedFields, version } = projectNarrationInput({
    before: args.before,
    after: args.after,
    delta: args.delta,
    timeAdvance: args.timeAdvance,
    viewpointId: args.viewpointId,
    policy: {
      length: {
        maxChars: args.maxChars ?? null,
        maxUtf8Bytes: args.maxUtf8Bytes ?? null,
      },
    },
  });
  const rendered = args.model === 'result-v2'
    ? renderResultInput(projection)
    : renderLegacyInput(projection);
  return { text: rendered.text, rendered, projection, includedEntities, visibleEntities, omittedFields, version };
}
