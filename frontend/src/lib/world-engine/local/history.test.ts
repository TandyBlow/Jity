import { describe, expect, it } from 'vitest';
import { restoredEntries } from './history';
import type { LocalGameSnapshot } from './session';

function snapshot(): LocalGameSnapshot {
  return {
    commands: ['我打开盒盖。', '我退回走廊。'],
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
    expect(entries[0].text).toBe('');
    expect(entries[0].note).toContain('没有保存成功');
    // Automatic points are not player turns and never become entries.
    expect(entries.length).toBe(2);
    expect(entries.every((entry) => entry.restored)).toBe(true);
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

  it('returns an empty history for an empty save instead of inventing turns', () => {
    expect(restoredEntries({ commands: [], transport: {} } as unknown as LocalGameSnapshot)).toEqual([]);
  });
});
