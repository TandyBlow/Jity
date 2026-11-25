/** Structured round events for continuation judgement.
 *
 * A repeated sentence is evidence, not a verdict: the same guard after a new
 * event is legitimate continuous behavior. These records describe what the
 * round actually changed, so repeat classification compares the event and the
 * world digest, not the prose alone. */
import type { EntityDelta, Id, TimeAdvance, WorldState } from '../../types';

export interface ContinuationRoundPoint {
  pointId: Id;
  timeAdvance: TimeAdvance | null;
  entityDeltas: Record<Id, EntityDelta>;
}

export type ContinuationEventKind = 'move' | 'appearance' | 'sanity' | 'task' | 'subtask';

export interface ContinuationEvent {
  pointId: Id;
  kind: ContinuationEventKind;
  entityId: Id;
  containerId: Id | null;
  slotId: Id | null;
  taskIds: Id[];
  text: string;
  worldDigest?: string;
}

/** A follow-up accepted earlier in this submission (or turn). */
export interface AcceptedContinuationEvent {
  roundId?: Id;
  characterId: Id;
  text: string;
  worldDigest?: string;
}

export type RepeatKind = 'new' | 'new_world' | 'same_world';

export function normalizeEventText(text: string): string {
  return text.replace(/\s+/gu, '').replace(/[。！？!?；;，,、]+$/u, '').trim();
}

function entityName(state: WorldState, id: Id): string {
  return state.initial.characters[id]?.name ?? state.initial.items[id]?.name
    ?? state.initial.locations[id]?.name ?? id;
}

function taskGoal(state: WorldState, ownerId: Id, taskId: Id): string {
  return state.initial.characters[ownerId]?.tasks?.[taskId]?.goal
    ?? state.characters[ownerId]?.tasks?.[taskId]?.goal ?? taskId;
}

/** Committed point deltas as one flat event list, in commit order. */
export function buildRoundEvents(
  points: readonly ContinuationRoundPoint[],
  state: WorldState,
  worldDigest?: string,
): ContinuationEvent[] {
  const out: ContinuationEvent[] = [];
  const push = (row: Omit<ContinuationEvent, 'worldDigest'>) => {
    out.push({ ...row, ...(worldDigest ? { worldDigest } : {}) });
  };
  for (const point of points) {
    for (const [entityId, delta] of Object.entries(point.entityDeltas) as Array<[Id, EntityDelta]>) {
      const name = entityName(state, entityId);
      if (delta.positionSet) {
        const container = entityName(state, delta.positionSet.containerId);
        const slot = delta.positionSet.slotId ?? null;
        push({
          pointId: point.pointId, kind: 'move', entityId,
          containerId: delta.positionSet.containerId, slotId: slot,
          taskIds: [], text: `${name}移动到${container}${slot ? `（${slot}）` : ''}`,
        });
      }
      for (const change of delta.appearanceChanges ?? []) {
        push({
          pointId: point.pointId, kind: 'appearance', entityId,
          containerId: null, slotId: null, taskIds: [],
          text: `${name}外貌变化：${change.text ?? '更新'}`,
        });
      }
      if (typeof delta.sanitySet === 'number') {
        push({
          pointId: point.pointId, kind: 'sanity', entityId,
          containerId: null, slotId: null, taskIds: [],
          text: `${name}理智变为${delta.sanitySet}`,
        });
      }
      for (const taskId of delta.tasksAchieved ?? []) {
        push({
          pointId: point.pointId, kind: 'task', entityId,
          containerId: null, slotId: null, taskIds: [taskId],
          text: `${name}完成任务：${taskGoal(state, entityId, taskId)}`,
        });
      }
      for (const task of delta.subtasksAdded ?? []) {
        push({
          pointId: point.pointId, kind: 'subtask', entityId,
          containerId: null, slotId: null, taskIds: [task.id],
          text: `${name}新增子任务：${task.goal}`,
        });
      }
    }
  }
  return out;
}

/** Prompt/evidence lines; identical texts from two points collapse. */
export function eventLines(events: readonly ContinuationEvent[], limit = 6): string[] {
  const seen = new Set<string>();
  const lines: string[] = [];
  for (const event of events) {
    const key = normalizeEventText(event.text);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    lines.push(`${event.pointId}：${event.text}`);
  }
  return lines.slice(-Math.max(1, limit));
}

export function repeatLabel(repeat: RepeatKind): string {
  if (repeat === 'same_world') return '刚做过同样的事且世界未变';
  if (repeat === 'new_world') return '做过类似的事但世界已变';
  return '没有重复';
}

/** Exact same follow-up under the same world digest is an invalid repeat.
 * A changed world digest may make the same sentence a new round of a
 * continuous behavior; the caller's streak rule still bounds it. */
export function classifyRepeat(
  candidate: { characterId: Id; text: string },
  history: readonly AcceptedContinuationEvent[],
  worldDigest?: string,
): RepeatKind {
  const text = normalizeEventText(candidate.text);
  let matched = false;
  for (const row of history) {
    if (row.characterId !== candidate.characterId) continue;
    if (normalizeEventText(row.text) !== text) continue;
    matched = true;
    if (!worldDigest || !row.worldDigest || row.worldDigest === worldDigest) return 'same_world';
  }
  return matched ? 'new_world' : 'new';
}
