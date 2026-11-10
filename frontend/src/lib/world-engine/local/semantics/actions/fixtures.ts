/** Small hermetic world for the action-handler tests.
 *
 * It mirrors the shapes of the shipped free-day world (nested location, a
 * container item holding another item, carried items, characters in other
 * rooms) without copying it: tests must not depend on the product world's
 * text. `buildInitialState` is the same constructor the local transport uses,
 * so the fixtures cannot drift from the real WorldState shape.
 */
import type { Id, InitialState, Position, WorldState } from '../../../types';
import { buildInitialState } from '../../state';

const ground = (containerId: Id, slotId: string | null = null): Position => ({ containerId, slotId, relativeTo: null });

export function buildTestWorld(): WorldState {
  const initial: InitialState = {
    engineVersion: 'world-engine-v1',
    schemaVersion: 1,
    worldId: 'action_test_world',
    protagonistId: 'hero',
    initialTime: { calendar: 'gregorian', dateTime: '2009-10-17T15:20:00', instantOrdinal: 0 },
    locations: {
      hall: { id: 'hall', name: '大厅', parentLocationId: null, initialAppearance: '空旷的大厅，木门半掩。' },
      study: { id: 'study', name: '书房', parentLocationId: null, initialAppearance: '书房里堆着旧书。' },
      cage: { id: 'cage', name: '铁笼', parentLocationId: 'hall', initialAppearance: '大厅角落的铁笼。' },
    },
    items: {
      crate: { id: 'crate', name: '木箱', initialPosition: ground('hall'), initialAppearance: '半人高的木箱。' },
      knife: { id: 'knife', name: '短刀', initialPosition: ground('crate', 'slot_top'), initialAppearance: '一把短刀。' },
      note: { id: 'note', name: '字条', initialPosition: ground('study'), initialAppearance: '上面写着字。' },
      torch: { id: 'torch', name: '手电', initialPosition: ground('hero', 'slot_body'), initialAppearance: '旧手电。' },
    },
    characters: {
      hero: {
        id: 'hero', name: '路明非', initialPosition: ground('hall', 'slot_entry'), initialAppearance: '穿旧外套。',
        initialPersonality: '嘴硬心软，遇事先退半步。', initialSanity: 60,
        tasks: { task_hero_key: { id: 'task_hero_key', ownerId: 'hero', parentTaskId: null, goal: '找到后门的钥匙', status: 'pending' } },
      },
      ally: {
        id: 'ally', name: '阿宁', initialPosition: ground('hall', 'slot_counter'), initialAppearance: '穿蓝队外套。',
        initialPersonality: '先确认撤离路线再动手。', initialSanity: 55,
        tasks: {
          task_ally_watch: { id: 'task_ally_watch', ownerId: 'ally', parentTaskId: null, goal: '守住大厅木门，别让红方进来', status: 'pending' },
          task_ally_done: { id: 'task_ally_done', ownerId: 'ally', parentTaskId: null, goal: '确认自己的对讲机有电', status: 'achieved' },
        },
      },
      rival: {
        id: 'rival', name: '老周', initialPosition: ground('study'), initialAppearance: '披着红队绶带。',
        initialPersonality: '只看结果。', initialSanity: 70,
        tasks: { task_rival_guard: { id: 'task_rival_guard', ownerId: 'rival', parentTaskId: null, goal: '守住书房里的字条', status: 'pending' } },
      },
      servant: {
        id: 'servant', name: '小满', initialPosition: ground('cage'), initialAppearance: '缩在铁笼角落。',
        initialPersonality: '不敢出声。', initialSanity: 40,
        tasks: {},
      },
    },
  };
  return buildInitialState(initial);
}

export function withPosition(state: WorldState, id: Id, position: Position): WorldState {
  const next = structuredClone(state);
  if (next.characters[id]) next.characters[id].position = position;
  else if (next.items[id]) next.items[id].position = position;
  else throw new Error(`unknown entity ${id}`);
  return next;
}

export function withSanity(state: WorldState, id: Id, sanity: number): WorldState {
  const next = structuredClone(state);
  next.characters[id].sanity = sanity;
  return next;
}
