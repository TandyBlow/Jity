/** Scene packet for the action-family tasks.
 *
 * Everything here is derived from the committed working state and the
 * declared call input; this file makes no decision. It answers four questions
 * the three handlers and their guards need:
 *   1. who is in the focused character's room (and where exactly they are),
 *   2. who is registered but elsewhere (never selectable as a target, never
 *      silently treated as present),
 *   3. which items are actually reachable in that room (container/slot paths
 *      included, so "打开箱子" is not mistaken for a person),
 *   4. which names the input may mention (full names plus optional aliases).
 */
import type { Id, WorldState } from '../../../types';
import { activeText, locationName, roomOf } from '../../prompt';

const SLOT_LABELS: Record<string, string> = {
  slot_wall: '墙边', slot_entry: '入口', slot_counter: '柜台后', slot_window: '窗边',
  slot_pillar3: '第三根柱子旁', slot_east_cover: '东侧掩体', slot_flag_base: '旗台底座',
  slot_cage: '笼内', slot_empty_bed: '空床上', slot_body: '身上', slot_right_hand: '右手',
  slot_left_hand: '左手', slot_waist: '腰间', slot_pocket: '口袋里', slot_top: '台面上',
  slot_shelf: '架子上', slot_under: '下面', slot_socket: '插槽里', slot_cell1: '一号槽',
  slot_cell2: '二号槽', slot_cold: '冷藏格', slot_wrap: '绷带格', slot_gloves: '手套格',
  slot_left: '左格', slot_right: '右格',
};

const RELATION_LABELS: Record<string, string> = {
  under: '下面', above: '上方', beside: '旁边', in_front_of: '前面', behind: '后面',
};

export interface SceneTask {
  id: Id;
  goal: string;
  status: 'pending' | 'achieved';
}

export interface SceneCharacter {
  id: Id;
  name: string;
  roomId: Id;
  roomName: string;
  position: string;
  sanity: number;
  personality: string[];
  appearance: string[];
  tasks: SceneTask[];
  held: { id: Id; name: string }[];
  role: 'actor' | 'visible' | 'absent';
}

export interface SceneItem {
  id: Id;
  name: string;
  position: string;
  appearance: string[];
}

export interface NameEntry {
  id: Id;
  name: string;
  kind: 'character' | 'item' | 'location';
  aliases: string[];
}

export interface ActionScene {
  actorId: Id;
  actorName: string;
  isProtagonist: boolean;
  protagonistId: Id;
  protagonistName: string;
  roomId: Id;
  roomName: string;
  roomChain: string[];
  protagonistRoomId: Id;
  protagonistRoomName: string;
  sameRoomAsProtagonist: boolean;
  actor: SceneCharacter;
  visible: SceneCharacter[];
  absent: SceneCharacter[];
  items: SceneItem[];
  playerInput: string | null;
  intentStatus: 'pending' | 'consumed' | 'expired';
  recentEvents: string[];
  time: string;
  names: NameEntry[];
}

export interface BuildSceneOptions {
  playerInput?: string | null;
  intentStatus?: string;
  events?: readonly string[];
  aliases?: Record<Id, string[]>;
  maxEvents?: number;
}

function entityName(state: WorldState, id: Id): string {
  return state.initial.characters[id]?.name ?? state.initial.items[id]?.name
    ?? state.initial.locations[id]?.name ?? id;
}

function isContainerItem(state: WorldState, id: Id): boolean {
  return state.initial.items[id] !== undefined;
}

/** Human-readable position: container (location, item or carrier), slot label
 * and an optional relativeTo relation. Container-of-container chains collapse
 * into "物品（在地点）" so the model can see that an item is inside a box. */
