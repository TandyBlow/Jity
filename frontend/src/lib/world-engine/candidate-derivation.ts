/** B-side corpus derivation (§9.3): recorded stage/commit candidates carry
 * model-chosen change/task ids from an era before the server bound stored
 * identities to allocations. The live controller allocates at send time and
 * rewrites the ids (controller.ensureCandidateIdentities); the corpus must
 * declare exactly that — one allocate_ids step per stage step plus every
 * stored definition AND its references (tasksAchieved, parentTaskId,
 * supersedes) rewritten to the granted value. Recorded preview requests are
 * only touched where they fold already-staged candidates; previews are
 * model-shaped and the server validates stored identities only on
 * stage/commit. Slot keys mirror the controller's
 * foldIdentity(scopeKey, entity, modelId) derivation exactly. */
import { foldIdentity } from './schedule';
import type { CorpusStep } from './harness';
import type { Id, Json } from './types';

type CandidateCarrier = { groupId?: Id | null;
  appearances?: Record<Id, { id: Id; supersedes?: Id[] }[]>;
  personalities?: Record<Id, { id: Id; supersedes?: Id[] }[]>;
  tasksAchieved?: Record<Id, Id[]>;
  subtasksAdded?: Record<Id, { id: Id; parentTaskId?: Id | null }[]> };

function groupsOf(step: CorpusStep): { scopeKey: Id; candidates: CandidateCarrier }[] {
  const request = step.request as Record<string, unknown>;
  if (step.operation === 'checkpoint_stage_unit' || step.operation === 'checkpoint_stage_time_scan') {
    const candidates = request.candidates as CandidateCarrier | undefined;
    return candidates ? [{ scopeKey: (candidates.groupId ?? request.pointId ?? step.scope.worldId ?? 'point') as Id, candidates }] : [];
  }
  if (step.operation === 'commit_point') {
    return ((request.settlementGroups as CandidateCarrier[] | undefined) ?? []).map((candidates) => ({
      scopeKey: (candidates.groupId ?? request.pointId ?? step.scope.worldId ?? 'point') as Id, candidates }));
  }
  return [];
}

/** Mutate the corpus in place: grant ids for every stored change/task
 * identity, rewrite the recorded candidates to them, and splice one
 * allocate_ids step before each stage step that needs it. */
