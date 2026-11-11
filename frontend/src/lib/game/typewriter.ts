/**
 * Pure, framework-free scheduling for character-by-character narration.
 *
 * The React hook (`useTypewriter`) owns the requestAnimationFrame loop and the
 * React state; this module owns *when* each character is allowed to appear.
 * Keeping the pacing rules here means they can be unit-tested at exact
 * timestamps without a DOM, real timers, or a running browser.
 */

/** Sentence-final marks: the long beat. */
const SENTENCE_END = new Set(["。", "？", "！", "．", ".", "?", "!", "…"]);
/** Clause marks: the short beat that keeps long lines from sounding flat. */
const CLAUSE_END = new Set(["，", "、"]);

export const DEFAULT_CHARS_PER_SECOND = 40;

/**
 * Nominal beats, inside the product bands (sentence 150–250 ms, clause 60–120
 * ms). Every draw is multiplied by 1 ± 30 % so repeated punctuation does not
 * tick like a metronome.
 */
export const SENTENCE_PAUSE_BASE_MS = 200;
export const CLAUSE_PAUSE_BASE_MS = 90;
export const PAUSE_JITTER_RATIO = 0.3;

/**
 * Hard caps. The jitter alone cannot produce a stall (200 ms ± 30 % is
 * 140–260 ms), but a bad injected random or a future base change must still
 * never turn one character into a noticeable freeze.
 */
export const SENTENCE_PAUSE_BOUNDS = { min: 120, max: 300 } as const;
export const CLAUSE_PAUSE_BOUNDS = { min: 40, max: 150 } as const;

export type PauseBounds = { readonly min: number; readonly max: number };
export type RandomSource = () => number;

export function isSentenceEnd(char: string): boolean {
  return SENTENCE_END.has(char);
}

export function isClauseEnd(char: string): boolean {
  return CLAUSE_END.has(char);
}

/**
 * Apply the ±30 % jitter to a base beat and clamp it to its bounds.
 *
 * `random` is injectable so tests can pin both ends of the distribution; a
 * value outside [0, 1] (or NaN) falls back to the neutral draw instead of
 * producing a negative or unbounded pause.
 */
export function jitteredPause(
  baseMs: number,
  random: RandomSource = Math.random,
  bounds: PauseBounds = SENTENCE_PAUSE_BOUNDS,
): number {
  const raw = random();
  const draw = Number.isFinite(raw) ? Math.min(1, Math.max(0, raw)) : 0.5;
  const factor = 1 + (draw * 2 - 1) * PAUSE_JITTER_RATIO;
  return Math.round(Math.min(bounds.max, Math.max(bounds.min, baseMs * factor)));
}

export function sentencePause(random: RandomSource = Math.random): number {
  return jitteredPause(SENTENCE_PAUSE_BASE_MS, random, SENTENCE_PAUSE_BOUNDS);
}

export function clausePause(random: RandomSource = Math.random): number {
  return jitteredPause(CLAUSE_PAUSE_BASE_MS, random, CLAUSE_PAUSE_BOUNDS);
}

export type TypewriterOptions = {
  /** Average reveal speed. Defaults to 40 characters per second. */
  charsPerSecond?: number;
  /** Injectable randomness, so tests can pin the jitter. */
  random?: RandomSource;
};

export type TypewriterFrame = {
  /** Text visible at this instant. */
  text: string;
  /** True once the final character has been revealed. */
  done: boolean;
  /** False when this tick revealed nothing new, so the caller can skip setState. */
  changed: boolean;
};

export class TypewriterEngine {
  private readonly units: string[];
  private readonly random: RandomSource;
  private index = 0;
  private nextAtMs: number | null = null;
  private lastText = "";

  constructor(
    private readonly source: string,
    private readonly options: TypewriterOptions = {},
  ) {
    // Array.from splits by Unicode code point: emoji and other surrogate pairs
    // count as one character instead of two broken halves.
    this.units = Array.from(source);
    this.random = options.random ?? Math.random;
  }

  get total(): number {
    return this.units.length;
  }

  get revealed(): number {
    return this.index;
  }

  get isDone(): boolean {
    return this.index >= this.units.length;
  }

  /**
   * Advance the reveal to `nowMs` (monotonic milliseconds).
   *
   * The first call starts the clock and reveals the first character, so the
   * scene never sits blank waiting for a frame. A large jump in `nowMs`
   * reveals several characters at once, which keeps the animation honest after
   * a dropped frame instead of slowing the whole paragraph down.
   */
  tick(nowMs: number): TypewriterFrame {
    if (this.nextAtMs === null) this.nextAtMs = nowMs;

    while (!this.isDone && nowMs >= this.nextAtMs) {
      const char = this.units[this.index];
      this.index += 1;
      this.nextAtMs += this.delayAfter(char);
    }

    const text = this.units.slice(0, this.index).join("");
    const changed = text !== this.lastText;
    this.lastText = text;
    return { text, done: this.isDone, changed };
  }

  /** Reveal everything immediately (animation disabled or reduced motion). */
  finish(): void {
    this.index = this.units.length;
    this.lastText = this.source;
  }

  private delayAfter(char: string): number {
    const base = 1000 / (this.options.charsPerSecond ?? DEFAULT_CHARS_PER_SECOND);
    const next = this.units[this.index];
    if (isSentenceEnd(char)) {
      // "……" is one beat, not one pause per glyph.
      if (char === "…" && next === "…") return base;
      return base + sentencePause(this.random);
    }
    if (isClauseEnd(char)) return base + clausePause(this.random);
    return base;
  }
}
