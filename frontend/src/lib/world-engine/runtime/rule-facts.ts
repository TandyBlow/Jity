/** Trusted, bounded simulation rules. A proposal is never a fact. Only this
 * authority can mint an in-process rule receipt, and receipts are not wire
 * data or persistent authorization. The server's point commit remains the
 * durable record; replay protection is bound to its advance/input status. */
import type { EntityDelta, Id, Json, WorldContext, WorldState } from '../types';

export type RuleProposal = { kind: 'move'; actorId: Id; destinationId: Id }
  | { kind: 'sanity'; actorId: Id; effect: 'strain' | 'recover' };
export interface RuleScope {
  worldId: Id; advanceId: Id; inputId: Id; roundId: Id; pointId: Id;
  baselinePointId: Id; baselineVersion: number; baselineDigest: string; fenceEpoch: number;
}
export interface RulePolicy {
  /** Directed edges are installed by the application, never generated. */
  routes: readonly { from: Id; to: Id; minimumSanity?: number }[];
  /** Explicit simulation bounds. No clamping or model-selected magnitude. */
  sanity: { minimum: number; maximum: number; effects: { strain: number; recover: number };
    milestones: Record<'strain' | 'recover', { taskId: Id; goal: string; requiredLocationId: Id;
      minimumElapsedSeconds: number; personalityText: string }> };
}
export type RuleEffect = { kind: 'moved'; actorId: Id; from: Id; to: Id }
  | { kind: 'sanity_changed'; actorId: Id; from: number; to: number;
    achievedTaskId: Id; goal: string; personalityText: string; draftChangeId: Id };
export type RuleDecision = { outcome: 'allowed'; effects: readonly RuleEffect[] }
  | { outcome: 'refused'; reason: string; effects: readonly [] };
declare const receiptBrand: unique symbol;
export interface RuleReceipt { readonly [receiptBrand]: true }

const clone = <T>(value: T): T => structuredClone(value);
const stable = (value: unknown): unknown => Array.isArray(value) ? value.map(stable)
  : value && typeof value === 'object' ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, item]) => [key, stable(item)])) : value;
const same = (a: unknown, b: unknown) => JSON.stringify(stable(a)) === JSON.stringify(stable(b));
const exact = (value: object, keys: string[]) => same(Object.keys(value).sort(), [...keys].sort());

export function validateRuleProposal(value: unknown): RuleProposal {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('rule_proposal_malformed');
  const p = value as Record<string, unknown>;
  if (typeof p.actorId !== 'string' || !p.actorId) throw new Error('rule_actor_missing');
  if (p.kind === 'move' && exact(p, ['kind', 'actorId', 'destinationId']) && typeof p.destinationId === 'string' && p.destinationId) return clone(p) as RuleProposal;
  if (p.kind === 'sanity' && exact(p, ['kind', 'actorId', 'effect']) && (p.effect === 'strain' || p.effect === 'recover')) return clone(p) as RuleProposal;
  throw new Error('unsupported_rule_proposal');
}

/** Only these exact user commands have authority to request the supported
 * simulation. Natural-language model outputs are never parsed as results. */
export function parseRuleCommand(text: string, state: WorldState): RuleProposal | null {
  const command = text.trim().replace(/[。！]$/, '');
  if (command === '完成压力试验') return { kind: 'sanity', actorId: state.protagonistId, effect: 'strain' };
  if (command === '完成恢复练习') return { kind: 'sanity', actorId: state.protagonistId, effect: 'recover' };
  const match = /^(?:我)?走到(.+)$/.exec(command);
  if (!match) return null;
  const locations = Object.entries(state.initial.locations).filter(([id, place]) => match[1] === id || match[1] === place.name);
  if (locations.length !== 1) return null; // ambiguous display names never guess
  return { kind: 'move', actorId: state.protagonistId, destinationId: locations[0][0] };
}

export function ruleScope(world: WorldContext, pointId: Id): RuleScope {
  if (!world.advance.advanceId || !world.advance.inputId || !world.round || !world.lease) throw new Error('rule_scope_incomplete');
  if (world.activePointId !== pointId || world.activeRoundId !== world.round.roundId) throw new Error('rule_active_point_mismatch');
  return { worldId: world.worldId, advanceId: world.advance.advanceId, inputId: world.advance.inputId,
    roundId: world.round.roundId, pointId, baselinePointId: world.head.pointId, baselineVersion: world.head.version,
    baselineDigest: world.head.stateDigest, fenceEpoch: world.lease.fenceEpoch };
}

