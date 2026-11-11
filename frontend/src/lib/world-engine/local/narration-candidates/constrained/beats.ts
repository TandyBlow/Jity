/** Fact -> beat plan.
 *
 * A beat is the verification unit: it declares which settled facts it must
 * express, which licensed details it may use, which names it must contain and
 * how long it may be. The planner only orders and groups facts; it never
 * invents one.
 */
import type { Id } from '../../../types';
import type { BeatDirective, BeatPlan, SceneFact, SceneSkeleton } from './types';

export interface BeatPlanOptions {
  /** Include facts the viewpoint cannot perceive (default false). */
  narrateHiddenDeltas?: boolean;
  maxBeats?: number;
  seed?: number;
  /** Minimum length per beat. */
  minChars?: number;
  maxChars?: number;
  /** Let fact-carrying beats include the scene texture instead of spending
   * separate model calls on an opening, texture and closing with no facts. */
  combineSceneMaterial?: boolean;
}

const DEFAULT_MIN = 22;
const DEFAULT_MAX = 150;

/** Stable 32-bit hash; the same point/beat always draws the same variant, and
 * different points draw different ones. */
export function hashSeed(...parts: (string | number | null | undefined)[]): number {
  let hash = 2166136261;
  for (const part of parts) {
    const text = String(part ?? '');
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    hash ^= 0x9e3779b9;
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function planBeats(scene: SceneSkeleton, options: BeatPlanOptions = {}): BeatPlan {
  const narrateHidden = options.narrateHiddenDeltas === true;
  const minChars = options.minChars ?? DEFAULT_MIN;
  const maxChars = options.maxChars ?? DEFAULT_MAX;
  const seed = options.seed ?? 0;
  const combineSceneMaterial = options.combineSceneMaterial === true;
  const maxBeats = Math.max(2, options.maxBeats ?? 6);
  const visible = scene.facts.filter((fact) => fact.visibility === 'scene' || narrateHidden);
  const hiddenFactIds = scene.facts.filter((fact) => fact.visibility === 'hidden' && !narrateHidden).map((fact) => fact.id);

  const mandatory = visible.filter((fact) => fact.mandatory);
  const optional = visible.filter((fact) => !fact.mandatory);
  const time = mandatory.find((fact) => fact.kind === 'time') ?? null;
  const moves = mandatory.filter((fact) => fact.kind === 'move') as Extract<SceneFact, { kind: 'move' }>[];
  const rest = mandatory.filter((fact) => fact.kind !== 'time' && fact.kind !== 'move');

  const beats: BeatDirective[] = [];
  const push = (beat: Omit<BeatDirective, 'index' | 'seed' | 'minChars' | 'maxChars'> & { seed?: number }) => {
    beats.push({
      ...beat,
      index: beats.length,
      seed: beat.seed ?? hashSeed(scene.anchor.pointId, beat.id, seed),
      minChars: beat.factIds.length ? minChars : Math.min(minChars, 12),
      // The budget follows the material. One fact is one or two sentences: the
      // reference corpus's median scene is 97 chars and 3 sentences, while the
      // 11a7/4794 quiet turn produced 256-502 chars over four beats that carried
      // one time fact between them. A beat with no fact gets one short sentence;
      // three or more facts keep the large budget so a rich turn is not thinned.
      maxChars: beat.factIds.length > 2
        ? Math.round(maxChars * 1.6)
        : combineSceneMaterial ? maxChars
          : beat.factIds.length === 1 ? Math.round(maxChars * 0.55) : Math.min(maxChars, 32),
    });
  };

  // 1. Opening: place + elapsed time.
  if (!combineSceneMaterial || time || mandatory.length === 0) {
    push({
      id: 'open',
      kind: 'open',
      subject: { id: scene.viewpoint.id, name: scene.viewpoint.name, viewpoint: true },
      factIds: time ? [time.id] : [],
      details: placeDetails(scene),
      mustMention: [scene.viewpoint.name],
    });
  }

  // 2. The viewpoint's own move comes first: it re-anchors the scene.
  const viewpointMove = moves.find((fact) => fact.viewpoint);
  if (viewpointMove) {
    push({
      id: `move:${viewpointMove.entityId}`,
      kind: 'move',
      subject: { id: viewpointMove.entityId, name: viewpointMove.name, viewpoint: true },
      factIds: [viewpointMove.id],
      details: [scene.place.note, scene.viewpoint.note].filter(Boolean),
      mustMention: [viewpointMove.from, viewpointMove.to],
    });
  }

  // 3. Other moves, grouped two at a time so a busy point stays readable.
  const otherMoves = moves.filter((fact) => !fact.viewpoint);
  for (let index = 0; index < otherMoves.length; index += 2) {
    const group = otherMoves.slice(index, index + 2);
    push({
      id: `move:${group.map((fact) => fact.entityId).join('+')}`,
      kind: 'move',
      subject: group.length === 1 ? { id: group[0].entityId, name: group[0].name, viewpoint: false } : null,
      factIds: group.map((fact) => fact.id),
      details: [],
      mustMention: [...new Set(group.flatMap((fact) => [fact.from, fact.to]))],
    });
  }

  // 4. Settled events, grouped by subject: a task and its personality/sanity
  // consequence read as one turn of the same person.
  const bySubject = new Map<Id, SceneFact[]>();
  for (const fact of rest) {
    const subject = 'ownerId' in fact ? fact.ownerId : 'entityId' in fact ? fact.entityId : '';
    const list = bySubject.get(subject) ?? [];
    list.push(fact);
    bySubject.set(subject, list);
  }
  const eventSubjects = [...bySubject.keys()].sort((left, right) => {
    const leftViewpoint = left === scene.viewpoint.id ? 0 : 1;
    const rightViewpoint = right === scene.viewpoint.id ? 0 : 1;
    return leftViewpoint - rightViewpoint || left.localeCompare(right);
  });
  for (const subject of eventSubjects) {
    const facts = bySubject.get(subject)!;
    const name = 'name' in facts[0] ? facts[0].name : scene.viewpoint.name;
    const viewpoint = subject === scene.viewpoint.id;
    const subjectRef = { id: subject, name, viewpoint };
    // Split one busy actor into small beats so a writer that drops one fact
    // only loses that beat, not the whole turn's wording. Order inside a turn:
    // what is visible -> what was done -> what changed inside.
    const groups: { suffix: string; facts: SceneFact[] }[] = [
      { suffix: 'look', facts: facts.filter((fact) => fact.kind === 'appearance_changed') },
      { suffix: 'did', facts: facts.filter((fact) => fact.kind === 'task_achieved' || fact.kind === 'subtask_added') },
      { suffix: 'inside', facts: facts.filter((fact) => fact.kind === 'personality_changed' || fact.kind === 'sanity_changed') },
    ];
    for (const group of groups) {
      if (!group.facts.length) continue;
      push({
        id: `event:${subject}:${group.suffix}`,
        kind: 'event',
        subject: subjectRef,
        factIds: group.facts.map((fact) => fact.id),
        details: group.facts.flatMap(factDetails),
        mustMention: [name],
      });
    }
  }

  // 5. Scene texture: existing objects. Optional facts only; never a new prop.
  const sceneFacts = optional.filter((fact) => fact.kind === 'item_discovered' || fact.kind === 'item_present');
  const hasTexture = scene.hasSceneMaterial && (scene.present.length > 0 || scene.objects.length > 0 || sceneFacts.length > 0);
  if (hasTexture && !combineSceneMaterial) {
    const chosen = sceneFacts.slice(0, 2);
    push({
      id: 'scene',
      kind: 'scene',
      subject: null,
      factIds: chosen.map((fact) => fact.id),
      details: chosen.map((fact) => ('note' in fact ? fact.note : '')).filter(Boolean),
      mustMention: chosen.map((fact) => fact.name),
    });
  }

  // 6. The settlement's result line, in the caller's own words. It is not
  // optional: dropping it loses the answer the player just read.
  const resultFact = visible.find((fact) => fact.kind === 'result');
  if (resultFact) {
    push({
      id: 'result',
      kind: 'result',
      subject: null,
      factIds: [resultFact.id],
      details: [],
      mustMention: [],
    });
  }

  // 7. Closing: a grounded micro-action; no new event, prop or promise.
  if (!combineSceneMaterial) {
    push({
      id: 'close',
      kind: 'close',
      subject: { id: scene.viewpoint.id, name: scene.viewpoint.name, viewpoint: true },
      factIds: [],
      details: scene.present.map((person) => person.name),
      mustMention: [],
    });
  }

  // Trim only if the plan exceeds the budget: merge the smallest event beats
  // into their neighbours instead of dropping facts.
  while (beats.length > maxBeats) {
    const candidates = beats
      .map((beat, index) => ({ beat, index }))
      .filter((entry) => entry.beat.id.startsWith('event:') || (entry.beat.kind === 'move' && !entry.beat.subject?.viewpoint))
      .sort((left, right) => left.beat.factIds.length - right.beat.factIds.length);
    const victim = candidates[0];
    if (!victim) break;
    // Only fold a beat into another of the same kind: merging a move into the
    // opening would tell the arrival before the travel, and merging an event
    // into a move would hide which beat carried the task.
    const target = [...beats.slice(0, victim.index)].reverse().find((beat) => beat.kind === victim.beat.kind)
      ?? beats.slice(victim.index + 1).find((beat) => beat.kind === victim.beat.kind);
    if (!target) break;
    target.factIds = [...target.factIds, ...victim.beat.factIds];
    target.details = [...new Set([...target.details, ...victim.beat.details])];
    target.mustMention = [...new Set([...target.mustMention, ...victim.beat.mustMention])];
    target.maxChars = Math.min(320, target.maxChars + victim.beat.maxChars);
    if (target.kind === 'move' && victim.beat.kind === 'move' && victim.beat.subject?.viewpoint) {
      target.subject = victim.beat.subject;
    }
    beats.splice(victim.index, 1);
  }
  beats.forEach((beat, index) => { beat.index = index; });

  return {
    beats,
    hiddenFactIds,
    optionalFactIds: optional.filter((fact) => !beats.some((beat) => beat.factIds.includes(fact.id))).map((fact) => fact.id),
  };
}

function placeDetails(scene: SceneSkeleton): string[] {
  return [scene.place.note, scene.viewpoint.note].filter((text) => typeof text === 'string' && text.length > 0);
}

function factDetails(fact: SceneFact): string[] {
  switch (fact.kind) {
    case 'task_achieved': return [fact.goal];
    case 'subtask_added': return [fact.goal, fact.parentGoal ?? ''].filter(Boolean);
    case 'personality_changed': return [fact.text, ...fact.supersededTexts].filter(Boolean);
    case 'appearance_changed': return [fact.text ?? '', ...fact.supersededTexts].filter(Boolean);
    case 'item_present':
    case 'item_discovered': return [fact.note].filter(Boolean);
    case 'result': return [fact.text];
    default: return [];
  }
}
