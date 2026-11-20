/** Test helpers. The row helper turns a stored dataset X into the same
 * projection shape the runtime produces; the tiny world exercises the real
 * state kernel instead of hand-written after states. */
import type { InitialState, TimeAdvance, TimelinePoint, WorldState, EntityDelta, Id } from '../../types';
import { applyPoint, buildInitialState, buildTimelinePoint } from '../state';
import { DEFAULT_NARRATION_PROJECTION_POLICY, type NarrationProjection } from './types';

export function projectionFromRowX(x: {
  视角: string;
  上回合状态: NarrationProjection['beforeState'];
  本回合变化: NarrationProjection['delta'];
  本回合状态: NarrationProjection['resultState'];
}): NarrationProjection {
  const match = /主角视角（(.+?)）/.exec(x.视角);
  return {
    projectionVersion: 'narration-projection-v1',
    viewpoint: { id: 'row-viewpoint', name: match?.[1] ?? x.视角, text: x.视角 },
    beforeState: x.上回合状态,
    delta: x.本回合变化,
    resultState: x.本回合状态,
    policy: {
      ...DEFAULT_NARRATION_PROJECTION_POLICY,
      length: { ...DEFAULT_NARRATION_PROJECTION_POLICY.length },
    },
  };
}

export function tinyWorld(): WorldState {
  const initial: InitialState = {
    engineVersion: 'world-engine-v1',
    schemaVersion: 1,
    worldId: 'tiny',
    protagonistId: 'hero',
    initialTime: { calendar: 'gregorian', dateTime: '2026-01-01T12:00:00', instantOrdinal: 0 },
    locations: {
      hall: { id: 'hall', name: '大厅', parentLocationId: null, initialAppearance: '大厅里点着一盏灯。', slots: [{ id: 'slot_front', label: '门前' }, { id: 'slot_back', label: '窗边' }] },
      alcove: { id: 'alcove', name: '壁龛', parentLocationId: 'hall', initialAppearance: '壁龛里落着灰。', slots: [] },
      garden: { id: 'garden', name: '庭院', parentLocationId: null, initialAppearance: '庭院里下着雨。', slots: [] },
      cellar: { id: 'cellar', name: '地窖', parentLocationId: null, initialAppearance: '地窖里很暗。', slots: [] },
    },
    items: {
      lamp: { id: 'lamp', name: '铜灯', initialPosition: { containerId: 'hall', slotId: 'slot_front', relativeTo: null }, initialAppearance: '灯罩擦得很亮。', slots: [] },
      box: { id: 'box', name: '木箱', initialPosition: { containerId: 'cellar', slotId: null, relativeTo: null }, initialAppearance: '箱盖裂了一条缝。', slots: [] },
      note: { id: 'note', name: '纸条', initialPosition: { containerId: 'hero', slotId: 'slot_pocket', relativeTo: null }, initialAppearance: '纸条折了两折。', slots: [] },
      keepsake: { id: 'keepsake', name: '旧照片', initialPosition: { containerId: 'lamp', slotId: null, relativeTo: null }, initialAppearance: '照片边角发黄。', slots: [] },
    },
    characters: {
      hero: {
        id: 'hero', name: '阿青', initialPosition: { containerId: 'hall', slotId: 'slot_back', relativeTo: null },
        initialAppearance: '袖口沾着灰。', slots: [{ id: 'slot_pocket', label: '衣袋' }],
        initialPersonality: '谨慎。', initialSanity: 50,
        tasks: {
          task_root: { id: 'task_root', ownerId: 'hero', parentTaskId: null, goal: '找到父亲留下的箱子', status: 'pending' },
          task_child: { id: 'task_child', ownerId: 'hero', parentTaskId: 'task_root', goal: '问清地窖的钥匙在谁手里', status: 'pending' },
          task_grand: { id: 'task_grand', ownerId: 'hero', parentTaskId: 'task_child', goal: '打开木箱看清里面的东西', status: 'pending' },
        },
      },
      friend: {
        id: 'friend', name: '阿白', initialPosition: { containerId: 'hall', slotId: 'slot_front', relativeTo: null },
        initialAppearance: '鞋面很干。', slots: [],
        initialPersonality: '嘴硬。', initialSanity: 60,
        tasks: { friend_root: { id: 'friend_root', ownerId: 'friend', parentTaskId: null, goal: '守住大厅的门', status: 'pending' } },
      },
      stranger: {
        id: 'stranger', name: '阿灰', initialPosition: { containerId: 'alcove', slotId: null, relativeTo: null },
        initialAppearance: '披着旧斗篷。', slots: [],
        initialPersonality: '寡言。', initialSanity: 44,
        tasks: { stranger_root: { id: 'stranger_root', ownerId: 'stranger', parentTaskId: null, goal: '等雨停', status: 'pending' } },
      },
      absent: {
        id: 'absent', name: '阿远', initialPosition: { containerId: 'garden', slotId: null, relativeTo: null },
        initialAppearance: '衣服湿透了。', slots: [],
        initialPersonality: '急躁。', initialSanity: 38,
        tasks: { absent_root: { id: 'absent_root', ownerId: 'absent', parentTaskId: null, goal: '找到避雨的地方', status: 'pending' } },
      },
      blank: {
        id: 'blank', name: '阿空', initialPosition: { containerId: 'cellar', slotId: null, relativeTo: null },
        initialAppearance: '神情空白。', slots: [],
        initialPersonality: '沉默。', initialSanity: 20,
        tasks: {},
      },
    },
  };
  return buildInitialState(initial);
}

let sequence = 0;

export function applyDelta(before: WorldState, delta: Record<Id, EntityDelta>, timeAdvance: TimeAdvance = { boundary: 'elapsed', duration: { amount: 3, unit: 'minute' } }): WorldState {
  sequence += 1;
  const point: TimelinePoint = buildTimelinePoint({
    worldId: before.worldId,
    id: `p_${sequence}`,
    sequence,
    kind: 'normal',
    previousPointId: 'p_root',
    roundId: 'r_1',
    advanceId: 'a_1',
    trigger: 'player',
    linkedFromPointId: null,
    timeAdvance,
    entityDeltas: delta,
  });
  return applyPoint(before, point);
}
