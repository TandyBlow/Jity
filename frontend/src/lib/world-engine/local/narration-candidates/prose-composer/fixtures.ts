/** Development fixtures for the prose composer.
 *
 * These are read-only fact skeletons built from the public free-day world and
 * the six short probes. They are not holdout material and do not claim to be
 * real browser records.
 */

import type { ProseScene } from './types';

export const SHORT_MOVE_SCENE: ProseScene = {
  worldId: 'world_short',
  pointId: 'point_short_move',
  protagonistId: 'person_c',
  location: {
    id: 'corridor',
    name: '走廊',
    details: ['明亮的走廊，通往门厅。'],
  },
  cast: [
    {
      id: 'person_a', name: '林川', gender: 'male',
      appearance: ['穿灰衣。'],
    },
    {
      id: 'person_c', name: '周宁', gender: 'female',
      appearance: ['穿蓝衣。'], isProtagonist: true,
    },
  ],
  items: [{ id: 'box', name: '盒子', details: ['盒盖关闭。'], positionName: '走廊' }],
  beats: [
    { kind: 'move', actorId: 'person_a', from: '走廊', to: '门厅' },
    { kind: 'stay', actorId: 'person_c', location: '走廊' },
  ],
  priorText: '走廊的灯亮着。\n\n林川站在门边，盒子放在两人之间的地上，盖着。\n\n周宁没有动。',
  policy: { minChars: 40, seed: 7 },
};

export const SERVICE_LANE_SCENE: ProseScene = {
  worldId: 'free_day',
  pointId: 'point_lane_choice',
  protagonistId: 'lu',
  location: {
    id: 'lane',
    name: '西侧服务巷',
    parentName: '西侧器材区',
    details: [
      '巷口的黄黑绳已放下，进入即算踏入演习区。',
      '右墙贴着赛区图，器材棚门敞开；巷子尽头的低墙挡住庭院视线，墙角留下新鲜的演习弹红痕。',
    ],
  },
  cast: [
    {
      id: 'lu', name: '路明非', gender: 'male', isProtagonist: true,
      appearance: ['校服领口松着，膝盖沾了灰；护目镜挂在胸前，右手还空着，身上没有红蓝识别带。'],
    },
    {
      id: 'nono', name: '诺诺', gender: 'female',
      appearance: ['红发用发圈束在脑后，红色识别带缠在左臂；手里的短枪枪口压向地面。'],
      references: ['她', '诺诺'],
    },
  ],
  items: [],
  beats: [
    { kind: 'line', speakerId: 'nono', text: '红方在集结点，蓝方守着钟楼。你打算站哪边？' },
    { kind: 'line', speakerId: 'lu', text: '我还没想好。' },
    { kind: 'line', speakerId: 'nono', text: '那就先别站到路中间。' },
    { kind: 'task', actorId: 'lu', label: '向诺诺问清当前红蓝两方局势', scope: 'sub', factText: '红蓝两方的局势，路明非问清了。' },
    { kind: 'time', amount: 2, unit: 'minute' },
    { kind: 'line', speakerId: 'nono', text: '想清楚了再走。' },
  ],
  priorText: null,
  policy: { minChars: 80, seed: 23 },
};

export const SHED_SCENE: ProseScene = {
  worldId: 'free_day',
  pointId: 'point_shed_battery',
  protagonistId: 'lu',
  location: {
    id: 'shed',
    name: '器材棚',
    parentName: '西侧器材区',
    details: [
      '推拉门可回服务巷。',
      '领用台与带锁器材笼分处两侧，中间留有担架能通过的宽度；备用弹药箱已开盖，笼门的挂锁仍扣着。',
    ],
  },
  cast: [
    {
      id: 'lu', name: '路明非', gender: 'male', isProtagonist: true,
      appearance: ['校服领口松着，膝盖沾了灰；护目镜挂在胸前，右手还空着，身上没有红蓝识别带。'],
    },
    {
      id: 'fingel', name: '芬格尔', gender: 'male',
      appearance: ['头盔歪扣着，食指蹭了油；旧相机挂在脖子上，左臂没有阵营布带。护膝一边扣紧、一边还敞着。'],
    },
  ],
  items: [
    {
      id: 'radio_battery', name: '短讯机电池',
      details: ['电池盒的盖子已经打开，槽里换上了一节新电池。'],
      positionName: '器材棚',
    },
    {
      id: 'camera_battery', name: '相机电池',
      details: ['包装还没拆，型号比短讯机电池短一截。'],
      positionName: '器材棚',
    },
  ],
  beats: [
    { kind: 'item', itemId: 'radio_battery', change: 'modified', detail: '电池盒的盖子已经打开，槽里换上了一节新电池。' },
    { kind: 'line', speakerId: 'fingel', text: '别看，机型不一样，插不进去。' },
    { kind: 'line', speakerId: 'lu', text: '能用就行。' },
    { kind: 'action', actorId: 'fingel', text: '芬格尔把备用电池盒往路明非那边推了推。' },
    { kind: 'task', actorId: 'fingel', label: '确认短讯机电池与相机电池型号不同', scope: 'sub', factText: '两种电池的型号，芬格尔已经确认过了。' },
    { kind: 'personality', actorId: 'fingel', text: '不再把每一件小事都算成一笔交易。' },
  ],
  priorText: null,
  policy: { minChars: 80, seed: 41 },
};

