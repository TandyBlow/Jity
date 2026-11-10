/** Copy-ready wiring for the main integration and lane 02.
 *
 *   const { rendered, projection, tasks, textCarryLimits } = narrationInputForPoint({
 *     before, after, delta: point.entityDeltas, timeAdvance: point.timeAdvance,
 *     viewpointId: view,
 *   });
 *   // rendered.text is the exact yuyan-prose-result-v2 input.
 *
 * `before` is the previous committed WorldState, `after` is the state after
 * this point, and `timeAdvance` is required. Do not pass `after` as `before`.
 */
import {
  buildNarrationInput,
  type NarrationModelPath,
  type RenderNarrationInputOptions,
} from '../../src/lib/world-engine/local/narration-input';
import type { EntityDelta, Id, TimeAdvance, WorldState } from '../../src/lib/world-engine/types';

export interface NarrationInputForPointArgs {
  before: WorldState;
  after: WorldState;
  delta: Record<Id, EntityDelta>;
  timeAdvance: TimeAdvance;
  viewpointId: Id;
  /** Defaults to 'result-v2', the format the v2 arm was trained on. */
  model?: NarrationModelPath;
  maxChars?: number;
  maxUtf8Bytes?: number;
}

export function narrationInputForPoint(args: NarrationInputForPointArgs) {
  const options: RenderNarrationInputOptions = {
    model: args.model ?? 'result-v2',
    limits: {
      maxChars: args.maxChars,
      maxUtf8Bytes: args.maxUtf8Bytes,
    },
  };
  return buildNarrationInput({
    before: args.before,
    after: args.after,
    delta: args.delta,
    timeAdvance: args.timeAdvance,
    viewpointId: args.viewpointId,
  }, options);
}
