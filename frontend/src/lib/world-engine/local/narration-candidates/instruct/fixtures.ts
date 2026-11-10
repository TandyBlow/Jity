/** Hermetic world fixture for the candidate tests. It is deliberately small
 * (three rooms, three characters, three items) so every prompt/test assertion
 * is readable; it is not the shipped world. */
import type { InitialTemplate } from '../../../types';

export const TEST_WORLD: InitialTemplate = {
  engineVersion: 'world-engine-v1',
  schemaVersion: 1,
  protagonistId: 'hero',
  initialTime: { calendar: 'gregorian', dateTime: '2026-01-01T09:00:00', instantOrdinal: 0 },
  locations: {
    hall: { id: 'hall', name: '大厅', parentLocationId: null, initialAppearance: '大厅里只开着一半的灯，长桌上摊着一张还没收起的报纸。' },
    yard: { id: 'yard', name: '庭院', parentLocationId: null, initialAppearance: '庭院里的石板还湿着，墙角堆着几盆没搬进屋的花。' },
    shed: { id: 'shed', name: '仓库', parentLocationId: null, initialAppearance: '仓库门半掩，里面堆着旧箱子和一台落了灰的风扇。' },
  },
  items: {
    lamp: {
      id: 'lamp', name: '铜台灯', initialPosition: { containerId: 'hall', slotId: null, relativeTo: null },
      initialAppearance: '灯罩上有一道细裂纹，开关还是热的。',
    },
    map: {
      id: 'map', name: '旧地图', initialPosition: { containerId: 'hall', slotId: null, relativeTo: null },
      initialAppearance: '折痕很深，右下角被水泡过。',
    },
    key: {
      id: 'key', name: '仓库钥匙', initialPosition: { containerId: 'ally', slotId: 'slot_pocket', relativeTo: null },
      initialAppearance: '钥匙上挂着一小截红绳。',
    },
  },
  characters: {
    hero: {
      id: 'hero', name: '陈默', initialPosition: { containerId: 'hall', slotId: null, relativeTo: null },
      initialAppearance: '外套还没扣好，袖口沾着一点墨。', initialPersonality: '说话前习惯先停半拍，遇到麻烦反而更安静。他也知道自己不擅长求人。',
      initialSanity: 50,
      tasks: {
        t1: { id: 't1', ownerId: 'hero', parentTaskId: null, goal: '把旧地图带到庭院', status: 'pending' },
      },
    },
    ally: {
      id: 'ally', name: '林夏', initialPosition: { containerId: 'hall', slotId: null, relativeTo: null },
      initialAppearance: '头发扎得很高，指尖有一层薄薄的机油。', initialPersonality: '手比嘴快，拆东西之前从不问能不能拆。',
      // The browser kernel rejects a slot that its container does not declare;
      // the ally's pocket must therefore be declared, not assumed.
      slots: [{ id: 'slot_pocket', label: '衣袋' }],
      initialSanity: 60,
      tasks: {
        t2: { id: 't2', ownerId: 'ally', parentTaskId: null, goal: '修好旧收音机', status: 'pending' },
      },
    },
    absent: {
      id: 'absent', name: '周舟', initialPosition: { containerId: 'shed', slotId: null, relativeTo: null },
      initialAppearance: '总戴着一顶压得很低的帽子。', initialPersonality: '不喜欢被人打听行踪。',
      initialSanity: 40,
      tasks: {},
    },
  },
};