export class RuleAuthority {
  private readonly receipts = new WeakMap<RuleReceipt, { scope: RuleScope; decision: RuleDecision; proposal: RuleProposal }>();
  private readonly policy: RulePolicy;
  constructor(policy: RulePolicy) {
    this.policy = clone(policy);
    const { minimum, maximum, effects } = this.policy.sanity;
    if (![minimum, maximum, effects.strain, effects.recover].every(Number.isSafeInteger)
      || minimum >= maximum || effects.strain >= 0 || effects.recover <= 0) throw new Error('invalid_rule_policy');
    if (this.policy.routes.some((edge) => !edge.from || !edge.to || (edge.minimumSanity !== undefined
      && (!Number.isSafeInteger(edge.minimumSanity) || edge.minimumSanity < minimum || edge.minimumSanity > maximum)))) throw new Error('invalid_route_policy');
    for (const effect of ['strain', 'recover'] as const) {
      const milestone = this.policy.sanity.milestones[effect];
      if (!milestone?.taskId || !milestone.goal || !milestone.requiredLocationId || !milestone.personalityText
        || !Number.isSafeInteger(milestone.minimumElapsedSeconds) || milestone.minimumElapsedSeconds < 1) throw new Error('invalid_milestone_policy');
    }
  }

  adjudicate(request: { proposal: unknown; inputText: string; world: WorldContext; state: WorldState; pointId: Id }): RuleReceipt {
    const { world, state } = request;
    if (world.worldId !== state.worldId || world.head.version < 0) throw new Error('rule_world_mismatch');
    // Server-owned status is checked before a receipt is minted. A cached
    // receipt from a previous input/point/epoch cannot authorize a new one.
    if (world.advance.intentStatus !== 'pending' || !world.advance.inputAvailable) throw new Error('rule_input_not_pending');
    const proposal = validateRuleProposal(request.proposal);
    const command = parseRuleCommand(request.inputText, state);
    if (!command || !same(command, proposal)) throw new Error('proposal_not_bound_to_supported_user_command');
    const actor = state.characters[proposal.actorId];
    let decision: RuleDecision;
    if (!actor || proposal.actorId !== state.protagonistId) throw new Error('rule_actor_not_authorized');
    if (proposal.kind === 'move') {
      const edge = this.policy.routes.find((edge) => edge.from === actor.position.containerId && edge.to === proposal.destinationId);
      if (!state.locations[actor.position.containerId] || actor.position.slotId != null || actor.position.relativeTo != null) decision = { outcome: 'refused', reason: 'unsupported_source_position', effects: [] };
      else if (!state.locations[proposal.destinationId] || !state.initial.locations[proposal.destinationId]) decision = { outcome: 'refused', reason: 'destination_missing', effects: [] };
      else if (actor.position.containerId === proposal.destinationId) decision = { outcome: 'refused', reason: 'already_at_destination', effects: [] };
      else if (!edge) decision = { outcome: 'refused', reason: 'route_not_allowed', effects: [] };
      else if (edge.minimumSanity !== undefined && actor.sanity < edge.minimumSanity) decision = { outcome: 'refused', reason: 'sanity_below_route_minimum', effects: [] };
      else decision = { outcome: 'allowed', effects: [{ kind: 'moved', actorId: proposal.actorId, from: actor.position.containerId, to: proposal.destinationId }] };
    } else {
      const { minimum, maximum, effects } = this.policy.sanity;
      const milestone = this.policy.sanity.milestones[proposal.effect];
      const task = actor.tasks[milestone.taskId];
      const original = state.initial.characters[proposal.actorId].tasks[milestone.taskId];
      const elapsedSeconds = (Date.parse(`${state.time.dateTime}Z`) - Date.parse(`${world.time.dateTime}Z`)) / 1000;
      const to = actor.sanity + effects[proposal.effect];
      decision = !task || !original || task.ownerId !== proposal.actorId || original.ownerId !== proposal.actorId
        || task.goal !== milestone.goal || original.goal !== milestone.goal
        ? { outcome: 'refused', reason: 'registered_task_missing_or_mismatched', effects: [] }
        : task.status !== 'pending' ? { outcome: 'refused', reason: 'task_already_achieved', effects: [] }
        : actor.position.containerId !== milestone.requiredLocationId ? { outcome: 'refused', reason: 'milestone_location_mismatch', effects: [] }
        : !Number.isFinite(elapsedSeconds) || elapsedSeconds < milestone.minimumElapsedSeconds
          ? { outcome: 'refused', reason: 'milestone_execution_time_incomplete', effects: [] }
        : !Number.isSafeInteger(actor.sanity) || actor.sanity < minimum || actor.sanity > maximum
        ? { outcome: 'refused', reason: 'source_value_outside_policy', effects: [] }
        : to < minimum || to > maximum ? { outcome: 'refused', reason: 'result_outside_policy', effects: [] }
        : { outcome: 'allowed', effects: [{ kind: 'sanity_changed', actorId: proposal.actorId, from: actor.sanity, to,
          achievedTaskId: milestone.taskId, goal: milestone.goal, personalityText: milestone.personalityText,
          draftChangeId: `rule_${proposal.effect}_${world.advance.inputId}` }] };
    }
    const receipt = Object.freeze({}) as RuleReceipt;
    this.receipts.set(receipt, clone({ scope: ruleScope(world, request.pointId), decision, proposal }));
    return receipt;
  }

