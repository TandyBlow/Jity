/** Build the scene the instruct model is allowed to write.
 *
 * The projection is read-only and derived from the settled world: the
 * viewpoint's room, the people and objects visible from it, and the changes
 * this point committed. It is not a second state model — nothing here is
 * persisted, and the verifier still grades against the committed facts.
 *
 * Two sources are supported:
 * 1. `state` (the real after-state): full visible projection.
 * 2. no state: the caller's serialized `inputText` (lane-01/02 shape) and
 *    `policy.scene` material, so existing scenario callers still work.
 */
import type { Id, TimeAdvance, WorldState } from '../../../types';
import { activeText, locationName, roomOf, visibleCharacters } from '../../prompt';
import type {
  CandidateDelta, CandidateFact, InstructCandidatePolicy, SceneCharacter, SceneItem, ScenePosition, SceneProjection,
} from './types';

const charLimit = (text: string, limit: number) => (text.length <= limit ? text : `${text.slice(0, limit)}…`);

const UNIT_NAMES: Record<TimeAdvance['duration']['unit'], string> = {
  second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年',
};

export function formatWorldTime(time: WorldState['time'] | null | undefined): string {
  if (!time?.dateTime) return '';
  const match = time.dateTime.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!match) return time.dateTime;
  const [, year, month, day, hour, minute] = match;
  return `${Number(year)}年${Number(month)}月${Number(day)}日 ${hour}:${minute}`;
}

export function advanceSentence(advance: TimeAdvance | null): string | null {
  if (!advance || advance.duration.amount <= 0) return null;
  const { amount, unit } = advance.duration;
  return `大约过了 ${amount} ${UNIT_NAMES[unit]}（用动作或环境带出来，不要直接写“时间过去”）`;
}

/** Visible appearance, cut to two short clauses. Long descriptions are copied
 * verbatim by a 1.5B model (and then repeated), so the scene gets a cue, not a
 * catalogue. */
function appearanceOf(state: WorldState, id: Id): string {
  const character = state.characters[id];
  const item = state.items[id];
  const initial = state.initial.characters[id] ?? state.initial.items[id];
  const changes = character ? activeText(character.appearanceChanges) : item ? activeText(item.appearanceChanges) : [];
  if (!initial) return '';
  const clauses = [initial.initialAppearance, ...changes].join('。').split(/[。；;]/).filter(Boolean)
    // Behavioural cues ("听见枪声会缩肩") are not visible facts; a small model
    // copies them verbatim into the prose. Keep visual/state clauses only.
    .filter((clause) => !/^(?:听见|听到|看到|闻到|习惯|喜欢|不愿|总会|从不|愿意|讨厌|害怕)/.test(clause.trim()));
  return charLimit(clauses.slice(0, 2).join('。'), 80);
}

/** Only the viewpoint gets a voice cue, and only its first clause: the rest of
 * a personality line often holds private knowledge that is not visible in the
 * scene and must not be handed to the model as material. */
function personalityOf(state: WorldState, id: Id, viewpoint: boolean): string {
  const initial = state.initial.characters[id];
  const character = state.characters[id];
  if (!viewpoint || !initial || !character) return '';
  const text = [initial.initialPersonality, ...activeText(character.personalityChanges)].join('。');
  const first = text.split(/[。；;]/)[0] ?? '';
  return charLimit(first, 60);
}

function carriedBy(state: WorldState, id: Id): string[] {
  return Object.keys(state.initial.items)
    .filter((itemId) => state.items[itemId]?.position.containerId === id)
    .sort()
    .map((itemId) => state.initial.items[itemId]?.name ?? itemId);
}

function placementLabel(state: WorldState, itemId: Id): string {
  const position = state.items[itemId]?.position;
  if (!position) return '';
  const container = position.containerId;
  if (state.initial.characters[container]) return `${state.initial.characters[container].name}带着`;
  return locationName(state, container);
}

/** Items whose innermost room is the viewpoint's room, excluding items carried
 * by someone else (they are listed on that character). */
