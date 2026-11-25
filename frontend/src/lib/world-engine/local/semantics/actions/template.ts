/** Routine NPC action text from a chosen behavior category.
 *
 * Slots come from the actor's pending task goals (a registered location, item
 * or visible character). `other` and missing slots return null so the LLM
 * answers instead; the caller still runs the normal action checks. */
import type { Id, WorldState } from '../../../types';
import type { ActionScene } from './scene';
import { matchItems } from './structure';
import { matchLocation } from '../settlement/fact-destinations';

export function templateAction(category: string, scene: ActionScene, state: WorldState): string | null {
  const goals = scene.actor.tasks.filter((task) => task.status === 'pending').map((task) => task.goal).join('；');
  if (!goals) return null;
  const location = matchLocation(state, goals);
  const itemId = matchItems(goals, Object.entries(state.initial.items).map(([id, item]) => ({ id, name: item.name ?? id })), scene.actorName)[0];
  const item = itemId ? (state.initial.items[itemId]?.name ?? itemId).replace(/^.+?的/u, '') : null;
  const target = scene.visible.find((character) => goals.includes(character.name));
  const place = location?.name ?? null;
  const text = (() => {
    switch (category) {
      case 'move': {
        if (!place || scene.roomName === place) return null;
        // A location merely referenced by the goal (守住东回廊对钟楼…) is not a destination.
        const at = goals.indexOf(place);
        const window = goals.slice(Math.max(0, at - 6), at);
        return ['前往', '走向', '走进', '赶到', '回到', '退到', '进入', '离开', '去', '到'].some((verb) => window.includes(verb))
          ? `走向${place}` : null;
      }
      case 'observe': return `查看${item ?? '周围环境'}`;
      case 'guard': return place ? `守住${place}` : null;
      case 'communicate': return target ? `向${target.name}询问下一步` : null;
      case 'assist': return target ? `把${item ?? '手边的器材'}递给${target.name}` : null;
      case 'hide': return '退到掩体后，不出声';
      case 'use': return item ? `拿起${item}` : null;
      default: return null;
    }
  })();
  return text ? `${scene.actorName}${text}。` : null;
}
