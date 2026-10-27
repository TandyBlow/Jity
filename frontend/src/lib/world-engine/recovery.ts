/** H2 bootstrap. Reads saved point records and short-lived frozen work only;
 * it never asks a model to reconstruct confirmed text, candidates or dice. */
import type { ControllerMemory, PlannedPoint, SourceAnalysis, StagedUnit } from './schedule';
import { foldIdentity, PROGRAM_ROLL_RULE } from './schedule';
import { WorldApiError, WorldTimeoutError, type WorldTransport } from './transport';
import type { Baseline, ContextResponse, DataMap, Id, LeaseGrant, PointRecovery, RequestMap, Success, WorldContext, WorldOperation } from './types';

export type RecoveryLease = Pick<LeaseGrant, 'leaseToken' | 'fenceEpoch'>;

export class RecoveryStopped extends Error {
  constructor(readonly reason: string) { super(reason); }
}

function requireRecovery(condition: unknown, reason: string): asserts condition {
  if (!condition) throw new RecoveryStopped(reason);
}

/** Threat identity across progress entries and final roll rows. */
function threatKey(item: { sourceId: Id; targetId: Id; triggerKey: Id }): string {
  return `${item.sourceId}|${item.targetId}|${item.triggerKey}`;
}

/** JSON equality for wire records; property insertion order is irrelevant. */
function equal(a: unknown, b: unknown): boolean {
  const normalize = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(normalize);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, item]) => [key, normalize(item)]));
    return value;
  };
  return JSON.stringify(normalize(a)) === JSON.stringify(normalize(b));
}

/** Expiry/clock and narration readiness may change independently. These
 * fields bind the computation snapshot; a different fence/head/round/work
 * invalidates the whole bootstrap rather than mixing two generations. */
function snapshot(world: WorldContext): unknown {
  return { worldId: world.worldId, head: { pointId: world.head.pointId, version: world.head.version, stateDigest: world.head.stateDigest },
    epoch: world.lease?.fenceEpoch, round: world.round, advance: world.advance,
    activePointId: world.activePointId, activeRoundId: world.activeRoundId, successor: world.successor };
}

export type PointMemory = Pick<ControllerMemory, 'staged' | 'stagedTimeScan' | 'groupActors' | 'groupActions' | 'sources' | 'lastResults' | 'restoredUnit'>;

/** Copy only confirmed current work. Missing fields are never empty work.
 * The recovery payload now carries the full dice facts (rolls) and the
 * persisted DFS checkpoint (progress); neither is ever re-derived from
 * member order, and a rejected roll is still reported to results. */
