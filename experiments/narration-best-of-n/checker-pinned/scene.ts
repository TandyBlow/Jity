/** Independent projection of one settled narration point.
 *
 * Input is the dataset row shape used by both the frozen 199-row corpus and
 * the 71-row short-scene corpus:
 *
 *   视角, 上回合状态{人物,地点,物品}, 本回合变化{时间推进,变化}, 本回合状态
 *
 * Nothing here imports the generation-side projection. Facts are rebuilt from
 * before/after fields so the review can disagree with the generator.
 */

export interface PersonBlock {
  位置?: string;
  精神值?: number;
  外貌?: string[];
  个性?: string[];
  任务?: {
    大任务?: { 目标?: string; 状态?: string } | null;
    小任务?: Array<{ 目标?: string; 状态?: string }>;
  };
}

export interface PlaceBlock {
  位于?: string | null;
  外貌?: string[];
}

export interface ItemBlock {
  位置?: string;
  外貌?: string[];
}

export interface DeltaBlock {
  位置?: string;
  精神值?: number;
  外貌?: string[];
  个性?: string[];
  任务?: PersonBlock['任务'];
  新增外貌?: string | string[];
  解除外貌?: string | string[];
  新增个性?: string | string[];
  解除个性?: string | string[];
}

export interface DatasetInput {
  视角?: string;
  上回合状态?: {
    人物?: Record<string, PersonBlock>;
    地点?: Record<string, PlaceBlock>;
    物品?: Record<string, ItemBlock>;
  };
  '本回合变化'?: {
    时间推进?: string;
    变化?: Record<string, DeltaBlock>;
  };
  '本回合状态'?: Record<string, DeltaBlock>;
}

export interface TaskState {
  goal: string;
  before: string | null;
  after: string | null;
}

export interface PersonFact {
  name: string;
  positionBefore: string | null;
  positionAfter: string | null;
  sanityBefore: number | null;
  sanityAfter: number | null;
  appearanceBefore: string[];
  appearanceAfter: string[];
  personalityBefore: string[];
  personalityAfter: string[];
  tasks: TaskState[];
  /** Verbatim description strings that license concrete detail. */
  descriptions: string[];
}

export interface MoveFact {
  id: string;
  kind: 'person' | 'item';
  name: string;
  from: string | null;
  to: string;
}

export interface SceneProjection {
  viewpoint: string | null;
  timeText: string | null;
  minutes: number | null;
  people: Record<string, PersonFact>;
  places: Record<string, { parent: string | null; description: string[] }>;
  items: Record<string, { positionBefore: string | null; positionAfter: string | null; descriptions: string[] }>;
  moves: MoveFact[];
  sanityChanges: Array<{ id: string; name: string; from: number; to: number }>;
  taskCompleted: Array<{ id: string; name: string; goal: string }>;
  taskAdded: Array<{ id: string; name: string; goal: string }>;
  personalityAdded: Array<{ id: string; name: string; text: string }>;
  appearanceAdded: Array<{ id: string; entity: string; text: string }>;
  appearanceRemoved: Array<{ id: string; entity: string; text: string }>;
  itemDescriptions: string[];
  /** Names of all people, places and items in the point. */
  names: string[];
  /** Names the viewpoint can currently perceive (at the viewpoint's place). */
  visibleNames: string[];
  /** Verbatim input text, for licensing checks. */
  sourceText: string;
}

const MINUTES_ARABIC = /(\d+)\s*(?:分钟|分|min)/u;
const MINUTES_CHINESE = /([零一二三四五六七八九十两半百]+)\s*(?:分钟|分)/u;

const CN_DIGIT: Record<string, number> = {
  零: 0, 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9,
};