export function positionLabel(state: WorldState, id: Id): string {
  const entity = state.characters[id] ?? state.items[id];
  if (!entity) return '未知位置';
  const containerId = entity.position.containerId;
  const slotId = entity.position.slotId;
  const location = state.initial.locations[containerId];
  let container: string;
  if (location) {
    container = location.name;
  } else if (isContainerItem(state, containerId)) {
    const inner = state.initial.items[containerId]!;
    container = `${inner.name}（在${locationName(state, roomOf(state, containerId))}）`;
  } else if (state.initial.characters[containerId]) {
    container = `${state.initial.characters[containerId]!.name}身上`;
  } else {
    container = containerId;
  }
  const slot = slotId ? `/${SLOT_LABELS[slotId] ?? slotId}` : '';
  const relative = entity.position.relativeTo
    ? `，在${entityName(state, entity.position.relativeTo.entityId)}${RELATION_LABELS[entity.position.relativeTo.relation] ?? ''}`
    : '';
  return `${container}${slot}${relative}`;
}

export function roomChain(state: WorldState, roomId: Id): string[] {
  const chain: string[] = [];
  let node: Id | null = roomId;
  const seen = new Set<Id>();
  while (node && !seen.has(node)) {
    seen.add(node);
    chain.push(locationName(state, node));
    node = state.initial.locations[node]?.parentLocationId ?? null;
  }
  return chain;
}

function heldItems(state: WorldState, characterId: Id): { id: Id; name: string }[] {
  return Object.keys(state.items)
    .filter((itemId) => state.items[itemId]?.position.containerId === characterId)
    .sort()
    .map((itemId) => ({ id: itemId, name: state.initial.items[itemId]!.name }));
}

export function characterView(state: WorldState, id: Id, role: SceneCharacter['role']): SceneCharacter {
  const initial = state.initial.characters[id]!;
  const current = state.characters[id]!;
  const roomId = roomOf(state, id);
  return {
    id,
    name: initial.name,
    roomId,
    roomName: locationName(state, roomId),
    position: positionLabel(state, id),
    sanity: current.sanity,
    personality: [initial.initialPersonality, ...activeText(current.personalityChanges)],
    appearance: [initial.initialAppearance, ...activeText(current.appearanceChanges)],
    tasks: Object.values(current.tasks)
      .map((task) => ({ id: task.id, goal: task.goal, status: task.status }))
      .sort((left, right) => (left.status === right.status ? (left.id < right.id ? -1 : 1) : left.status === 'pending' ? -1 : 1)),
    held: heldItems(state, id),
    role,
  };
}

export function itemView(state: WorldState, id: Id): SceneItem {
  const initial = state.initial.items[id]!;
  const current = state.items[id];
  return {
    id,
    name: initial.name,
    position: positionLabel(state, id),
    appearance: [initial.initialAppearance, ...activeText(current?.appearanceChanges ?? [])],
  };
}

/** Registered names the input may legitimately mention.
 *
 * Only full names plus caller-declared extra aliases land here. A shortened
 * personal name ("路明非" → "明非") is NOT added automatically: a 2-character
 * suffix also occurs inside unrelated words, and a false "absent character"
 * hit would reject a legal action. The target normalizer adds those suffixes
 * separately, where a wrong guess only affects name→id mapping. */
export function nameTable(state: WorldState, aliases: Record<Id, string[]> = {}): NameEntry[] {
  const entries: NameEntry[] = [];
  const push = (id: Id, name: string, kind: NameEntry['kind'], extra: string[] = []): void => {
    const set = new Set<string>([name, ...extra, ...(aliases[id] ?? [])].map((value) => value.trim()).filter((value) => [...value].length >= 2));
    entries.push({ id, name, kind, aliases: [...set] });
  };
  for (const id of Object.keys(state.initial.characters).sort()) push(id, state.initial.characters[id]!.name, 'character');
  for (const id of Object.keys(state.initial.items).sort()) push(id, state.initial.items[id]!.name, 'item');
  for (const id of Object.keys(state.initial.locations).sort()) push(id, state.initial.locations[id]!.name, 'location');
  return entries;
}

export interface Mention {
  entry: NameEntry;
  alias: string;
  index: number;
}

/** Longest-alias-first, non-overlapping mention scan. Detection only: it
 * feeds evidence and absent-entity guards; it never selects a target. */