function visibleItems(state: WorldState, viewId: Id): SceneItem[] {
  const room = roomOf(state, viewId);
  const items = Object.keys(state.initial.items)
    .filter((itemId) => {
      const position = state.items[itemId]?.position;
      if (!position) return false;
      if (state.initial.characters[position.containerId] && position.containerId !== viewId) return false;
      return roomOf(state, itemId) === room;
    })
    .sort()
    .map((itemId) => ({
      id: itemId,
      name: state.initial.items[itemId].name,
      appearance: charLimit(appearanceOf(state, itemId), 60),
      placement: placementLabel(state, itemId),
    }));
  // Keep the prompt small enough for a 1.5B CPU prefill: the viewpoint's own
  // things first, then the room's props in name order. The list is optional
  // texture, not a completeness claim.
  const own = (item: SceneItem) => (state.items[item.id]?.position.containerId === viewId ? 0 : 1);
  return items.sort((a, b) => own(a) - own(b)).slice(0, 5);
}

function statementOf(fact: { name?: unknown; kind: string; [key: string]: unknown }): string | null {
  const name = String(fact.name ?? '');
  switch (fact.kind) {
    case 'at': return null; // standing position is context, not a change
    case 'moved': return `${name}从${String(fact.from)}走到${String(fact.to)}`;
    case 'sanity': return null;
    case 'sanity_changed': return `${name}的精神状态有了变化（写成情绪或神色的变化，不要写数值）`;
    case 'task_achieved': return `${name}做成了这件事：${String(fact.goal)}（写结果，不要写“完成任务”这类话）`;
    case 'personality_changed': return `${name}此后${String(fact.text)}`;
    default: return null;
  }
}

function committedFacts(committed: { facts: { id: string; kind: string; [key: string]: unknown }[] } | null | undefined): CandidateFact[] {
  if (!committed) return [];
  const facts: CandidateFact[] = [];
  for (const fact of committed.facts) {
    const statement = statementOf(fact);
    if (!statement) continue;
    facts.push({
      id: fact.id, kind: fact.kind, statement, source: 'committed', mandatory: true,
      ...(fact.kind === 'moved' ? { from: String(fact.from ?? ''), to: String(fact.to ?? '') } : {}),
    });
  }
  return facts;
}

/** Item position changes are real settled changes but have no CommittedNarration
 * fact kind. They stay in the scene list and are checked by name presence. */
function itemFacts(state: WorldState, before: WorldState | null, delta: CandidateDelta | null): CandidateFact[] {
  const facts: CandidateFact[] = [];
  for (const [id, entityDelta] of Object.entries(delta?.entityDeltas ?? {})) {
    if (!state.initial.items[id] || !entityDelta.positionSet) continue;
    const previous = before?.items[id]?.position.containerId;
    const next = state.items[id]?.position.containerId;
    if (!next || previous === next) continue;
    const holder = state.initial.characters[next]?.name;
    const place = holder ? `${holder}手上` : locationName(state, next);
    facts.push({
      id: `${id}:item-position`, kind: 'item_moved', source: 'item', mandatory: true,
      entity: state.initial.items[id].name,
      holder,
      statement: `${state.initial.items[id].name}现在在${place}`,
    });
  }
  return facts;
}

function appearanceFacts(state: WorldState, delta: CandidateDelta | null): CandidateFact[] {
  const facts: CandidateFact[] = [];
  for (const [id, entityDelta] of Object.entries(delta?.entityDeltas ?? {})) {
    for (const change of entityDelta.appearanceChanges ?? []) {
      if (!change.text) continue;
      const name = state.initial.characters[id]?.name ?? state.initial.items[id]?.name ?? locationName(state, id);
      facts.push({
        id: `${id}:appearance:${change.id}`, kind: 'appearance', source: 'appearance', mandatory: false,
        statement: `${name}身上可见的变化：${change.text}`,
      });
    }
  }
  return facts;
}

export interface ProjectionInputs {
  state?: WorldState | null;
  inputText?: string;
  before?: WorldState | null;
  delta?: CandidateDelta | null;
  committed?: { facts: { id: string; kind: string; [key: string]: unknown }[] } | null;
  policy?: InstructCandidatePolicy;
  playerInput?: string | null;
  priorText?: string | null;
  settledResults?: string[];
  recentEvents?: string[];
}