export function recoverPoint(point: PointRecovery, world: WorldContext, baseline: Baseline = { headPointId: world.head.pointId, version: world.head.version, stateDigest: world.head.stateDigest }): PointMemory {
  const work = point.work;
  requireRecovery(equal(work.baseline, baseline), 'recovery_baseline_mismatch');
  requireRecovery(point.payloadStatus === 'available', 'recovery_payload_unavailable');
  requireRecovery(new Set(point.groups.map((g) => g.groupId)).size === point.groups.length, 'recovery_duplicate_group');
  requireRecovery(point.groups.every((g) => g.pointId === work.pointId), 'recovery_point_mismatch');
  requireRecovery(equal(point.groups.map((g) => g.groupId).sort(), [...work.settledUnits.map((u) => u.groupId), ...(work.pendingGroup ? [work.pendingGroup.groupId] : [])].sort()), 'recovery_groups_incomplete');
  const staged: StagedUnit[] = work.settledUnits.map((unit) => {
    const group = point.groups.find((g) => g.groupId === unit.groupId);
    requireRecovery(group?.candidates, `recovery_candidates_missing:${unit.groupId}`);
    requireRecovery(equal([...group.candidates.actorIds].sort(), [...unit.memberIds].sort()), `recovery_members_mismatch:${unit.groupId}`);
    requireRecovery(equal(group.members.map((m) => m.memberId).sort(), [...unit.memberIds].sort()), `recovery_members_mismatch:${unit.groupId}`);
    const results: Record<Id, string> = {};
    for (const id of unit.memberIds) {
      const member = group.members.find((m) => m.memberId === id);
      requireRecovery(typeof member?.actionText === 'string' && member.actionText.length > 0, `frozen_actions_missing:${id}`);
      requireRecovery(typeof member.resultText === 'string', `recovery_results_missing:${id}`);
      results[id] = member.resultText;
    }
    return { groupId: unit.groupId, actorIds: [...unit.memberIds], candidates: structuredClone(group.candidates), results };
  });
  requireRecovery(work.timeScanComplete === (point.timeScanCandidates !== null), 'recovery_time_scan_missing');
  const memory: PointMemory = { staged, stagedTimeScan: structuredClone(point.timeScanCandidates),
    groupActors: [...new Set([...world.round?.visitedIds ?? [], ...work.working.visitedIds, ...work.working.actedIds])],
    groupActions: [], sources: [], lastResults: null, restoredUnit: null };
  const pending = work.pendingGroup;
  if (!pending) return memory;
  const group = point.groups.find((g) => g.groupId === pending.groupId);
  requireRecovery(group, `recovery_group_missing:${pending.groupId}`);
  requireRecovery(equal(group.members.map((m) => m.memberId).sort(), [...pending.memberIds].sort()), 'recovery_members_mismatch');
  // Independent cross-checks over the payload the wire schema cannot bind:
  // threat progress mirrors confirmed targets one-to-one, every non-pending
  // threat references exactly one final roll of the same key, and rolls
  // never outrun their references.
  const threats = new Map(group.progress.threats.map((t) => [threatKey(t), t] as const));
  const rolls = new Map(group.rolls.map((r) => [threatKey(r), r] as const));
  const confirmed = new Set(group.members.flatMap((m) => (m.targets ?? []).map((t) => threatKey({ sourceId: m.memberId, targetId: t.targetId, triggerKey: t.triggerKey }))));
  requireRecovery(threats.size === confirmed.size && [...threats.keys()].every((key) => confirmed.has(key)), 'recovery_progress_target_mismatch');
  for (const [key, threat] of threats) {
    const roll = rolls.get(key);
    if (threat.status === 'pending_roll') requireRecovery(roll === undefined, 'recovery_progress_roll_conflict');
    else requireRecovery(roll !== undefined && threat.rollId === roll.rollId, 'recovery_progress_roll_mismatch');
  }
  requireRecovery(rolls.size === [...threats.values()].filter((t) => t.status !== 'pending_roll').length, 'recovery_progress_roll_unreferenced');
  // Reaction-pending members are placeholders awaiting their generated
  // reaction; every other member must carry confirmed frozen text.
  const pendingReactions = new Set([...threats.values()].filter((t) => t.status === 'reaction_pending').map((t) => t.targetId));
  for (const member of group.members) {
    requireRecovery(member.actionText === null ? pendingReactions.has(member.memberId) : member.actionText.length > 0, `frozen_actions_missing:${member.memberId}`);
    if (member.actionText !== null) {
      memory.groupActions.push({ memberId: member.memberId, actionText: member.actionText,
        rolls: group.rolls.filter((roll) => roll.sourceId === member.memberId).map((roll) => ({ targetId: roll.targetId, rollId: roll.rollId, result: roll.result, eligible: roll.eligible, admitted: roll.admitted })) });
    }
    if (!memory.groupActors.includes(member.memberId)) memory.groupActors.push(member.memberId);
  }
  const results = Object.fromEntries(group.members.filter((m) => m.resultText !== null).map((m) => [m.memberId, m.resultText! ]));
  requireRecovery(Object.keys(results).length === 0 || Object.keys(results).length === group.members.length, 'recovery_results_incomplete');
  if (Object.keys(results).length) memory.lastResults = results;
  requireRecovery(!memory.lastResults || pending.closed, 'recovery_results_before_close');
  if (group.candidates) {
    requireRecovery(pending.closed && memory.lastResults, 'recovery_candidates_without_results');
    memory.restoredUnit = { groupId: group.groupId, actorIds: [...pending.memberIds], candidates: structuredClone(group.candidates), results };
    return memory;
  }
  // A saved result permits updates without asking results again. Closed
  // groups without saved results go straight to the results task instead:
  // groupActions above already carries every confirmed member's frozen text
  // and full dice facts, including rejected rolls.
  if (group.candidates) {
    requireRecovery(pending.closed && memory.lastResults, 'recovery_candidates_without_results');
    memory.restoredUnit = { groupId: group.groupId, actorIds: [...pending.memberIds], candidates: structuredClone(group.candidates), results };
    return memory;
  }
  if (pending.closed) {
    requireRecovery(group.progress.sourceStack.length === 0, 'recovery_closed_stack_remaining');
    return memory;
  }
  // Rebuild the saved DFS checkpoint instead of guessing an order from
  // member layout: sourceStack[0] is the source to work on, the tail is the
  // initiator. Threat states decide what each frame still owes — a
  // pending_roll frame re-rolls the SAME key, a reaction_pending frame
  // generates only the unconfirmed reaction, and handled frames simply wait
  // until the subtree saved above them finishes. Frames are never re-pushed
  // here: the stack is the server-persisted truth.
  if (group.progress.sourceStack.length === 0) return memory; // every threat handled; the next decision is close_group
  const members = new Map(group.members.map((m) => [m.memberId, m] as const));
  const order = (a: { targetId: Id; triggerKey: Id }, b: { targetId: Id; triggerKey: Id }) =>
    a.targetId < b.targetId ? -1 : a.targetId > b.targetId ? 1 : a.triggerKey < b.triggerKey ? -1 : a.triggerKey > b.triggerKey ? 1 : 0;
  memory.sources = group.progress.sourceStack.map((sourceId) => {
    const actionText = members.get(sourceId)?.actionText ?? null;
    requireRecovery(typeof actionText === 'string' && actionText.length > 0, `recovery_stack_source_unconfirmed:${sourceId}`);
    const mine = [...threats.values()].filter((t) => t.sourceId === sourceId);
    const pendingTargets = mine.filter((t) => t.status === 'pending_roll')
      .map((t) => ({ targetId: t.targetId, triggerKey: t.triggerKey, rule: PROGRAM_ROLL_RULE })).sort(order);
    const rolled = mine.filter((t) => t.status !== 'pending_roll').map((t) => {
      const roll = rolls.get(threatKey(t))!;
      return { targetId: t.targetId, triggerKey: t.triggerKey, rule: { ruleVersion: roll.ruleVersion, target: roll.target },
        rollId: roll.rollId, admitted: roll.admitted, reacted: t.status === 'handled' };
    }).sort(order);
    return { sourceId, actionText, targetsExtended: members.get(sourceId)!.targets !== null, pendingTargets, rolled };
  });
  return memory;
}