/** Parse a Chinese/Arabic minute expression. `半` alone is treated as 30. */
export function parseMinutes(value: string | null | undefined): number | null {
  if (!value) return null;
  if (/半小时|半个钟头/u.test(value)) return 30;
  if (/一刻钟/u.test(value)) return 15;
  const arabic = MINUTES_ARABIC.exec(value);
  if (arabic) return Number(arabic[1]);
  const chinese = MINUTES_CHINESE.exec(value);
  if (!chinese) return null;
  const raw = chinese[1];
  if (raw === '半') return 30;
  let total = 0;
  let current = 0;
  for (const char of raw) {
    if (char === '十') {
      total += (current === 0 ? 1 : current) * 10;
      current = 0;
    } else if (char === '百') {
      total += (current === 0 ? 1 : current) * 100;
      current = 0;
    } else if (char in CN_DIGIT) {
      current = CN_DIGIT[char];
    } else {
      return null;
    }
  }
  total += current;
  return total > 0 ? total : null;
}

function uniq(values: readonly string[]): string[] {
  return [...new Set(values.filter((value) => value.trim().length > 0))];
}

/** Corpora differ: some store a single string where others store an array. */
function listOf(value: string | readonly string[] | undefined | null): string[] {
  if (typeof value === 'string') return value.trim() ? [value] : [];
  return [...(value ?? [])];
}

function mergeStrings(
  before: string | readonly string[] | undefined,
  add: string | readonly string[] | undefined,
  remove: string | readonly string[] | undefined,
): string[] {
  const removed = new Set(listOf(remove).map((entry) => entry.trim()));
  const base = listOf(before).filter((entry) => !removed.has(entry.trim()));
  return uniq([...base, ...listOf(add)]);
}

function taskEntries(person: PersonBlock | undefined): TaskState[] {
  const tasks: TaskState[] = [];
  const big = person?.任务?.大任务;
  if (big?.目标) tasks.push({ goal: big.目标, before: big.状态 ?? null, after: null });
  for (const small of person?.任务?.小任务 ?? []) {
    if (small.目标) tasks.push({ goal: small.目标, before: small.状态 ?? null, after: null });
  }
  return tasks;
}

function statusMap(person: PersonBlock | undefined): Map<string, string | null> {
  const map = new Map<string, string | null>();
  for (const task of taskEntries(person)) map.set(task.goal, task.before ?? null);
  return map;
}

/** A place is visible if it is the viewpoint's place or an ancestor of it. */
function isWithin(place: string | null, root: string | null, places: SceneProjection['places']): boolean {
  if (!place || !root) return false;
  if (place === root) return true;
  let cursor = places[place]?.parent ?? null;
  let guard = 0;
  while (cursor && guard < 12) {
    if (cursor === root) return true;
    cursor = places[cursor]?.parent ?? null;
    guard += 1;
  }
  return false;
}

