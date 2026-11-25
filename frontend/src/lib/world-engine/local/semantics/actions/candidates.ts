/** Legal NPC behavior candidates from one pending task at a time.
 *
 * Each candidate carries the actor, category, target/item/destination and the
 * task it serves. Items are restricted to what the actor can see or hold, and
 * a candidate without its item/target is not generated (no vague "手边的器材"). */
import type { Id, WorldState } from '../../../types';
import type { ActionDestination, ActionCategory } from './structure';
import type { ActionScene } from './scene';
import { matchItems } from './structure';
import { matchLocation } from '../settlement/fact-destinations';

export interface BehaviorCandidate {
  id: string;
  category: ActionCategory;
  text: string;
  targetIds: Id[];
  itemIds: Id[];
  destination: ActionDestination | null;
  taskId: Id | null;
  taskGoal: string;
}

function core(name: string): string {
  const value = name.replace(/^.+?的/u, '');
  return value.length >= 2 ? value : name;
}

export function behaviorCandidates(scene: ActionScene, state: WorldState): BehaviorCandidate[] {
  const visibleItems = new Set(scene.items.map((item) => item.id));
  const items = Object.entries(state.initial.items)
    .filter(([id]) => visibleItems.has(id) || scene.actor.held.some((held) => held.id === id))
    .map(([id, item]) => ({ id, name: item.name ?? id }));
  const out: BehaviorCandidate[] = [];
  const push = (category: ActionCategory, text: string, extra: Partial<BehaviorCandidate>, task: { id: Id; goal: string }) => {
    if (!text) return;
    if (out.some((row) => row.text === text)) return;
    out.push({ id: `bc${out.length + 1}`, category, text, targetIds: [], itemIds: [], destination: null, taskId: task.id, taskGoal: task.goal, ...extra });
  };
  for (const task of scene.actor.tasks.filter((row) => row.status === 'pending').slice(0, 3)) {
    const goal = task.goal;
    const location = matchLocation(state, goal);
    if (location) {
      const moves = ['前往', '走向', '走进', '进入', '赶到', '回到', '退到', '离开', '去', '到'].some((verb) => goal.includes(verb));
      if (moves && scene.roomName !== location.name) {
        push('move', `${scene.actorName}走向${location.name}。`, { destination: { entityId: scene.actorId, containerId: location.id, slotId: null } }, task);
      }
      if (['守住', '护住', '挡住', '拦住', '守'].some((verb) => goal.includes(verb))) {
        push('guard', `${scene.actorName}守住${location.name}。`, { destination: { entityId: scene.actorId, containerId: location.id, slotId: null } }, task);
      }
    }
    const itemId = matchItems(goal, items, scene.actorName)[0];
    const item = itemId ? core(items.find((row) => row.id === itemId)?.name ?? itemId) : null;
    if (item && itemId) {
      push('observe', `${scene.actorName}查看${item}。`, { itemIds: [itemId] }, task);
      push('use', `${scene.actorName}拿起${item}。`, { itemIds: [itemId] }, task);
    }
    const target = scene.visible.find((character) => goal.includes(character.name));
    if (target) {
      push('communicate', `${scene.actorName}向${target.name}询问下一步。`, { targetIds: [target.id] }, task);
      if (item && itemId) {
        push('assist', `${scene.actorName}把${item}递给${target.name}。`, { targetIds: [target.id], itemIds: [itemId] }, task);
      }
    }
  }
  return out.slice(0, 6);
}
