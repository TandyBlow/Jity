/** Adapter for lane 04's per-beat composer contract.
 *
 * Lane 04 owns the fact projection, beat plan and verification. This module
 * only turns one `ComposeBeatRequest` into prose: it maps the frozen facts of
 * that beat into the composer's internal beat types, then renders those beats
 * without adding a scene anchor or a closing texture. The result is 1-3
 * sentences, sourced from `scene.licensed` only.
 *
 * The types are structural on purpose: 04 can inject this composer without a
 * cross-lane import, and a future shape change fails at the adapter boundary
 * instead of inside the writer.
 */
import { composeProse } from './compose';
import { hash32 } from './support';
import type {
  ProseActor, ProseBeat, ProseItem, ProseScene,
} from './types';

export interface BeatFactLike {
  id: string;
  kind: string;
  mandatory?: boolean;
  visibility?: 'scene' | 'hidden';
  [key: string]: unknown;
}

export interface BeatDirectiveLike {
  id: string;
  index?: number;
  kind: 'open' | 'move' | 'event' | 'scene' | 'close' | string;
  subject?: { id: string; name: string; viewpoint?: boolean } | null;
  factIds: string[];
  details?: string[];
  mustMention?: string[];
  seed?: number;
  minChars?: number;
  maxChars?: number;
}

export interface SceneSkeletonLike {
  viewpoint: { id: string; name: string; location?: string; note?: string };
  place: { id?: string; name: string; note?: string; parentName?: string | null };
  present: Array<{ id: string; name: string; note?: string; viewpoint?: boolean }>;
  objects: Array<{ id: string; name: string; note?: string }>;
  facts: BeatFactLike[];
  licensed?: {
    names?: string[];
    locations?: string[];
    items?: string[];
    details?: string[];
    quotes?: string[];
  };
  /** Every registered name in the world; used only to reject a note that would
   * introduce a room the route did not license. */
  worldNames?: { characters?: string[]; locations?: string[]; items?: string[] };
  priorText?: string | null;
}

export interface ComposeBeatRequestLike {
  beat: BeatDirectiveLike;
  scene: SceneSkeletonLike;
  prior?: string | null;
}

export interface ComposeBeatResultLike {
  text: string;
  source: 'program';
  attempts: number;
  ms: number;
}

export type BeatComposerLike = (
  request: ComposeBeatRequestLike,
  options?: { signal?: AbortSignal; onProgress?: (progress: { text: string; elapsedMs: number }) => void },
) => Promise<ComposeBeatResultLike>;

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

