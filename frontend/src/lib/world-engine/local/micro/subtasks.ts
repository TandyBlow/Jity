/** Program subtask proposer (E58/S04): structured fact markers -> one concrete
 * subgoal under a related pending task. No free generation; the existing
 * readSubtaskProposals filters still reject duplicates, foreign subjects,
 * restatements and ungrounded goals. */
import type { Id, WorldState } from '../../types';
import { sharesGoalWording } from '../semantics/settlement/updates';
import type { MicroSubtasksFn } from '../semantics/settlement/types';

function entityName(state: WorldState, id: string): string | null {
  const space = [state.initial.items, state.initial.locations, state.initial.characters];
  for (const group of space) {
    const row = (group as Record<string, { name?: string }>)[id];
    if (row?.name) return row.name;
  }
  return null;
}

function candidatesFor(state: WorldState, memberId: Id, text: string): string[] {
  const out: string[] = [];
  const route = /确认了?([^，。；]{2,12}?)的(?:通行|路况|情况)/u.exec(text);
  if (route) out.push(`确认${route[1]}是否仍能通行`);
  const info = /信息=([^:；]+):([^；。]+)/u.exec(text);
  if (info) {
    const name = entityName(state, info[1]);
    if (name) out.push(`查看${name}上的内容`);
  }
  const partial = /环境=([^:；]+):已被部分([^；。]+)/u.exec(text);
  if (partial) {
    const name = entityName(state, partial[1]);
    if (name) out.push(`把${name}完全${partial[2]}`);
  }
  if (text.includes('只完成一部分')) {
    const destination = /去向=[^:；]+:([^/；。]+)/u.exec(text);
    if (destination) {
      const name = entityName(state, destination[1]);
      if (name) out.push(`到达${name}`);
    }
  }
  return out;
}

function normalize(goal: string): string {
  return goal.replace(/[^一-鿿A-Za-z0-9]/gu, '');
}

/** The subgoal must stay on the parent task's topic. Wording overlap is the
 * first signal; a shared registered entity is the second. */
function related(state: WorldState, candidate: string, parentGoal: string): boolean {
  if (sharesGoalWording(candidate, parentGoal)) return true;
  for (const group of [state.initial.items, state.initial.locations, state.initial.characters]) {
    for (const entity of Object.values(group as Record<string, { name?: string }>)) {
      const name = entity.name ?? '';
      const core = name.split('的').pop() ?? '';
      for (const token of [name, core]) {
        if (token.length >= 2 && candidate.includes(token) && parentGoal.includes(token)) return true;
      }
    }
  }
  return false;
}

/** A pending parent that already names a check ("查明X是否…") can host the
 * matching confirmation subgoal when this point's fact names X. */
function parentCandidates(parentGoal: string, factText: string): string[] {
  const probe = /(?:查明|确认|核实)([^，。；]{2,12}?)((?:是否|能否)[^，。；]*)/u.exec(parentGoal);
  if (!probe) return [];
  const entity = probe[1].replace(/^.+?的/u, '');
  return entity && factText.includes(entity) ? [`确认${probe[1]}${probe[2]}`] : [];
}

export const createProgramSubtasks: MicroSubtasksFn = (request) => {
  const owners = new Set(request.ownerIds);
  const pending = Object.entries(request.state.characters).flatMap(([ownerId, current]) => {
    if (!owners.has(ownerId)) return [];
    const name = request.state.initial.characters[ownerId]?.name ?? ownerId;
    return Object.values(current.tasks)
      .filter((task) => task.status === 'pending')
      .map((task) => ({ ownerId, name, task }));
  });
  const existing = new Set(pending.map((row) => normalize(row.task.goal)));
  const seen = new Set<string>();
  const best = new Map<string, { characterId: Id; parentTaskId: Id; goal: string; basis: string }>();
  for (const fact of request.facts) {
    for (const row of pending) {
      if (fact.memberId !== row.ownerId && !fact.text.includes(row.name)) continue;
      const candidates = [...candidatesFor(request.state, fact.memberId, fact.text),
        ...parentCandidates(row.task.goal, fact.text)];
      for (const candidate of candidates) {
        if (!related(request.state, candidate, row.task.goal)) continue;
        const key = normalize(candidate);
        if (existing.has(key) || seen.has(key)) continue;
        if (!best.has(row.task.id)) {
          best.set(row.task.id, { characterId: row.ownerId, parentTaskId: row.task.id, goal: candidate, basis: fact.id });
        }
        seen.add(key);
      }
    }
  }
  return { subtasks: [...best.values()], source: 'program' };
};