export function buildProjection(inputs: ProjectionInputs): SceneProjection {
  const { state } = inputs;
  if (state) return fromState(inputs, state);
  return fromSerializedText(inputs);
}

function fromState(inputs: ProjectionInputs, state: WorldState): SceneProjection {
  const { committed, policy, playerInput, priorText } = inputs;
  const viewId = policy?.viewpointId ?? policy?.viewpoint?.id ?? state.protagonistId;
  const viewName = state.initial.characters[viewId]?.name ?? viewId;
  const room = roomOf(state, viewId);
  const advance = inputs.delta?.timeAdvance ?? null;

  const present = visibleCharacters(state, viewId).filter((id) => id !== viewId);
  const characters: SceneCharacter[] = [viewId, ...present].map((id) => ({
    id,
    name: state.initial.characters[id]?.name ?? id,
    viewpoint: id === viewId,
    appearance: appearanceOf(state, id),
    personality: personalityOf(state, id, id === viewId),
    carrying: id === viewId ? carriedBy(state, id).slice(0, 3) : [],
  }));

  const facts = [
    ...committedFacts(committed ?? null),
    ...itemFacts(state, inputs.before ?? null, inputs.delta ?? null),
    ...appearanceFacts(state, inputs.delta ?? null),
  ];
  const advanceText = advanceSentence(advance);
  if (advanceText) facts.unshift({ id: 'time', kind: 'time', source: 'time', mandatory: true, statement: advanceText });

  const positions: ScenePosition[] = [viewId, ...present].map((id) => ({
    name: state.initial.characters[id]?.name ?? id,
    location: locationName(state, roomOf(state, id)),
    viewpoint: id === viewId,
  }));
  const priorExcerpt = priorText ? charLimit(priorText.trim().replace(/\s+/g, ' '), 200) : null;
  // The player's committed action often IS the movement this point settled.
  // Printing it twice (action block + must-write fact + plan step) made a 1.5B
  // model narrate the same walk twice (run-2 S1). The fact keeps it; the
  // separate action line is redundant then.
  const action = playerInput?.trim() || null;
  const movedPairs = (inputs.committed?.facts ?? [])
    .filter((fact) => fact.kind === 'moved')
    .map((fact) => ({ from: String(fact.from ?? ''), to: String(fact.to ?? '') }));
  const actionCarriesMovement = Boolean(action)
    && movedPairs.some((pair) => action!.includes(pair.from) && action!.includes(pair.to));
  return {
    viewpoint: { id: viewId, name: viewName },
    time: [formatWorldTime(state.time), advance?.duration.amount ? `（推进 ${advance.duration.amount} ${UNIT_NAMES[advance.duration.unit]}）` : ''].join(''),
    advance,
    place: {
      id: room,
      name: state.initial.locations[room]?.name ?? locationName(state, room),
      appearance: charLimit(state.initial.locations[room]?.initialAppearance ?? '', 160),
      notes: [charLimit(activeText(state.locations[room]?.appearanceChanges ?? []).join('；'), 120)].filter(Boolean),
    },
    characters,
    positions,
    items: visibleItems(state, viewId),
    facts,
    playerAction: actionCarriesMovement ? null : action,
    priorExcerpt,
    recentEvents: (inputs.recentEvents ?? []).slice(-4),
    fromState: true,
    licensing: {
      roster: policy?.roster ?? Object.values(state.initial.characters).map((entity) => entity.name),
      locations: policy?.locations ?? Object.values(state.initial.locations).map((entity) => entity.name),
      items: Object.values(state.initial.items).map((entity) => entity.name),
      // Only positions the viewpoint can actually see. A caller's list may
      // include the whole roster (lane 09 passes it mechanically); printing or
      // licensing an off-screen true position is still a viewpoint leak.
      knownPositions: [viewId, ...present].map((id) => ({
        name: state.initial.characters[id]?.name ?? id,
        location: locationName(state, roomOf(state, id)),
      })),
      visibleEntities: policy?.visibleEntities ?? visibleItems(state, viewId).map((item) => item.name),
      licensedEvents: policy?.licensedEvents ?? [],
      forbiddenKnowledge: policy?.forbiddenKnowledge ?? [],
    },
  };
}

