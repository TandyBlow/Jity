import { describe, expect, test } from 'vitest';
import { StageTimer } from './stage-timer';

function clock(start = 1000) {
  let value = start;
  return { now: () => value, advance(ms: number) { value += ms; } };
}

describe('StageTimer', () => {
  test('marks carry elapsed time and JSON-safe detail', () => {
    const time = clock();
    const timer = new StageTimer(time.now);
    time.advance(120);
    const mark = timer.mark('model-ready', { loadMs: 120 });
    expect(mark).toMatchObject({ stage: 'model-ready', elapsedMs: 120, detail: { loadMs: 120 } });
    time.advance(30);
    timer.mark('action-submitted');
    expect(timer.elapsedMs).toBe(150);
    expect(timer.entries.map((entry) => entry.stage)).toEqual(['model-ready', 'action-submitted']);
    expect(timer.snapshot().marks).toHaveLength(2);
  });

  test('the longest gap includes leading wait, mark gaps and streamed-chunk stalls', () => {
    const time = clock();
    const timer = new StageTimer(time.now);
    time.advance(90); // leading wait before the first mark
    timer.mark('first-readable');
    time.advance(10);
    timer.tick();
    time.advance(200); // a stalled decode
    timer.tick();
    time.advance(5);
    timer.mark('complete');
    expect(timer.maxGapMs).toBe(200);
    expect(timer.elapsedMs).toBe(305);
  });

  test('tick returns the gap since the previous mark or tick', () => {
    const time = clock();
    const timer = new StageTimer(time.now);
    time.advance(40);
    expect(timer.tick()).toBe(40);
    time.advance(7);
    expect(timer.tick()).toBe(7);
    expect(timer.maxGapMs).toBe(40);
  });
});
