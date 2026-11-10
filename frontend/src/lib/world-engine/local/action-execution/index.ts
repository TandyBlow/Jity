/** Action execution: the product-facing side of the action family.
 *
 * Owns:
 *   - round order (ascending sanity, id tiebreak) for a new non-linked round;
 *   - subset ordering for automatic rounds created by a continuation;
 *   - the WorldModelPort adapter that answers action/targets/reaction with
 *     the guarded semantics handlers and delegates every other task.
 *
 * Does not own: schedule flow, group freezing, dice storage, settlement,
 * updates, continuation or narration. Those stay with 04/05/06 and the
 * transport; this module only makes the semantic answers correct and
 * inspectable.
 */
export { roundOrder, orderSubset, isFreshRoundOrder, type RoundOrderOptions } from './order';
export {
  ActionExecutionModel, createActionExecutionModel, roundRoster,
  type ActionExecutionOptions, type ActionTaskReport,
} from './port';
export { createActionHandlers, type ActionHandlers } from '../semantics/actions/index';
export type { ActionHandlerOptions, ActionIssue, HandlerResult } from '../semantics/actions/types';
