// Deterministic before/after dump of the constrained beat prompt. No model, no
// GPU. Builds four representative beats (walk, item move, question, another
// actor's fact) and prints what the prompt looks like with 06's tree as-is and
// with 02's combined patch applied.
//
//   node --experimental-strip-types probe.mjs
const scene = {
  anchor: { worldId: 'w', pointId: 'p1', version: 3, stateDigest: 'd', previousPointId: null },
  viewpoint: {
    id: 'lu', name: '路明非', locationId: 'corridor', location: '钟楼西回廊',
    note: '黑发凌乱，校服外套敞着', personality: '谨慎', sanity: 62,
  },
  time: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } },
  place: { id: 'corridor', name: '钟楼西回廊', note: '廊柱下有积水，石板湿滑', parentName: '演习场' },
  present: [
    { id: 'lu', name: '路明非', note: '黑发凌乱，校服外套敞着', viewpoint: true },
    { id: 'nono', name: '诺诺', note: '红发用发圈束在脑后，红色识别带缠在左臂', viewpoint: false },
  ],
  objects: [{ id: 'goggles', name: '护目镜', note: '镜片无裂纹，镜带松着，现挂在胸前' }],
  facts: [
    { id: 'f_move', kind: 'move', mandatory: true, visibility: 'scene', entityId: 'lu', name: '路明非', entityKind: 'character', fromId: 'service', from: '西侧服务巷', toId: 'corridor', to: '西回廊', fromVisibility: 'in_view', toVisibility: 'in_view', viewpoint: true },
    { id: 'f_item', kind: 'move', mandatory: true, visibility: 'scene', entityId: 'goggles', name: '护目镜', entityKind: 'item', fromId: 'service', from: '西侧服务巷', toId: 'corridor', to: '西回廊', fromVisibility: 'in_view', toVisibility: 'in_view', viewpoint: true },
    { id: 'f_ask', kind: 'result', mandatory: true, visibility: 'scene', text: '路明非问诺诺红蓝两方现在在哪，诺诺摇头说不知道', structured: { actorId: 'lu', actor: '路明非', action: '问诺诺红蓝两方现在各在哪个方位', targetId: 'nono', target: '诺诺', outcome: 'failed' } },
    { id: 'f_other', kind: 'result', mandatory: true, visibility: 'scene', text: '诺诺把红色识别带在墙边压了压，说先别乱走', structured: { actorId: 'nono', actor: '诺诺', action: '压了压红色识别带，让路明非先别乱走', targetId: 'lu', target: '路明非', outcome: 'completed' } },
    { id: 'f_walk', kind: 'result', mandatory: true, visibility: 'scene', text: '路明非沿西回廊走到廊柱下', structured: { actorId: 'lu', actor: '路明非', action: '沿西回廊走到廊柱下', outcome: 'completed' } },
  ],
  worldNames: { characters: ['路明非', '诺诺'], locations: ['钟楼西回廊'], items: ['护目镜'] },
  licensed: {
    names: ['路明非', '诺诺'], locations: ['钟楼西回廊', '西侧服务巷'], items: ['护目镜'],
    details: ['廊柱下有积水，石板湿滑'], quotes: [],
  },
  knowledge: {},
  inputText: '我选了西回廊那条有掩护的路，起身就往钟楼西侧走。',
  previousAction: '路明非选了西回廊那条有掩护的路，起身往钟楼西侧走',
  resultsText: null,
  hasSceneMaterial: true,
  timeOnly: false,
};

const beats = {
  walk: { id: 'result_1', index: 0, kind: 'result', subject: { id: 'lu', name: '路明非', viewpoint: true }, factIds: ['f_walk'], details: ['廊柱下有积水，石板湿滑'], mustMention: ['路明非'], seed: 1, minChars: 40, maxChars: 120 },
  item: { id: 'move_2', index: 0, kind: 'move', subject: { id: 'goggles', name: '护目镜', viewpoint: false }, factIds: ['f_item'], details: [], mustMention: ['护目镜', '西回廊'], seed: 2, minChars: 20, maxChars: 80 },
  ask: { id: 'result_3', index: 0, kind: 'result', subject: { id: 'lu', name: '路明非', viewpoint: true }, factIds: ['f_ask'], details: [], mustMention: ['路明非', '诺诺'], seed: 3, minChars: 40, maxChars: 140 },
  other: { id: 'result_4', index: 0, kind: 'result', subject: { id: 'nono', name: '诺诺', viewpoint: false }, factIds: ['f_other'], details: [], mustMention: ['诺诺', '路明非'], seed: 4, minChars: 40, maxChars: 140 },
};

const before = await import('./before/src/lib/world-engine/local/narration-candidates/constrained/compose.ts');
const after = await import('./run/src/lib/world-engine/local/narration-candidates/constrained/compose.ts');
const options = { sanityStyle: 'direction', maxDetails: 4 };
for (const [name, beat] of Object.entries(beats)) {
  console.log(`\n########## ${name} ##########`);
  for (const [label, mod] of [['BEFORE', before], ['AFTER', after]]) {
    const prompt = mod.buildBeatPrompt(beat, scene, options);
    console.log(`\n----- ${label} (${[...prompt].length} chars) -----\n${prompt}`);
  }
}