export const NO_CHANGE_SCENE: ProseScene = {
  worldId: 'free_day',
  pointId: 'point_no_change',
  protagonistId: 'lu',
  location: {
    id: 'lane',
    name: '西侧服务巷',
    parentName: '西侧器材区',
    details: ['巷口的黄黑绳已放下，进入即算踏入演习区。', '墙角留下新鲜的演习弹红痕。'],
  },
  cast: [
    { id: 'lu', name: '路明非', gender: 'male', isProtagonist: true },
    { id: 'nono', name: '诺诺', gender: 'female' },
  ],
  items: [],
  beats: [
    { kind: 'noChange' },
    { kind: 'time', amount: 1, unit: 'minute' },
  ],
  policy: { minChars: 16, seed: 3 },
};

export const CONTINUATION_SCENE: ProseScene = {
  ...SHED_SCENE,
  pointId: 'point_shed_battery_2',
  cast: [
    SHED_SCENE.cast[0],
    SHED_SCENE.cast[1],
  ],
  items: [],
  beats: [
    { kind: 'stay', actorId: 'lu', location: '器材棚' },
    { kind: 'line', speakerId: 'lu', text: '这节电池能撑多久？' },
    { kind: 'line', speakerId: 'fingel', text: '够你把话说完。' },
    { kind: 'leave', actorId: 'fingel', to: '西侧服务巷' },
  ],
  priorText: '器材棚的推拉门开着一半。\n\n芬格尔把短讯机翻过来，电池盒的盖子已经打开，槽里换上了一节新电池。\n\n「别看，机型不一样，插不进去。」\n\n路明非站在领用台边上，没有伸手。',
  policy: { minChars: 50, seed: 11 },
};

export const RICH_SCENE: ProseScene = {
  worldId: 'free_day',
  pointId: 'point_lane_full',
  protagonistId: 'lu',
  location: {
    id: 'lane',
    name: '西侧服务巷',
    parentName: '西侧器材区',
    details: [
      '巷口的黄黑绳已放下，进入即算踏入演习区。',
      '右墙贴着赛区图，器材棚门敞开；巷子尽头的低墙挡住庭院视线，墙角留下新鲜的演习弹红痕。',
    ],
  },
  cast: [
    {
      id: 'lu', name: '路明非', gender: 'male', isProtagonist: true,
      appearance: ['校服领口松着，膝盖沾了灰；护目镜挂在胸前，右手还空着，身上没有红蓝识别带。'],
    },
    {
      id: 'nono', name: '诺诺', gender: 'female',
      appearance: ['红发用发圈束在脑后，红色识别带缠在左臂；手里的短枪枪口压向地面。'],
      references: ['她', '诺诺'],
    },
  ],
  items: [],
  beats: [
    { kind: 'action', actorId: 'nono', text: '诺诺把短枪换到左手，抬起右手指向巷子尽头。' },
    { kind: 'line', speakerId: 'nono', text: '红方在集结点，蓝方守着钟楼。你要过去，别走正中。' },
    { kind: 'line', speakerId: 'lu', text: '走哪边？' },
    { kind: 'line', speakerId: 'nono', text: '西回廊有柱子，地下通道要过检修口。两条都比正路慢。' },
    { kind: 'task', actorId: 'lu', label: '向诺诺问清当前红蓝两方局势', scope: 'sub', factText: '红蓝两方的局势，路明非问清了。' },
    { kind: 'action', actorId: 'lu', text: '路明非把胸前的护目镜摘下来，带子在手腕上绕了一圈。' },
    { kind: 'time', amount: 3, unit: 'minute' },
    { kind: 'line', speakerId: 'lu', text: '我再想想。' },
    { kind: 'line', speakerId: 'nono', text: '想好了再进来。' },
    { kind: 'leave', actorId: 'nono', to: '红方集结点' },
  ],
  policy: { minChars: 120, seed: 61 },
};

export const FIXTURES = {
  shortMove: SHORT_MOVE_SCENE,
  serviceLane: SERVICE_LANE_SCENE,
  shed: SHED_SCENE,
  noChange: NO_CHANGE_SCENE,
  continuation: CONTINUATION_SCENE,
  rich: RICH_SCENE,
} as const;