export function deriveCandidateIdentities(steps: CorpusStep[]): void {
  const granted = new Map<string, Id>();
  const byScope = new Map<Id, Map<Id, { alloc: Id; at: number }>>();
  let changes = 0;
  let tasks = 0;
  const stageSites: { index: number; scopeKey: Id; slots: { slotKey: Id; kind: 'change' | 'task' }[] }[] = [];
  const scopeMap = (scopeKey: Id): Map<Id, { alloc: Id; at: number }> => {
    let map = byScope.get(scopeKey);
    if (!map) { map = new Map(); byScope.set(scopeKey, map); }
    return map;
  };
  const walk = (step: CorpusStep, index: number): void => {
    for (const { scopeKey, candidates } of groupsOf(step)) {
      const grants = scopeMap(scopeKey);
      const collect = (entity: Id, kind: 'change' | 'task', list: { id: Id }[] | undefined) => {
        for (const target of list ?? []) {
          const alias = `${kind}:${foldIdentity(scopeKey, entity, target.id)}`;
          let allocated = granted.get(alias);
          if (allocated === undefined) {
            allocated = kind === 'change' ? `alloc_change_${changes++}` : `alloc_task_${tasks++}`;
            granted.set(alias, allocated);
          }
          // First grant wins the index: a later commit step re-walks the same
          // ids and must not push their grant time past earlier previews.
          if (!grants.get(target.id)) grants.set(target.id, { alloc: allocated, at: index });
          target.id = allocated;
        }
      };
      for (const [entity, list] of Object.entries(candidates.appearances ?? {})) collect(entity, 'change', list);
      for (const [entity, list] of Object.entries(candidates.personalities ?? {})) collect(entity, 'change', list);
      for (const [entity, list] of Object.entries(candidates.subtasksAdded ?? {})) collect(entity, 'task', list);
    }
  };
  // First pass: grant + rewrite everywhere (stage steps register slots).
  for (let index = 0; index < steps.length; index++) {
    const step = steps[index];
    const isStage = step.operation === 'checkpoint_stage_unit' || step.operation === 'checkpoint_stage_time_scan';
    const before = granted.size;
    walk(step, index);
    if (isStage) {
      const fresh = [...granted.keys()].slice(before);
      if (fresh.length) {
        const request = step.request as Record<string, unknown>;
        const scopeKey = ((request.candidates as CandidateCarrier)?.groupId ?? request.pointId ?? step.scope.worldId ?? 'point') as Id;
        stageSites.push({ index, scopeKey, slots: fresh.map((alias) => ({
          slotKey: alias as Id, kind: (alias.startsWith('task:') ? 'task' : 'change') as 'task' | 'change' })) });
      }
    }
  }
  // Stored identities are definitions; tasksAchieved, parentTaskId and
  // supersedes are references. The live controller rewrites both sides with
  // the SAME slot map, so the corpus must not leave a reference on the draft
  // after the definition moved to its allocated id.
  const rewriteReferences = (scopeKey: Id, candidates: CandidateCarrier, index: number, inclusive: boolean): void => {
    const grants = byScope.get(scopeKey);
    if (!grants) return;
    const mapped = (id: Id): Id => {
      const grant = grants.get(id);
      return grant && (inclusive ? grant.at <= index : grant.at < index) ? grant.alloc : id;
    };
    for (const list of [...Object.values(candidates.appearances ?? {}), ...Object.values(candidates.personalities ?? {})]) {
      for (const change of list) if (change.supersedes) change.supersedes = change.supersedes.map(mapped);
    }
    for (const list of Object.values(candidates.tasksAchieved ?? {})) {
      for (let position = 0; position < list.length; position++) list[position] = mapped(list[position]);
    }
    for (const list of Object.values(candidates.subtasksAdded ?? {})) {
      for (const task of list) if (task.parentTaskId != null) task.parentTaskId = mapped(task.parentTaskId);
    }
  };
  // Stage/commit requests carry the complete identity set at send time, so a
  // definition granted in this same step is a legal reference target.
  for (let index = 0; index < steps.length; index++) {
    const step = steps[index];
    if (step.operation !== 'checkpoint_stage_unit' && step.operation !== 'checkpoint_stage_time_scan'
        && step.operation !== 'commit_point') continue;
    for (const { scopeKey, candidates } of groupsOf(step)) rewriteReferences(scopeKey, candidates, index, true);
  }
  // Second pass: staged-derived previews. Once a group has been staged, the
  // controller folds the SAME (rewritten) candidate objects into later
  // preview requests, so recorded previews whose ids were granted at an
  // EARLIER index must be rewritten too. Boundary previews carry genuinely
  // model-new ids (not granted yet at their point in the stream) and stay
  // exactly as recorded.
  if (process.env.DEBUG_CANDIDATE_DERIVATION) {
    console.error('[derive] grants:', [...byScope.entries()].map(([scope, map]) => ({ scope,
      ids: [...map.entries()].map(([id, v]) => `${id}@${v.at}->${v.alloc}`) })));
    for (const step of steps) if (step.operation === 'preview_point') console.error('[derive] preview step', step.id, 'index', steps.indexOf(step));
  }
  for (let index = 0; index < steps.length; index++) {
    const step = steps[index];
    if (step.operation !== 'preview_point') continue;
    const request = step.request as Record<string, unknown>;
    for (const group of (request.settlementGroups as CandidateCarrier[] | undefined) ?? []) {
      const grants = byScope.get((group.groupId ?? request.pointId ?? step.scope.worldId ?? 'point') as Id);
      if (!grants) continue;
      const rewrite = (list: { id: Id }[] | undefined) => {
        for (const target of list ?? []) {
          const grantedAt = grants.get(target.id);
          if (grantedAt && grantedAt.at < index) target.id = grantedAt.alloc;
        }
      };
      for (const [entity, list] of Object.entries(group.appearances ?? {})) rewrite(list);
      for (const [entity, list] of Object.entries(group.personalities ?? {})) rewrite(list);
      for (const [entity, list] of Object.entries(group.subtasksAdded ?? {})) rewrite(list);
      rewriteReferences((group.groupId ?? request.pointId ?? step.scope.worldId ?? 'point') as Id, group, index, false);
    }
  }
  // Second pass: splice one allocate step before each stage site, last first
  // so the earlier indices stay valid.
  for (const site of [...stageSites].reverse()) {
    const stage = steps[site.index];
    const stageRequest = stage.request as Record<string, unknown>;
    const allocation: CorpusStep = {
      id: `${stage.id}-alloc-candidates`, segment: 'controller', sharedStepId: null, operation: 'allocate_ids',
      request: { protocolVersion: 2, worldId: stageRequest.worldId,
        leaseToken: stageRequest.leaseToken, fenceEpoch: stageRequest.fenceEpoch,
        allocationKey: `candidates:${foldIdentity(site.scopeKey)}`, slots: site.slots } as unknown as Json,
      requestIdRequired: true, requestIdExpectation: 'fresh', scope: stage.scope,
      response: { ...structuredClone(stage.response as Record<string, unknown>), operation: 'allocate_ids', requestHash: '0'.repeat(64),
        data: { allocations: site.slots.map(({ slotKey }) => ({ slotKey, id: granted.get(slotKey) })) } } as unknown as Json,
      responseKind: 'success', captures: [], digestChain: [],
    };
    steps.splice(site.index, 0, allocation);
  }
}
