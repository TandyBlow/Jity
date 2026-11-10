/** Declared call input readers. The scheduler's action/targets/reaction inputs
 * are structural: a caller (or a probe) may hand a plain Json object. These
 * readers reject a missing world state with a legible error and otherwise
 * keep unknown/missing optional fields inert instead of inventing values. */
import type { Id, WorldState } from '../../../types';
import type { ActionCallInput, ReactionCallInput, TargetsCallInput } from './types';

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function asWorldState(value: unknown, task: string): WorldState {
  const state = asRecord(value) as unknown as WorldState | null;
  if (!state || !asRecord(state.characters) || !asRecord(state.initial) || !asRecord(state.items)) {
    throw new Error(`${task} without workingState`);
  }
  return state;
}

function asId(value: unknown): Id | null {
  return typeof value === 'string' && value.length ? value : null;
}

export interface ReadActionCall {
  actor: Id;
  protagonistId: Id;
  inputText: string | null;
  intentStatus: 'pending' | 'consumed' | 'expired';
  state: WorldState;
}

export function readActionCall(key: string, input: unknown): ReadActionCall {
  const data = asRecord(input) as ActionCallInput | null;
  if (!data) throw new Error('action input must be an object');
  const state = asWorldState(data.workingState, 'action');
  const actor = asId(data.actor) ?? key;
  if (!actor) throw new Error('action without actor');
  const advance = asRecord(data.advance);
  const text = typeof advance?.inputText === 'string' ? advance.inputText : null;
  const status = advance?.intentStatus;
  return {
    actor,
    protagonistId: state.protagonistId,
    inputText: text && text.trim().length ? text : null,
    intentStatus: status === 'consumed' || status === 'expired' ? status : 'pending',
    state,
  };
}

export interface ReadTargetsCall {
  sourceId: Id;
  actionText: string;
  state: WorldState;
}

export function readTargetsCall(key: string, input: unknown): ReadTargetsCall {
  const data = asRecord(input) as TargetsCallInput | null;
  if (!data) throw new Error('targets input must be an object');
  const state = asWorldState(data.workingState, 'targets');
  const sourceId = asId(data.sourceId) ?? key;
  if (!sourceId) throw new Error('targets without sourceId');
  if (typeof data.actionText !== 'string' || !data.actionText.trim().length) throw new Error('targets without actionText');
  return { sourceId, actionText: data.actionText.trim(), state };
}

export interface ReadReactionCall {
  sourceId: Id;
  memberId: Id;
  sourceActionText: string;
  rollId: Id | null;
  state: WorldState;
}

export function readReactionCall(key: string, input: unknown): ReadReactionCall {
  const data = asRecord(input) as ReactionCallInput | null;
  if (!data) throw new Error('reaction input must be an object');
  const state = asWorldState(data.workingState, 'reaction');
  const sourceId = asId(data.sourceId) ?? key;
  const memberId = asId(data.memberId);
  if (!sourceId) throw new Error('reaction without sourceId');
  if (!memberId) throw new Error('reaction without memberId');
  if (typeof data.sourceActionText !== 'string' || !data.sourceActionText.trim().length) {
    throw new Error('reaction without sourceActionText');
  }
  return { sourceId, memberId, sourceActionText: data.sourceActionText.trim(), rollId: asId(data.rollId), state };
}
