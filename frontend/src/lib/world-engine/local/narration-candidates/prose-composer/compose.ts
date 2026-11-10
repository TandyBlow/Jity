/** Deterministic prose realisation.
 *
 * The writer turns validated beats into short paragraphs. It chooses sentence
 * forms without repeating one form twice in a row, resolves names into natural
 * references, anchors the scene in a licensed detail and keeps the last beat
 * as the ending instead of adding a stock conclusion.
 */

import { buildLicense, echoOfPrior, guardParagraph } from './guard';
import {
  charCount, clampInt, createRandom, ensurePeriod, fillSlots, firstClause, hash32,
  lastSentence, normalizeClause, overlapRatio, splitSentences, stripQuotes,
} from './support';
import type {
  ComposedProse, ProseActor, ProseBeat, ProseIssue, ProseItem, ProseScene, RenderedBeat,
} from './types';

export const PROSE_STRATEGY_VERSION = 'prose-composer-v1';

const nowMs = (): number => (typeof performance !== 'undefined' ? performance.now() : Date.now());

class Referencer {
  private readonly actors: Map<string, ProseActor>;
  private readonly counts = new Map<string, number>();
  private readonly rng: () => number;
  private readonly pronounSafe: Map<string, boolean>;

  constructor(actors: ProseActor[], rng: () => number) {
    this.actors = new Map(actors.map((actor) => [actor.id, actor]));
    this.rng = rng;
    this.pronounSafe = new Map();
    for (const actor of actors) {
      const gender = actor.gender ?? 'unknown';
      const same = gender !== 'unknown'
        ? actors.filter((other) => (other.gender ?? 'unknown') === gender).length
        : 0;
      this.pronounSafe.set(actor.id, same === 1);
    }
  }

  has(id: string): boolean {
    return this.actors.has(id);
  }

  name(id: string): string {
    return this.actors.get(id)?.name ?? id;
  }

  /** Full name; this is what verification looks for. */
  full(id: string): string {
    this.counts.set(id, (this.counts.get(id) ?? 0) + 1);
    return this.name(id);
  }

  /** Natural subject: full name on first use, then an explicit reference or a
   * pronoun only when the cast has exactly one actor of that gender. */
  subject(id: string): string {
    const actor = this.actors.get(id);
    if (!actor) return id;
    const count = this.counts.get(id) ?? 0;
    if (count === 0) return this.full(id);
    this.counts.set(id, count + 1);
    const explicit = actor.references?.filter((ref) => ref && ref !== actor.name) ?? [];
    if (explicit.length) {
      const index = Math.min(explicit.length - 1, Math.floor(this.rng() * explicit.length));
      return explicit[index];
    }
    if (this.pronounSafe.get(id)) {
      const pronoun = (actor.gender ?? 'unknown') === 'female' ? '她' : '他';
      // Do not make every second mention a pronoun; names are normal in the
      // source prose and avoid ambiguity after a dialogue exchange.
      if (count % 3 !== 2) return pronoun;
    }
    return this.name(id);
  }

  /** Reference for a paragraph that already opened with this name: an explicit
   * reference or an unambiguous pronoun, otherwise the name again. Unlike
   * `subject`, this does not enforce the every-third-mention rhythm. */
  reference(id: string): string {
    const actor = this.actors.get(id);
    if (!actor) return id;
    const explicit = actor.references?.find((ref) => ref && ref !== actor.name);
    if (explicit) return explicit;
    if (this.pronounSafe.get(id)) return (actor.gender ?? 'unknown') === 'female' ? '她' : '他';
    return this.name(id);
  }

  /** Object position: names are preferred; 对方 only for a known addressee. */
  object(id: string, addressee = false): string {
    if (addressee) return '对方';
    return this.name(id);
  }
}

class TemplateBag {
  private readonly used = new Map<string, Set<number>>();
  private readonly rng: () => number;

  constructor(rng: () => number) {
    this.rng = rng;
  }

  pick(key: string, variants: readonly string[]): string {
    if (!variants.length) throw new Error(`no template variants for ${key}`);
    const used = this.used.get(key) ?? new Set<number>();
    this.used.set(key, used);
    const available = variants
      .map((text, index) => ({ text, index }))
      .filter((entry) => !used.has(entry.index));
    const pool = available.length ? available : variants.map((text, index) => ({ text, index }));
    const chosen = pool[Math.floor(this.rng() * pool.length) % pool.length];
    used.add(chosen.index);
    return chosen.text;
  }

  reset(key: string): void {
    this.used.delete(key);
  }
}