function number(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function timeAdvance(fact: BeatFactLike): { amount: number; unit: 'second' | 'minute' | 'hour' | 'day' | 'month' | 'year' } | null {
  const advance = record(fact.advance);
  const duration = record(advance.duration);
  const units = ['second', 'minute', 'hour', 'day', 'month', 'year'] as const;
  const unit = units.find((entry) => entry === duration.unit);
  const amount = number(duration.amount);
  if (!unit || amount <= 0) return null;
  return { amount, unit };
}

/** Keep a long licensed detail usable as one beat, without cutting mid-clause. */
function placeDetail(place: string, detail: string): string {
  const clean = clipDetail(detail);
  if (!clean) return '';
  return clean.startsWith(place) ? clean : `${place}里，${clean}`;
}

/** True when every world name inside `text` is covered by the route's license
 * book. Used before quoting a settled note as a scene beat. */
function licensedText(scene: SceneSkeletonLike, text: string): boolean {
  if (!text) return false;
  const licensed = scene.licensed;
  if (!licensed) return false;
  const allowed = [licensed.names, licensed.locations, licensed.items, licensed.details, licensed.quotes]
    .flatMap((list) => list ?? [])
    .filter(Boolean)
    .sort((left, right) => right.length - left.length);
  const mask = new Array<boolean>(text.length).fill(false);
  for (const span of allowed) {
    let from = 0;
    while (from <= text.length) {
      const at = text.indexOf(span, from);
      if (at < 0) break;
      for (let index = at; index < at + span.length; index += 1) mask[index] = true;
      from = at + 1;
    }
  }
  const names = [
    ...(scene.worldNames?.characters ?? []),
    ...(scene.worldNames?.locations ?? []),
    ...(scene.worldNames?.items ?? []),
  ].sort((left, right) => right.length - left.length);
  for (const name of names) {
    let from = 0;
    while (from <= text.length) {
      const at = text.indexOf(name, from);
      if (at < 0) break;
      if (!mask[at] || !mask[at + name.length - 1]) return false;
      from = at + 1;
    }
  }
  return true;
}

function clipDetail(detail: string, max = 52): string {
  const clean = detail.replace(/\s+/gu, ' ').trim();
  if ([...clean].length <= max) return clean;
  const parts = clean.split(/[。；;]/u).map((part) => part.trim()).filter(Boolean);
  if (parts[0] && [...parts[0]].length <= max) return parts[0];
  const comma = clean.indexOf('，');
  if (comma >= 8 && comma <= max) return clean.slice(0, comma);
  return clean.slice(0, max);
}

function ensureActor(scene: ProseScene, id: string, name: string): ProseActor {
  const existing = scene.cast.find((actor) => actor.id === id);
  if (existing) return existing;
  const actor: ProseActor = { id, name, gender: 'unknown' };
  scene.cast.push(actor);
  return actor;
}

function ensureItem(scene: ProseScene, id: string, name: string, note?: string): ProseItem {
  const existing = (scene.items ?? []).find((item) => item.id === id);
  if (existing) {
    if (note && !existing.details?.includes(note)) existing.details = [...(existing.details ?? []), note];
    return existing;
  }
  const item: ProseItem = { id, name, details: note ? [note] : [] };
  scene.items = [...(scene.items ?? []), item];
  return item;
}

function taskFactText(name: string, goal: string): string {
  // The grader requires the exact goal string in the same clause as the
  // completing actor. A goal that already begins with 把/将 must not get a
  // second 把 from the template.
  return /^[把将]/u.test(goal)
    ? `${name}完成了「${goal}」。`
    : `${name}把「${goal}」这件事办完了。`;
}

function factToBeats(fact: BeatFactLike, scene: ProseScene): ProseBeat[] {
  switch (fact.kind) {
    case 'time': {
      const advance = timeAdvance(fact);
      return advance ? [{ kind: 'time', amount: advance.amount, unit: advance.unit }] : [];
    }
    case 'move': {
      const actorId = text(fact.entityId) || text(fact.actorId);
      const name = text(fact.name);
      const from = text(fact.from);
      const to = text(fact.to);
      if (!actorId || !name || !from || !to) return [];
      if (fact.entityKind === 'item') {
        ensureItem(scene, actorId, name);
        // If the item was in a character's pocket, naming that character in the
        // same clause makes the base grader read the payload as that actor's
        // move. Keep the destination and let the transfer stay implicit.
        const fromIsPerson = scene.cast.some((person) => person.name === from);
        return [{
          kind: 'move', actorId, from, to, entityKind: 'item',
          factText: fromIsPerson ? `${name}被带到了${to}。` : `${name}从${from}到了${to}。`,
        }];
      }
      ensureActor(scene, actorId, name);
      return [{ kind: 'move', actorId, from, to }];
    }
    case 'task_achieved': {
      const actorId = text(fact.ownerId) || text(fact.actorId);
      const name = text(fact.name);
      const goal = text(fact.goal) || text(fact.label);
      if (!actorId || !goal) return [];
      ensureActor(scene, actorId, name || actorId);
      return [{ kind: 'task', actorId, label: goal, factText: taskFactText(name || actorId, goal) }];
    }
    case 'subtask_added': {
      const actorId = text(fact.ownerId) || text(fact.actorId);
      const name = text(fact.name);
      const goal = text(fact.goal);
      if (!actorId || !goal) return [];
      ensureActor(scene, actorId, name || actorId);
      return [{
        kind: 'subtask', actorId, goal,
        parentGoal: text(fact.parentGoal) || undefined,
        factText: `${name || actorId}记下一条：${goal.replace(/[。；;]+$/u, '')}。`,
      }];
    }
    case 'personality_changed': {
      const actorId = text(fact.ownerId) || text(fact.actorId);
      const name = text(fact.name);
      const removed = fact.removed === true;
      const old = Array.isArray(fact.supersededTexts) ? text(fact.supersededTexts[0]) : '';
      const change = text(fact.text) || old;
      if (!actorId || !change) return [];
      ensureActor(scene, actorId, name || actorId);
      return [{
        kind: 'personality',
        actorId,
        text: removed ? `不再像先前那样${old.replace(/[。；;]+$/u, '')}` : change.replace(/[。；;]+$/u, ''),
        factText: removed
          ? `${name || actorId}不再像先前那样${old.replace(/[。；;]+$/u, '')}。`
          : undefined,
      }];
    }
    case 'sanity_changed': {
      const actorId = text(fact.ownerId) || text(fact.actorId);
      const name = text(fact.name);
      if (!actorId) return [];
      ensureActor(scene, actorId, name || actorId);
      return [{ kind: 'sanity', actorId, from: number(fact.from), to: number(fact.to) }];
    }
    case 'appearance_changed': {
      const subjectName = text(fact.name);
      const change = text(fact.text);
      const old = Array.isArray(fact.supersededTexts) ? text(fact.supersededTexts[0]) : '';
      if (!subjectName || (!change && !old)) return [];
      const entityKind = fact.entityKind === 'item' || fact.entityKind === 'location'
        ? fact.entityKind : 'character';
      return [{
        kind: 'appearance',
        subjectName,
        entityKind,
        text: change || old,
        removed: fact.removed === true,
        previous: old || undefined,
      }];
    }
    case 'item_present':
    case 'item_discovered': {
      const itemId = text(fact.itemId) || text(fact.id);
      const name = text(fact.name);
      const note = text(fact.note);
      if (!itemId || !name) return [];
      ensureItem(scene, itemId, name, note || undefined);
      return [{
        kind: 'item', itemId,
        container: text(fact.container) || undefined,
        note: note || undefined,
        discovered: fact.kind === 'item_discovered',
      }];
    }
    case 'action': {
      const actorId = text(fact.actorId) || text(fact.entityId);
      const name = text(fact.name);
      const action = text(fact.text) || text(fact.detail);
      if (!actorId || !action) return [];
      ensureActor(scene, actorId, name || actorId);
      return [{ kind: 'action', actorId, text: action }];
    }
    case 'line':
    case 'dialogue': {
      const speakerId = text(fact.speakerId) || text(fact.actorId);
      const name = text(fact.name);
      const line = text(fact.text) || text(fact.content);
      if (!speakerId || !line) return [];
      ensureActor(scene, speakerId, name || speakerId);
      return [{ kind: 'line', speakerId, text: line }];
    }
    case 'at': {
      const actorId = text(fact.entityId) || text(fact.actorId);
      const name = text(fact.name);
      const location = text(fact.location);
      if (!actorId || !location) return [];
      ensureActor(scene, actorId, name || actorId);
      return [{ kind: 'stay', actorId, location, factText: `${name || actorId}在${location}。` }];
    }
    default:
      return [];
  }
}

function factsFor(request: ComposeBeatRequestLike): BeatFactLike[] {
  const ids = new Set(request.beat.factIds ?? []);
  return (request.scene.facts ?? []).filter((fact) => ids.has(fact.id));
}

function sceneBeats(request: ComposeBeatRequestLike, scene: ProseScene, facts: BeatFactLike[]): ProseBeat[] {
  const { beat } = request;
  if (beat.kind === 'open') {
    const beats: ProseBeat[] = [];
    const time = facts.find((fact) => fact.kind === 'time');
    if (time) beats.push(...factToBeats(time, scene));
    // The open beat only owns the time fact; the move lives in a later beat.
    const viewpointMove = (request.scene.facts ?? []).find((fact) => fact.kind === 'move' && fact.viewpoint === true);
    if (viewpointMove) {
      // The point's place is where the viewpoint ENDS. Before writing the move
      // beat, opening there would put him in the destination too early.
      const from = text(viewpointMove.from) || request.scene.place.name;
      beats.push({
        kind: 'stay',
        actorId: scene.protagonistId,
        location: from,
        factText: `${request.scene.viewpoint.name}还在${from}。`,
      });
      return beats;
    }
    const place = request.scene.place.name;
    beats.push({
      kind: 'stay',
      actorId: scene.protagonistId,
      location: place,
      factText: `${request.scene.viewpoint.name}还在${place}。`,
    });
    const detail = text(request.scene.place.note);
    if (detail) beats.push({ kind: 'scene', detail: placeDetail(place, detail) });
    else if (text(request.scene.viewpoint.note)) beats.push({ kind: 'scene', detail: clipDetail(text(request.scene.viewpoint.note)) });
    return beats;
  }
  if (beat.kind === 'move') {
    const beats = facts.flatMap((fact) => factToBeats(fact, scene));
    const viewpointMoved = facts.some((fact) => fact.kind === 'move' && fact.viewpoint === true);
    const detail = beat.details?.map(text).find((entry) => entry.length > 0);
    if (viewpointMoved && detail && beats.length < 4) {
      beats.push({ kind: 'scene', detail: placeDetail(request.scene.place.name, detail) });
    }
    return beats;
  }
  if (beat.kind === 'event') {
    return facts.flatMap((fact) => factToBeats(fact, scene));
  }
  if (beat.kind === 'scene') {
    const beats = facts.flatMap((fact) => factToBeats(fact, scene));
    if (!beats.length) {
      // Texture only from material the route already licensed. An object note
      // may name other rooms (a map lists the whole campus), which the route's
      // license check would reject; a person's settled appearance does not.
      const person = request.scene.present.find((entry) => entry.id !== scene.protagonistId
        && text(entry.note) && licensedText(request.scene, text(entry.note)));
      if (person) {
        // No stance in the location: the route's base grader would read
        // "某人也在<地点>" as a position claim and flag an actor swap with the
        // viewpoint's own at-fact.
        beats.push({
          kind: 'scene',
          detail: `身边还有${person.name}，${clipDetail(text(person.note))}`,
        });
      } else {
        // Name the object when the route licensed it, otherwise fall back to a
        // licensed detail. A map note that lists other rooms is only usable
        // when the whole note is licensed.
        const object = request.scene.objects.find((entry) => text(entry.note)
          && licensedText(request.scene, `${entry.name}${text(entry.note)}`));
        const detail = [text(request.scene.place.note), ...(request.scene.licensed?.details ?? [])]
          .find((entry) => entry && licensedText(request.scene, entry));
        if (object) {
          beats.push({
            kind: 'scene',
            detail: `${object.name}还在${request.scene.place.name}，${clipDetail(text(object.note))}`,
          });
        } else if (detail) {
          beats.push({ kind: 'scene', detail: clipDetail(detail) });
        }
      }
    }
    return beats;
  }
  // close: a grounded micro-action, no new event or prop.
  //
  // The closer must not become a house stamp repeated at the end of every
  // turn ("没有马上再动/也没有动"). Choose from several equally unsupported
  // shapes, salt it by this beat, and drop any shape the previous turn already
  // used, so consecutive turns do not end on the same sentence.
  const name = request.scene.viewpoint.name;
  const presentName = request.scene.present
    .map((person) => person.name)
    .find((personName) => personName && personName !== name);
  const prior = text(request.prior) || '';
  const variants = [
    `${name}没有马上再动。`,
    `${name}把视线收回来。`,
    `${name}在原地站了一会儿。`,
    `${name}没有再往前。`,
    `${name}没有作声。`,
  ];
  if (presentName) {
    variants.push(`${presentName}那边没有动静。`);
    variants.push(`${name}停了一下，${presentName}也没有动。`);
  }
  const fresh = variants.filter((variant) => !prior.includes(variant));
  const pool = fresh.length ? fresh : variants;
  const picked = pool[hash32(`${request.beat.id}|${request.beat.seed ?? 0}|close`) % pool.length];
  return [{ kind: 'action', actorId: scene.protagonistId, text: picked }];
}

/** Build the internal whole-scene shape for one 04 beat. Exported for tests
 * and for callers that want to inspect the mapping before rendering. */
export function sceneFromBeatRequest(request: ComposeBeatRequestLike): ProseScene {
  const source = request.scene;
  const protagonistId = source.viewpoint.id;
  const cast: ProseActor[] = source.present.map((person) => ({
    id: person.id,
    name: person.name,
    gender: 'unknown',
    appearance: text(person.note) ? [person.note as string] : [],
    isProtagonist: person.id === protagonistId,
  }));
  if (!cast.some((actor) => actor.id === protagonistId)) {
    cast.unshift({
      id: protagonistId,
      name: source.viewpoint.name,
      gender: 'unknown',
      appearance: text(source.viewpoint.note) ? [source.viewpoint.note as string] : [],
      isProtagonist: true,
    });
  } else if (text(source.viewpoint.note)) {
    const actor = cast.find((entry) => entry.id === protagonistId)!;
    actor.appearance = [...(actor.appearance ?? []), source.viewpoint.note as string];
  }
  const scene: ProseScene = {
    worldId: undefined,
    pointId: request.beat.id,
    protagonistId,
    location: {
      id: source.place.id,
      name: source.place.name,
      parentName: source.place.parentName ?? null,
      details: text(source.place.note) ? [source.place.note as string] : [],
    },
    parentLocation: source.place.parentName
      ? { name: source.place.parentName, details: [] }
      : null,
    cast,
    items: source.objects.map((object) => ({
      id: object.id,
      name: object.name,
      details: text(object.note) ? [object.note as string] : [],
    })),
    beats: [],
    priorText: request.prior ?? source.priorText ?? null,
    policy: {
      beatOnly: true,
      allowMinorAction: false,
      deriveDialogue: false,
      requireTime: true,
      seed: request.beat.seed,
    },
    seed: request.beat.seed,
  };
  const facts = factsFor(request);
  scene.beats = sceneBeats(request, scene, facts);
  return scene;
}

function stripPeriod(text: string): string {
  return text.replace(/[。！？!?]+$/u, '').trim();
}

/** A subject-changing beat is one turn of one person. Group clauses by their
 * leading name, drop the repeated name, and join the group with commas, so the
 * result reads as a sentence rather than a list of fact cards. The grader
 * still binds every fact to the named subject. */
function joinEventParagraphs(paragraphs: string[], subjectName: string, presentNames: string[] = []): string[] {
  if (paragraphs.length < 2) return paragraphs;
  const names = [...new Set([subjectName, ...presentNames])].filter(Boolean).sort((a, b) => b.length - a.length);
  const groups: Array<{ lead: string; parts: string[] }> = [];
  for (const paragraph of paragraphs) {
    if (paragraph.startsWith('「')) return paragraphs;
    const lead = names.find((name) => paragraph.startsWith(name));
    const pronoun = /^[他她]/u.test(paragraph);
    if (!lead && !pronoun) return paragraphs;
    if (pronoun && groups.length) {
      groups[groups.length - 1].parts.push(paragraph);
    } else if (lead) {
      const last = groups[groups.length - 1];
      if (last && last.lead === lead) last.parts.push(paragraph);
      else groups.push({ lead, parts: [paragraph] });
    }
  }
  const output: string[] = [];
  for (const group of groups) {
    const parts = group.parts.map(stripPeriod);
    // The visible appearance is its own result; the changes that follow are
    // one turn and read best as a single comma chain.
    const firstIsAppearance = parts.length > 1
      && (parts[0].includes('，') || /(身上|的样子)/u.test(parts[0]));
    const head = firstIsAppearance ? [parts[0]] : [];
    const rest = firstIsAppearance ? parts.slice(1) : parts;
    if (head.length) output.push(`${head[0]}。`);
    if (rest.length === 1) {
      output.push(`${rest[0]}。`);
      continue;
    }
    const TASK_ISH = /^(?:完成了「|记下一条：|还有下一件事)/u;
    // Keep the possessive 的: every clause after the first becomes a new
    // sentence with the subject re-attached, and "路明非呼吸紧了一下" would
    // lose the relation the settled fact stated.
    const clauses = rest.map((part, index) => (
      index > 0 && part.startsWith(group.lead) ? part.slice(group.lead.length) : part
    ));
    // Task and subtask belong to one turn ("完成了X，记下一条Y"). A personality
    // change or a sanity beat is its own sentence, prefixed with the subject so
    // the reader never sees a sentence that starts with a bare verb.
    let chunk: string[] = [];
    for (const [index, clause] of clauses.entries()) {
      const chainable = TASK_ISH.test(clause) && chunk.length > 0 && !clause.includes('，');
      if (!chainable && chunk.length) {
        output.push(`${chunk.join('，')}。`);
        chunk = [];
      }
      chunk.push(chunk.length === 0 && index > 0 ? `${group.lead}${clause}` : clause);
    }
    if (chunk.length) output.push(`${chunk.join('，')}。`);
  }
  return output;
}

/** "三分钟过去" and "路明非还在巷里" are one temporal clause in natural prose. */
function joinOpenParagraphs(paragraphs: string[], viewpointName: string): string[] {
  if (paragraphs.length < 2) return paragraphs;
  const [first, second, ...rest] = paragraphs;
  if (!/(?:过了.+|.+过去)。$/u.test(first) || !second.startsWith(viewpointName)) return paragraphs;
  return [`${stripPeriod(first)}，${second}`, ...rest];
}

/** Two people walking at the same time read as one sentence, not two cards. */
function joinMoveParagraphs(paragraphs: string[]): string[] {
  const moves: string[] = [];
  let consumed = 0;
  for (const paragraph of paragraphs) {
    if (!/^[^，。]+从.+?(?:走到|走进|来到)[^。]*。$/u.test(paragraph)) break;
    moves.push(stripPeriod(paragraph));
    consumed += 1;
  }
  if (consumed < 2) return paragraphs;
  return [`${moves.join('，')}。`, ...paragraphs.slice(consumed)];
}

function joinCloseParagraphs(paragraphs: string[]): string[] {
  if (paragraphs.length !== 2) return paragraphs;
  return [`${stripPeriod(paragraphs[0])}，${stripPeriod(paragraphs[1])}。`];
}

/** Render one beat for lane 04. Program-only: never calls onProgress, because
 * a finished string is not a stream. */
export function composeConstrainedBeat(request: ComposeBeatRequestLike): ComposeBeatResultLike {
  const started = performance.now();
  const scene = sceneFromBeatRequest(request);
  const composed = composeProse(scene);
  let paragraphs = composed.paragraphs;
  if (request.beat.kind === 'event') {
    paragraphs = joinEventParagraphs(
      paragraphs,
      request.beat.subject?.name ?? request.scene.viewpoint.name,
      request.scene.present.map((person) => person.name),
    );
  } else if (request.beat.kind === 'open') {
    paragraphs = joinOpenParagraphs(paragraphs, request.scene.viewpoint.name);
  } else if (request.beat.kind === 'move') {
    paragraphs = joinMoveParagraphs(paragraphs);
  } else if (request.beat.kind === 'close') {
    paragraphs = joinCloseParagraphs(paragraphs);
  }
  return {
    text: paragraphs.join('\n\n'),
    source: 'program',
    attempts: 1,
    ms: performance.now() - started,
  };
}

export function createBeatComposer(): BeatComposerLike {
  const composer = (async (request: ComposeBeatRequestLike, options?: { signal?: AbortSignal }) => {
    if (options?.signal?.aborted) {
      throw new DOMException('Aborted', 'AbortError');
    }
    return composeConstrainedBeat(request);
  }) as BeatComposerLike;
  Object.defineProperty(composer, 'name', { value: 'prose-composer', configurable: true });
  return composer;
}