/** Compatibility path: parse the lane-01/02 serialized scene text. */
function fromSerializedText(inputs: ProjectionInputs): SceneProjection {
  const text = inputs.inputText ?? '';
  const section = (name: string): string[] => {
    const match = text.match(new RegExp(`【${name}】\\n?([\\s\\S]*?)(?=\\n【|$)`));
    return match ? match[1].split('\n').map((line) => line.trim()).filter(Boolean) : [];
  };
  const viewLine = section('视角')[0] ?? '';
  const nameMatch = viewLine.match(/^(.*?)（id=/);
  const viewpointName = nameMatch?.[1]?.trim() || inputs.policy?.scene?.present?.[0]?.name || '主角';
  const scene = inputs.policy?.scene ?? null;
  const stateLines = section('本回合状态');
  const present = scene?.present ?? stateLines.map((line: string) => {
    const stripped = line.replace(/^- /, '');
    const name = stripped.match(/^-?\s*([^（(]+)[（(]/)?.[1]?.trim() ?? stripped.slice(0, 8);
    return { name, note: stripped };
  });
  const characters: SceneCharacter[] = present.map((entry, index) => ({
    id: `scene-${index}`,
    name: entry.name,
    viewpoint: index === 0,
    appearance: entry.note ?? '',
    personality: '',
    carrying: [],
  }));
  if (!characters.length) characters.push({ id: 'view', name: viewpointName, viewpoint: true, appearance: '', personality: '', carrying: [] });
  const itemLine = section('可写到的东西')[0] ?? '';
  const objectList: { name: string; note?: string }[] = scene?.objects ?? (itemLine && itemLine !== '无'
    ? itemLine.split('；').filter(Boolean).map((name: string) => ({ name: name.split('（')[0] }))
    : []);
  const items: SceneItem[] = objectList.map((entry, index) => ({
    id: `item-${index}`, name: entry.name, appearance: entry.note ?? '', placement: '',
  }));
  const changeLines = section('本回合变化').filter((line) => line && !line.startsWith('【'));
  const facts: CandidateFact[] = committedFacts(inputs.committed ?? null);
  if (!facts.length) {
    for (const line of changeLines) facts.push({ id: `serialized-${facts.length}`, kind: 'serialized', source: 'delta', mandatory: true, statement: line.replace(/^- /, '') });
  }
  return {
    viewpoint: { id: 'view', name: viewpointName },
    time: section('时间和地点')[0] ?? '',
    advance: null,
    place: {
      id: 'scene',
      name: scene?.location ?? (section('时间和地点')[0]?.split('；').pop()?.replace(/^地点：/, '') ?? ''),
      appearance: (scene?.placeNotes ?? []).join('；'),
      notes: [],
    },
    characters,
    positions: [{ name: viewpointName, location: scene?.location ?? '', viewpoint: true }],
    items,
    facts,
    playerAction: inputs.playerInput?.trim() || scene?.previousAction || null,
    priorExcerpt: inputs.priorText ? charLimit(inputs.priorText.trim(), 200) : null,
    recentEvents: (inputs.recentEvents ?? []).slice(-4),
    fromState: false,
    licensing: {
      roster: inputs.policy?.roster ?? [],
      locations: inputs.policy?.locations ?? [],
      items: [],
      knownPositions: inputs.policy?.knownPositions ?? [],
      visibleEntities: inputs.policy?.visibleEntities ?? items.map((item) => item.name),
      licensedEvents: inputs.policy?.licensedEvents ?? [],
      forbiddenKnowledge: inputs.policy?.forbiddenKnowledge ?? [],
    },
  };
}

/** A per-point identity for the prompt header (the schedule's point id). */
export function pointIdOf(inputText: string | undefined): Id | null {
  const match = inputText?.match(/"pointId"\s*:\s*"([^"]+)"/);
  return match?.[1] ?? null;
}