  inspect(receipt: RuleReceipt): { scope: RuleScope; decision: RuleDecision; proposal: RuleProposal } {
    const saved = this.receipts.get(receipt);
    if (!saved) throw new Error('rule_receipt_not_issued_by_this_authority');
    return clone(saved);
  }

  deltas(receipt: RuleReceipt, world: WorldContext, pointId: Id, state: WorldState): Record<Id, EntityDelta> {
    const saved = this.inspect(receipt);
    if (world.advance.intentStatus !== 'pending' || !world.advance.inputAvailable) throw new Error('rule_input_not_pending');
    if (!same(saved.scope, ruleScope(world, pointId)) || state.worldId !== saved.scope.worldId) throw new Error('rule_receipt_scope_changed');
    const deltas: Record<Id, EntityDelta> = {};
    for (const effect of saved.decision.effects) {
      const actor = state.characters[effect.actorId];
      if (!actor) throw new Error('rule_effect_actor_missing');
      if (effect.kind === 'moved') {
        if (actor.position.containerId !== effect.from || actor.position.slotId != null || actor.position.relativeTo != null) throw new Error('rule_effect_precondition_changed');
        deltas[effect.actorId] = { entityId: effect.actorId, positionSet: { containerId: effect.to, slotId: null, relativeTo: null } };
      } else {
        if (actor.sanity !== effect.from) throw new Error('rule_effect_precondition_changed');
        const task = actor.tasks[effect.achievedTaskId];
        if (!task || task.status !== 'pending') throw new Error('rule_task_already_consumed');
        const milestone = this.policy.sanity.milestones[(saved.proposal as Extract<RuleProposal, { kind: 'sanity' }>).effect];
        if (task.goal !== effect.goal || task.ownerId !== effect.actorId || actor.position.containerId !== milestone.requiredLocationId) throw new Error('rule_effect_precondition_changed');
        deltas[effect.actorId] = { entityId: effect.actorId, tasksAchieved: [effect.achievedTaskId],
          personalityChanges: [{ id: effect.draftChangeId, text: effect.personalityText, supersedes: [] }], sanitySet: effect.to };
      }
    }
    return deltas;
  }
}

export function describeRuleDecision(decision: RuleDecision, state: WorldState): string {
  if (decision.outcome === 'refused') return `规则拒绝执行（${decision.reason}）；没有位置或数值变化。`;
  return decision.effects.map((effect) => {
    const name = state.initial.characters[effect.actorId].name;
    return effect.kind === 'moved'
      ? `${name}从${state.initial.locations[effect.from].name}走到${state.initial.locations[effect.to].name}。`
      : `${name}完成任务「${effect.goal}」，${effect.personalityText}；精神值从${effect.from}变为${effect.to}。`;
  }).join('');
}

export const RULE_ACTION_PREFIX = 'rule-proposal-v1:';
export const encodeRuleAction = (proposal: RuleProposal) => RULE_ACTION_PREFIX + JSON.stringify(proposal);
export const decodeRuleAction = (text: string): RuleProposal => {
  if (!text.startsWith(RULE_ACTION_PREFIX)) throw new Error('free_text_is_not_rule_execution_evidence');
  return validateRuleProposal(JSON.parse(text.slice(RULE_ACTION_PREFIX.length)) as Json);
};
