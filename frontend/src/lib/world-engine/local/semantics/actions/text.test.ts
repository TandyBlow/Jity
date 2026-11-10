/** Unit tests for the text guards. These are pure functions: the cases pin
 * the exact behaviour the handlers rely on (verbatim span, in-order coverage,
 * quote splitting, first person, speech attribution). */
import { describe, expect, it } from 'vitest';
import {
  firstPersonOutsideQuotes, hasAnaphora, longQuotes, longestSharedSpan, sharedSubsequence, skeleton, splitQuotes, speaksAs, startsWithName,
} from './text';

describe('verbatim and paraphrase detection', () => {
  it('finds the longest contiguous shared span on skeletons', () => {
    const span = longestSharedSpan('我把护目镜推上去，先看巷口的动静。', '把护目镜推上去，看巷口的动静。');
    expect(span.length).toBe(7);
    expect(span.text).toBe('把护目镜推上去');
  });

  it('exposes an in-order paraphrase that a contiguous span misses', () => {
    const player = '我把护目镜推上去，先看巷口的动静。';
    const npc = '把护目镜推上去，看巷口的动静。';
    expect(longestSharedSpan(npc, player).length).toBe(7);
    expect(sharedSubsequence(npc, player).coverage).toBe(1);
  });

  it('does not flag a standalone NPC action as a paraphrase', () => {
    const player = '我把护目镜推上去，先看巷口的动静。';
    const npc = '阿宁把对讲机从腰间取下来，换了一块电池。';
    expect(sharedSubsequence(npc, player).coverage).toBeLessThan(0.4);
  });

  it('normalizes whitespace and punctuation away from the comparison', () => {
    expect(skeleton('把 护目镜，推上去！')).toBe('把护目镜推上去');
  });
});

describe('quotes, person and attribution', () => {
  it('splits quoted speech out of the narration', () => {
    const { plain, quotes } = splitQuotes('诺诺回答：“我叫诺诺。”然后看向门口。');
    expect(plain).not.toContain('我叫诺诺');
    expect(quotes).toEqual(['我叫诺诺。']);
  });

  it('allows first person inside quotes but not in narration', () => {
    expect(firstPersonOutsideQuotes('诺诺说：“我来。”')).toBe(false);
    expect(firstPersonOutsideQuotes('我退回门边。')).toBe(true);
  });

  it('detects speech attributed to a named subject', () => {
    expect(speaksAs('路明非说：“别动。”', '路明非')).toBe(true);
    expect(speaksAs('诺诺看了一眼路明非，没说话。', '路明非')).toBe(false);
    expect(startsWithName('路明非被诺诺拉住。', '路明非')).toBe(true);
  });

  it('reports anaphora and long quotes', () => {
    expect(hasAnaphora('我把地图递给他。')).toBe(true);
    expect(hasAnaphora('我把地图递给诺诺。')).toBe(false);
    expect(longQuotes('她说：“这条路我认得。”')).toEqual(['这条路我认得。']);
    expect(longQuotes('他说：“走。”')).toEqual([]);
  });
});