export function findMentions(text: string, names: NameEntry[]): Mention[] {
  const normalized = text.normalize('NFC');
  const candidates: Mention[] = [];
  for (const entry of names) {
    for (const alias of entry.aliases) {
      let index = normalized.indexOf(alias);
      while (index >= 0) {
        candidates.push({ entry, alias, index });
        index = normalized.indexOf(alias, index + alias.length);
      }
    }
  }
  candidates.sort((left, right) => (right.alias.length - left.alias.length) || (left.index - right.index));
  const taken: { start: number; end: number }[] = [];
  const chosen: Mention[] = [];
  for (const candidate of candidates) {
    const start = candidate.index;
    const end = start + candidate.alias.length;
    if (taken.some((range) => start < range.end && end > range.start)) continue;
    taken.push({ start, end });
    chosen.push(candidate);
  }
  return chosen.sort((left, right) => left.index - right.index);
}

/** Scene for one character. Throws when the focus id is not a registered
 * character: that is a caller/scenario error, not something to guess about. */
export function buildScene(state: WorldState, focusId: Id, options: BuildSceneOptions = {}): ActionScene {
  const focus = state.characters[focusId];
  const initial = state.initial.characters[focusId];
  if (!focus || !initial) throw new Error(`actor_unknown:${focusId}`);
  const protagonistId = state.protagonistId;
  const protagonistInitial = state.initial.characters[protagonistId];
  if (!protagonistInitial) throw new Error(`protagonist_unknown:${protagonistId}`);
  const roomId = roomOf(state, focusId);
  const protagonistRoomId = roomOf(state, protagonistId);
  const visible: SceneCharacter[] = [];
  const absent: SceneCharacter[] = [];
  for (const id of Object.keys(state.characters).sort()) {
    if (id === focusId) continue;
    (roomOf(state, id) === roomId ? visible : absent).push(characterView(state, id, roomOf(state, id) === roomId ? 'visible' : 'absent'));
  }
  // Items reachable in the room: lying in the room or carried by someone in
  // it. A box's contents are listed through their container's position.
  const items = Object.keys(state.items)
    .filter((id) => roomOf(state, id) === roomId)
    .sort()
    .map((id) => itemView(state, id));
  const intent = options.intentStatus;
  return {
    actorId: focusId,
    actorName: initial.name,
    isProtagonist: focusId === protagonistId,
    protagonistId,
    protagonistName: protagonistInitial.name,
    roomId,
    roomName: locationName(state, roomId),
    roomChain: roomChain(state, roomId),
    protagonistRoomId,
    protagonistRoomName: locationName(state, protagonistRoomId),
    sameRoomAsProtagonist: roomId === protagonistRoomId,
    actor: characterView(state, focusId, 'actor'),
    visible,
    absent,
    items,
    playerInput: options.playerInput?.normalize('NFC').trim() || null,
    intentStatus: intent === 'consumed' || intent === 'expired' ? intent : 'pending',
    recentEvents: (options.events ?? []).map((event) => event.trim()).filter(Boolean).slice(-(options.maxEvents ?? 4)),
    time: state.time.dateTime,
    names: nameTable(state, options.aliases),
  };
}

export interface SceneMentions {
  characters: Mention[];
  absentCharacters: Mention[];
  items: Mention[];
  absentItems: Mention[];
  locations: Mention[];
}

/** Which registered entities a piece of text names, split by scene presence.
 * `absentItems` are items whose room differs from the scene's room. */
export function sceneMentions(scene: ActionScene, state: WorldState, text: string): SceneMentions {
  const mentions = findMentions(text, scene.names);
  const present = new Set<string>();
  const result: SceneMentions = { characters: [], absentCharacters: [], items: [], absentItems: [], locations: [] };
  for (const mention of mentions) {
    const key = `${mention.entry.kind}:${mention.entry.id}`;
    if (present.has(key)) continue;
    present.add(key);
    if (mention.entry.kind === 'location') result.locations.push(mention);
    else if (mention.entry.kind === 'character') {
      (roomOf(state, mention.entry.id) === scene.roomId ? result.characters : result.absentCharacters).push(mention);
    } else {
      (roomOf(state, mention.entry.id) === scene.roomId ? result.items : result.absentItems).push(mention);
    }
  }
  return result;
}