export function projectScene(input: DatasetInput): SceneProjection {
  const before = input.上回合状态 ?? {};
  const delta = input['本回合变化']?.变化 ?? {};
  const after = input['本回合状态'] ?? {};
  const people: SceneProjection['people'] = {};
  const places: SceneProjection['places'] = {};
  const items: SceneProjection['items'] = {};

  for (const [name, block] of Object.entries(before.地点 ?? {})) {
    places[name] = { parent: block.位于 ?? null, description: block.外貌 ?? [] };
  }
  // A newly added place appears only in 本回合状态/变化.
  for (const [name, block] of Object.entries(after)) {
    if (!(name in places) && !(name in (before.人物 ?? {})) && !(name in (before.物品 ?? {})) && (block.新增外貌 || block.解除外貌)) {
      places[name] = { parent: null, description: mergeStrings([], block.新增外貌, block.解除外貌) };
    }
  }

  for (const [name, block] of Object.entries(before.物品 ?? {})) {
    const change = delta[name] ?? {};
    items[name] = {
      positionBefore: block.位置 ?? null,
      positionAfter: change.位置 ?? (after[name]?.位置 ?? block.位置 ?? null),
      descriptions: mergeStrings(block.外貌, change.新增外貌 ?? after[name]?.新增外貌, change.解除外貌 ?? after[name]?.解除外貌),
    };
  }
  for (const [name, block] of Object.entries(after)) {
    if (name in items || name in people) continue;
    if (name in (before.地点 ?? {}) || name in (before.人物 ?? {})) continue;
    // Unknown entity: could be a place or an item. Default to place unless the
    // block only carries item-like fields and no 位于.
    places[name] = { parent: null, description: mergeStrings([], block.新增外貌 ?? block.外貌, block.解除外貌) };
  }

  const moves: MoveFact[] = [];
  const sanityChanges: SceneProjection['sanityChanges'] = [];
  const taskCompleted: SceneProjection['taskCompleted'] = [];
  const taskAdded: SceneProjection['taskAdded'] = [];
  const personalityAdded: SceneProjection['personalityAdded'] = [];
  const appearanceAdded: SceneProjection['appearanceAdded'] = [];
  const appearanceRemoved: SceneProjection['appearanceRemoved'] = [];

  for (const [name, block] of Object.entries(before.人物 ?? {})) {
    const change = delta[name] ?? {};
    const afterBlock = after[name] ?? {};
    const positionAfter = change.位置 ?? afterBlock.位置 ?? block.位置 ?? null;
    const sanityAfter = change.精神值 ?? afterBlock.精神值 ?? block.精神值 ?? null;
    const personalityAfterBase = statusPersonality(block, change, afterBlock);
    const appearanceAfterBase = mergeStrings(block.外貌, change.新增外貌 ?? afterBlock.新增外貌, change.解除外貌 ?? afterBlock.解除外貌);
    const tasks = taskEntries(block);
    const afterStatus = statusMap({ 任务: change.任务 ?? afterBlock.任务 ?? block.任务 });
    for (const task of tasks) {
      const next = afterStatus.get(task.goal) ?? null;
      task.after = next;
      if (task.before !== '已完成' && next === '已完成') {
        taskCompleted.push({ id: `task:${name}:${task.goal}`, name, goal: task.goal });
      }
    }
    for (const goal of afterStatus.keys()) {
      if (!tasks.some((task) => task.goal === goal)) {
        taskAdded.push({ id: `task-new:${name}:${goal}`, name, goal });
      }
    }
    for (const text of listOf(change.新增个性)) {
      if (!block.个性?.includes(text)) personalityAdded.push({ id: `personality:${name}:${text}`, name, text });
    }
    for (const text of listOf(change.新增外貌)) {
      appearanceAdded.push({ id: `appearance:${name}:${text}`, entity: name, text });
    }
    for (const text of listOf(change.解除外貌)) {
      appearanceRemoved.push({ id: `appearance-:${name}:${text}`, entity: name, text });
    }
    people[name] = {
      name,
      positionBefore: block.位置 ?? null,
      positionAfter,
      sanityBefore: block.精神值 ?? null,
      sanityAfter,
      appearanceBefore: block.外貌 ?? [],
      appearanceAfter: appearanceAfterBase,
      personalityBefore: block.个性 ?? [],
      personalityAfter: personalityAfterBase,
      tasks,
      descriptions: uniq([...(block.外貌 ?? []), ...(block.个性 ?? []), ...personalityAfterBase, ...tasks.map((task) => task.goal)]),
    };
    if (positionAfter && block.位置 && positionAfter !== block.位置) {
      moves.push({ id: `move:${name}`, kind: 'person', name, from: block.位置, to: positionAfter });
    } else if (positionAfter && !block.位置) {
      moves.push({ id: `move:${name}`, kind: 'person', name, from: null, to: positionAfter });
    }
    if (typeof block.精神值 === 'number' && typeof sanityAfter === 'number' && block.精神值 !== sanityAfter) {
      sanityChanges.push({ id: `sanity:${name}`, name, from: block.精神值, to: sanityAfter });
    }
  }
  // People introduced by the after-state only.
  for (const [name, block] of Object.entries(after)) {
    if (name in people || name in items || name in (before.地点 ?? {})) continue;
    if (!block.新增外貌 && !block.解除外貌 && block.位置 === undefined && block.精神值 === undefined) continue;
    people[name] = {
      name,
      positionBefore: null,
      positionAfter: block.位置 ?? null,
      sanityBefore: null,
      sanityAfter: block.精神值 ?? null,
      appearanceBefore: [],
      appearanceAfter: listOf(block.新增外貌),
      personalityBefore: [],
      personalityAfter: listOf(block.新增个性),
      tasks: [],
      descriptions: uniq(listOf(block.新增外貌)),
    };
    if (block.位置) moves.push({ id: `move:${name}`, kind: 'person', name, from: null, to: block.位置 });
  }

  for (const [name, item] of Object.entries(items)) {
    const change = delta[name] ?? {};
    if (item.positionAfter && item.positionBefore && item.positionAfter !== item.positionBefore) {
      moves.push({ id: `move-item:${name}`, kind: 'item', name, from: item.positionBefore, to: item.positionAfter });
    }
    for (const text of listOf(change.新增外貌)) appearanceAdded.push({ id: `appearance:${name}:${text}`, entity: name, text });
    for (const text of listOf(change.解除外貌)) appearanceRemoved.push({ id: `appearance-:${name}:${text}`, entity: name, text });
  }
  for (const [name, block] of Object.entries(after)) {
    if (name in items || name in people || name in (before.地点 ?? {})) continue;
    for (const text of listOf(block.新增外貌)) appearanceAdded.push({ id: `appearance:${name}:${text}`, entity: name, text });
    for (const text of listOf(block.解除外貌)) appearanceRemoved.push({ id: `appearance-:${name}:${text}`, entity: name, text });
  }

  const viewpoint = parseViewpoint(input.视角);
  const names = uniq([...Object.keys(people), ...Object.keys(places), ...Object.keys(items), ...(viewpoint ? [viewpoint] : [])]);
  const viewpointPlace = viewpoint ? people[viewpoint]?.positionAfter ?? people[viewpoint]?.positionBefore ?? null : null;
  const visibleNames = uniq([
    ...(viewpoint ? [viewpoint] : []),
    ...Object.entries(people)
      .filter(([name, person]) => name !== viewpoint && isWithin(person.positionAfter ?? person.positionBefore, viewpointPlace, places))
      .map(([name]) => name),
    ...Object.entries(places).filter(([name]) => isWithin(name, viewpointPlace, places)).map(([name]) => name),
    ...itemsPositionedAt(Object.entries(items).map(([name, item]) => ({ name, position: item.positionAfter ?? item.positionBefore })), viewpointPlace, places),
  ]);

  const timeText = input['本回合变化']?.时间推进 ?? null;
  return {
    viewpoint,
    timeText,
    minutes: parseMinutes(timeText),
    people,
    places,
    items,
    moves,
    sanityChanges,
    taskCompleted,
    taskAdded,
    personalityAdded,
    appearanceAdded,
    appearanceRemoved,
    itemDescriptions: uniq(Object.values(items).flatMap((item) => item.descriptions)),
    names: names.sort((a, b) => b.length - a.length),
    visibleNames,
    sourceText: JSON.stringify(input),
  };
}

function statusPersonality(block: PersonBlock, change: DeltaBlock, afterBlock: DeltaBlock): string[] {
  const base = (block.个性 ?? []);
  const add = change.新增个性 ?? afterBlock.新增个性 ?? [];
  const remove = change.解除个性 ?? afterBlock.解除个性 ?? [];
  return mergeStrings(base, add, remove);
}

function itemsPositionedAt(
  entries: Array<{ name: string; position: string | null }>,
  viewpointPlace: string | null,
  places: SceneProjection['places'],
): string[] {
  const names: string[] = [];
  for (const entry of entries) {
    if (!entry.position) continue;
    // An item positioned on a person ("在路明非里") is visible when that
    // person is visible.
    if (isWithin(entry.position, viewpointPlace, places)) names.push(entry.name);
  }
  return names;
}

/** `主角视角（周宁）；只表达已结算的世界事实` -> 周宁 */
export function parseViewpoint(raw: string | undefined): string | null {
  if (!raw) return null;
  const paren = /[（(]([^）)]+)[）)]/u.exec(raw);
  if (paren) return paren[1].trim();
  return null;
}
