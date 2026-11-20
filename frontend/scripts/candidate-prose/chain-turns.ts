/** The twenty settled turns used by both the cross-turn check
 * (`chain-10.ts`) and lane 01's independent review (`review-01-gate.ts`), so
 * the two scripts always describe the same world history. This is a
 * development input, not product acceptance.
 */
export interface ChainTurn {
  text: string;
  time: { amount: number; unit: 'second' | 'minute' };
  deltas: Record<string, Record<string, unknown>>;
}

export const CHAIN_TURNS: ChainTurn[] = [
  { text: '走到器材棚', time: { amount: 2, unit: 'minute' }, deltas: { lu: { entityId: 'lu', positionSet: { containerId: 'shed', slotId: 'slot_counter', relativeTo: null } } } },
  { text: '戴好护目镜（任务达成）', time: { amount: 3, unit: 'minute' }, deltas: { lu: { entityId: 'lu', tasksAchieved: ['task_lu_goggles'] } } },
  { text: '芬格尔跟进来', time: { amount: 1, unit: 'minute' }, deltas: { fingel: { entityId: 'fingel', positionSet: { containerId: 'shed', slotId: null, relativeTo: null } } } },
  { text: '个性与精神变化', time: { amount: 2, unit: 'minute' }, deltas: { lu: { entityId: 'lu', personalityChanges: [{ id: 'chain_p1', text: '不再把选择留给别人。', supersedes: [] }], sanitySet: 44 } } },
  { text: '只在原地过一分钟', time: { amount: 1, unit: 'minute' }, deltas: {} },
  { text: '走到中央庭院', time: { amount: 4, unit: 'minute' }, deltas: { lu: { entityId: 'lu', positionSet: { containerId: 'yard', slotId: null, relativeTo: null } } } },
  { text: '诺诺也在庭院', time: { amount: 1, unit: 'minute' }, deltas: { nono: { entityId: 'nono', positionSet: { containerId: 'yard', slotId: null, relativeTo: null } } } },
  { text: '外貌变化', time: { amount: 2, unit: 'minute' }, deltas: { lu: { entityId: 'lu', appearanceChanges: [{ id: 'chain_a1', text: '袖口沾了喷泉边的水。', supersedes: [] }] } } },
  { text: '精神回升', time: { amount: 2, unit: 'minute' }, deltas: { lu: { entityId: 'lu', personalityChanges: [{ id: 'chain_p2', text: '愿意先听完再回答。', supersedes: [] }], sanitySet: 58 } } },
  { text: '回到服务巷', time: { amount: 3, unit: 'minute' }, deltas: { lu: { entityId: 'lu', positionSet: { containerId: 'lane', slotId: null, relativeTo: null } } } },
  // 11-20: items, dialogue, two actors at once, task progress, sanity, no-change.
  { text: '在服务巷拿到地图', time: { amount: 2, unit: 'minute' }, deltas: { map: { entityId: 'map', positionSet: { containerId: 'lane', slotId: null, relativeTo: null } } } },
  { text: '两名同伴同时进巷', time: { amount: 2, unit: 'minute' }, deltas: { fingel: { entityId: 'fingel', positionSet: { containerId: 'lane', slotId: null, relativeTo: null } }, nono: { entityId: 'nono', positionSet: { containerId: 'lane', slotId: null, relativeTo: null } } } },
  { text: '与诺诺对话一句', time: { amount: 1, unit: 'minute' }, deltas: { nono: { entityId: 'nono', quotesAdded: [{ id: 'chain_q1', text: '你先说清楚自己要站在哪一边。' }] } } },
  { text: '推进子任务', time: { amount: 2, unit: 'minute' }, deltas: { lu: { entityId: 'lu', tasksAchieved: ['task_lu_choice'] } } },
  { text: '精神下降', time: { amount: 1, unit: 'minute' }, deltas: { lu: { entityId: 'lu', sanitySet: 38 } } },
  { text: '又一分钟没变化', time: { amount: 1, unit: 'minute' }, deltas: {} },
  { text: '地图被收走', time: { amount: 1, unit: 'minute' }, deltas: { map: { entityId: 'map', positionSet: { containerId: 'shed', slotId: null, relativeTo: null } } } },
  { text: '同伴离开', time: { amount: 2, unit: 'minute' }, deltas: { fingel: { entityId: 'fingel', positionSet: { containerId: 'yard', slotId: null, relativeTo: null } } } },
  { text: '诺诺后退半步', time: { amount: 1, unit: 'minute' }, deltas: { nono: { entityId: 'nono', positionChanges: [{ axis: 'y', delta: -0.5 }] } } },
  { text: '走到器材棚', time: { amount: 3, unit: 'minute' }, deltas: { lu: { entityId: 'lu', positionSet: { containerId: 'shed', slotId: null, relativeTo: null } } } },
];