interface Unit {
  text: string;
  beats: ProseBeat[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/** Validate references and impossible skeletons before composing. */
export function validateScene(scene: ProseScene): ProseIssue[] {
  const issues: ProseIssue[] = [];
  if (!scene || !isRecord(scene as unknown)) {
    return [{ kind: 'empty_scene', severity: 'hard', detail: 'scene is not an object' }];
  }
  if (!scene.protagonistId) {
    issues.push({ kind: 'unknown_reference', severity: 'hard', detail: 'protagonistId is missing' });
  }
  const actors = new Set((scene.cast ?? []).map((actor) => actor.id));
  const items = new Set((scene.items ?? []).map((item) => item.id));
  if (!actors.has(scene.protagonistId)) {
    issues.push({ kind: 'unknown_reference', severity: 'hard', detail: `protagonist ${scene.protagonistId} is not in cast` });
  }
  for (const beat of scene.beats ?? []) {
    switch (beat.kind) {
      case 'move':
        if (beat.entityKind === 'item') {
          if (!items.has(beat.actorId) && !beat.actorName) {
            issues.push({ kind: 'unknown_reference', severity: 'hard', detail: `move item ${beat.actorId} is not in items` });
          }
        } else if (!actors.has(beat.actorId) && !beat.actorName) {
          issues.push({ kind: 'unknown_reference', severity: 'hard', detail: `move actor ${beat.actorId} is not in cast` });
        }
        break;
      case 'stay': case 'leave': case 'arrive': case 'task': case 'subtask':
      case 'personality': case 'sanity': case 'action':
        if (!actors.has(beat.actorId)) {
          issues.push({ kind: 'unknown_reference', severity: 'hard', detail: `${beat.kind} actor ${beat.actorId} is not in cast` });
        }
        break;
      case 'line':
        if (!actors.has(beat.speakerId)) {
          issues.push({ kind: 'unknown_reference', severity: 'hard', detail: `line speaker ${beat.speakerId} is not in cast` });
        }
        if (beat.addresseeId && !actors.has(beat.addresseeId)) {
          issues.push({ kind: 'unknown_reference', severity: 'hard', detail: `line addressee ${beat.addresseeId} is not in cast` });
        }
        break;
      case 'item':
        if (!items.has(beat.itemId)) {
          issues.push({ kind: 'unknown_reference', severity: 'hard', detail: `item ${beat.itemId} is not in items` });
        }
        break;
      default:
        break;
    }
  }
  return issues;
}

function actorOf(scene: ProseScene, id: string): ProseActor | undefined {
  return scene.cast.find((actor) => actor.id === id);
}

function itemOf(scene: ProseScene, id: string): ProseItem | undefined {
  return (scene.items ?? []).find((item) => item.id === id);
}

function isRequired(beat: ProseBeat): boolean {
  return beat.kind === 'move' || beat.kind === 'leave' || beat.kind === 'arrive'
    || beat.kind === 'item' || beat.kind === 'task' || beat.kind === 'subtask'
    || beat.kind === 'personality' || beat.kind === 'appearance'
    || beat.kind === 'action' || beat.kind === 'line' || beat.kind === 'scene'
    || beat.kind === 'sanity';
}

/** A detail that can open a paragraph without becoming a wall of scenery. */
function anchorClause(detail: string, max = 44): string {
  const text = detail.trim();
  if (charCount(text) <= max) return text;
  // A scene anchor is one or two clauses, not a whole paragraph of scenery.
  // Split on every clause separator, then take the longest prefix under `max`
  // that still ends on a clause boundary.
  const tokens = text.match(/[^。；，!?！？]+[。；，!?！？]?/gu) ?? [text];
  let picked = '';
  for (const token of tokens) {
    const next = `${picked}${token}`;
    if (picked && charCount(next) > max) break;
    picked = next;
  }
  const clean = picked.replace(/[，；]+$/u, '').trim();
  return charCount(clean) >= 6 ? clean : text.slice(0, max);
}

function priorSentences(priorText: string | null): string[] {
  if (!priorText) return [];
  return splitSentences(priorText).filter((sentence) => charCount(sentence) >= 6);
}

/** Pick one licensed scene anchor. Changed details win over unchanged ones,
 * and a detail the previous turn already used is skipped when possible. */
function chooseAnchor(scene: ProseScene, priorText: string | null): string[] {
  const candidates: Array<{ text: string; weight: number }> = [];
  const prior = priorSentences(priorText);
  const add = (value: string | null | undefined, weight: number) => {
    const text = value?.trim();
    if (!text) return;
    if (scene.toldFacts?.some((fact) => fact && text.includes(fact))) return;
    if (candidates.some((entry) => entry.text === text)) return;
    candidates.push({ text: anchorClause(text), weight });
  };
  for (const beat of scene.beats) {
    if (beat.kind === 'scene') {
      // Who is standing nearby is texture, not the opening. The place note (or
      // a changed object) should lead; otherwise the turn opens with what is
      // effectively a state list entry.
      const presenceOnly = /^(?:身边还有|不远处是|近处还有|旁边是)/u.test(beat.detail);
      // On a continuation the place line is usually the echoed one; opening the
      // new turn with "who is nearby" instead would be a state-list opener.
      if (presenceOnly && priorText) continue;
      add(beat.detail, presenceOnly ? 35 : 100);
    }
    // An item change is this turn's event; it is rendered as a beat, not as a
    // scene opening. Only an unchanged item may serve as the anchor.
    if (beat.kind === 'item' && beat.change === undefined) add(beat.detail ?? beat.note, 90);
  }
  for (const detail of scene.locationChange?.added ?? []) add(detail, 95);
  for (const detail of scene.location.details ?? []) add(detail, 60);
  for (const detail of scene.parentLocation?.details ?? []) add(detail, 30);
  const protagonist = actorOf(scene, scene.protagonistId);
  // On a continuation the reader already knows how the viewpoint looks; do
  // not open the new turn by describing him again.
  if (!scene.priorText) {
    for (const detail of protagonist?.appearance ?? []) add(detail, 20);
  }
  const fresh = candidates.filter((entry) => {
    if (!prior.length) return true;
    if (priorText?.includes(entry.text.slice(0, 3))) return false;
    return !prior.some((sentence) => overlapRatio(entry.text, sentence) > 0.4);
  });
  // On a continuation, an all-echo candidate set means the turn has nothing
  // new to open with; starting on the first beat is better than repeating.
  const pool = fresh.length ? fresh : (priorText ? [] : candidates);
  if (!pool.length) return [];
  pool.sort((left, right) => right.weight - left.weight);
  const chosen = pool[0];
  const rest = candidates.filter((entry) => entry.text !== chosen.text).map((entry) => entry.text);
  return [chosen.text, ...rest];
}

function paragraphStart(paragraph: string): string {
  return firstClause(paragraph).slice(0, 5);
}

export function composeProse(scene: ProseScene): ComposedProse {
  const started = nowMs();
  const planStart = nowMs();
  const policy = scene.policy ?? {};
  const issues = validateScene(scene);
  if (!scene.cast?.length) {
    return emptyResult(scene, issues, started);
  }

  const seed = scene.seed ?? policy.seed ?? hash32(`${scene.pointId ?? ''}|${scene.protagonistId}|${scene.location.name}`);
  const rng = createRandom(seed);
  const refs = new Referencer(scene.cast, rng);
  const templates = new TemplateBag(rng);
  const license = buildLicense(scene);
  const beatOnly = policy.beatOnly === true;
  // Static texture already read this session must not come back. `priorText` is
  // one turn; `avoidText` is the session transcript when the caller has it.
  const seenText = [scene.priorText, policy.avoidText ?? scene.avoidText]
    .filter((part): part is string => Boolean(part))
    .join(String.fromCharCode(10));
  if (typeof process !== 'undefined' && process.env?.PROSE_DEBUG_BEATS) {
    console.error('DEBUG scene beats', JSON.stringify(scene.beats.map((b) => ({
      k: b.kind, id: (b as { itemId?: string }).itemId, d: (b as { detail?: string }).detail,
      a: (b as { actorId?: string }).actorId, n: (b as { actorName?: string }).actorName,
      from: (b as { from?: string }).from, to: (b as { to?: string }).to,
    }))));
  }
  const anchorScene: ProseScene = { ...scene, priorText: seenText || scene.priorText || null };
  const anchorPool = beatOnly ? [] : chooseAnchor(anchorScene, seenText || null);
  const protagonistAppearance = actorOf(scene, scene.protagonistId)?.appearance ?? [];
  const appearanceOnly = anchorPool[0] !== undefined
    && protagonistAppearance.some((detail) => anchorClause(detail) === anchorPool[0]);
  let anchor = !beatOnly && scene.priorText && appearanceOnly
    && (scene.beats ?? []).some((beat) => beat.kind === 'line' || beat.kind === 'action')
    ? null
    : anchorPool[0] ?? null;
  if (anchor) {
    // An item beat prints its own detail; using the same detail as the anchor
    // would say it twice in one turn.
    const itemText = (beat: { detail?: string; note?: string; factText?: string }) =>
      [beat.detail, beat.note, beat.factText].filter(Boolean).join(' ');
    const itemBeatOwnsIt = (scene.beats ?? []).some((beat) => beat.kind === 'item'
      && itemText(beat as { detail?: string; note?: string; factText?: string }).includes(anchor as string));
    // Anything the reader already has may not come back as the opening.
    const seenAlready = Boolean(seenText) && echoOfPrior(anchor, seenText) > 0.6;
    if (itemBeatOwnsIt || seenAlready) anchor = null;
  }
  // The anchor is a truncated clause, so match the beat by its clause too;
  // otherwise the same sentence is printed once as the opening and again as
  // its own paragraph.
  const anchorBeat = (scene.beats ?? []).find((beat) =>
    beat.kind === 'scene' && anchor !== null && anchorClause(beat.detail) === anchor);
  let body = (scene.beats ?? []).filter((beat) => beat !== anchorBeat);
  // A stay beat only matters as contrast to someone else moving. It is placed
  // after that movement and dropped when the "only one remains" line will say
  // the same thing more naturally.
  const stayBeats = body.filter((beat) => beat.kind === 'stay');
  if (stayBeats.length) {
    const rest = body.filter((beat) => beat.kind !== 'stay');
    const lastMovement = rest.reduce((index, beat, position) => (
      beat.kind === 'move' || beat.kind === 'leave' || beat.kind === 'arrive' ? position : index
    ), -1);
    if (lastMovement >= 0) {
      const reordered: ProseBeat[] = [];
      rest.forEach((beat, position) => {
        reordered.push(beat);
        if (position === lastMovement) reordered.push(...stayBeats);
      });
      body = reordered;
    }
  }
  const units: Unit[] = [];
  const rendered: RenderedBeat[] = [];

  const push = (text: string, beats: ProseBeat[] = []): void => {
    const clean = text.trim();
    if (!clean) return;
    const last = units[units.length - 1];
    if (last && last.text === clean) return;
    units.push({ text: clean, beats });
  };

  const record = (beat: ProseBeat, paragraph: number, sentence: string | null): void => {
    rendered.push({ beat, paragraph, sentence });
  };

  // A finished paragraph carries a beat only when the beat is actually stated.
  const pushBeat = (text: string, beat: ProseBeat): void => {
    push(text, [beat]);
    record(beat, units.length - 1, text);
  };

  const bodyStart = nowMs();
  if (anchor) {
    const paragraph = ensurePeriod(anchor);
    push(paragraph);
    if (anchorBeat) record(anchorBeat, 0, paragraph);
  }

  let lastSpeaker: string | null = null;
  let lastQuestion = false;
  let minorLooks = 0;

  for (let index = 0; index < body.length; index += 1) {
    const beat = body[index];
    const before = units.length;
    switch (beat.kind) {
      case 'scene': {
        const text = ensurePeriod(beat.factText ?? beat.detail);
        // Scene texture is optional colour. If the reader has already had this
        // exact line, drop it instead of stamping it again.
        if (seenText && echoOfPrior(text, seenText) > 0.72) break;
        pushBeat(text, beat);
        break;
      }
      case 'move': {
        const movingItem = beat.entityKind === 'item' ? itemOf(scene, beat.actorId) : undefined;
        // An item or a person who already left this place has no entry in the
        // cast/items list, but the move still happened and must be told with a
        // name, never a pronoun.
        const itemName = movingItem?.name ?? (beat.entityKind === 'item' ? beat.actorName : undefined);
        const actor = itemName ? undefined : actorOf(scene, beat.actorId);
        const subjectName = itemName ?? actor?.name ?? beat.actorName;
        if (!subjectName) break;
        const from = beat.from;
        const to = beat.to;
        // Departures name the person; arrivals use the same references as any
        // other beat so the prose does not read like a report.
        const subject = actor && itemName === undefined ? refs.subject(actor.id) : subjectName;
        const variants = itemName
          ? [`${subject}从${from}到了${to}。`, `${subject}被从${from}带到了${to}。`]
          : [
            `${subject}从${from}走到${to}。`,
            `${subject}从${from}走进${to}。`,
            `${subject}从${from}来到${to}。`,
          ];
        if (beat.manner && actor) variants.push(`${subject}${beat.manner}，从${from}到了${to}。`);
        let sentence = templates.pick('move', variants);
        if (beat.factText) sentence = ensurePeriod(fillSlots(beat.factText, nameMap(scene), beat.actorId));
        pushBeat(sentence, beat);
        const next = body[index + 1];
        if (!beatOnly && actor && beat.to !== scene.location.name && next?.kind !== 'line') {
          push(`${refs.subject(beat.actorId)}的脚步声往${beat.to}那边去了。`, []);
        }
        break;
      }
      case 'stay': {
        const actor = actorOf(scene, beat.actorId);
        if (!actor) break;
        const subject = refs.subject(actor.id);
        const location = beat.location ?? scene.location.name;
        const sentence = templates.pick('stay', [
          `${subject}留在${location}。`,
          `${subject}留在原地。`,
          `${subject}站在原地。`,
        ]);
        pushBeat(beat.factText ? ensurePeriod(fillSlots(beat.factText, nameMap(scene), beat.actorId)) : sentence, beat);
        break;
      }
      case 'leave': {
        const actor = actorOf(scene, beat.actorId);
        if (!actor) break;
        const subject = refs.subject(actor.id);
        const sentence = beat.to
          ? templates.pick('leave', [
            `${subject}往${beat.to}去了。`,
            `${subject}出了${scene.location.name}，往${beat.to}去。`,
            `${subject}没有回头，往${beat.to}去了。`,
          ])
          : templates.pick('leave-alone', [
            `${subject}离开了${scene.location.name}。`,
            `${subject}出了${scene.location.name}。`,
            `${subject}的脚步声很快听不见了。`,
          ]);
        pushBeat(beat.factText ? ensurePeriod(fillSlots(beat.factText, nameMap(scene), beat.actorId)) : sentence, beat);
        break;
      }
      case 'arrive': {
        const actor = actorOf(scene, beat.actorId);
        if (!actor) break;
        const subject = refs.subject(actor.id);
        const location = beat.location ?? scene.location.name;
        const sentence = templates.pick('arrive', [
          `${subject}进来的时候，${location}里没有别的声音。`,
          `${subject}从外面进来，停在${location}边上。`,
          `${subject}出现在${location}。`,
        ]);
        pushBeat(beat.factText ? ensurePeriod(fillSlots(beat.factText, nameMap(scene), beat.actorId)) : sentence, beat);
        break;
      }
      case 'item': {
        const item = itemOf(scene, beat.itemId);
        if (!item) break;
        const detail = beat.detail ?? beat.note ?? item.details?.find((value) => !scene.toldFacts?.includes(value));
        let sentence: string;
        if (beat.factText) sentence = ensurePeriod(fillSlots(beat.factText, nameMap(scene)));
        else if (beat.container) {
          const note = detail ? ensurePeriod(detail) : '';
          sentence = `${item.name}${beat.discovered ? '就在' : '还在'}${beat.container}。${note}`;
        } else if (beat.change === 'removed' && !detail) sentence = `${item.name}已经不是先前那样。`;
        else if (detail) sentence = ensurePeriod(detail);
        else sentence = `${item.name}动过了。`;
        // An unchanged object is static texture. Once the reader has had that
        // sentence, repeating it every quiet turn is a house stamp.
        const staticItem = beat.change === undefined && !beat.factText && !beat.discovered;
        if (staticItem && seenText && echoOfPrior(sentence, seenText) > 0.72) break;
        pushBeat(sentence, beat);
        // A "look at the thing" line after the thing was just described reads
        // as filler, and repeating it every turn is the kind of house stamp
        // the product complains about. Only add it when the item line itself
        // does not already name the item in the same turn.
        const alreadyNamed = units.some((unit) => unit.text.includes(item.name))
          || (scene.priorText?.includes(item.name) ?? false);
        if (policy.allowMinorAction !== false && detail && minorLooks === 0
          && !alreadyNamed && rng() < 0.35) {
          const protagonist = actorOf(scene, scene.protagonistId);
          if (protagonist && protagonist.id !== beat.itemId) {
            const look = templates.pick('item-look', [
              `${refs.subject(protagonist.id)}看了一眼${item.name}。`,
              `${refs.subject(protagonist.id)}把目光落到${item.name}上。`,
            ]);
            push(look, []);
            minorLooks += 1;
          }
        }
        break;
      }
      case 'task': {
        const actor = actorOf(scene, beat.actorId);
        if (!actor) break;
        if (beat.factText) {
          pushBeat(ensurePeriod(fillSlots(beat.factText, nameMap(scene), beat.actorId)), beat);
        } else {
          const name = refs.name(actor.id);
          const label = beat.label;
          // Always the full name: a pronoun right after another speaker's line
          // reads as that speaker, not as the task owner.
          const quoted = `「${normalizeClause(label)}」`;
          const variants = [
            `${quoted}，${name}做完了。`,
            `${name}把${quoted}这件事办完了。`,
            `${quoted}这件事，${name}收了尾。`,
          ];
          pushBeat(templates.pick('task', variants), beat);
        }
        break;
      }
      case 'subtask': {
        const actor = actorOf(scene, beat.actorId);
        if (!actor) break;
        if (beat.factText) {
          pushBeat(ensurePeriod(fillSlots(beat.factText, nameMap(scene), beat.actorId)), beat);
        } else {
          const name = refs.name(actor.id);
          const goal = normalizeClause(beat.goal);
          pushBeat(templates.pick('subtask', [
            `${name}记下一条：${goal}。`,
            `${name}还有下一件事：${goal}。`,
          ]), beat);
        }
        break;
      }
      case 'personality': {
        const actor = actorOf(scene, beat.actorId);
        if (!actor) break;
        const text = normalizeClause(beat.factText ?? beat.text);
        const filled = fillSlots(text, nameMap(scene), beat.actorId);
        const named = filled.startsWith(refs.name(actor.id)) || /^[他她]/u.test(filled)
          ? filled
          : `${refs.name(actor.id)}${filled}`;
        // A paragraph that is only the settled personality sentence reads like
        // a status panel (01's complaint). When nothing else happened, the
        // place is a licensed anchor that keeps it in the scene. Stuffing a
        // second scenery clause here was tried and read worse than the panel
        // ("但要同时暴露给两边的窗口，路明非..."), so the place alone is used.
        const mentalOnly = body.every((entry) => entry.kind === 'time' || entry.kind === 'scene'
          || entry.kind === 'personality' || entry.kind === 'sanity');
        const place = scene.location.name;
        const anchored = mentalOnly && place && !named.startsWith(place)
          ? `${place}里，${named}`
          : named;
        pushBeat(ensurePeriod(anchored), beat);
        break;
      }
      case 'appearance': {
        const subject = beat.subjectName;
        if (!subject) break;
        if (beat.removed) {
          const old = normalizeClause(beat.previous ?? beat.text);
          pushBeat(old
            ? ensurePeriod(templates.pick('appearance-removed', [
              `${subject}不再像先前那样${old}`,
              `${subject}身上，${old}的样子没有了`,
            ]))
            : `${subject}身上先前那点变化淡了。`, beat);
        } else {
          const text = normalizeClause(beat.factText ?? beat.text);
          if (!text) break;
          const named = text.startsWith(subject) || /^[他她]/u.test(text);
          const variants = named
            ? [text]
            : beat.entityKind === 'character'
              ? [`${subject}身上，${text}`]
              : [`${subject}${text}`, `${subject}的样子变了：${text}`];
          pushBeat(ensurePeriod(templates.pick('appearance', variants)), beat);
        }
        break;
      }
      case 'sanity': {
        const actor = actorOf(scene, beat.actorId);
        if (!actor) break;
        // Equal endpoints mean the record carries no change; narrating it
        // would invent an event out of a non-event.
        if (beat.to === beat.from) break;
        const down = beat.to < beat.from;
        // Two actors can lose sanity in the same point; keying the variant by
        // actor id keeps their sentences from being word-for-word identical.
        const variants = down
          ? [
            `${refs.subject(actor.id)}的呼吸紧了一下。`,
            `${refs.subject(actor.id)}把手指收紧了。`,
            `${refs.subject(actor.id)}把话咽了回去，喉咙发紧。`,
          ]
          : beat.to > beat.from
            ? [
              `${refs.subject(actor.id)}松了口气。`,
              `${refs.subject(actor.id)}的呼吸稳下来。`,
              `${refs.subject(actor.id)}的肩膀松了些。`,
            ]
            : [`${refs.subject(actor.id)}照旧。`];
        const salt = hash32(`${scene.seed ?? 0}|${beat.actorId}|${down ? 'down' : beat.to > beat.from ? 'up' : 'flat'}`);
        // The same cue at two points reads as a stamp; drop anything the
        // session already read before picking.
        const fresh = seenText ? variants.filter((variant) => !seenText.includes(variant)) : variants;
        const pool = fresh.length ? fresh : variants;
        const sentence = beat.factText
          ? ensurePeriod(fillSlots(beat.factText, nameMap(scene), beat.actorId))
          : pool[salt % pool.length];
        pushBeat(sentence, beat);
        break;
      }
      case 'action': {
        const actor = actorOf(scene, beat.actorId);
        if (!actor) break;
        const text = fillSlots(beat.text, nameMap(scene), beat.actorId);
        for (const sentence of splitSentences(text)) {
          if (scene.priorText && echoOfPrior(sentence, scene.priorText) > 0.82) continue;
          pushBeat(ensurePeriod(sentence), beat);
        }
        break;
      }
      case 'line': {
        const speaker = actorOf(scene, beat.speakerId);
        if (!speaker) break;
        const raw = stripQuotes(beat.text);
        const parts = splitSentences(raw);
        const question = /[？?]$/u.test(parts[parts.length - 1] ?? raw);
        let paragraph = `「${raw}」`;
        let taggedByPause = false;
        if (lastQuestion && lastSpeaker !== beat.speakerId && policy.allowMinorAction !== false && rng() < 0.6) {
          const pause = templates.pick('answer-pause', [
            `${refs.name(beat.speakerId)}没有立刻答。`,
            `${refs.name(beat.speakerId)}停了停。`,
            `${refs.name(beat.speakerId)}想了一会儿。`,
          ]);
          push(pause, []);
          taggedByPause = true;
        }
        const speakerChanges = lastSpeaker !== beat.speakerId;
        if (speakerChanges && !taggedByPause) {
          const tagSubject = refs.subject(speaker.id);
          const questionTag = question || /[？?]$/u.test(parts[0] ?? '');
          const tag = templates.pick(
            questionTag ? 'line-tag-question' : 'line-tag',
            questionTag ? [`${tagSubject}问`] : [`${tagSubject}说`, `${tagSubject}开口`],
          );
          paragraph = parts.length > 1 && charCount(raw) <= 70
            ? `「${parts[0]}」${tag}，「${parts.slice(1).join('')}」`
            : `「${raw}」${tag}。`;
        } else if (parts.length > 1 && charCount(raw) <= 70) {
          paragraph = `「${parts[0]}」${refs.subject(speaker.id)}又说，「${parts.slice(1).join('')}」`;
        }
        pushBeat(paragraph, beat);
        lastSpeaker = beat.speakerId;
        lastQuestion = question;
        break;
      }
      case 'silence': {
        const sentence = beat.actorId && actorOf(scene, beat.actorId)
          ? templates.pick('silence-one', [
            `${refs.name(beat.actorId)}没有回答。`,
            `${refs.name(beat.actorId)}没有说话。`,
          ])
          : templates.pick('silence', ['没有人接话。', '谁也没有再开口。']);
        pushBeat(sentence, beat);
        break;
      }
      case 'time': {
        let exact = beat.text ?? null;
        if (!exact && policy.requireTime && beat.amount) {
          const amount = numberToChinese(beat.amount);
          const unit = unitName(beat.unit ?? 'minute');
          const forms = [
            `过了${amount}${unit}。`, `${amount}${unit}过去。`, `${amount}${unit}之后。`,
            `又过了${amount}${unit}。`, `${amount}${unit}过去了。`, `再过${amount}${unit}。`,
          ];
          exact = forms[hash32(`${scene.seed ?? 0}|${scene.pointId ?? ''}|time|${beat.amount}|${beat.unit ?? 'minute'}`) % forms.length];
        }
        pushBeat(exact ?? '过了一会儿。', beat);
        break;
      }
      case 'noChange': {
        pushBeat(beat.text ? ensurePeriod(beat.text) : '没有人动。', beat);
        break;
      }
      default:
        break;
    }
    if (units.length === before) continue;
    // Avoid two paragraphs opening with the same name/subject.
    if (units.length >= 2) {
      const current = units[units.length - 1];
      const previous = units[units.length - 2];
      if (!current.text.startsWith('「') && paragraphStart(current.text) === paragraphStart(previous.text)) {
        const merger = previous.text.endsWith('。') ? `${previous.text}${current.text}` : `${previous.text} ${current.text}`;
        previous.text = merger;
        units.pop();
      }
    }
  }

  // No extra "still there" object line is appended here. A settled object is
  // already offered as texture by the scene builder; a second one would be the
  // inventory tone, and repeating it every turn is a house stamp.
  if (!beatOnly) {

  // If only one cast member remains in the scene, say so once. This is a
  // consequence of the supplied moves, not an assumption about off-screen NPCs.
  const gone = new Set<string>();
  for (const beat of scene.beats ?? []) {
    if (beat.kind === 'move' && beat.to !== scene.location.name) gone.add(beat.actorId);
    if (beat.kind === 'leave') gone.add(beat.actorId);
  }
  const remaining = scene.cast.filter((actor) => !gone.has(actor.id));
  if (gone.size > 0 && remaining.length === 1 && units.length) {
    const only = remaining[0];
    // The stay paragraph is redundant once the scene says only one is left.
    const redundant = (unit: Unit) => unit.beats.some((beat) => beat.kind === 'stay' && beat.actorId === only.id);
    if (units.some(redundant)) {
      const keep = units.filter((unit) => !redundant(unit));
      units.length = 0;
      units.push(...keep);
    }
    const named = `${scene.location.name}里只剩${only.name}一个人。`;
    // Do not name the place twice in a row: if the previous paragraph already
    // said it (e.g. "她出了西侧服务巷"), the shorter line reads better.
    const lastText = units[units.length - 1]?.text ?? '';
    const onlyLine = lastText.includes(scene.location.name)
      ? `${only.name}一个人留在原地。`
      : named;
    const alreadySaid = units.some((unit) => unit.text.includes(onlyLine.slice(0, 6)))
      || (scene.priorText?.includes(onlyLine.slice(0, 6)) ?? false);
    if (!alreadySaid) push(onlyLine, []);
  }
  }

  // If the skeleton carried no body at all, the anchor is still a valid
  // static description; a fully empty scene is an explicit failure.
  if (!units.length) {
    issues.push({ kind: 'empty_scene', severity: 'hard', detail: 'no beat or anchor produced a paragraph' });
  }

  const planMs = bodyStart - planStart;

  // Guard every paragraph, then merge the survivors.
  const kept: string[] = [];
  for (const unit of units) {
    const { clean, findings } = guardParagraph(unit.text, license);
    for (const finding of findings) {
      issues.push({ kind: finding.kind, severity: 'hard', detail: finding.detail, sentence: finding.sentence });
    }
    if (!clean) continue;
    const echo = echoOfPrior(clean, scene.priorText ?? null);
    if (echo > 0.72) {
      issues.push({ kind: 'echo_prior', severity: 'hard', detail: `overlap ${echo.toFixed(2)} with previous turn`, sentence: clean });
      continue;
    }
    kept.push(clean);
  }

  // A paragraph may be split further if it grew too long for the house style.
  const paragraphs: string[] = [];
  for (const paragraph of kept) {
    if (charCount(paragraph) <= 120) {
      paragraphs.push(paragraph);
      continue;
    }
    const sentences = splitSentences(paragraph);
    let bucket = '';
    for (const sentence of sentences) {
      if (bucket && charCount(bucket) + charCount(sentence) > 70) {
        paragraphs.push(bucket);
        bucket = '';
      }
      bucket += sentence;
    }
    if (bucket) paragraphs.push(bucket);
  }

  const varied = beatOnly ? paragraphs : varyRepeatedSubjects(paragraphs, scene, refs);
  const merged = beatOnly ? varied : mergeShortNarration(varied, scene);
  const text = merged.join('\n\n');
  const verifyMs = nowMs();
  const factIssues = verifyBeats(scene, body, rendered);
  issues.push(...factIssues);
  const quiet = (scene.beats ?? []).every((beat) => beat.kind === 'noChange' || beat.kind === 'time'
    || beat.kind === 'stay' || beat.kind === 'silence');
  // A turn that settled nothing but the clock has nothing else to say. Telling
  // it in one short sentence is complete, not padded; a length target must not
  // push the composer into inventing an action.
  const spoken = rendered.filter((entry) => entry.paragraph >= 0);
  const timeOnly = !beatOnly && spoken.length > 0 && spoken.every((entry) => entry.beat.kind === 'time');
  const minChars = timeOnly ? 4 : clampInt(policy.minChars ?? 60, quiet ? 8 : 12, 4000);
  if (timeOnly) {
    issues.push({ kind: 'time_only', severity: 'soft', detail: 'the turn settled only elapsed time' });
  }
  if (!beatOnly && charCount(text) < minChars) {
    issues.push({ kind: 'too_short', severity: 'hard', detail: `${charCount(text)} < ${minChars}` });
  }
  const accepted = issues.every((issue) => issue.severity !== 'hard') && paragraphCount(text) > 0;
  const totalMs = nowMs();

  return {
    text,
    paragraphs: merged,
    opening: merged[0] ?? '',
    closing: lastSentence(merged[merged.length - 1] ?? ''),
    strategyVersion: PROSE_STRATEGY_VERSION,
    beats: rendered,
    derivedDialogue: [],
    issues,
    accepted,
    timings: { planMs, composeMs: verifyMs - bodyStart, verifyMs: totalMs - verifyMs, totalMs },
  };
}

function paragraphCount(text: string): number {
  return text.split(/\n{2,}/).filter((part) => part.trim()).length;
}

/** Merge two short narration paragraphs when they share a scene block. Quotes,
 * time cues and repeated-name pairs stay separate, which keeps the rhythm of
 * the source prose instead of producing one paragraph per fact. */
/** A paragraph that opens with the same name as the one before it reads like a
 * list. Replace the second mention with a pronoun when the cast makes that
 * pronoun unambiguous; otherwise keep the name. */
function varyRepeatedSubjects(paragraphs: string[], scene: ProseScene, refs: Referencer): string[] {
  const byLength = [...scene.cast].sort((left, right) => right.name.length - left.name.length);
  let lastSubject: string | null = null;
  return paragraphs.map((paragraph) => {
    if (paragraph.startsWith('「')) return paragraph;
    const lead = byLength.find((actor) => paragraph.startsWith(actor.name));
    if (!lead) return paragraph;
    const replacement = lead.name === lastSubject ? refs.reference(lead.id) : lead.name;
    lastSubject = lead.name;
    if (replacement === lead.name || charCount(paragraph) <= 6) return paragraph;
    return `${replacement}${paragraph.slice(lead.name.length)}`;
  });
}

function mergeShortNarration(paragraphs: string[], scene: ProseScene): string[] {
  const placeNames = [scene.location.name, scene.parentLocation?.name].filter((name): name is string => Boolean(name));
  const startsWithPlace = (text: string) => placeNames.some((name) => text.startsWith(name));
  const startsWithPronoun = (text: string) => /^[他她]/u.test(text);
  const countSentences = (text: string) => splitSentences(text).length;
  const merged: string[] = [];
  let merges = 0;
  for (const paragraph of paragraphs) {
    const previous = merged[merged.length - 1];
    const canMerge = Boolean(previous) && merges < 2
      && !previous.startsWith('「') && !paragraph.startsWith('「')
      && charCount(previous) + charCount(paragraph) <= 76
      && countSentences(previous) + countSentences(paragraph) <= 3
      && (startsWithPronoun(paragraph) || startsWithPlace(paragraph))
      // "还在西侧服务巷。" followed by "西侧服务巷里，…" is a stutter; keep the
      // place named once and let the detail stand as its own beat.
      && !placeNames.some((name) => previous.includes(name) && paragraph.startsWith(name));
    if (canMerge) {
      merged[merged.length - 1] = previous + paragraph;
      merges += 1;
    } else {
      merged.push(paragraph);
    }
  }
  // A bare time line reads better as the start of the next action than as its
  // own paragraph: "过了五分钟，路明非走进器材棚。"
  const out: string[] = [];
  for (let index = 0; index < merged.length; index += 1) {
    const current = merged[index];
    const next = merged[index + 1];
    const bareTime = /^(?:又?过了)?[零一二两三四五六七八九十百\d]+(?:分钟|秒|个小时|天|个月|年)(?:过去|之后)?。$/u.test(current);
    // A quoted task label is not dialogue: "过了三分钟，「…」，路明非做完了。"
    const quotedTask = Boolean(next && next.startsWith('「')
      && /^「[^」]{1,60}」.{0,8}(?:做完了|办完了|收了尾)/u.test(next));
    if (bareTime && next && (!next.startsWith('「') || quotedTask)
      && charCount(current) + charCount(next) <= 80) {
      out.push(`${current.slice(0, -1)}，${next}`);
      index += 1;
    } else {
      out.push(current);
    }
  }
  return out;
}
function nameMap(scene: ProseScene): Map<string, string> {
  return new Map(scene.cast.map((actor) => [actor.id, actor.name]));
}

const CN_NUMBERS = ['零', '一', '两', '三', '四', '五', '六', '七', '八', '九', '十'];

function numberToChinese(value: number): string {
  const rounded = Math.max(0, Math.round(value));
  if (rounded <= 10) return CN_NUMBERS[rounded];
  if (rounded < 20) return `十${CN_NUMBERS[rounded - 10]}`;
  if (rounded < 60) {
    const tens = Math.floor(rounded / 10);
    const units = rounded % 10;
    return `${CN_NUMBERS[tens]}十${units ? CN_NUMBERS[units] : ''}`;
  }
  return String(rounded);
}

function unitName(unit: string): string {
  if (unit === 'second') return '秒';
  if (unit === 'hour') return '个小时';
  if (unit === 'day') return '天';
  if (unit === 'month') return '个月';
  if (unit === 'year') return '年';
  return '分钟';
}

function emptyResult(scene: ProseScene, issues: ProseIssue[], started: number): ComposedProse {
  const total = nowMs() - started;
  return {
    text: '',
    paragraphs: [],
    opening: '',
    closing: '',
    strategyVersion: PROSE_STRATEGY_VERSION,
    beats: [],
    derivedDialogue: [],
    issues: issues.length ? issues : [{ kind: 'empty_scene', severity: 'hard', detail: 'cast is empty' }],
    accepted: false,
    timings: { planMs: 0, composeMs: 0, verifyMs: 0, totalMs: total },
  };
}

/** Confirm every mandatory beat reached the final text with its core tokens. */
function verifyBeats(
  scene: ProseScene,
  beats: ProseBeat[],
  rendered: RenderedBeat[],
): ProseIssue[] {
  const issues: ProseIssue[] = [];
  const byBeat = new Map(rendered.map((entry) => [entry.beat, entry]));
  const names = nameMap(scene);
  for (const beat of beats) {
    if (!isRequired(beat)) continue;
    const entry = byBeat.get(beat);
    if (!entry || !entry.sentence) {
      // Scene texture may be dropped as an echo; a flat sanity record carries
      // no change to narrate. Neither loses a settled fact.
      if (beat.kind !== 'scene' && beat.kind !== 'sanity') {
        issues.push({ kind: 'beat_unrendered', severity: 'hard', detail: `beat ${beat.kind} was not rendered` });
      }
      continue;
    }
    const sentence = entry.sentence;
    const checks: Array<{ token: string; label: string }> = [];
    switch (beat.kind) {
      case 'move':
        checks.push({
          token: names.get(beat.actorId) ?? itemOf(scene, beat.actorId)?.name
            ?? beat.actorName ?? beat.actorId,
          label: 'actor',
        });
        checks.push({ token: beat.to, label: 'destination' });
        if (!sentence.includes(beat.to) && !sentence.includes(beat.factText ?? '\u0000')) {
          issues.push({ kind: 'fact_token_missing', severity: 'hard', detail: `move destination ${beat.to} missing`, sentence });
        }
        {
          const fromIndex = sentence.indexOf(beat.from);
          const toIndex = sentence.indexOf(beat.to);
          if (fromIndex >= 0 && toIndex >= 0 && toIndex < fromIndex) {
            issues.push({ kind: 'direction_reversed', severity: 'hard', detail: `${beat.from} -> ${beat.to} rendered backwards`, sentence });
          }
        }
        break;
      case 'task':
        checks.push({
          token: (beat.factText ?? beat.label).slice(0, Math.min(6, (beat.factText ?? beat.label).length)),
          label: 'task label',
        });
        break;
      case 'item': {
        const detail = beat.detail ?? beat.factText;
        if (detail) checks.push({ token: firstClause(detail).slice(0, 4), label: 'item detail' });
        break;
      }
      case 'personality':
        checks.push({ token: (beat.factText ?? beat.text).slice(0, 4), label: 'personality text' });
        break;
      case 'subtask':
        checks.push({ token: (beat.factText ?? beat.goal).slice(0, 4), label: 'subtask goal' });
        break;
      case 'appearance': {
        const needle = beat.removed ? beat.previous ?? beat.text : beat.factText ?? beat.text;
        if (needle) checks.push({ token: firstClause(needle).slice(0, 4), label: 'appearance text' });
        break;
      }
      case 'action':
        checks.push({ token: beat.text.replace(/\{[^}]+\}/gu, '').slice(0, 4), label: 'action text' });
        break;
      case 'line':
        checks.push({ token: stripQuotes(beat.text).slice(0, 4), label: 'line text' });
        break;
      case 'scene':
        // Scene texture is optional: an echoed or surplus detail may be
        // dropped without losing a settled fact.
        break;
      case 'stay':
        checks.push({ token: names.get(beat.actorId) ?? beat.actorId, label: 'actor' });
        break;
      case 'sanity':
        break;
      default:
        break;
    }
    for (const check of checks) {
      if (!sentence.includes(check.token)) {
        issues.push({ kind: 'fact_token_missing', severity: 'hard', detail: `${check.label} ${check.token} missing`, sentence });
      }
    }
  }
  return issues;
}
