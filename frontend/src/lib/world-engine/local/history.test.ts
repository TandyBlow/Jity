import { describe, expect, it } from 'vitest';
import { restoredEntries } from './history';
import type { LocalGameSnapshot } from './session';

function snapshot(): LocalGameSnapshot {
  return {
    commands: ['我打开盒盖。', '我退回走廊。'],
    narrationSources: { p2: { source: 'draft' } },
    transport: {
      // The opening/root point lives in pointStates, not in `points`; only real
      // player and automatic points appear here.
      points: {
        p1: { id: 'p1', sequence: 1, trigger: 'player' },
        p2: { id: 'p2', sequence: 2, trigger: 'player' },
        auto: { id: 'auto', sequence: 3, trigger: 'automatic' },
      },
      narrations: {
        p1: { status: 'pending', text: null },
        p2: { status: 'ready', text: '走廊尽头有光。' },
      },
    },
  } as unknown as LocalGameSnapshot;
}

describe('restoredEntries', () => {
  it('pairs stored commands with ready narration and marks unfinished points', () => {
    const entries = restoredEntries(snapshot());
    expect(entries.map((entry) => entry.input)).toEqual(['我打开盒盖。', '我退回走廊。']);
    expect(entries[1].text).toBe('走廊尽头有光。');
    expect(entries[1].source).toBe('draft');
    expect(entries[1].note).toContain('草稿');
    expect(entries[0].text).toBe('');
    expect(entries[0].note).toContain('没有保存成功');
    // Automatic points are not player turns and never become entries.
    expect(entries.length).toBe(2);
    expect(entries.every((entry) => entry.restored)).toBe(true);
  });

  it('joins the automatic points of one turn after the player point', () => {
    const withAuto = {
      commands: ['我走进服务巷。'],
      narrationSources: { p1: { source: 'model' }, auto: { source: 'draft' } },
      transport: {
        points: {
          p1: { id: 'p1', sequence: 1, trigger: 'player' },
          auto: { id: 'auto', sequence: 2, trigger: 'automatic' },
        },
        narrations: {
          p1: { status: 'ready', text: '巷口的绳已经放下。' },
          auto: { status: 'ready', text: '诺诺没有动，只把手套收紧。' },
        },
      },
    } as unknown as LocalGameSnapshot;
    const entries = restoredEntries(withAuto);
    // One player turn, but both committed paragraphs stay: the automatic round
    // must not replace the player point's prose.
    expect(entries.length).toBe(1);
    expect(entries[0].text).toBe('巷口的绳已经放下。\n\n诺诺没有动，只把手套收紧。');
    expect(entries[0].points?.map((part) => part.pointId)).toEqual(['p1', 'auto']);
    // The player point's accepted text keeps its own source; the later draft
    // is labelled per point and in the note, not by relabelling the entry.
    expect(entries[0].source).toBe('model');
    expect(entries[0].points?.map((part) => part.source)).toEqual(['model', 'draft']);
    expect(entries[0].note).toContain('草稿');
  });

  it('keeps a submitted-but-uncommitted turn as an explicit unfinished entry', () => {
    const base = snapshot();
    const withPending = {
      commands: [...base.commands, '我沿着服务巷往里走。'],
      transport: { ...(base.transport as object), advance: { inputText: '我沿着服务巷往里走。', intentStatus: 'consumed' } },
    } as unknown as LocalGameSnapshot;
    const entries = restoredEntries(withPending);
    expect(entries.length).toBe(3);
    expect(entries[2].unfinished).toBe(true);
    expect(entries[2].text).toBe('');
    expect(entries[2].note).toContain('没有完成');
  });

  it('keeps a failed command in its own slot instead of borrowing the next prose', () => {
    const withMap = {
      commands: ['我先看规则牌。', '我没走成。', '我退到巷口。'],
      commandPointIds: ['p1', null, 'p3'],
      narrationSources: { p1: { source: 'model' }, p3: { source: 'model' } },
      transport: {
        points: {
          p1: { id: 'p1', sequence: 1, trigger: 'player' },
          p3: { id: 'p3', sequence: 3, trigger: 'player' },
        },
        narrations: {
          p1: { status: 'ready', text: '绳已经放下。' },
          p3: { status: 'ready', text: '他退回巷口。' },
        },
      },
    } as unknown as LocalGameSnapshot;
    const entries = restoredEntries(withMap);
    expect(entries.map((entry) => entry.input)).toEqual(['我先看规则牌。', '我没走成。', '我退到巷口。']);
    expect(entries[1].text).toBe('');
    expect(entries[1].unfinished).toBe(true);
    expect(entries[2].text).toBe('他退回巷口。');
  });

  it('returns an empty history for an empty save instead of inventing turns', () => {
    expect(restoredEntries({ commands: [], transport: {} } as unknown as LocalGameSnapshot)).toEqual([]);
  });
});
