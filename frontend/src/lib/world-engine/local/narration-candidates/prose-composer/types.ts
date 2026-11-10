/** Input/output contract of the prose composer.
 *
 * The composer is the language layer of route C: lane 04 builds a read-only
 * fact skeleton from the visible projection and committed changes; this module
 * turns that skeleton into readable paragraphs. It never writes world state,
 * never invents events and never needs a model call.
 *
 * Facts are supplied as structured beats (move/task/item/line/...) plus
 * optional faithful `factText` clauses. The composer owns order, reference,
 * rhythm, scene anchoring, dialogue spacing and continuity. Anything not in
 * `scene` is unlicensed: no new props, weather, people, memories, clues or
 * promises.
 */

export type ProseGender = 'male' | 'female' | 'unknown';

export interface ProseActor {
  id: string;
  /** Display name. The composer never prints ids. */
  name: string;
  /** Optional; when omitted the composer repeats the name instead of guessing. */
  gender?: ProseGender;
  /** Explicit reference forms in preference order, e.g. ['她', '诺诺']. Only
   * used after the first full-name mention. */
  references?: string[];
  /** Existing appearance details, licensed for physical description. */
  appearance?: string[];
  isProtagonist?: boolean;
}

export interface ProseLocation {
  id?: string;
  name: string;
  parentName?: string | null;
  /** Appearance details of this small location. Licensed verbatim. */
  details?: string[];
}

export interface ProseItem {
  id: string;
  name: string;
  /** Appearance details, licensed verbatim. */
  details?: string[];
  positionName?: string | null;
}

export type ProseBeat =
  /** A scene detail that changed (or is newly visible). */
  | { kind: 'scene'; detail: string; locationId?: string; factText?: string }
  /** Explicit spatial move; direction is from -> to and must not reverse. */
  | {
    kind: 'move'; actorId: string; from: string; to: string; manner?: string; factText?: string;
    /** Items move too; they are not cast members. */
    entityKind?: 'character' | 'item';
  }
  /** An actor keeps their position while others move. */
  | { kind: 'stay'; actorId: string; location?: string; factText?: string }
  /** Leaves the visible scene; `to` is optional and may be a parent area. */
  | { kind: 'leave'; actorId: string; to?: string; factText?: string }
  /** Enters the visible scene without a known origin. */
  | { kind: 'arrive'; actorId: string; location?: string; factText?: string }
  /** Item appearance/state change. `detail` is the new licensed appearance. */
  | {
    kind: 'item'; itemId: string; change?: 'added' | 'removed' | 'modified';
    detail?: string; container?: string; note?: string; discovered?: boolean; factText?: string;
  }
  /** A task (or subtask) reached `achieved`. `label` should be the short goal. */
  | { kind: 'task'; actorId: string; label: string; scope?: 'main' | 'sub'; factText?: string }
  /** A new task was recorded; it is not complete. */
  | { kind: 'subtask'; actorId: string; goal: string; parentGoal?: string; factText?: string }
  /** Personality change; `text` is the licensed new trait sentence. */
  | { kind: 'personality'; actorId: string; text: string; factText?: string }
  /** Appearance/state detail of a character, item or location. `subjectName`
   * is used when the subject is not in the cast (an item or the room itself). */
  | {
    kind: 'appearance'; subjectName: string; text: string; entityKind?: 'character' | 'item' | 'location';
    removed?: boolean; previous?: string; factText?: string;
  }
  /** Sanity change. Numbers are never printed as a status report. */
  | { kind: 'sanity'; actorId: string; from: number; to: number; factText?: string }
  /** A licensed action clause. `text` may use {name} / {actor:ID} slots. */
  | { kind: 'action'; actorId: string; text: string }
  /** Licensed dialogue. `text` is the spoken content, without 「」. */
  | { kind: 'line'; speakerId: string; text: string; addresseeId?: string }
  /** A beat where nobody answers or moves. */
  | { kind: 'silence'; actorId?: string }
  /** Elapsed time. `text` overrides the generated phrase. */
  | { kind: 'time'; amount?: number; unit?: 'minute' | 'second' | 'hour' | 'day' | 'month' | 'year'; text?: string }
  /** Explicitly nothing changed; used for no-change points. */
  | { kind: 'noChange'; text?: string };

export interface ProsePolicy {
  /** Derived Q/A about a licensed change. Default true. Never adds new info. */
  deriveDialogue?: boolean;
  /** Allow unregistered micro-actions (a glance, a pause). Default true. */
  allowMinorAction?: boolean;
  /** Length floor; below it `accepted` is false. Default 90. */
  minChars?: number;
  /** Soft ceiling; paragraphs beyond it are dropped. Default 900. */
  maxChars?: number;
  /** Print the exact elapsed duration when a time beat exists. Default false. */
  requireTime?: boolean;
  /** Protagonist viewpoint by default. neutral = no inferred interiority. */
  perspective?: 'protagonist' | 'neutral';
  seed?: number;
  /** Render only the supplied beats; no scene anchor, post-pass or paragraph
   * merging. Used by lane 04's per-beat composer contract. */
  beatOnly?: boolean;
}

export interface ProseScene {
  worldId?: string;
  pointId?: string;
  protagonistId: string;
  location: ProseLocation;
  /** Changes to the location itself this turn, already projected. */
  locationChange?: { added?: string[]; removed?: string[] };
  parentLocation?: ProseLocation | null;
  cast: ProseActor[];
  items?: ProseItem[];
  beats: ProseBeat[];
  /** Previous accepted prose. Used only to avoid repeating its openings and
   * sentences; facts already told there should not be supplied as beats. */
  priorText?: string | null;
  /** Short human labels for facts already told, to avoid restating them. */
  toldFacts?: string[];
  policy?: ProsePolicy;
  seed?: number;
}

export type ProseIssueKind =
  | 'beat_unrendered'
  | 'fact_token_missing'
  | 'direction_reversed'
  | 'unlicensed_detail'
  | 'unlicensed_past'
  | 'unlicensed_promise'
  | 'stock_phrase'
  | 'echo_prior'
  | 'too_short'
  | 'unknown_reference'
  | 'unmapped_fact'
  | 'empty_scene';

export interface ProseIssue {
  kind: ProseIssueKind;
  severity: 'hard' | 'soft';
  detail: string;
  sentence?: string;
}

export interface RenderedBeat {
  beat: ProseBeat;
  /** Index of the paragraph that carries this beat, or -1 if omitted. */
  paragraph: number;
  /** The exact sentence fragment used for the beat. */
  sentence: string | null;
}

export interface ComposeTimings {
  planMs: number;
  composeMs: number;
  verifyMs: number;
  totalMs: number;
}

export interface ComposedProse {
  text: string;
  paragraphs: string[];
  opening: string;
  closing: string;
  strategyVersion: string;
  beats: RenderedBeat[];
  derivedDialogue: string[];
  issues: ProseIssue[];
  /** Programmatic fact/guard verification. Human reading quality is separate. */
  accepted: boolean;
  timings: ComposeTimings;
}