export interface RecoveredController {
  context: ContextResponse;
  leaseToken: Id;
  point: PointMemory | null;
  successor: PointRecovery | null;
  plan: PlannedPoint[] | null;
  ids: Record<Id, Id>;
  workingState: NonNullable<ControllerMemory['workingState']>;
  roundChanges: ControllerMemory['roundChanges'];
}

export async function readControllerRecovery(transport: WorldTransport, worldId: Id, holderId: Id, nextRequestId: () => Id, retryLimit = 3, heldLease?: RecoveryLease): Promise<RecoveredController> {
  let retries = retryLimit;
  const call = async <K extends WorldOperation>(operation: K, request: RequestMap[K]): Promise<Success<K>> => {
    // Retain exact bytes/identity on unknown fate. Other errors STOP this
    // bootstrap; no error followup may silently swap its authority/snapshot.
    for (;;) {
      try { return await transport.execute(operation, request, { worldId }); }
      catch (error) {
        if (error instanceof WorldTimeoutError || error instanceof WorldApiError && error.response.error.code === 'request_in_progress') {
          requireRecovery(retries-- > 0, `recovery_retry_limit:${operation}`);
          continue;
        }
        if (error instanceof WorldApiError) throw new RecoveryStopped(`recovery_refused:${operation}:${error.response.error.code}`);
        throw error;
      }
    }
  };
  const grant = heldLease
    ? await call('lease_renew', { protocolVersion: 2, requestId: nextRequestId(), worldId, ...heldLease })
    : await call('lease_acquire', { protocolVersion: 2, requestId: nextRequestId(), worldId, holderId });
  requireRecovery(grant.world.worldId === worldId && grant.world.lease?.fenceEpoch === grant.data.fenceEpoch && grant.data.leaseToken, 'recovery_lease_mismatch');
  requireRecovery(!heldLease || grant.data.fenceEpoch === heldLease.fenceEpoch && grant.data.leaseToken === heldLease.leaseToken, 'recovery_lease_mismatch');
  const binding = { leaseToken: grant.data.leaseToken, fenceEpoch: grant.data.fenceEpoch };
  const readContext = () => call('get_context', { includeRecovery: true, ...binding });
  let context = await readContext();
  const checkWorld = (world: WorldContext) => requireRecovery(equal(snapshot(context.world), snapshot(world)), 'recovery_snapshot_changed');
  requireRecovery(context.world.worldId === worldId && context.world.lease?.fenceEpoch === binding.fenceEpoch, 'recovery_lease_mismatch');
  const checkRecovery = (c: ContextResponse) => {
    requireRecovery(c.recovery ? c.recovery.fenceEpoch === binding.fenceEpoch
      : c.work === null && c.world.activePointId === null && c.world.successor === null, 'recovery_context_missing');
  };
  checkRecovery(context);
  const original = context;
  const points = [context.recovery?.current ?? null, context.recovery?.successor ?? null].filter((p): p is PointRecovery => p !== null);
  for (const point of points) {
    if (point.payloadStatus !== 'restore_required') continue;
    requireRecovery(point.restoreSources.length > 0, 'recovery_sources_missing');
    for (const source of point.restoreSources) {
      requireRecovery(source.pointId === point.work.pointId && source.manifest.length > 0, 'recovery_source_mismatch');
      const restored = await call('checkpoint_restore_group_work', { protocolVersion: 2, requestId: nextRequestId(), worldId, ...binding,
        expectedPointId: context.world.head.pointId, expectedVersion: context.world.head.version, expectedCheckpointRevision: context.control.revision,
        operation: 'restore_group_work', ...structuredClone(source) });
      checkWorld(restored.world);
      requireRecovery(equal(context.control, restored.control) && equal(context.work, restored.work), 'recovery_snapshot_changed');
      requireRecovery(restored.data.pointId === source.pointId && restored.data.groupId === source.groupId && restored.data.fenceEpoch === binding.fenceEpoch
        && restored.data.sourceEpoch === source.sourceEpoch && restored.data.sourceAttempt === source.sourceAttempt
        && equal([...restored.data.restoredMemberIds].sort(), source.manifest.map((m) => m.memberId).sort()), 'recovery_restore_receipt_mismatch');
    }
  }
  // Always read originals after copying; a restore receipt is not the text.
  if (points.some((p) => p.payloadStatus === 'restore_required')) {
    context = await readContext();
    requireRecovery(equal(snapshot(original.world), snapshot(context.world)) && equal(original.control, context.control) && equal(original.work, context.work), 'recovery_snapshot_changed');
  }
  checkRecovery(context);
  requireRecovery(equal(context.work, context.recovery?.current?.work ?? null), 'recovery_work_mismatch');
  const current = context.recovery?.current ?? null;
  const successor = context.recovery?.successor ?? null;
  const pointMemory = current ? recoverPoint(current, context.world) : null;
  let successorMemory: PointMemory | null = null;
  if (successor) {
    const reservation = current?.work.successor;
    requireRecovery(current?.work.sealed && reservation && reservation.pointId === successor.work.pointId
      && reservation.predecessorPointId === current.work.pointId && equal(reservation, context.world.successor)
      && reservation.prefixDigest === current.work.prefixDigest && reservation.expectedPredecessorVersion === context.world.head.version + 1
      && reservation.baseline.headPointId === current.work.pointId && reservation.baseline.version === reservation.expectedPredecessorVersion
      && reservation.baseline.stateDigest === reservation.expectedPredecessorStateDigest && equal(reservation.timeAdvance, successor.work.timeAdvance), 'recovery_successor_mismatch');
    // The reserved successor's baseline is the FUTURE predecessor commit,
    // not the presently committed head. Validate its explicit reservation.
    successorMemory = recoverPoint(successor, context.world, reservation.baseline);
  }
  requireRecovery(!context.world.successor || successor, 'recovery_successor_missing');

  // Page from the root through the captured head, checking EVERY sequence.
  // Filtering to this round before checking would conceal missing pages or
  // points and misrepresent a local suffix as the complete round history.
  const summaries: DataMap['list_points']['points'] = [];
  let after: number | null = null;
  while (summaries.length <= context.world.head.version) {
    const page = await call('list_points', { after, limit: 100 });
    checkWorld(page.world);
    requireRecovery(page.data.points.length > 0, 'recovery_history_incomplete');
    for (const point of page.data.points) {
      requireRecovery(point.sequence === summaries.length && !summaries.some((p) => p.pointId === point.pointId), 'recovery_history_gap');
      requireRecovery(point.sequence <= context.world.head.version, 'recovery_snapshot_changed');
      summaries.push(point);
    }
    after = summaries.length - 1;
  }
  const head = summaries[summaries.length - 1];
  requireRecovery(head.pointId === context.world.head.pointId && head.stateDigest === context.world.head.stateDigest && summaries[0].kind === 'root', 'recovery_history_head_mismatch');
  const roundId = context.world.round?.roundId;
  const roundPoints = summaries.filter((p) => p.roundId === roundId);
  if (roundPoints.length) {
    const start = roundPoints[0].sequence;
    requireRecovery(roundPoints.every((p, index) => p.sequence === start + index) && roundPoints[roundPoints.length - 1].pointId === head.pointId, 'recovery_history_round_mismatch');
  }
  const changes: NonNullable<ControllerMemory['roundChanges']>['points'] = [];
  let state: DataMap['get_state'] | null = null;
  for (const summary of summaries.filter((p) => p.roundId === roundId || p.pointId === head.pointId)) {
    const read = await call('get_state', { point: summary.pointId });
    checkWorld(read.world);
    const data = read.data;
    requireRecovery(data?.pointId === summary.pointId && data.version === summary.sequence && data.stateDigest === summary.stateDigest
      && data.state?.worldId === worldId && data.entityDeltas !== undefined && data.entityDeltas !== null
      && data.previousPointId === (summary.sequence === 0 ? null : summaries[summary.sequence - 1].pointId)
      && (summary.sequence === 0 ? data.timeAdvance === null : data.timeAdvance != null), `recovery_point_read_incomplete:${summary.pointId}`);
    if (summary.roundId === roundId) {
      // The advance binding only exists while an advance IS active. At a
      // handback boundary the server keeps the concluded round view while
      // advance is null — the round points' advanceId is then the advance
      // that committed them, a historical fact with nothing to bind to.
      if (context.world.advance.advanceId !== null) {
        requireRecovery(summary.advanceId === context.world.advance.advanceId, 'recovery_history_advance_mismatch');
      }
      changes.push({ pointId: summary.pointId, timeAdvance: structuredClone(data.timeAdvance!), entityDeltas: structuredClone(data.entityDeltas) });
    }
    if (summary.pointId === head.pointId) state = data;
  }
  requireRecovery(changes.length === roundPoints.length && state, 'recovery_history_incomplete');
  const verified = await readContext();
  requireRecovery(equal(snapshot(context.world), snapshot(verified.world)) && equal(context.control, verified.control)
    && equal(context.work, verified.work) && equal(context.recovery, verified.recovery), 'recovery_snapshot_changed');

  const ids: Record<Id, Id> = {};
  // Future, unconfirmed action opportunities still need program-owned group
  // identities. This allocation happens only after ALL recovery reads pass.
  const allocationPoint = current && !current.work.sealed ? current : successor && !successor.work.sealed ? successor : null;
  const allocationMemory = allocationPoint === current ? pointMemory : successorMemory;
  const remaining = allocationPoint ? context.world.round?.order.filter((id) => !allocationMemory!.groupActors.includes(id)) ?? [] : [];
  if (remaining.length) {
    const slots = remaining.map((id) => ({ slotKey: `group_${foldIdentity(id)}`, kind: 'group' as const }));
    const allocated = await call('allocate_ids', { protocolVersion: 2, requestId: nextRequestId(), worldId, ...binding,
      allocationKey: `recover_${foldIdentity(worldId, roundId!, allocationPoint!.work.pointId)}`, slots });
    checkWorld(allocated.world);
    requireRecovery(equal(context.control, allocated.control) && equal(context.work, allocated.work), 'recovery_snapshot_changed');
    requireRecovery(allocated.data.allocations.length === slots.length && new Set(allocated.data.allocations.map((a) => a.slotKey)).size === slots.length
      && slots.every((s) => allocated.data.allocations.some((a) => a.slotKey === s.slotKey)), 'recovery_allocation_incomplete');
    for (let index = 0; index < remaining.length; index++) ids[`group:${remaining[index]}`] = allocated.data.allocations.find((a) => a.slotKey === slots[index].slotKey)!.id;
  }
  const plan = current ? [current, ...(successor ? [successor] : [])].map((p) => ({ pointId: p.work.pointId, kind: p.work.kind,
    timeAdvance: structuredClone(p.work.timeAdvance), actorIds: [...context.world.round?.order ?? []] })) : null;
  return { context: verified, leaseToken: binding.leaseToken, point: pointMemory, successor: structuredClone(successor), plan, ids,
    workingState: { key: `recovered:${head.pointId}`, state: structuredClone(state.state) },
    roundChanges: roundId ? { roundId, points: changes } : null };
}
