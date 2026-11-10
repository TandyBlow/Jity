/** Round order and linked-group ordering rules (R06, workflow §5.1).
 *
 * A new, non-linked time point freezes action opportunities by ascending
 * sanity: the most fragile character decides first. Ties break on the stable
 * character id so a refresh or a replay reproduces the same order. A linked
 * point never re-sorts — it continues the order frozen when the round began,
 * even if sanity changed inside the group (design: 关联点中即使个性和理智
 * 改变，仍然继续原顺序).
 *
 * These are pure reads of the committed state. They do not freeze anything
 * themselves: the caller hands the result to `start_advance` / a continuation
 * conclusion, and the transport stores it as the authoritative order.
 */
import type { Id, WorldState } from '../../types';

function sanityOf(state: WorldState, id: Id): number {
  const value = state.characters[id]?.sanity;
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`round_order_sanity_missing:${id}`);
  }
  return value;
}

export interface RoundOrderOptions {
  /** Characters that must not receive an action opportunity (e.g. a caller
   * that already excluded someone on purpose). */
  exclude?: readonly Id[];
}

/** Every registered character, ascending sanity, id tiebreak. */
export function roundOrder(state: WorldState, options: RoundOrderOptions = {}): Id[] {
  const exclude = new Set(options.exclude ?? []);
  return Object.keys(state.characters)
    .filter((id) => !exclude.has(id))
    .sort((a, b) => sanityOf(state, a) - sanityOf(state, b) || (a < b ? -1 : a > b ? 1 : 0));
}

/** Order a subset (automatic-round candidates) with the same rule. An
 * unknown id is rejected instead of silently dropped: a continuation
 * conclusion naming a dead character is a bug, not a shorter round. */
export function orderSubset(state: WorldState, ids: readonly Id[]): Id[] {
  const unique = [...new Set(ids)];
  const unknown = unique.filter((id) => !state.characters[id]);
  if (unknown.length) throw new Error(`round_order_unknown_character:${unknown.join(',')}`);
  return unique.sort((a, b) => sanityOf(state, a) - sanityOf(state, b) || (a < b ? -1 : a > b ? 1 : 0));
}

/** True when `order` is exactly what a fresh freeze would produce for that
 * roster. Used by probes and regression tests, never to rewrite a stored
 * linked order. */
export function isFreshRoundOrder(state: WorldState, order: readonly Id[]): boolean {
  const fresh = roundOrder(state, { exclude: Object.keys(state.characters).filter((id) => !order.includes(id)) });
  return fresh.length === order.length && fresh.every((id, index) => id === order[index]);
}
