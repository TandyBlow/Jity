/** Wall-clock stage timing for the player-visible waiting budget. The page
 * marks coarse stages (action submitted, semantic done, narration started,
 * first readable text, segment complete) and ticks on every streamed chunk;
 * the timer keeps the longest silence between ticks so a stalled decode is
 * visible instead of averaged away. It only measures — it never decides. */
export interface StageMark {
  stage: string;
  /** performance.now-style monotonic timestamp. */
  at: number;
  elapsedMs: number;
  detail?: Record<string, unknown>;
}

export interface StageTimerSnapshot {
  startedAt: number;
  elapsedMs: number;
  /** Longest gap between consecutive marks/ticks, including leading wait. */
  maxGapMs: number;
  marks: StageMark[];
}

export class StageTimer {
  private readonly startedAt: number;
  private marks: StageMark[] = [];
  private lastTickAt: number;
  private maxTickGapMs = 0;

  constructor(private readonly now: () => number = () => performance.now()) {
    this.startedAt = this.now();
    this.lastTickAt = this.startedAt;
  }

  /** Record a named boundary. `detail` stays JSON-friendly on purpose. */
  mark(stage: string, detail?: Record<string, unknown>): StageMark {
    const at = this.now();
    this.trackGap(at);
    const mark: StageMark = { stage, at, elapsedMs: Math.round((at - this.startedAt) * 10) / 10 };
    if (detail !== undefined) mark.detail = detail;
    this.marks.push(mark);
    return mark;
  }

  /** Call on every streamed chunk. Returns the gap since the previous tick. */
  tick(): number {
    const at = this.now();
    const gap = at - this.lastTickAt;
    if (gap > this.maxTickGapMs) this.maxTickGapMs = gap;
    this.lastTickAt = at;
    return gap;
  }

  get elapsedMs(): number { return Math.round((this.now() - this.startedAt) * 10) / 10; }

  /** Longest silence over the whole run: every mark and tick updates it in
   * chronological order, so a mark-to-mark span is not mistaken for silence
   * when chunks arrived in between. */
  get maxGapMs(): number { return Math.round(this.maxTickGapMs * 10) / 10; }

  get entries(): readonly StageMark[] { return this.marks; }

  snapshot(): StageTimerSnapshot {
    return {
      startedAt: this.startedAt,
      elapsedMs: this.elapsedMs,
      maxGapMs: this.maxGapMs,
      marks: this.marks.slice(),
    };
  }

  toJSON(): StageTimerSnapshot { return this.snapshot(); }

  private trackGap(at: number): void {
    const gap = at - this.lastTickAt;
    if (gap > this.maxTickGapMs) this.maxTickGapMs = gap;
    this.lastTickAt = at;
  }
}
